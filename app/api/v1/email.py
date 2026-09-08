"""Patient e-mail routes (EMAIL-1) — the SMS gateway's shape over SendGrid.

``router`` (auth): ``POST /email/send``, ``GET /email/gateway``, ``GET /email/metadata``.
``webhook_router`` (**unauthenticated**, signed): ``POST /email/webhooks/sendgrid``
— SendGrid's event webhook, verified with the ECDSA public key when configured.
The generic ``/email-messages`` log resource lives in the CRUD registry.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.core.config import settings
from app.core.exceptions import ForbiddenError, ValidationError
from app.integrations import sendgrid_client
from app.schemas.common import ErrorResponse
from app.schemas.sms import (
    EmailGatewayStatus,
    EmailMessageRead,
    EmailMetadata,
    EmailSendRequest,
    WebhookAck,
)
from app.services import email_service

router = APIRouter(
    prefix="/email",
    tags=["Communications"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
               422: {"model": ErrorResponse}},
)

webhook_router = APIRouter(prefix="/email/webhooks", tags=["Communications"])


@router.post(
    "/send", response_model=EmailMessageRead, status_code=status.HTTP_201_CREATED,
    operation_id="send_email", summary="Send an e-mail to a patient via SendGrid (EMAIL-1)",
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
               502: {"model": ErrorResponse, "description": "sendgrid_error (row persisted as failed)"}},
)
def send_email(body: EmailSendRequest, db: DbSession, tenant_id: TenantId, current: CurrentUser):
    return email_service.send(db, tenant_id, current.id, body.model_dump())


@router.get("/gateway", response_model=EmailGatewayStatus, operation_id="get_email_gateway_status",
            summary="Is SendGrid configured (live) or is the gateway in log-only mode?")
def get_email_gateway_status():
    return email_service.gateway_status()


@router.get("/metadata", response_model=EmailMetadata, operation_id="get_email_metadata")
def get_email_metadata():
    return email_service.metadata()


@webhook_router.post(
    "/sendgrid", operation_id="sendgrid_event_webhook", include_in_schema=False,
    response_model=WebhookAck, summary="SendGrid event webhook (EMAIL-1)",
)
async def sendgrid_event_webhook(request: Request, db: DbSession):
    raw = await request.body()
    ok = sendgrid_client.verify_event_signature(
        public_key=settings.SENDGRID_WEBHOOK_PUBLIC_KEY,
        signature=request.headers.get("X-Twilio-Email-Event-Webhook-Signature"),
        timestamp=request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp"),
        body=raw,
    )
    if not ok:
        raise ForbiddenError("Invalid or missing SendGrid webhook signature",
                             code="sendgrid_signature_invalid")
    try:
        events = json.loads(raw or b"[]")
    except ValueError as exc:
        raise ValidationError("Malformed event payload", code="sendgrid_bad_payload") from exc
    if isinstance(events, dict):
        events = [events]
    applied = await run_in_threadpool(email_service.handle_events, db, list(events), raw_body=raw)
    return WebhookAck(ok=True, applied=applied)
