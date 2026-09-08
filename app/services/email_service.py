"""Patient e-mail log + send (EMAIL-1) — the SMS module's shape, via SendGrid.

Mirrors :mod:`sms_service`: the row is persisted **before** the provider call
(``send_status="queued"``), a provider rejection is stored as ``failed`` and
surfaced as a 502 ``sendgrid_error``, sends are idempotent per ``client_id``,
and the (signed) event webhook updates ``send_status`` by
``provider_message_id``. With no ``SENDGRID_API_KEY`` the gateway is in
log-only mode — the row is the audit trail and nothing is delivered.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import EmailMessage, Office, Patient
from app.integrations import sendgrid_client
from app.integrations.sendgrid_client import SendGridError

logger = get_logger(__name__)

MESSAGE_TYPES = ("manual", "appointment_reminder", "appointment_confirmation", "recall",
                 "balance", "statement", "other")
SEND_STATUSES = ("queued", "processed", "delivered", "deferred", "bounce", "dropped",
                 "open", "click", "spamreport", "unsubscribe", "failed")
_STATUS_RANK = {"queued": 0, "processed": 1, "deferred": 1, "delivered": 2, "open": 3,
                "click": 3, "bounce": 4, "dropped": 4, "spamreport": 4, "unsubscribe": 4,
                "failed": 4}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def row_dict(row: EmailMessage) -> dict[str, Any]:
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder({c.key: getattr(row, c.key) for c in sa_inspect(row).mapper.column_attrs})


def gateway_status() -> dict[str, Any]:
    configured = sendgrid_client.is_configured()
    return {
        "configured": configured,
        "mode": "live" if configured else "log_only",
        "provider": "sendgrid" if configured else None,
        "from_email": settings.SENDGRID_FROM_EMAIL if configured else None,
        "webhook_validation": bool(settings.SENDGRID_WEBHOOK_VALIDATE),
        "webhook_signing_ready": bool(settings.SENDGRID_WEBHOOK_PUBLIC_KEY),
    }


def send(db: Session, tenant_id: int, user_id: int | None, payload: dict[str, Any]) -> EmailMessage:
    patient = db.get(Patient, int(payload["patient_id"]))
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError(f"Patient '{payload['patient_id']}' was not found")
    to_email = (payload.get("to_email") or patient.email or "").strip()
    if not _EMAIL_RE.match(to_email):
        raise ValidationError("to_email must be a valid e-mail address", code="invalid_email")
    subject = (payload.get("subject") or "").strip()
    if not subject:
        raise ValidationError("subject is required", code="email_subject_required")
    body_html, body_text = payload.get("body_html"), payload.get("body_text")
    if not (body_html or body_text):
        raise ValidationError("body_html or body_text is required", code="email_body_required")
    message_type = (payload.get("message_type") or "manual").strip().lower()
    if message_type not in MESSAGE_TYPES:
        raise ValidationError(f"message_type must be one of {', '.join(MESSAGE_TYPES)}",
                              code="email_invalid_message_type")
    if patient.no_auto_email and message_type != "manual":
        raise AppError("Patient has opted out of automated e-mail", code="patient_opted_out",
                       status_code=400, details={"patient_id": patient.id})
    if patient.no_auto_email and not payload.get("override_consent"):
        raise AppError("Patient has opted out of e-mail; a manual e-mail needs override_consent=true",
                       code="consent_override_required", status_code=400)
    client_id = (payload.get("client_id") or "").strip() or None
    if client_id:
        existing = db.execute(select(EmailMessage).where(
            EmailMessage.tenant_id == tenant_id, EmailMessage.client_id == client_id)).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("An e-mail with this client_id was already sent",
                                code="duplicate_client_id", details={"email_message": row_dict(existing)})
    office_id = payload.get("office_id")
    office = None
    if office_id is not None:
        office = db.get(Office, int(office_id))
        if office is None or office.tenant_id != tenant_id:
            raise NotFoundError(f"Office '{office_id}' was not found")
    elif patient.home_office_id:
        office = db.get(Office, patient.home_office_id)

    row = EmailMessage(
        tenant_id=tenant_id,
        office_id=office.id if office else None,
        patient_id=patient.id,
        appointment_id=payload.get("appointment_id") or None,
        to_email=to_email,
        from_email=settings.SENDGRID_FROM_EMAIL if sendgrid_client.is_configured() else None,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        provider="sendgrid" if sendgrid_client.is_configured() else None,
        send_status="queued",
        sent_at=_now(),
        message_type=message_type,
        client_id=client_id,
        is_read=True,
        created_by=user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if not sendgrid_client.is_configured():
        return row
    try:
        result = sendgrid_client.send_mail(
            to_email=to_email, subject=subject, body_html=body_html, body_text=body_text,
            from_name=(office.name if office else None),
            custom_args={"email_message_id": str(row.id), "tenant_id": str(tenant_id)},
        )
    except SendGridError as exc:
        row.send_status = "failed"
        row.error_message = exc.message
        row.updated_at = _now()
        db.commit()
        db.refresh(row)
        raise AppError(exc.message or "SendGrid rejected the message", code="sendgrid_error",
                       status_code=502, details={"message": exc.message, "email_message": row_dict(row)}) from exc
    row.provider_message_id = result.get("message_id")
    row.send_status = "processed" if result.get("message_id") else "queued"
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def handle_events(db: Session, events: list[dict[str, Any]], *, raw_body: bytes | None = None) -> int:
    """Apply a SendGrid event-webhook batch. Rows are matched by the
    ``email_message_id`` custom arg first, then by ``sg_message_id`` prefix."""
    applied = 0
    payload_hash = hashlib.sha256(raw_body).hexdigest() if raw_body else None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        status = str(ev.get("event") or "").lower()
        if status not in _STATUS_RANK:
            continue
        row = None
        mid = ev.get("email_message_id")
        if mid is not None:
            try:
                row = db.get(EmailMessage, int(mid))
            except (TypeError, ValueError):
                row = None
        if row is None:
            sg_id = str(ev.get("sg_message_id") or "").split(".")[0]
            if sg_id:
                row = db.execute(select(EmailMessage).where(
                    EmailMessage.provider_message_id == sg_id)).scalars().first()
        if row is None:
            continue
        now = _now()
        if _STATUS_RANK[status] >= _STATUS_RANK.get(row.send_status, 0):
            row.send_status = status
        if status == "delivered" and row.delivered_at is None:
            row.delivered_at = now
        if status in ("open", "click") and row.opened_at is None:
            row.opened_at = now
        if status in ("bounce", "dropped", "deferred"):
            reason = ev.get("reason") or ev.get("response")
            if reason:
                row.error_message = str(reason)[:1000]
        row.status_payload_hash = payload_hash
        row.updated_at = now
        applied += 1
    if applied:
        db.commit()
    return applied


def metadata() -> dict[str, Any]:
    return {"message_types": list(MESSAGE_TYPES), "send_statuses": list(SEND_STATUSES)}
