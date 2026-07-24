"""Direct Messaging domain models (MSG-1).

conversations · conversation_participants · messages · message_receipts
message_attachments · message_reactions · user_presence

Implements the schema in the frontend hand-off (``MESSAGING_BACKEND_REQUIREMENTS``
§2-§3). Phase 1 ships 1:1 direct messages only, but every table is modelled for N
participants so group chats are a purely additive change:

* per-user conversation state (pin/mute/archive/block/read cursor) lives on
  ``conversation_participants``, not on ``conversations`` — each side owns its view;
* delivery/read state lives in ``message_receipts`` (one row per recipient) rather
  than as two columns on ``messages``.

Ids for conversations/messages/attachments are UUIDv7 (see ``app.core.ids``) so
they are time-sortable, which is what makes keyset pagination over history work.
``sqlalchemy.Uuid`` renders as native ``uuid`` on Postgres and ``CHAR(32)`` on
SQLite, so the test suite runs unchanged.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.db.base import Base, CreatedAtMixin, IntPKMixin


class Conversation(Base):
    """A container for messages between a fixed set of participants."""

    __tablename__ = "conversations"
    __table_args__ = (
        # 1:1 dedupe: one direct conversation per user pair per tenant. NULLs are
        # distinct in both Postgres and SQLite, so future group rows (which leave
        # dedupe_key NULL) never collide with each other.
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_conversations_tenant_dedupe_key"),
        Index("ix_conversations_tenant_last_message_at", "tenant_id", "last_message_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    type: Mapped[str] = mapped_column(String(20), default="direct")
    title: Mapped[str | None] = mapped_column(String(255))  # null for 1:1 (derived from peer)
    # Deterministic key for 1:1 dedupe: "dm:{least(a,b)}:{greatest(a,b)}".
    dedupe_key: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    # Denormalized so the conversation list is one indexed query (no N+1 on messages).
    last_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class ConversationParticipant(Base, IntPKMixin):
    """Membership + the caller's own view state for a conversation."""

    __tablename__ = "conversation_participants"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "user_id", name="uq_conversation_participants_conversation_user"
        ),
        Index("ix_conversation_participants_tenant_user", "tenant_id", "user_id"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)  # this user blocked the other
    last_read_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime)
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # Set by DELETE /conversations/{id} — a per-user soft delete. Shared history is
    # never hard-deleted, so the other participant keeps their copy.
    left_at: Mapped[datetime | None] = mapped_column(DateTime)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Idempotent sends: a retry with the same client_id hits this constraint
        # and the service returns the original row instead of duplicating.
        UniqueConstraint("conversation_id", "client_id", name="uq_messages_conversation_client_id"),
        Index("ix_messages_conversation_id_desc", "conversation_id", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text, default="")  # markdown; '' when attachments-only
    # ON DELETE SET NULL so deleting a quoted message doesn't cascade to the reply.
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL")
    )
    # Display name of the original sender when this message was forwarded.
    forwarded_from: Mapped[str | None] = mapped_column(String(255))
    client_id: Mapped[str | None] = mapped_column(String(64))
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_for_everyone: Mapped[bool] = mapped_column(Boolean, default=False)  # tombstone
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class MessageRecipientState(Base, IntPKMixin):
    """Per-user 'delete for me' tombstone — hides a message from one participant only."""

    __tablename__ = "message_recipient_states"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_recipient_states_message_user"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class MessageReceipt(Base, IntPKMixin):
    """Per-recipient delivery/read state. One row per recipient (never the sender)."""

    __tablename__ = "message_receipts"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_receipts_message_user"),
        Index("ix_message_receipts_user_delivered", "user_id", "delivered_at"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)


class MessageAttachment(Base, CreatedAtMixin):
    """Attachment metadata; bytes live in object storage (MSG-6).

    The table lands with the rest of the schema so ``Message.attachments``
    serializes today, but the two-phase upload endpoints are out of scope for this
    pass — no rows are written yet.
    """

    __tablename__ = "message_attachments"
    __table_args__ = (Index("ix_message_attachments_message", "message_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    # Nullable: a client uploads *before* the message row is committed, then the
    # attachment is linked on send.
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE")
    )
    uploader_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))  # 'image' | 'file'
    name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(150))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(500))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|ready|blocked


class MessageReaction(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "message_reactions"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "user_id", "emoji", name="uq_message_reactions_message_user_emoji"
        ),
        Index("ix_message_reactions_message", "message_id"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    emoji: Mapped[str] = mapped_column(String(32))


class UserPresence(Base):
    """Durable presence snapshot. Redis is the hot path; this is for last_seen."""

    __tablename__ = "user_presence"
    __table_args__ = (Index("ix_user_presence_tenant_status", "tenant_id", "status"),)

    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="offline")  # online|away|offline
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
