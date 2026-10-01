"""Patient SMS (RingCentral) routes — SMS-1/2/4/5/6/7/8/9.

Two routers:

* ``router`` (auth) — ``/sms/send`` (the gateway the Messages tab probes:
  **POST-only**, so the FE's ``GET`` probe gets the 405 that means "live"),
  ``/sms/gateway`` (configured / log-only), ``/sms/render`` (merge fields),
  ``/sms/inbox/summary`` + ``/sms/inbox/mark-read`` (practice-wide inbox),
  ``/sms/sender`` (what number an office sends from), ``/sms/reminders/run``
  (the SMS-9 job, admin) and ``/sms/metadata``.
* ``webhook_router`` (**unauthenticated**) — ``/sms/webhooks/ringcentral/
  {secret}``, ONE route for both inbound messages and outbound status
  changes (RingCentral delivers both through the same Subscription feed —
  unlike Twilio's two separate webhook URLs, see sms_service.
  route_webhook_event). Guarded by a secret embedded in the URL path
  (RC_WEBHOOK_SECRET) rather than a per-request signature — RingCentral's
  docs don't describe an ongoing per-delivery signature the way Twilio's
  X-Twilio-Signature works; see ringcentral_client.py for the reasoning.
  Also handles RingCentral's subscription-validation handshake (a
  "Validation-Token" header that must be echoed back). A request we cannot
  route is still acknowledged with 200 so RingCentral does not retry it
  forever.

The generic ``/sms-messages`` and ``/sms-templates`` resources stay in the CRUD
registry (with ``SmsMessageCRUD`` + ``enrich_sms_messages`` attached).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user, require_roles
from app.core.exceptions import ForbiddenError
from app.integrations import ringcentral_client
from app.schemas.common import ErrorResponse
from app.schemas.sms import (
    SmsGatewayStatus,
    SmsInboxSummary,
    SmsMarkReadRequest,
    SmsMarkReadResult,
    SmsMessageRead,
    SmsMetadata,
    SmsReminderRunRequest,
    SmsReminderRunResult,
    SmsRenderRequest,
    SmsRenderResult,
    SmsSendRequest,
    SmsSenderResolution,
)
from app.services import office_scope_service, sms_service

router = APIRouter(
    prefix="/sms",
    tags=["Communications"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
               422: {"model": ErrorResponse}},
)

webhook_router = APIRouter(prefix="/sms/webhooks", tags=["Communications"])


@router.post(
    "/send", response_model=SmsMessageRead, status_code=status.HTTP_201_CREATED,
    operation_id="send_sms",
    summary="Send a text to a patient via RingCentral (SMS-1)",
    responses={400: {"model": ErrorResponse, "description": "patient_opted_out / consent_override_required"},
               409: {"model": ErrorResponse, "description": "duplicate_client_id (details.sms_message is the existing row)"},
               429: {"model": ErrorResponse, "description": "sms_rate_limited"},
               502: {"model": ErrorResponse, "description": "ringcentral_error (row persisted as failed)"}},
)
def send_sms(body: SmsSendRequest, db: DbSession, tenant_id: TenantId, current: CurrentUser,
             office=Depends(office_scope_service.get_office_context)):
    payload = body.model_dump()
    # OFF-SCOPE-14: a new outbound message defaults its office to the caller's
    # working office (X-Office-ID) when the body omits one; an explicit office in
    # the body wins and is validated against the caller's assignments. (An
    # existing thread keeps its own office — this only stamps a fresh send.)
    if payload.get("office_id") is not None:
        office_scope_service.validate_target_office(office, payload["office_id"])
    elif office.x_office_id is not None:
        payload["office_id"] = office.x_office_id
    row = sms_service.send(db, tenant_id, current.id, payload)
    sms_service.enrich_sms_messages(db, [row], tenant_id)
    return row


@router.get("/gateway", response_model=SmsGatewayStatus, operation_id="get_sms_gateway_status",
            summary="Is RingCentral configured (live) or is the gateway in log-only mode?")
def get_sms_gateway_status(db: DbSession, tenant_id: TenantId):
    return sms_service.gateway_status(db, tenant_id)


@router.get("/sender", response_model=SmsSenderResolution, operation_id="resolve_sms_sender",
            summary="Which From number / Messaging Service an office sends from (SMS-7)")
def resolve_sms_sender(db: DbSession, tenant_id: TenantId,
                       office_id: int | None = Query(None)):
    out = sms_service.resolve_sender(db, tenant_id, office_id)
    return SmsSenderResolution(office_id=office_id, **out)


@router.post("/render", response_model=SmsRenderResult, operation_id="render_sms",
             summary="Render {{merge_fields}} for one patient (SMS-5)")
def render_sms(body: SmsRenderRequest, db: DbSession, tenant_id: TenantId):
    return sms_service.render_for_patient(
        db, tenant_id, body=body.body, template_id=body.template_id, patient_id=body.patient_id,
        appointment_id=body.appointment_id, office_id=body.office_id,
    )


@router.get("/inbox/summary", response_model=SmsInboxSummary, operation_id="get_sms_inbox_summary",
            summary="Unread / needs-attention / unmatched / failed counts per office (SMS-6)")
def get_sms_inbox_summary(db: DbSession, tenant_id: TenantId, office_id: int | None = Query(None)):
    return sms_service.inbox_summary(db, tenant_id, office_id)


@router.post("/inbox/mark-read", response_model=SmsMarkReadResult, operation_id="mark_sms_replies_read",
             summary="Mark every unread reply read (per patient and/or office)")
def mark_sms_replies_read(body: SmsMarkReadRequest, db: DbSession, tenant_id: TenantId):
    n = sms_service.mark_all_read(db, tenant_id, patient_id=body.patient_id, office_id=body.office_id)
    return SmsMarkReadResult(updated=n)


@router.post("/reminders/run", response_model=SmsReminderRunResult, operation_id="run_sms_reminders",
             summary="Send every due automated appointment reminder for this tenant (SMS-9)",
             dependencies=[Depends(require_roles("admin"))])
def run_sms_reminders(db: DbSession, tenant_id: TenantId, body: SmsReminderRunRequest | None = None):
    return sms_service.run_reminders(db, tenant_id=tenant_id, dry_run=bool(body and body.dry_run))


@router.get("/metadata", response_model=SmsMetadata, operation_id="get_sms_metadata",
            summary="Message-type / status / intent vocabularies + merge fields")
def get_sms_metadata():
    return sms_service.metadata()


# ── RingCentral webhook (UNAUTH, secret-in-path) ─────────────────────────────
@webhook_router.post(
    "/ringcentral/{secret}", operation_id="ringcentral_webhook", include_in_schema=False,
    summary="RingCentral SMS-2 Subscription notification (inbound messages + outbound status)",
)
async def ringcentral_webhook(secret: str, request: Request, db: DbSession):
    # RingCentral's subscription-validation handshake: on create/renew (and,
    # per their docs, potentially again later) it sends a request carrying
    # this header and expects it echoed back, HTTP 200, within 3000ms — a
    # different mechanism from (and not a substitute for) the secret check
    # below, which is this route's actual per-delivery trust boundary.
    validation_token = request.headers.get("Validation-Token")
    if validation_token:
        return Response(status_code=status.HTTP_200_OK,
                        headers={"Validation-Token": validation_token})

    if not ringcentral_client.validate_webhook_secret(secret):
        raise ForbiddenError("Invalid webhook secret", code="ringcentral_webhook_secret_invalid")

    raw = await request.body()
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 — malformed body: ack, don't retry-loop it
        return Response(status_code=status.HTTP_200_OK)
    body = payload.get("body") if isinstance(payload, dict) else None
    if not isinstance(body, dict):
        return Response(status_code=status.HTTP_200_OK)
    await run_in_threadpool(sms_service.route_webhook_event, db, body, raw_body=raw)
    return Response(status_code=status.HTTP_200_OK)
