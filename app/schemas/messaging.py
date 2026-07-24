"""Direct Messaging wire schemas.

Hand-written rather than derived via ``build_schemas`` because the messaging
contract is shaped by the frontend, not by the ORM: keyset pagination, idempotent
`client_id` sends, a denormalized `peer`, and nested reaction/attachment sets.

**Every id crosses the wire as a string.** The frontend's `ChatUser.id`,
`DirectMessage.sender_id`, `Reaction.user_ids` and `Conversation.participant_ids`
are all `string` (see `src/features/messaging/messagingModel.ts`), even though
users are `bigint` in Postgres. Serializing an int here would break `===`
comparisons against `useAuth().user.id` throughout the UI, so the service layer
stringifies on the way out and the request schemas coerce on the way in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator


def iso_utc(value: datetime | None) -> str | None:
    """Serialize a timestamp as ISO-8601 with an explicit ``Z``.

    The messaging tables store naive UTC (matching the rest of this schema).
    Pydantic would emit that bare — ``2026-07-20T04:58:37.532381`` — and
    ``new Date()`` in the browser parses a bare timestamp as **local** time, which
    would silently shift every message by the viewer's UTC offset. The contract's
    examples are all ``Z``-suffixed, so pin the marker on explicitly here.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


# Use for every timestamp that crosses the wire in this module.
UtcDateTime = Annotated[
    datetime, PlainSerializer(iso_utc, return_type=str, when_used="json")
]

DeliveryStatus = Literal["sending", "sent", "delivered", "read", "failed"]
PresenceStatus = Literal["online", "away", "offline"]

MAX_BODY_CHARS = 8000
MAX_CLIENT_ID_CHARS = 64
MAX_EMOJI_BYTES = 16


class ChatUser(BaseModel):
    """A person you can message — mirrors the frontend `ChatUser`."""

    id: str
    name: str
    username: str
    email: str
    role: str
    avatar_url: str | None = None
    initials: str


class Attachment(BaseModel):
    id: str
    name: str
    mime_type: str
    size: int
    kind: Literal["image", "file"]
    url: str | None = None
    width: int | None = None
    height: int | None = None


class Reaction(BaseModel):
    emoji: str
    user_ids: list[str]


class ReplyRef(BaseModel):
    message_id: str
    sender_id: str
    sender_name: str
    preview: str


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: str
    conversation_id: str
    sender_id: str
    body: str
    created_at: UtcDateTime
    edited_at: UtcDateTime | None = None
    status: DeliveryStatus = "sent"
    attachments: list[Attachment] = Field(default_factory=list)
    reactions: list[Reaction] = Field(default_factory=list)
    reply_to: ReplyRef | None = None
    forwarded_from: str | None = None
    deleted_for_everyone: bool = False
    client_id: str | None = None


class ConversationRead(BaseModel):
    id: str
    type: str = "direct"
    participant_ids: list[str]
    peer: ChatUser
    last_message: MessageRead | None = None
    unread_count: int = 0
    pinned: bool = False
    muted: bool = False
    archived: bool = False
    blocked: bool = False
    created_at: UtcDateTime
    updated_at: UtcDateTime


class PageMeta(BaseModel):
    page: int
    size: int
    total: int
    pages: int


class ConversationPage(BaseModel):
    """Matches the existing DentC `PaginatedResponse*` envelope."""

    items: list[ConversationRead]
    meta: PageMeta


class MessagePage(BaseModel):
    """Keyset page. `items` ascend (oldest first); `cursor` is the oldest id returned."""

    items: list[MessageRead]
    has_more: bool
    cursor: str | None = None


# ── Requests ────────────────────────────────────────────────────────────────
class ConversationCreate(BaseModel):
    # The client sends `peer.id`, which is a *string* in its view model, so accept
    # either form and normalize to int.
    participant_id: int

    @field_validator("participant_id", mode="before")
    @classmethod
    def _coerce(cls, v: object) -> object:
        if isinstance(v, str) and v.strip().isdigit():
            return int(v)
        return v


class ConversationUpdate(BaseModel):
    """PATCH body — every field optional; only the caller's participant row moves."""

    pinned: bool | None = None
    muted: bool | None = None
    archived: bool | None = None
    blocked: bool | None = None


class ConversationReadRequest(BaseModel):
    up_to_message_id: str | None = None


class ConversationReadResult(BaseModel):
    conversation_id: str
    unread_count: int
    last_read_message_id: str | None = None


def clean_body(v: str) -> str:
    """Strip NULs and C0 control characters (keeping \\n and \\t) and enforce the
    length cap (§28). Markdown is stored raw; the client renders it sanitized."""
    v = "".join(ch for ch in (v or "") if ch in "\n\t" or ord(ch) >= 0x20)
    if len(v) > MAX_BODY_CHARS:
        raise ValueError(f"Message exceeds {MAX_BODY_CHARS} characters.")
    return v


class MessageCreate(BaseModel):
    body: str = ""
    client_id: str | None = Field(default=None, max_length=MAX_CLIENT_ID_CHARS)
    reply_to_id: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    forwarded_from: str | None = None

    _clean = field_validator("body")(clean_body)

    @field_validator("attachment_ids", mode="before")
    @classmethod
    def _accept_attachment_objects(cls, v: object) -> object:
        """`realTransport.sendMessage` posts `attachments: Attachment[]`, while the
        contract specifies `attachment_ids: string[]`. Accept both so the cutover
        doesn't hinge on which one ships first."""
        if isinstance(v, list):
            return [x.get("id") if isinstance(x, dict) else x for x in v]
        return v


class MessageUpdate(BaseModel):
    body: str

    _clean = field_validator("body")(clean_body)


class ReactionRequest(BaseModel):
    emoji: str = Field(min_length=1)

    @field_validator("emoji")
    @classmethod
    def _check(cls, v: str) -> str:
        if len(v.encode("utf-8")) > MAX_EMOJI_BYTES:
            raise ValueError("Emoji is too long.")
        return v


class ReactionSet(BaseModel):
    reactions: list[Reaction]


class ForwardRequest(BaseModel):
    participant_ids: list[int]

    @field_validator("participant_ids", mode="before")
    @classmethod
    def _coerce(cls, v: object) -> object:
        if isinstance(v, list):
            return [int(x) if isinstance(x, str) and x.strip().isdigit() else x for x in v]
        return v


class PresenceInfo(BaseModel):
    status: PresenceStatus
    last_seen: UtcDateTime | None = None
