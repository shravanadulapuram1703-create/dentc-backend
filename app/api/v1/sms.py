"""Patient SMS (Twilio) routes — SMS-1/2/4/5/6/7/8/9.

Two routers:

* ``router`` (auth) — ``/sms/send`` (the gateway the Messages tab probes:
  **POST-only**, so the FE's ``GET`` probe gets the 405 that means "live"),
  ``/sms/gateway`` (configured / log-only), ``/sms/render`` (merge fields),
  ``/sms/inbox/summary`` + ``/sms/inbox/mark-read`` (practice-wide inbox),
  ``/sms/sender`` (what number an office sends from), ``/sms/reminders/run``
  (the SMS-9 job, admin) and ``/sms/metadata``.
* ``webhook_router`` (**unauthenticated**) — ``/sms/webhooks/inbound`` and
  ``/sms/webhooks/status``. Twilio signs them (``X-Twilio-Signature``); the
  signature is validated against the Auth Token before anything is read. A
  request we cannot route is still acknowledged with 200 so Twilio does not
  retry it forever.

The generic ``/sms-messages`` and ``/sms-templates`` resources stay in the CRUD
registry (with ``SmsMessageCRUD`` + ``enrich_sms_messages`` attached).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user, require_roles
from app.core.exceptions import ForbiddenError
from app.integrations import twilio_client
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
from app.services import sms_service

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
    summary="Send a text to a patient via Twilio (SMS-1)",
    responses={400: {"model": ErrorResponse, "description": "patient_opted_out / consent_override_required"},
               409: {"model": ErrorResponse, "description": "duplicate_client_id (details.sms_message is the existing row)"},
               429: {"model": ErrorResponse, "description": "sms_rate_limited"},
               502: {"model": ErrorResponse, "description": "twilio_error (row persisted as failed)"}},
)
def send_sms(body: SmsSendRequest, db: DbSession, tenant_id: TenantId, current: CurrentUser):
    row = sms_service.send(db, tenant_id, current.id, body.model_dump())
    sms_service.enrich_sms_messages(db, [row], tenant_id)
    return row


@router.get("/gateway", response_model=SmsGatewayStatus, operation_id="get_sms_gateway_status",
            summary="Is Twilio configured (live) or is the gateway in log-only mode?")
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


# ── Twilio webhooks (UNAUTH, signed) ─────────────────────────────────────────
async def _twilio_form(request: Request) -> tuple[dict[str, str], bytes]:
    raw = await request.body()
    form = await request.form()
    return {k: str(v) for k, v in form.items()}, raw


def _verify(request: Request, params: dict[str, str]) -> None:
    qs = request.url.query
    path_qs = request.url.path + (f"?{qs}" if qs else "")
    ok = twilio_client.validate_signature(
        signature=request.headers.get("X-Twilio-Signature"),
        request_url=str(request.url), path_qs=path_qs, params=params,
    )
    if not ok:
        raise ForbiddenError("Invalid or missing X-Twilio-Signature", code="twilio_signature_invalid")


@webhook_router.post(
    "/inbound", operation_id="twilio_inbound_webhook", include_in_schema=False,
    summary="Twilio inbound-message webhook (SMS-2)",
)
async def twilio_inbound_webhook(request: Request, db: DbSession):
    params, raw = await _twilio_form(request)
    _verify(request, params)
    twiml = await run_in_threadpool(sms_service.handle_inbound, db, params, raw_body=raw)
    return Response(content=twiml, media_type="application/xml")


@webhook_router.post(
    "/status", operation_id="twilio_status_webhook", include_in_schema=False,
    summary="Twilio delivery-status callback (SMS-2)",
)
async def twilio_status_webhook(request: Request, db: DbSession):
    params, raw = await _twilio_form(request)
    _verify(request, params)
    await run_in_threadpool(sms_service.handle_status, db, params, raw_body=raw)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
