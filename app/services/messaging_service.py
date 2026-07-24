"""Direct Messaging domain logic (MSG-2 / MSG-5).

REST is the source of truth; every durable write here ends by publishing the
resulting event to each recipient's channel (``messaging_events.publish``). The
WebSocket layer only carries those broadcasts — it never owns state — so a client
that misses an event recovers it from history on reconnect.

Two invariants worth stating up front, because most of the fiddly code serves them:

1. **No N+1.** Conversation lists and message pages batch-load their senders,
   receipts, reactions, attachments and reply targets in one query each. A thread
   render is a fixed number of queries regardless of page size.
2. **Ids serialize as strings.** See ``app.schemas.messaging`` — the frontend
   compares message/user ids with ``===`` against values sourced from the auth
   context, so an int would silently break identity checks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.core.logging import get_logger
from app.db.models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageAttachment,
    MessageReaction,
    MessageReceipt,
    MessageRecipientState,
    User,
)
from app.schemas.messaging import (
    Attachment,
    ChatUser,
    ConversationRead,
    ConversationReadResult,
    MessagePage,
    MessageRead,
    PageMeta,
    Reaction,
    ReplyRef,
    iso_utc,
)
from app.services import messaging_events

logger = get_logger(__name__)

_PREVIEW_CHARS = 120


def _utcnow() -> datetime:
    """Naive UTC — the models use ``DateTime`` without timezone, like the rest of
    this schema, so everything must be stored in the same frame."""
    return datetime.now(UTC).replace(tzinfo=None)


# ── User projection ──────────────────────────────────────────────────────────
def _display_name(user: User) -> str:
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full or user.username or user.email or f"User {user.id}"


def _initials(name: str) -> str:
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _chat_user(user: User) -> ChatUser:
    name = _display_name(user)
    return ChatUser(
        id=str(user.id),
        name=name,
        username=user.username,
        email=user.email,
        role=user.role,
        avatar_url=user.image_url,
        initials=_initials(name),
    )


def _load_users(db: Session, user_ids: set[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    rows = db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    return {u.id: u for u in rows}


# ── Access control ───────────────────────────────────────────────────────────
def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        # 404 rather than 400: a malformed id and an id in another tenant must be
        # indistinguishable, so ids can't be probed for existence (§28).
        raise NotFoundError(f"{label} not found") from None


def _get_participation(
    db: Session, tenant_id: int, conversation_id: uuid.UUID, user_id: int
) -> ConversationParticipant:
    row = db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.tenant_id == tenant_id,
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Conversation not found")
    return row


def _participants(
    db: Session, conversation_id: uuid.UUID
) -> list[ConversationParticipant]:
    return list(
        db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id
            )
        )
        .scalars()
        .all()
    )


def _recipients(participants: list[ConversationParticipant], sender_id: int) -> list[int]:
    return [p.user_id for p in participants if p.user_id != sender_id]


# ── Message serialization ────────────────────────────────────────────────────
def _status_for(receipts: list[MessageReceipt]) -> str:
    """Sender-view delivery status = the *minimum* state across recipients (§7).

    No receipt rows means nobody has it yet beyond the server, i.e. ``sent``.
    """
    if not receipts:
        return "sent"
    if all(r.read_at is not None for r in receipts):
        return "read"
    if all(r.delivered_at is not None for r in receipts):
        return "delivered"
    return "sent"


def _preview(body: str, deleted: bool) -> str:
    if deleted:
        return "This message was deleted"
    text = " ".join((body or "").split())
    return text[:_PREVIEW_CHARS]


def serialize_messages(
    db: Session, messages: list[Message], caller_id: int
) -> list[MessageRead]:
    """Batch-hydrate a set of messages into wire shape."""
    if not messages:
        return []

    ids = [m.id for m in messages]

    receipts_by_message: dict[uuid.UUID, list[MessageReceipt]] = {}
    for receipt in (
        db.execute(select(MessageReceipt).where(MessageReceipt.message_id.in_(ids)))
        .scalars()
        .all()
    ):
        receipts_by_message.setdefault(receipt.message_id, []).append(receipt)

    reactions_by_message: dict[uuid.UUID, dict[str, list[str]]] = {}
    for reaction in (
        db.execute(
            select(MessageReaction)
            .where(MessageReaction.message_id.in_(ids))
            .order_by(MessageReaction.id)
        )
        .scalars()
        .all()
    ):
        bucket = reactions_by_message.setdefault(reaction.message_id, {})
        bucket.setdefault(reaction.emoji, []).append(str(reaction.user_id))

    attachments_by_message: dict[uuid.UUID, list[MessageAttachment]] = {}
    for att in (
        db.execute(
            select(MessageAttachment).where(MessageAttachment.message_id.in_(ids))
        )
        .scalars()
        .all()
    ):
        if att.message_id is not None:
            attachments_by_message.setdefault(att.message_id, []).append(att)

    # Reply targets (one extra query, then their senders join the same user batch).
    reply_ids = {m.reply_to_id for m in messages if m.reply_to_id is not None}
    replies: dict[uuid.UUID, Message] = {}
    if reply_ids:
        replies = {
            r.id: r
            for r in db.execute(select(Message).where(Message.id.in_(reply_ids)))
            .scalars()
            .all()
        }

    user_ids = {m.sender_id for m in messages} | {r.sender_id for r in replies.values()}
    users = _load_users(db, user_ids)

    out: list[MessageRead] = []
    for m in messages:
        reply_ref = None
        target = replies.get(m.reply_to_id) if m.reply_to_id else None
        if target is not None:
            sender = users.get(target.sender_id)
            reply_ref = ReplyRef(
                message_id=str(target.id),
                sender_id=str(target.sender_id),
                sender_name=_display_name(sender) if sender else "Unknown",
                preview=_preview(target.body, target.deleted_for_everyone),
            )

        out.append(
            MessageRead(
                id=str(m.id),
                conversation_id=str(m.conversation_id),
                sender_id=str(m.sender_id),
                # A tombstoned message keeps its row (ordering, replies) but must
                # never leak its original text.
                body="" if m.deleted_for_everyone else m.body,
                created_at=m.created_at,
                edited_at=m.edited_at,
                status=_status_for(receipts_by_message.get(m.id, [])),
                attachments=[
                    Attachment(
                        id=str(a.id),
                        name=a.name,
                        mime_type=a.mime_type,
                        size=a.size_bytes,
                        kind=a.kind,
                        url=None,  # signed URLs land with MSG-6
                        width=a.width,
                        height=a.height,
                    )
                    for a in attachments_by_message.get(m.id, [])
                ],
                reactions=[
                    Reaction(emoji=emoji, user_ids=user_ids_)
                    for emoji, user_ids_ in reactions_by_message.get(m.id, {}).items()
                ],
                reply_to=reply_ref,
                forwarded_from=m.forwarded_from,
                deleted_for_everyone=m.deleted_for_everyone,
                client_id=m.client_id,
            )
        )
    return out


def serialize_message(db: Session, message: Message, caller_id: int) -> MessageRead:
    return serialize_messages(db, [message], caller_id)[0]


# ── Conversation serialization ───────────────────────────────────────────────
def serialize_conversations(
    db: Session, conversations: list[Conversation], caller_id: int
) -> list[ConversationRead]:
    if not conversations:
        return []

    conv_ids = [c.id for c in conversations]
    parts_by_conv: dict[uuid.UUID, list[ConversationParticipant]] = {}
    for p in (
        db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id.in_(conv_ids)
            )
        )
        .scalars()
        .all()
    ):
        parts_by_conv.setdefault(p.conversation_id, []).append(p)

    peer_ids = {
        p.user_id
        for parts in parts_by_conv.values()
        for p in parts
        if p.user_id != caller_id
    }
    users = _load_users(db, peer_ids)

    last_ids = [c.last_message_id for c in conversations if c.last_message_id]
    last_messages: dict[uuid.UUID, MessageRead] = {}
    if last_ids:
        rows = (
            db.execute(select(Message).where(Message.id.in_(last_ids))).scalars().all()
        )
        # serialize_messages preserves input order, so these stay aligned.
        for serialized, row in zip(
            serialize_messages(db, list(rows), caller_id), rows, strict=True
        ):
            last_messages[row.id] = serialized

    out: list[ConversationRead] = []
    for conv in conversations:
        parts = parts_by_conv.get(conv.id, [])
        mine = next((p for p in parts if p.user_id == caller_id), None)
        if mine is None:
            continue
        peer_part = next((p for p in parts if p.user_id != caller_id), None)
        peer_user = users.get(peer_part.user_id) if peer_part else None
        if peer_user is None:
            # A participant whose user row was hard-deleted. Render a placeholder
            # rather than dropping the thread — its history is still readable.
            peer = ChatUser(
                id=str(peer_part.user_id) if peer_part else "0",
                name="Unknown user",
                username="",
                email="",
                role="",
                avatar_url=None,
                initials="?",
            )
        else:
            peer = _chat_user(peer_user)

        out.append(
            ConversationRead(
                id=str(conv.id),
                type=conv.type,
                participant_ids=[str(p.user_id) for p in parts],
                peer=peer,
                last_message=last_messages.get(conv.last_message_id)
                if conv.last_message_id
                else None,
                unread_count=mine.unread_count or 0,
                pinned=bool(mine.is_pinned),
                muted=bool(mine.is_muted),
                archived=bool(mine.is_archived),
                blocked=bool(mine.is_blocked),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
        )
    return out


def _serialize_one(db: Session, conv: Conversation, caller_id: int) -> ConversationRead:
    items = serialize_conversations(db, [conv], caller_id)
    if not items:
        raise NotFoundError("Conversation not found")
    return items[0]


def _broadcast_conversation(db: Session, conv: Conversation, user_ids: list[int]) -> None:
    """Push `conversation.updated` — serialized per recipient, since unread_count
    and the pin/mute flags differ for each side."""
    for uid in user_ids:
        try:
            view = _serialize_one(db, conv, uid)
        except NotFoundError:
            continue
        messaging_events.publish(
            conv.tenant_id,
            uid,
            {"type": "conversation.updated", "conversation": view.model_dump(mode="json")},
        )


# ── Conversations ────────────────────────────────────────────────────────────
def dedupe_key_for(a: int, b: int) -> str:
    lo, hi = sorted((a, b))
    return f"dm:{lo}:{hi}"


def get_or_create_conversation(
    db: Session, tenant_id: int, caller_id: int, participant_id: int
) -> ConversationRead:
    if participant_id == caller_id:
        raise ValidationError("Cannot start a conversation with yourself.")

    peer = db.execute(
        select(User).where(User.id == participant_id, User.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if peer is None or not peer.is_active:
        # Cross-tenant targets look identical to non-existent ones (§19).
        raise NotFoundError("User not found")

    key = dedupe_key_for(caller_id, participant_id)
    existing = db.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id, Conversation.dedupe_key == key
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Re-opening a thread the caller previously removed from their list.
        mine = _get_participation(db, tenant_id, existing.id, caller_id)
        if mine.left_at is not None:
            mine.left_at = None
            db.commit()
        return _serialize_one(db, existing, caller_id)

    now = _utcnow()
    conv = Conversation(
        id=uuid7(),
        tenant_id=tenant_id,
        type="direct",
        dedupe_key=key,
        created_by=caller_id,
        created_at=now,
        updated_at=now,
    )
    db.add(conv)
    db.add_all(
        [
            ConversationParticipant(
                tenant_id=tenant_id,
                conversation_id=conv.id,
                user_id=uid,
                joined_at=now,
                unread_count=0,
            )
            for uid in (caller_id, participant_id)
        ]
    )
    try:
        db.commit()
    except IntegrityError:
        # Both participants tapped "message" simultaneously; the unique index on
        # (tenant_id, dedupe_key) is what makes get-or-create actually idempotent.
        db.rollback()
        existing = db.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id, Conversation.dedupe_key == key
            )
        ).scalar_one_or_none()
        if existing is None:
            raise ConflictError("Could not create the conversation.") from None
        return _serialize_one(db, existing, caller_id)

    return _serialize_one(db, conv, caller_id)


def list_conversations(
    db: Session,
    tenant_id: int,
    caller_id: int,
    *,
    page: int = 1,
    size: int = 30,
    search: str | None = None,
    archived: bool | None = None,
) -> tuple[list[ConversationRead], PageMeta]:
    stmt = (
        select(Conversation)
        .join(
            ConversationParticipant,
            ConversationParticipant.conversation_id == Conversation.id,
        )
        .where(
            Conversation.tenant_id == tenant_id,
            ConversationParticipant.user_id == caller_id,
            ConversationParticipant.left_at.is_(None),
        )
    )
    if archived is not None:
        stmt = stmt.where(ConversationParticipant.is_archived.is_(archived))

    if search:
        # Search the peer's name/username/email, matching what the left rail shows.
        peer = ConversationParticipant.__table__.alias("peer_part")
        term = f"%{search.lower()}%"
        peer_users = (
            select(peer.c.conversation_id)
            .join(User, User.id == peer.c.user_id)
            .where(
                peer.c.user_id != caller_id,
                or_(
                    func.lower(func.coalesce(User.first_name, "")).like(term),
                    func.lower(func.coalesce(User.last_name, "")).like(term),
                    func.lower(User.username).like(term),
                    func.lower(User.email).like(term),
                ),
            )
        )
        stmt = stmt.where(Conversation.id.in_(peer_users))

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()

    rows = (
        db.execute(
            stmt.order_by(
                ConversationParticipant.is_pinned.desc(),
                Conversation.last_message_at.desc().nulls_last(),
                Conversation.id.desc(),
            )
            .offset((page - 1) * size)
            .limit(size)
        )
        .scalars()
        .all()
    )

    pages = (total + size - 1) // size if size else 0
    meta = PageMeta(page=page, size=size, total=total, pages=pages)
    return serialize_conversations(db, list(rows), caller_id), meta


def get_conversation(
    db: Session, tenant_id: int, caller_id: int, conversation_id: str
) -> ConversationRead:
    cid = _parse_uuid(conversation_id, "Conversation")
    _get_participation(db, tenant_id, cid, caller_id)
    conv = db.get(Conversation, cid)
    if conv is None or conv.tenant_id != tenant_id:
        raise NotFoundError("Conversation not found")
    return _serialize_one(db, conv, caller_id)


def update_conversation(
    db: Session, tenant_id: int, caller_id: int, conversation_id: str, changes: dict
) -> ConversationRead:
    cid = _parse_uuid(conversation_id, "Conversation")
    mine = _get_participation(db, tenant_id, cid, caller_id)

    field_map = {
        "pinned": "is_pinned",
        "muted": "is_muted",
        "archived": "is_archived",
        "blocked": "is_blocked",
    }
    for key, column in field_map.items():
        value = changes.get(key)
        if value is not None:
            setattr(mine, column, bool(value))
    db.commit()

    conv = db.get(Conversation, cid)
    if conv is None:
        raise NotFoundError("Conversation not found")
    view = _serialize_one(db, conv, caller_id)
    # Only the caller's own view changed — these flags are per-participant.
    messaging_events.publish(
        tenant_id,
        caller_id,
        {"type": "conversation.updated", "conversation": view.model_dump(mode="json")},
    )
    return view


def delete_conversation(
    db: Session, tenant_id: int, caller_id: int, conversation_id: str
) -> None:
    """Per-user soft delete. Shared history survives for the other participant."""
    cid = _parse_uuid(conversation_id, "Conversation")
    mine = _get_participation(db, tenant_id, cid, caller_id)
    mine.left_at = _utcnow()
    mine.unread_count = 0
    db.commit()


# ── Read receipts (MSG-5) ────────────────────────────────────────────────────
def mark_read(
    db: Session,
    tenant_id: int,
    caller_id: int,
    conversation_id: str,
    up_to_message_id: str | None = None,
) -> ConversationReadResult:
    cid = _parse_uuid(conversation_id, "Conversation")
    mine = _get_participation(db, tenant_id, cid, caller_id)

    if up_to_message_id:
        cutoff_id = _parse_uuid(up_to_message_id, "Message")
        cutoff = db.get(Message, cutoff_id)
        if cutoff is None or cutoff.conversation_id != cid:
            raise NotFoundError("Message not found")
    else:
        cutoff = db.execute(
            select(Message)
            .where(Message.conversation_id == cid)
            .order_by(Message.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if cutoff is None:
            return ConversationReadResult(
                conversation_id=str(cid), unread_count=0, last_read_message_id=None
            )

    now = _utcnow()
    # One UPDATE for the whole backlog, and one event below — not one per message.
    unread = (
        db.execute(
            select(MessageReceipt)
            .join(Message, Message.id == MessageReceipt.message_id)
            .where(
                MessageReceipt.user_id == caller_id,
                MessageReceipt.tenant_id == tenant_id,
                Message.conversation_id == cid,
                Message.id <= cutoff.id,
                MessageReceipt.read_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    senders: set[int] = set()
    for receipt in unread:
        receipt.read_at = now
        if receipt.delivered_at is None:
            receipt.delivered_at = now

    if unread:
        message_ids = {r.message_id for r in unread}
        for msg in (
            db.execute(select(Message).where(Message.id.in_(message_ids))).scalars().all()
        ):
            senders.add(msg.sender_id)

    mine.last_read_message_id = cutoff.id
    mine.last_read_at = now
    mine.unread_count = 0
    db.commit()

    senders.discard(caller_id)
    for sender_id in senders:
        messaging_events.publish(
            tenant_id,
            sender_id,
            {
                "type": "receipt.read",
                "conversation_id": str(cid),
                "reader_id": str(caller_id),
                "up_to_message_id": str(cutoff.id),
                "read_at": iso_utc(now),
            },
        )

    # ...and tell the reader's *own* other sockets, so a second tab/device clears
    # its unread badge too. `receipt.read` goes to the senders, not back to the
    # reader, so without this the reader's other tabs stay stale until reload.
    conv = db.get(Conversation, cid)
    if conv is not None:
        _broadcast_conversation(db, conv, [caller_id])

    return ConversationReadResult(
        conversation_id=str(cid), unread_count=0, last_read_message_id=str(cutoff.id)
    )


def mark_delivered(db: Session, tenant_id: int, caller_id: int, message_id: str) -> None:
    """Handle a `receipt.delivered` WS frame; tell the sender if it's a transition."""
    try:
        mid = uuid.UUID(str(message_id))
    except (ValueError, TypeError):
        return
    receipt = db.execute(
        select(MessageReceipt).where(
            MessageReceipt.message_id == mid,
            MessageReceipt.user_id == caller_id,
            MessageReceipt.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if receipt is None or receipt.delivered_at is not None:
        return  # unknown, or already delivered — stay idempotent
    receipt.delivered_at = _utcnow()
    db.commit()

    msg = db.get(Message, mid)
    if msg is None or msg.sender_id == caller_id:
        return
    messaging_events.publish(
        tenant_id,
        msg.sender_id,
        {
            "type": "message.status",
            "conversation_id": str(msg.conversation_id),
            "message_id": str(mid),
            "status": _status_for(
                db.execute(select(MessageReceipt).where(MessageReceipt.message_id == mid))
                .scalars()
                .all()
            ),
        },
    )


def flush_undelivered(db: Session, tenant_id: int, user_id: int) -> None:
    """On WS connect, mark the user's backlog delivered and notify each sender.

    This is what moves a message from one tick to two after the recipient was
    offline when it was sent (§10 / §25 "reconnect backlog").
    """
    pending = (
        db.execute(
            select(MessageReceipt).where(
                MessageReceipt.tenant_id == tenant_id,
                MessageReceipt.user_id == user_id,
                MessageReceipt.delivered_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    if not pending:
        return

    now = _utcnow()
    for receipt in pending:
        receipt.delivered_at = now
    db.commit()

    message_ids = [r.message_id for r in pending]
    messages = (
        db.execute(select(Message).where(Message.id.in_(message_ids))).scalars().all()
    )
    receipts_by_message: dict[uuid.UUID, list[MessageReceipt]] = {}
    for receipt in (
        db.execute(select(MessageReceipt).where(MessageReceipt.message_id.in_(message_ids)))
        .scalars()
        .all()
    ):
        receipts_by_message.setdefault(receipt.message_id, []).append(receipt)

    for msg in messages:
        if msg.sender_id == user_id:
            continue
        messaging_events.publish(
            tenant_id,
            msg.sender_id,
            {
                "type": "message.status",
                "conversation_id": str(msg.conversation_id),
                "message_id": str(msg.id),
                "status": _status_for(receipts_by_message.get(msg.id, [])),
            },
        )


# ── Messages ─────────────────────────────────────────────────────────────────
def list_messages(
    db: Session,
    tenant_id: int,
    caller_id: int,
    conversation_id: str,
    *,
    before: str | None = None,
    limit: int | None = None,
) -> MessagePage:
    """Keyset page of history, oldest-first (§17).

    Keyset rather than offset because a live thread mutates between requests and
    offset paging would skip or duplicate rows. UUIDv7 ids are time-sortable, so
    ``id < :before`` is both the cursor test and the sort key.
    """
    cid = _parse_uuid(conversation_id, "Conversation")
    _get_participation(db, tenant_id, cid, caller_id)

    limit = limit or settings.MESSAGING_HISTORY_DEFAULT_LIMIT
    limit = max(1, min(limit, settings.MESSAGING_HISTORY_MAX_LIMIT))

    hidden = select(MessageRecipientState.message_id).where(
        MessageRecipientState.user_id == caller_id,
        MessageRecipientState.is_deleted.is_(True),
    )
    stmt = select(Message).where(
        Message.conversation_id == cid,
        Message.tenant_id == tenant_id,
        Message.id.not_in(hidden),
    )
    if before:
        stmt = stmt.where(Message.id < _parse_uuid(before, "Message"))

    # Over-fetch by one to learn whether an older page exists without a COUNT.
    rows = (
        db.execute(stmt.order_by(Message.id.desc()).limit(limit + 1)).scalars().all()
    )
    has_more = len(rows) > limit
    rows = list(rows[:limit])
    cursor = str(rows[-1].id) if rows else None
    rows.reverse()  # ascending for display

    return MessagePage(
        items=serialize_messages(db, rows, caller_id), has_more=has_more, cursor=cursor
    )


def _assert_not_blocked(participants: list[ConversationParticipant], sender_id: int) -> None:
    for p in participants:
        if p.user_id != sender_id and p.is_blocked:
            raise ForbiddenError(
                "You can no longer send messages in this conversation.", code="blocked"
            )


def send_message(
    db: Session,
    tenant_id: int,
    caller_id: int,
    conversation_id: str,
    *,
    body: str,
    client_id: str | None = None,
    reply_to_id: str | None = None,
    attachment_ids: list[str] | None = None,
    forwarded_from: str | None = None,
) -> MessageRead:
    cid = _parse_uuid(conversation_id, "Conversation")
    _get_participation(db, tenant_id, cid, caller_id)
    participants = _participants(db, cid)
    _assert_not_blocked(participants, caller_id)

    attachment_ids = attachment_ids or []
    if not body.strip() and not attachment_ids:
        raise ValidationError("A message must have a body or at least one attachment.")

    # Idempotent send: a retry with the same client_id returns the original row so
    # a flaky network can't double-post (§7).
    if client_id:
        existing = db.execute(
            select(Message).where(
                Message.conversation_id == cid, Message.client_id == client_id
            )
        ).scalar_one_or_none()
        if existing is not None:
            return serialize_message(db, existing, caller_id)

    reply_uuid = None
    if reply_to_id:
        reply_uuid = _parse_uuid(reply_to_id, "Message")
        target = db.get(Message, reply_uuid)
        if target is None or target.conversation_id != cid:
            raise ValidationError("Cannot reply to a message from another conversation.")

    now = _utcnow()
    message = Message(
        id=uuid7(),
        tenant_id=tenant_id,
        conversation_id=cid,
        sender_id=caller_id,
        body=body,
        reply_to_id=reply_uuid,
        forwarded_from=forwarded_from,
        client_id=client_id,
        created_at=now,
    )
    db.add(message)

    recipients = _recipients(participants, caller_id)
    db.add_all(
        [
            MessageReceipt(tenant_id=tenant_id, message_id=message.id, user_id=uid)
            for uid in recipients
        ]
    )

    if attachment_ids:
        _link_attachments(db, tenant_id, caller_id, message.id, attachment_ids)

    conv = db.get(Conversation, cid)
    if conv is not None:
        conv.last_message_id = message.id
        conv.last_message_at = now
        conv.updated_at = now

    for p in participants:
        if p.user_id != caller_id:
            p.unread_count = (p.unread_count or 0) + 1
            # A new message pulls the thread back into an archived list.
            p.is_archived = False
            p.left_at = None

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if client_id:
            existing = db.execute(
                select(Message).where(
                    Message.conversation_id == cid, Message.client_id == client_id
                )
            ).scalar_one_or_none()
            if existing is not None:
                return serialize_message(db, existing, caller_id)
        raise ConflictError("Could not send the message.") from None

    view = serialize_message(db, message, caller_id)
    payload = view.model_dump(mode="json")
    messaging_events.publish_many(
        tenant_id,
        [p.user_id for p in participants],
        {"type": "message.new", "conversation_id": str(cid), "message": payload},
    )
    if conv is not None:
        _broadcast_conversation(db, conv, [p.user_id for p in participants])
    return view


def _link_attachments(
    db: Session,
    tenant_id: int,
    caller_id: int,
    message_id: uuid.UUID,
    attachment_ids: list[str],
) -> None:
    """Attach previously-uploaded blobs. No-op until MSG-6 creates rows."""
    ids = [_parse_uuid(a, "Attachment") for a in attachment_ids]
    rows = (
        db.execute(
            select(MessageAttachment).where(
                MessageAttachment.id.in_(ids),
                MessageAttachment.tenant_id == tenant_id,
                MessageAttachment.uploader_id == caller_id,
                MessageAttachment.message_id.is_(None),
            )
        )
        .scalars()
        .all()
    )
    if len(rows) != len(ids):
        raise ValidationError("One or more attachments are unknown or already used.")
    for row in rows:
        row.message_id = message_id


def edit_message(
    db: Session,
    tenant_id: int,
    caller_id: int,
    conversation_id: str,
    message_id: str,
    body: str,
) -> MessageRead:
    cid = _parse_uuid(conversation_id, "Conversation")
    mid = _parse_uuid(message_id, "Message")
    _get_participation(db, tenant_id, cid, caller_id)

    message = db.get(Message, mid)
    if message is None or message.conversation_id != cid or message.tenant_id != tenant_id:
        raise NotFoundError("Message not found")
    if message.sender_id != caller_id:
        raise ForbiddenError("You can only edit your own messages.")
    if message.deleted_for_everyone:
        raise ValidationError("This message was deleted.")
    if not body.strip():
        raise ValidationError("An edited message cannot be empty.")

    window = timedelta(seconds=settings.MESSAGING_EDIT_WINDOW_SECONDS)
    if _utcnow() - message.created_at > window:
        raise ForbiddenError("The edit window for this message has passed.")

    now = _utcnow()
    message.body = body
    message.is_edited = True
    message.edited_at = now
    db.commit()

    view = serialize_message(db, message, caller_id)
    messaging_events.publish_many(
        tenant_id,
        [p.user_id for p in _participants(db, cid)],
        {
            "type": "message.updated",
            "conversation_id": str(cid),
            "message": view.model_dump(mode="json"),
        },
    )
    return view


def delete_message(
    db: Session,
    tenant_id: int,
    caller_id: int,
    conversation_id: str,
    message_id: str,
    for_everyone: bool = False,
) -> None:
    cid = _parse_uuid(conversation_id, "Conversation")
    mid = _parse_uuid(message_id, "Message")
    _get_participation(db, tenant_id, cid, caller_id)

    message = db.get(Message, mid)
    if message is None or message.conversation_id != cid or message.tenant_id != tenant_id:
        raise NotFoundError("Message not found")

    if not for_everyone:
        # Delete for me: a per-user tombstone, invisible to the other side.
        existing = db.execute(
            select(MessageRecipientState).where(
                MessageRecipientState.message_id == mid,
                MessageRecipientState.user_id == caller_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                MessageRecipientState(
                    tenant_id=tenant_id,
                    message_id=mid,
                    user_id=caller_id,
                    is_deleted=True,
                    deleted_at=_utcnow(),
                )
            )
        else:
            existing.is_deleted = True
            existing.deleted_at = _utcnow()
        db.commit()
        messaging_events.publish(
            tenant_id,
            caller_id,
            {
                "type": "message.deleted",
                "conversation_id": str(cid),
                "message_id": str(mid),
                "for_everyone": False,
            },
        )
        return

    if message.sender_id != caller_id:
        raise ForbiddenError("You can only delete your own messages for everyone.")
    window = timedelta(seconds=settings.MESSAGING_DELETE_WINDOW_SECONDS)
    if _utcnow() - message.created_at > window:
        raise ForbiddenError("The delete-for-everyone window for this message has passed.")

    # Tombstone rather than DELETE: replies point here, and the row is the audit
    # trail for a healthcare-adjacent thread (MSG-10).
    message.deleted_for_everyone = True
    message.deleted_at = _utcnow()
    message.body = ""
    db.commit()

    messaging_events.publish_many(
        tenant_id,
        [p.user_id for p in _participants(db, cid)],
        {
            "type": "message.deleted",
            "conversation_id": str(cid),
            "message_id": str(mid),
            "for_everyone": True,
        },
    )


def toggle_reaction(
    db: Session,
    tenant_id: int,
    caller_id: int,
    conversation_id: str,
    message_id: str,
    emoji: str,
) -> list[Reaction]:
    cid = _parse_uuid(conversation_id, "Conversation")
    mid = _parse_uuid(message_id, "Message")
    _get_participation(db, tenant_id, cid, caller_id)

    message = db.get(Message, mid)
    if message is None or message.conversation_id != cid or message.tenant_id != tenant_id:
        raise NotFoundError("Message not found")

    existing = db.execute(
        select(MessageReaction).where(
            MessageReaction.message_id == mid,
            MessageReaction.user_id == caller_id,
            MessageReaction.emoji == emoji,
        )
    ).scalar_one_or_none()
    if existing is not None:
        db.delete(existing)
    else:
        db.add(
            MessageReaction(
                tenant_id=tenant_id, message_id=mid, user_id=caller_id, emoji=emoji
            )
        )
    db.commit()

    reactions = serialize_message(db, message, caller_id).reactions
    messaging_events.publish_many(
        tenant_id,
        [p.user_id for p in _participants(db, cid)],
        {
            "type": "reaction.updated",
            "conversation_id": str(cid),
            "message_id": str(mid),
            "reactions": [r.model_dump(mode="json") for r in reactions],
        },
    )
    return reactions


def forward_message(
    db: Session, tenant_id: int, caller_id: int, message_id: str, participant_ids: list[int]
) -> list[MessageRead]:
    """Copy a message into a 1:1 conversation with each target user."""
    mid = _parse_uuid(message_id, "Message")
    source = db.get(Message, mid)
    if source is None or source.tenant_id != tenant_id:
        raise NotFoundError("Message not found")
    _get_participation(db, tenant_id, source.conversation_id, caller_id)
    if source.deleted_for_everyone:
        raise ValidationError("This message was deleted.")

    origin = db.get(User, source.sender_id)
    origin_name = _display_name(origin) if origin else "Unknown"

    out: list[MessageRead] = []
    for target_id in participant_ids:
        if target_id == caller_id:
            continue
        conv = get_or_create_conversation(db, tenant_id, caller_id, target_id)
        out.append(
            send_message(
                db,
                tenant_id,
                caller_id,
                conv.id,
                body=source.body,
                forwarded_from=origin_name,
            )
        )
    return out


# ── WebSocket warm-up ────────────────────────────────────────────────────────
def sync_snapshot(db: Session, tenant_id: int, caller_id: int) -> dict:
    """Compact `sync` payload sent right after `connection.ack` (§23).

    Saves the client N REST calls on every reconnect.
    """
    conversations, _ = list_conversations(
        db,
        tenant_id,
        caller_id,
        page=1,
        size=settings.MESSAGING_SYNC_CONVERSATION_LIMIT,
    )
    return {
        "type": "sync",
        "conversations": [c.model_dump(mode="json") for c in conversations],
        "unread": [
            {"conversation_id": c.id, "unread_count": c.unread_count}
            for c in conversations
            if c.unread_count
        ],
    }


def typing_targets(db: Session, tenant_id: int, caller_id: int, conversation_id: str) -> list[int]:
    """Recipients for an ephemeral typing frame — validates membership too."""
    cid = _parse_uuid(conversation_id, "Conversation")
    _get_participation(db, tenant_id, cid, caller_id)
    return _recipients(_participants(db, cid), caller_id)
