"""Direct Messaging REST endpoints (MSG-2 / MSG-4 / MSG-5).

Thin routing layer — all logic lives in ``app.services.messaging_service``. Paths
match ``docs/api-contracts/MESSAGING_API_CONTRACT.md`` §2 exactly; the frontend's
``RealMessagingTransport`` maps 1:1 onto them, so renaming anything here breaks the
cutover.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.messaging import (
    ConversationCreate,
    ConversationPage,
    ConversationRead,
    ConversationReadRequest,
    ConversationReadResult,
    ConversationUpdate,
    ForwardRequest,
    MessageCreate,
    MessagePage,
    MessageRead,
    MessageUpdate,
    PresenceInfo,
    ReactionRequest,
    ReactionSet,
)
from app.services import messaging_service, presence_service

router = APIRouter(
    prefix="/messaging",
    tags=["Messaging"],
    dependencies=[Depends(get_current_user)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

ConversationId = Annotated[str, Path(description="Conversation id (UUID)")]
MessageId = Annotated[str, Path(description="Message id (UUID)")]


# ── Conversations ────────────────────────────────────────────────────────────
@router.get(
    "/conversations",
    response_model=ConversationPage,
    operation_id="list_messaging_conversations",
    summary="List my conversations (pinned first, then most recent)",
)
def list_conversations(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 30,
    search: Annotated[str | None, Query(description="Match the peer's name/username/email")] = None,
    archived: Annotated[bool | None, Query(description="Filter by my archived flag")] = None,
):
    items, meta = messaging_service.list_conversations(
        db, tenant_id, current.id, page=page, size=size, search=search, archived=archived
    )
    return ConversationPage(items=items, meta=meta)


@router.post(
    "/conversations",
    response_model=ConversationRead,
    operation_id="create_messaging_conversation",
    summary="Get-or-create a 1:1 conversation (idempotent per user pair)",
)
def create_conversation(
    db: DbSession, tenant_id: TenantId, current: CurrentUser, body: ConversationCreate
):
    return messaging_service.get_or_create_conversation(
        db, tenant_id, current.id, body.participant_id
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationRead,
    operation_id="get_messaging_conversation",
    summary="Fetch one conversation with my participant state",
)
def get_conversation(
    db: DbSession, tenant_id: TenantId, current: CurrentUser, conversation_id: ConversationId
):
    return messaging_service.get_conversation(db, tenant_id, current.id, conversation_id)


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationRead,
    operation_id="update_messaging_conversation",
    summary="Update my pinned/muted/archived/blocked flags",
)
def update_conversation(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    conversation_id: ConversationId,
    body: ConversationUpdate,
):
    return messaging_service.update_conversation(
        db, tenant_id, current.id, conversation_id, body.model_dump(exclude_unset=True)
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_messaging_conversation",
    summary="Remove the conversation from my list (per-user soft delete)",
)
def delete_conversation(
    db: DbSession, tenant_id: TenantId, current: CurrentUser, conversation_id: ConversationId
):
    messaging_service.delete_conversation(db, tenant_id, current.id, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/conversations/{conversation_id}/read",
    response_model=ConversationReadResult,
    operation_id="mark_messaging_conversation_read",
    summary="Mark read up to a message (default: the latest)",
)
def mark_read(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    conversation_id: ConversationId,
    body: ConversationReadRequest | None = None,
):
    return messaging_service.mark_read(
        db,
        tenant_id,
        current.id,
        conversation_id,
        (body.up_to_message_id if body else None),
    )


# ── Messages ─────────────────────────────────────────────────────────────────
@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessagePage,
    operation_id="list_messaging_messages",
    summary="Message history, keyset-paginated (oldest first)",
)
def list_messages(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    conversation_id: ConversationId,
    before: Annotated[str | None, Query(description="Return messages older than this id")] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
):
    return messaging_service.list_messages(
        db, tenant_id, current.id, conversation_id, before=before, limit=limit
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="send_messaging_message",
    summary="Send a message (idempotent per client_id)",
)
def send_message(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    conversation_id: ConversationId,
    body: MessageCreate,
):
    return messaging_service.send_message(
        db,
        tenant_id,
        current.id,
        conversation_id,
        body=body.body,
        client_id=body.client_id,
        reply_to_id=body.reply_to_id,
        attachment_ids=body.attachment_ids,
        forwarded_from=body.forwarded_from,
    )


@router.patch(
    "/conversations/{conversation_id}/messages/{message_id}",
    response_model=MessageRead,
    operation_id="edit_messaging_message",
    summary="Edit my own message within the edit window",
)
def edit_message(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    conversation_id: ConversationId,
    message_id: MessageId,
    body: MessageUpdate,
):
    return messaging_service.edit_message(
        db, tenant_id, current.id, conversation_id, message_id, body.body
    )


@router.delete(
    "/conversations/{conversation_id}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_messaging_message",
    summary="Delete a message for me, or for everyone (sender only)",
)
def delete_message(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    conversation_id: ConversationId,
    message_id: MessageId,
    for_everyone: Annotated[bool, Query()] = False,
):
    messaging_service.delete_message(
        db, tenant_id, current.id, conversation_id, message_id, for_everyone
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/reactions",
    response_model=ReactionSet,
    operation_id="toggle_messaging_reaction",
    summary="Toggle an emoji reaction; returns the full reaction set",
)
def toggle_reaction(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    conversation_id: ConversationId,
    message_id: MessageId,
    body: ReactionRequest,
):
    reactions = messaging_service.toggle_reaction(
        db, tenant_id, current.id, conversation_id, message_id, body.emoji
    )
    return ReactionSet(reactions=reactions)


@router.post(
    "/messages/{message_id}/forward",
    response_model=list[MessageRead],
    operation_id="forward_messaging_message",
    summary="Forward a message to one or more users",
)
def forward_message(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    message_id: MessageId,
    body: ForwardRequest,
):
    return messaging_service.forward_message(
        db, tenant_id, current.id, message_id, body.participant_ids
    )


# ── Presence ─────────────────────────────────────────────────────────────────
@router.get(
    "/presence",
    response_model=dict[str, PresenceInfo],
    operation_id="get_messaging_presence",
    summary="Presence snapshot for a set of users",
)
def get_presence(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    user_ids: Annotated[str, Query(description="Comma-separated user ids, e.g. 12,34,56")],
):
    ids: list[int] = []
    for raw in (user_ids or "").split(","):
        raw = raw.strip()
        if raw.isdigit():
            ids.append(int(raw))
    return presence_service.get_presence(db, tenant_id, ids)
