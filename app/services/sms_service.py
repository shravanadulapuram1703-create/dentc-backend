"""Patient SMS (Twilio) — send gateway, webhooks, inbox, templates, reminders.

Backs ``docs/sms/SMS_BACKEND_DEVREPORT.md`` (SMS-1…10). The table keeps its
legacy shape — **one row per outbound text, with the reply on the same row** —
because the frontend fans a row out into up to two inbox entries from
``sent_text`` / ``reply_text``. A stand-alone inbound text is a row with
``sent_text IS NULL`` and ``direction='inbound'``.

What lives here:

* :func:`send` — SMS-1. Consent (SMS-8), quiet hours, per-tenant throttle,
  idempotency by ``client_id``, sender resolution per office (SMS-7), the row
  is persisted **before** Twilio is called, and a Twilio rejection is stored as
  ``failed`` *and* surfaced as a 502 ``twilio_error`` so the UI can show both.
* :func:`handle_inbound` / :func:`handle_status` — SMS-2. Idempotent by Twilio
  sid; a reply within ``SMS_REPLY_WINDOW_HOURS`` of an unanswered outbound text
  lands on that row (legacy parity), otherwise it is a stand-alone inbound row;
  confirmation keywords act on the appointment; STOP/START flip
  ``patients.no_auto_sms`` and are recorded as ``opt_out`` / ``opt_in`` rows.
* :class:`SmsMessageCRUD` + :func:`enrich_sms_messages` — SMS-6 practice-wide
  inbox filters and the denormalised patient/office/actor names.
* :func:`render` — SMS-5 merge fields (``{{patient_first_name}}`` …), shared by
  the on-demand renderer and the SMS-9 reminder job.
* :func:`run_reminders` — SMS-9, de-duplicated on
  ``(appointment_id, message_type, reminder_lead_hours)``.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.datetimes import office_tz
from app.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from app.core.logging import get_logger
from app.crud.base import CRUDBase
from app.db.models import (
    AccountCommunications,
    Appointment,
    Office,
    OfficePhoneAssignment,
    Patient,
    Provider,
    SmsMessage,
    SmsTemplate,
)
from app.integrations import redis_store, twilio_client
from app.integrations.twilio_client import TwilioError, status_rank
from app.services import sms_events
from app.services.sms_phone import normalize_e164, phone_variants

logger = get_logger(__name__)

# ── Vocabularies (published at GET /sms/metadata) ─────────────────────────────
MESSAGE_TYPES = (
    "manual", "appointment_reminder", "appointment_confirmation", "recall",
    "balance", "inbound_reply", "opt_out", "opt_in", "other",
)
#: Types a caller may *send*. ``inbound_reply``/``opt_*`` are written by the
#: inbound webhook only.
SENDABLE_TYPES = ("manual", "appointment_reminder", "appointment_confirmation",
                  "recall", "balance", "other")
SEND_STATUSES = twilio_client.SEND_STATUSES
REPLY_INTENTS = ("confirm", "reschedule", "cancel", "stop", "start", "help", "other")
DIRECTIONS = ("outbound", "inbound")
MAX_BODY_LENGTH = 1600

#: SMS-5 merge fields. Rendering is ``{{field}}`` substitution; an unresolvable
#: field renders blank and is reported, never left as a literal ``{{token}}``.
MERGE_FIELDS = (
    "patient_first_name", "patient_last_name", "patient_name",
    "appointment_date", "appointment_time", "appointment_datetime",
    "provider_name", "office_name", "office_phone",
)
_MERGE_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

DEFAULT_REMINDER_BODY = (
    "Hi {{patient_first_name}}, this is a reminder of your appointment at "
    "{{office_name}} on {{appointment_datetime}}. Reply C to confirm, R to "
    "reschedule. Questions? Call {{office_phone}}."
)
DEFAULT_REMINDER_LEAD_HOURS = [48, 2]

# Carrier-level keywords (Twilio's standard STOP / START lists) — matched on the
# *whole* trimmed body, case-insensitively.
STOP_KEYWORDS = frozenset({"stop", "stopall", "unsubscribe", "cancel", "end", "quit"})
START_KEYWORDS = frozenset({"start", "unstop"})
HELP_KEYWORDS = frozenset({"help", "info"})
# SMS-2 step 3: reply intent on a text that answers an appointment message.
_CONFIRM_RE = re.compile(r"^(yes|y|confirm|confirmed|c)\b")
_RESCHEDULE_RE = re.compile(r"^(reschedule|r)\b")
_CANCEL_RE = re.compile(r"^(cancel|no|n)\b")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _sha256(raw: bytes | str | None) -> str | None:
    if raw is None:
        return None
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    return hashlib.sha256(data).hexdigest()


def row_dict(row: SmsMessage) -> dict[str, Any]:
    """Plain column dict (for error ``details`` — the 409/502 paths hand the
    persisted row back without going through the response model)."""
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder({c.key: getattr(row, c.key) for c in sa_inspect(row).mapper.column_attrs})


# ── Legacy backfill parity (SMS-3) ────────────────────────────────────────────
def infer_message_type(sent_text: str | None, reply_text: str | None) -> str:
    """The frontend's text-sniffing heuristic, mirrored for the migration
    backfill so a row classified by SQL and by the UI agree."""
    if not sent_text:
        return "inbound_reply" if reply_text else "other"
    t = sent_text.lower()
    if "confirm" in t:
        return "appointment_confirmation"
    if "reminder" in t or "appointment" in t or "appt" in t:
        return "appointment_reminder"
    if "recall" in t or "due for" in t or "cleaning" in t or "check-up" in t or "checkup" in t:
        return "recall"
    if "balance" in t or "payment" in t or "statement" in t or "past due" in t:
        return "balance"
    return "manual"


# ── Merge fields (SMS-5) ──────────────────────────────────────────────────────
def _patient_name(p: Patient | None) -> str:
    if p is None:
        return ""
    first = (p.preferred_name or p.first_name or "").strip()
    return " ".join(x for x in (first, (p.last_name or "").strip()) if x)


def build_merge_context(
    db: Session,
    *,
    patient: Patient | None,
    appointment: Appointment | None = None,
    office: Office | None = None,
) -> dict[str, str]:
    """Resolve every merge field for one patient (+ optional appointment/office).

    Office falls back appointment.office -> patient.home_office; provider falls
    back appointment.provider -> patient.preferred_provider.
    """
    if office is None and appointment is not None and appointment.office_id:
        office = db.get(Office, appointment.office_id)
    if office is None and patient is not None and patient.home_office_id:
        office = db.get(Office, patient.home_office_id)
    provider: Provider | None = None
    if appointment is not None and appointment.provider_id:
        provider = db.get(Provider, appointment.provider_id)
    if provider is None and patient is not None and patient.preferred_provider_id:
        provider = db.get(Provider, patient.preferred_provider_id)

    ctx: dict[str, str] = {
        "patient_first_name": (patient.preferred_name or patient.first_name or "") if patient else "",
        "patient_last_name": (patient.last_name or "") if patient else "",
        "patient_name": _patient_name(patient),
        "appointment_date": "",
        "appointment_time": "",
        "appointment_datetime": "",
        "provider_name": "",
        "office_name": (office.name or "") if office else "",
        "office_phone": (office.phone or "") if office else "",
    }
    if appointment is not None and appointment.date:
        d = appointment.date
        ctx["appointment_date"] = d.strftime("%a, %b %d").replace(" 0", " ")
        if appointment.start_time:
            t = appointment.start_time.strftime("%I:%M %p").lstrip("0")
            ctx["appointment_time"] = t
            ctx["appointment_datetime"] = f"{ctx['appointment_date']} at {t}"
        else:
            ctx["appointment_datetime"] = ctx["appointment_date"]
    if provider is not None:
        title = (provider.title or "").strip()
        name = (provider.name or "").strip()
        ctx["provider_name"] = f"{title} {name}".strip() if title and not name.lower().startswith(title.lower()) else name
    return ctx


def render(body: str, context: dict[str, str]) -> tuple[str, list[str]]:
    """Substitute ``{{field}}`` tokens. Returns ``(text, unresolved_fields)``;
    an unknown or empty field renders blank so a patient never sees ``{{…}}``."""
    unresolved: list[str] = []

    def _sub(m: re.Match) -> str:
        key = m.group(1)
        value = context.get(key)
        if not value:
            if key not in unresolved:
                unresolved.append(key)
            return ""
        return value

    text = _MERGE_RE.sub(_sub, body or "")
    # Collapse the double spaces a blank token leaves behind.
    return re.sub(r"[ \t]{2,}", " ", text).strip(), unresolved


def render_for_patient(
    db: Session, tenant_id: int, *, body: str | None, template_id: int | None,
    patient_id: int, appointment_id: str | None, office_id: int | None,
) -> dict[str, Any]:
    patient = _get_patient(db, tenant_id, patient_id)
    template = _get_template(db, tenant_id, template_id) if template_id else None
    source = body if body is not None else (template.body if template else None)
    if source is None:
        raise ValidationError("Provide body or template_id", code="sms_render_no_body")
    appointment = _get_appointment(db, tenant_id, appointment_id) if appointment_id else None
    office = _get_office(db, tenant_id, office_id) if office_id else None
    ctx = build_merge_context(db, patient=patient, appointment=appointment, office=office)
    text, unresolved = render(source, ctx)
    return {
        "body": text,
        "unresolved_fields": unresolved,
        "context": ctx,
        "template_id": template.id if template else None,
        "message_type": template.message_type if template else None,
        "length": len(text),
        "segments": _estimate_segments(text),
    }


def _estimate_segments(text: str) -> int:
    """GSM-7 vs UCS-2 segment estimate (what Twilio will bill)."""
    if not text:
        return 0
    is_gsm = all(ord(ch) < 128 for ch in text)
    single, multi = (160, 153) if is_gsm else (70, 67)
    n = len(text)
    return 1 if n <= single else -(-n // multi)


# ── Lookups ──────────────────────────────────────────────────────────────────
def _get_patient(db: Session, tenant_id: int, patient_id: int) -> Patient:
    p = db.get(Patient, patient_id)
    if p is None or p.tenant_id != tenant_id:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return p


def _get_office(db: Session, tenant_id: int, office_id: int) -> Office:
    o = db.get(Office, office_id)
    if o is None or o.tenant_id != tenant_id:
        raise NotFoundError(f"Office '{office_id}' was not found")
    return o


def _get_template(db: Session, tenant_id: int, template_id: int) -> SmsTemplate:
    t = db.get(SmsTemplate, template_id)
    if t is None or t.tenant_id != tenant_id:
        raise NotFoundError(f"SmsTemplate '{template_id}' was not found")
    return t


def _get_appointment(db: Session, tenant_id: int, appointment_id: str) -> Appointment:
    a = db.get(Appointment, appointment_id)
    if a is None:
        raise NotFoundError(f"Appointment '{appointment_id}' was not found")
    office = db.get(Office, a.office_id) if a.office_id else None
    if office is not None and office.tenant_id != tenant_id:
        raise NotFoundError(f"Appointment '{appointment_id}' was not found")
    return a


def _comm_settings(db: Session, tenant_id: int) -> AccountCommunications | None:
    return db.execute(
        select(AccountCommunications).where(AccountCommunications.tenant_id == tenant_id)
    ).scalar_one_or_none()


# ── SMS-7: sender resolution ─────────────────────────────────────────────────
def resolve_sender(db: Session, tenant_id: int, office_id: int | None) -> dict[str, Any]:
    """``OFFICE_SPECIFIC`` assignment → ``MULTI_OFFICE_SHARED`` → tenant default
    → platform default; Messaging Service SID per assignment → tenant →
    platform. Returns ``{from_phone, messaging_service_sid, source}``."""
    comm = _comm_settings(db, tenant_id)
    from_phone: str | None = None
    service_sid: str | None = None
    source = "none"
    if office_id is not None:
        rows = db.execute(
            select(OfficePhoneAssignment).where(
                OfficePhoneAssignment.tenant_id == tenant_id,
                OfficePhoneAssignment.office_id == office_id,
            )
        ).scalars().all()
        by_type = {(r.assignment_type or "").lower(): r for r in rows}
        for kind in ("office_specific", "multi_office_shared"):
            row = by_type.get(kind)
            if row is not None and (row.phone_number or row.messaging_service_sid):
                from_phone = normalize_e164(row.phone_number) or row.phone_number
                service_sid = row.messaging_service_sid
                source = kind
                break
    if from_phone is None and comm is not None and comm.sms_from_phone:
        from_phone = normalize_e164(comm.sms_from_phone) or comm.sms_from_phone
        source = "tenant_default"
    if from_phone is None and settings.TWILIO_DEFAULT_FROM:
        from_phone = settings.TWILIO_DEFAULT_FROM
        source = "platform_default"
    if not service_sid and comm is not None and comm.messaging_service_sid:
        service_sid = comm.messaging_service_sid
    if not service_sid and settings.TWILIO_MESSAGING_SERVICE_SID:
        service_sid = settings.TWILIO_MESSAGING_SERVICE_SID
    return {"from_phone": from_phone, "messaging_service_sid": service_sid, "source": source}


def _status_callback_url() -> str | None:
    if settings.TWILIO_STATUS_CALLBACK_URL:
        return settings.TWILIO_STATUS_CALLBACK_URL
    base = (settings.PUBLIC_API_BASE_URL or "").rstrip("/")
    if base:
        return f"{base}{settings.API_V1_PREFIX}/sms/webhooks/status"
    return None


def gateway_status(db: Session | None = None, tenant_id: int | None = None) -> dict[str, Any]:
    """What the Messages screen needs to label itself Live / Log only."""
    configured = twilio_client.is_configured()
    out: dict[str, Any] = {
        "configured": configured,
        "mode": "live" if configured else "log_only",
        "webhook_validation": bool(settings.TWILIO_WEBHOOK_VALIDATE),
        "webhook_signing_ready": twilio_client.can_validate_webhooks(),
        "status_callback_url": _status_callback_url(),
        "messaging_service_configured": bool(settings.TWILIO_MESSAGING_SERVICE_SID),
        "quiet_hours": None,
        "reminders_enabled": None,
    }
    if db is not None and tenant_id is not None:
        comm = _comm_settings(db, tenant_id)
        if comm is not None:
            out["messaging_service_configured"] = bool(
                comm.messaging_service_sid or settings.TWILIO_MESSAGING_SERVICE_SID
            )
            out["quiet_hours"] = {
                "start_hour": comm.sms_quiet_hours_start if comm.sms_quiet_hours_start is not None else 8,
                "end_hour": comm.sms_quiet_hours_end if comm.sms_quiet_hours_end is not None else 21,
            }
            out["reminders_enabled"] = bool(comm.sms_reminders_enabled)
        else:
            out["quiet_hours"] = {"start_hour": 8, "end_hour": 21}
            out["reminders_enabled"] = False
    return out


# ── SMS-8: compliance guards ─────────────────────────────────────────────────
def _check_consent(patient: Patient, message_type: str, override_consent: bool) -> None:
    if not patient.no_auto_sms:
        return
    if message_type != "manual":
        raise AppError(
            "Patient has opted out of automated text messages",
            code="patient_opted_out", status_code=400,
            details={"patient_id": patient.id, "message_type": message_type,
                     "sms_opt_out_at": patient.sms_opt_out_at.isoformat()
                     if patient.sms_opt_out_at else None},
        )
    if not override_consent:
        raise AppError(
            "Patient has opted out of text messages; a manual text needs override_consent=true",
            code="consent_override_required", status_code=400,
            details={"patient_id": patient.id},
        )


def quiet_hours_window(comm: AccountCommunications | None) -> tuple[int, int]:
    start = comm.sms_quiet_hours_start if comm is not None and comm.sms_quiet_hours_start is not None else 8
    end = comm.sms_quiet_hours_end if comm is not None and comm.sms_quiet_hours_end is not None else 21
    return int(start), int(end)


def _quiet_hours_violation(
    comm: AccountCommunications | None, office: Office | None, at: datetime | None = None,
) -> datetime | None:
    """Returns the next allowed local datetime when ``at`` (UTC) falls outside
    the sending window, else None. Window is [start, end) office-local."""
    start, end = quiet_hours_window(comm)
    if start <= 0 and end >= 24:
        return None
    tz = office_tz(office.timezone if office is not None else None)
    moment = at or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    now_local = moment.astimezone(tz)
    if start <= now_local.hour < end:
        return None
    next_day = now_local.date() if now_local.hour < start else now_local.date() + timedelta(days=1)
    return datetime.combine(next_day, time(hour=start), tzinfo=tz)


def _check_quiet_hours(
    comm: AccountCommunications | None, office: Office | None, message_type: str,
    at: datetime | None = None,
) -> None:
    if message_type == "manual":
        return
    next_allowed = _quiet_hours_violation(comm, office, at)
    if next_allowed is not None:
        start, end = quiet_hours_window(comm)
        raise ValidationError(
            f"Automated texts are only sent between {start:02d}:00 and {end:02d}:00 office time",
            code="sms_quiet_hours",
            details={"next_allowed_at": next_allowed.isoformat(),
                     "quiet_hours": {"start_hour": start, "end_hour": end}},
        )


def _check_rate_limit(tenant_id: int) -> None:
    limit = settings.SMS_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return
    count = redis_store.incr_counter(f"sms:rl:{tenant_id}", 60)
    if count is not None and count > limit:
        raise RateLimitError(
            "Outbound text throughput limit reached; try again in a minute",
            code="sms_rate_limited",
        )


# ── SMS-1: send ──────────────────────────────────────────────────────────────
def send(
    db: Session, tenant_id: int, user_id: int | None, payload: dict[str, Any],
    *, at: datetime | None = None,
) -> SmsMessage:
    """Persist-then-send. Raises 400/404/409/422/429 before anything is written,
    502 ``twilio_error`` after the row is stored as ``failed``. ``at`` is the
    moment quiet hours are judged against (the reminder job passes its own
    clock so a batch is evaluated consistently)."""
    patient = _get_patient(db, tenant_id, int(payload["patient_id"]))
    body = (payload.get("body") or "").strip()
    if not body:
        raise ValidationError("Message body is required", code="sms_body_required")
    if len(body) > MAX_BODY_LENGTH:
        raise ValidationError(f"Message body exceeds {MAX_BODY_LENGTH} characters",
                              code="sms_body_too_long")
    message_type = (payload.get("message_type") or "manual").strip().lower()
    if message_type not in SENDABLE_TYPES:
        raise ValidationError(
            f"message_type must be one of {', '.join(SENDABLE_TYPES)}",
            code="sms_invalid_message_type",
        )
    to_phone = normalize_e164(payload.get("to_phone"))
    if to_phone is None:
        raise ValidationError("to_phone must be an E.164 number", code="invalid_phone")

    client_id = (payload.get("client_id") or "").strip() or None
    if client_id:
        existing = db.execute(
            select(SmsMessage).where(
                SmsMessage.tenant_id == tenant_id, SmsMessage.client_id == client_id
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(
                "A text with this client_id was already sent",
                code="duplicate_client_id",
                details={"sms_message": row_dict(existing)},
            )

    _check_consent(patient, message_type, bool(payload.get("override_consent")))

    office: Office | None = None
    office_id = payload.get("office_id")
    if office_id is not None:
        office = _get_office(db, tenant_id, int(office_id))
    elif patient.home_office_id:
        office = db.get(Office, patient.home_office_id)
    appointment_id = payload.get("appointment_id") or None
    if appointment_id:
        _get_appointment(db, tenant_id, str(appointment_id))
    template_id = payload.get("template_id")
    if template_id is not None:
        _get_template(db, tenant_id, int(template_id))

    comm = _comm_settings(db, tenant_id)
    _check_quiet_hours(comm, office, message_type, at)
    _check_rate_limit(tenant_id)

    sender = resolve_sender(db, tenant_id, office.id if office else None)
    row = SmsMessage(
        tenant_id=tenant_id,
        office_id=office.id if office else None,
        patient_id=patient.id,
        appointment_id=str(appointment_id) if appointment_id else None,
        sent_text=body,
        sent_phone=to_phone,
        from_phone=sender["from_phone"],
        direction="outbound",
        send_status="queued",
        sent_at=_now(),
        message_type=message_type,
        client_id=client_id,
        template_id=int(template_id) if template_id is not None else None,
        reminder_lead_hours=payload.get("reminder_lead_hours"),
        created_by=user_id,
        is_read=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _dispatch(db, row, sender)


def _dispatch(db: Session, row: SmsMessage, sender: dict[str, Any]) -> SmsMessage:
    """Hand a persisted ``queued`` row to Twilio and record the outcome."""
    if not twilio_client.is_configured():
        # Log-only mode: the row is the audit trail; nothing reaches a carrier.
        return row
    try:
        result = twilio_client.send_message(
            to=row.sent_phone or "",
            body=row.sent_text or "",
            from_phone=sender.get("from_phone"),
            messaging_service_sid=sender.get("messaging_service_sid"),
            status_callback=_status_callback_url(),
        )
    except TwilioError as exc:
        row.send_status = "failed"
        row.error_code = exc.code
        row.error_message = exc.message
        row.updated_at = _now()
        db.commit()
        db.refresh(row)
        raise AppError(
            exc.message or "Twilio rejected the message",
            code="twilio_error", status_code=502,
            details={"code": exc.code, "message": exc.message, "sms_message": row_dict(row)},
        ) from exc
    row.twilio_sid = result.get("sid")
    row.send_status = (result.get("status") or "queued").lower()
    row.segments = result.get("num_segments")
    if result.get("error_code") is not None:
        try:
            row.error_code = int(result["error_code"])
        except (TypeError, ValueError):
            row.error_code = None
        row.error_message = result.get("error_message")
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


# ── SMS-2: inbound webhook ───────────────────────────────────────────────────
def _resolve_inbound_target(db: Session, to_e164: str | None) -> tuple[int, int | None] | None:
    """``To`` → (tenant_id, office_id): phone assignment (office-specific first)
    → tenant default number → the last office that sent from this number."""
    variants = phone_variants(to_e164)
    if not variants:
        return None
    rows = db.execute(
        select(OfficePhoneAssignment).where(OfficePhoneAssignment.phone_number.in_(variants))
    ).scalars().all()
    if rows:
        rows.sort(key=lambda r: 0 if (r.assignment_type or "").lower() == "office_specific" else 1)
        return rows[0].tenant_id, rows[0].office_id
    comm = db.execute(
        select(AccountCommunications).where(AccountCommunications.sms_from_phone.in_(variants))
    ).scalars().first()
    if comm is not None:
        return comm.tenant_id, None
    last = db.execute(
        select(SmsMessage)
        .where(SmsMessage.from_phone.in_(variants))
        .order_by(SmsMessage.sent_at.desc().nullslast(), SmsMessage.id.desc())
    ).scalars().first()
    if last is not None:
        return last.tenant_id, last.office_id
    return None


def _match_patient(
    db: Session, tenant_id: int, office_id: int | None, from_e164: str,
) -> tuple[int | None, list[int]]:
    """Patients sharing the number; one → them, several → whoever most recently
    received a text (this office preferred), none of those → unmatched."""
    variants = phone_variants(from_e164)
    stmt = select(Patient).where(
        Patient.tenant_id == tenant_id,
        or_(Patient.cell_phone.in_(variants), Patient.phone.in_(variants),
            Patient.work_phone.in_(variants)),
    )
    candidates = list(db.execute(stmt).scalars().all())
    active = [p for p in candidates if getattr(p, "is_active", True)]
    if active:
        candidates = active
    if not candidates:
        return None, []
    ids = [p.id for p in candidates]
    if len(ids) == 1:
        return ids[0], ids
    recent = db.execute(
        select(SmsMessage)
        .where(SmsMessage.tenant_id == tenant_id, SmsMessage.patient_id.in_(ids),
               SmsMessage.sent_phone.in_(variants), SmsMessage.sent_text.isnot(None))
        .order_by(SmsMessage.sent_at.desc().nullslast(), SmsMessage.id.desc())
    ).scalars().all()
    if recent:
        same_office = [r for r in recent if office_id is not None and r.office_id == office_id]
        pick = (same_office or recent)[0]
        return pick.patient_id, ids
    return None, ids


def _find_reply_target(
    db: Session, tenant_id: int, from_e164: str, patient_id: int | None,
) -> SmsMessage | None:
    """The most recent unanswered outbound text to this number within the
    reply window (SMS-2 step 2)."""
    variants = phone_variants(from_e164)
    since = _now() - timedelta(hours=settings.SMS_REPLY_WINDOW_HOURS)
    stmt = (
        select(SmsMessage)
        .where(SmsMessage.tenant_id == tenant_id, SmsMessage.sent_text.isnot(None),
               SmsMessage.sent_phone.in_(variants), SmsMessage.reply_text.is_(None),
               func.coalesce(SmsMessage.sent_at, SmsMessage.created_at) >= since)
        .order_by(SmsMessage.sent_at.desc().nullslast(), SmsMessage.id.desc())
    )
    if patient_id is not None:
        stmt = stmt.where(or_(SmsMessage.patient_id == patient_id, SmsMessage.patient_id.is_(None)))
    return db.execute(stmt).scalars().first()


def classify_reply(body: str, *, answers_appointment: bool) -> tuple[str | None, bool]:
    """``(reply_intent, needs_attention)`` for an inbound body."""
    text = (body or "").strip().lower()
    if not text:
        return None, False
    word = re.sub(r"[^a-z]", "", text)
    if word in STOP_KEYWORDS and not (answers_appointment and _CANCEL_RE.match(text)):
        return "stop", False
    if word in START_KEYWORDS:
        return "start", False
    if word in HELP_KEYWORDS:
        return "help", False
    if answers_appointment:
        if _CONFIRM_RE.match(text):
            return "confirm", False
        if _RESCHEDULE_RE.match(text):
            return "reschedule", True
        if _CANCEL_RE.match(text):
            return "cancel", True
    return "other", True


def _twiml(message: str | None = None) -> str:
    if not message:
        return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    safe = (message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>'


def handle_inbound(db: Session, form: dict[str, str], *, raw_body: bytes | None = None) -> str:
    """Process one Twilio inbound-message webhook. Always returns TwiML; a
    request we cannot route is acknowledged (200) so Twilio stops retrying."""
    sid = (form.get("MessageSid") or form.get("SmsSid") or "").strip() or None
    from_e164 = normalize_e164(form.get("From"))
    to_e164 = normalize_e164(form.get("To"))
    body = (form.get("Body") or "").strip()
    payload_hash = _sha256(raw_body) if raw_body is not None else _sha256(
        "&".join(f"{k}={form[k]}" for k in sorted(form)))

    if sid:
        dup = db.execute(
            select(SmsMessage).where(
                or_(SmsMessage.reply_twilio_sid == sid, SmsMessage.twilio_sid == sid)
            )
        ).scalars().first()
        if dup is not None:
            return _twiml()
    if from_e164 is None:
        logger.warning("Inbound SMS with unparseable From; ignored (sid=%s)", sid)
        return _twiml()
    target = _resolve_inbound_target(db, to_e164)
    if target is None:
        logger.warning("Inbound SMS to unknown number %s; ignored (sid=%s)", to_e164, sid)
        return _twiml()
    tenant_id, office_id = target

    patient_id, candidates = _match_patient(db, tenant_id, office_id, from_e164)
    parent = _find_reply_target(db, tenant_id, from_e164, patient_id)
    answers_appt = bool(parent is not None and parent.appointment_id)
    intent, needs_attention = classify_reply(body, answers_appointment=answers_appt)
    now = _now()

    if parent is not None:
        row = parent
        row.reply_text = body
        row.reply_phone = from_e164
        row.reply_received_on = now
        row.reply_twilio_sid = sid
        row.is_read = False
        if row.patient_id is None and patient_id is not None:
            row.patient_id = patient_id
        if row.office_id is None:
            row.office_id = office_id
    else:
        row = SmsMessage(
            tenant_id=tenant_id,
            office_id=office_id,
            patient_id=patient_id,
            sent_text=None,
            sent_phone=None,
            from_phone=to_e164,
            direction="inbound",
            send_status="received",
            reply_text=body,
            reply_phone=from_e164,
            reply_received_on=now,
            reply_twilio_sid=sid,
            message_type="inbound_reply",
            is_read=False,
            candidate_patient_ids=candidates if patient_id is None and candidates else None,
        )
        db.add(row)
    row.reply_intent = intent
    row.needs_attention = needs_attention
    row.inbound_payload_hash = payload_hash
    row.updated_at = now

    auto_reply: str | None = None
    patient = db.get(Patient, patient_id) if patient_id is not None else None
    if intent == "stop":
        if patient is not None:
            patient.no_auto_sms = True
            patient.sms_opt_out_at = now
        if parent is None:
            row.message_type = "opt_out"
        else:
            # Keep the opt-out visible as its own row too, so staff see it.
            db.add(SmsMessage(
                tenant_id=tenant_id, office_id=office_id, patient_id=patient_id,
                from_phone=to_e164, direction="inbound", send_status="received",
                reply_text=body, reply_phone=from_e164, reply_received_on=now,
                message_type="opt_out", is_read=False, reply_intent="stop",
                inbound_payload_hash=payload_hash, updated_at=now,
            ))
    elif intent == "start" or (intent in (None, "other", "confirm") and _is_reoptin(body, patient)):
        if patient is not None:
            patient.no_auto_sms = False
            patient.sms_opt_in_at = now
        if parent is None:
            row.message_type = "opt_in"
        row.reply_intent = "start"
        row.needs_attention = False
    elif intent == "confirm" and parent is not None and parent.appointment_id:
        appt = db.get(Appointment, parent.appointment_id)
        if appt is not None:
            appt.confirmed_on = now
            appt.status = "Confirmed"
            appt.updated_at = now
        auto_reply = settings.SMS_CONFIRMATION_AUTO_REPLY or None
    elif intent == "reschedule" and parent is not None and parent.appointment_id:
        appt = db.get(Appointment, parent.appointment_id)
        if appt is not None:
            appt.add_to_call_list = True
            appt.updated_at = now
    # "cancel" → needs_attention only; staff cancel, never the webhook (SMS-2 step 3).

    db.commit()
    db.refresh(row)
    sms_events.announce_inbound(row)
    return _twiml(auto_reply)


def _is_reoptin(body: str, patient: Patient | None) -> bool:
    """Twilio treats YES as opt-in only after a STOP; mirror that so a plain
    "yes" to a reminder is a confirmation, not a consent change."""
    if patient is None or not patient.no_auto_sms:
        return False
    return re.sub(r"[^a-z]", "", (body or "").lower()) == "yes"


# ── SMS-2: status webhook ────────────────────────────────────────────────────
def handle_status(db: Session, form: dict[str, str], *, raw_body: bytes | None = None) -> bool:
    """Apply one delivery-status callback. Idempotent: a stale/out-of-order
    callback never regresses the row. Returns False when the sid is unknown."""
    sid = (form.get("MessageSid") or form.get("SmsSid") or "").strip()
    status = (form.get("MessageStatus") or form.get("SmsStatus") or "").strip().lower()
    if not sid or not status:
        return False
    row = db.execute(select(SmsMessage).where(SmsMessage.twilio_sid == sid)).scalar_one_or_none()
    if row is None:
        logger.info("Status callback for unknown sid %s (%s)", sid, status)
        return False
    now = _now()
    incoming, current = status_rank(status), status_rank(row.send_status)
    changed = False
    if incoming >= current and status != (row.send_status or "").lower():
        row.send_status = status
        changed = True
    if status == "delivered" and row.delivered_on is None:
        row.delivered_on = now
        changed = True
    if status in ("undelivered", "failed", "canceled"):
        code = form.get("ErrorCode")
        try:
            row.error_code = int(code) if code not in (None, "") else row.error_code
        except (TypeError, ValueError):
            pass
        msg = form.get("ErrorMessage")
        if msg:
            row.error_message = msg[:1000]
        changed = True
    row.status_payload_hash = _sha256(raw_body) if raw_body is not None else _sha256(
        "&".join(f"{k}={form[k]}" for k in sorted(form)))
    row.updated_at = now
    db.commit()
    if changed:
        db.refresh(row)
        sms_events.announce_status(row)
    return True


# ── SMS-6: inbox CRUD + enrichment ───────────────────────────────────────────
def _activity_ts():
    return func.coalesce(SmsMessage.sent_at, SmsMessage.reply_received_on,
                         SmsMessage.delivered_on, SmsMessage.created_at)


class SmsMessageCRUD(CRUDBase[SmsMessage]):
    """Generic ``/sms-messages`` resource with the inbox filters (SMS-6) and
    the invariants a hand-posted row must satisfy (the FE's log-only fallback)."""

    custom_filter_fields = ("date_from", "date_to", "unmatched", "has_reply", "unread_replies")

    def _extra_list_clauses(self, filters: dict[str, Any]) -> list:
        clauses: list = []
        date_from = filters.get("date_from")
        if date_from is not None:
            lo = datetime.combine(date_from, time.min) if isinstance(date_from, date) and not isinstance(date_from, datetime) else date_from
            clauses.append(_activity_ts() >= lo)
        date_to = filters.get("date_to")
        if date_to is not None:
            if isinstance(date_to, date) and not isinstance(date_to, datetime):
                hi = datetime.combine(date_to + timedelta(days=1), time.min)
                clauses.append(_activity_ts() < hi)
            else:
                clauses.append(_activity_ts() <= date_to)
        unmatched = filters.get("unmatched")
        if unmatched is not None:
            clauses.append(SmsMessage.patient_id.is_(None) if unmatched else SmsMessage.patient_id.isnot(None))
        has_reply = filters.get("has_reply")
        if has_reply is not None:
            clauses.append(SmsMessage.reply_text.isnot(None) if has_reply else SmsMessage.reply_text.is_(None))
        if filters.get("unread_replies"):
            clauses.append(SmsMessage.reply_text.isnot(None))
            clauses.append(SmsMessage.is_read.is_(False))
        return clauses

    @staticmethod
    def _normalise(data: dict[str, Any], *, existing: SmsMessage | None = None) -> dict[str, Any]:
        out = dict(data)
        mt = out.get("message_type")
        if mt is not None:
            mt = str(mt).strip().lower()
            if mt not in MESSAGE_TYPES:
                raise ValidationError(
                    f"message_type must be one of {', '.join(MESSAGE_TYPES)}",
                    code="sms_invalid_message_type",
                )
            out["message_type"] = mt
        st = out.get("send_status")
        if st is not None:
            st = str(st).strip().lower()
            out["send_status"] = "delivered" if st == "success" else st
        d = out.get("direction")
        if d is not None and str(d).lower() not in DIRECTIONS:
            raise ValidationError("direction must be outbound or inbound", code="sms_invalid_direction")
        for key in ("sent_phone", "reply_phone", "from_phone"):
            if out.get(key):
                out[key] = normalize_e164(out[key]) or out[key]
        return out

    def create(self, db: Session, data: dict[str, Any], **kwargs: Any) -> SmsMessage:
        payload = self._normalise(data)
        sent_text, reply_text = payload.get("sent_text"), payload.get("reply_text")
        if not payload.get("direction"):
            payload["direction"] = "outbound" if sent_text else ("inbound" if reply_text else None)
        if sent_text and payload.get("sent_at") is None:
            payload["sent_at"] = _now()
        if sent_text and not payload.get("send_status"):
            payload["send_status"] = "queued"
        if not sent_text and reply_text:
            payload.setdefault("send_status", "received")
            payload.setdefault("message_type", "inbound_reply")
            if payload.get("reply_received_on") is None:
                payload["reply_received_on"] = _now()
        if not payload.get("message_type"):
            payload["message_type"] = infer_message_type(sent_text, reply_text)
        return super().create(db, payload, **kwargs)

    def update(self, db: Session, obj_id: Any, data: dict[str, Any], **kwargs: Any) -> SmsMessage:
        payload = self._normalise(data)
        payload["updated_at"] = _now()
        return super().update(db, obj_id, payload, **kwargs)


def enrich_sms_messages(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    """Denormalised names for the inbox (SMS-6): patient, office, actor, template."""
    from app.services.user_admin_service import resolve_user_names

    rows = list(items)
    if not rows:
        return
    patient_ids = {r.patient_id for r in rows if r.patient_id is not None}
    office_ids = {r.office_id for r in rows if r.office_id is not None}
    template_ids = {r.template_id for r in rows if getattr(r, "template_id", None) is not None}
    actor_ids = {r.created_by for r in rows if r.created_by is not None}
    patients: dict[int, Patient] = {}
    if patient_ids:
        patients = {p.id: p for p in db.execute(select(Patient).where(Patient.id.in_(patient_ids))).scalars()}
    offices: dict[int, str] = {}
    if office_ids:
        offices = {o.id: o.name for o in db.execute(select(Office).where(Office.id.in_(office_ids))).scalars()}
    templates: dict[int, str] = {}
    if template_ids:
        templates = {t.id: t.name for t in db.execute(select(SmsTemplate).where(SmsTemplate.id.in_(template_ids))).scalars()}
    names = resolve_user_names(db, actor_ids)
    for r in rows:
        p = patients.get(r.patient_id) if r.patient_id is not None else None
        r.patient_first_name = (p.first_name if p else None)
        r.patient_last_name = (p.last_name if p else None)
        r.patient_name = _patient_name(p) or None
        r.patient_chart_no = (p.chart_no if p else None)
        r.office_name = offices.get(r.office_id) if r.office_id is not None else None
        r.template_name = templates.get(r.template_id) if getattr(r, "template_id", None) is not None else None
        r.created_by_name = names.get(r.created_by) if r.created_by is not None else None


def inbox_summary(db: Session, tenant_id: int, office_id: int | None = None) -> dict[str, Any]:
    """Badge counts for the practice-wide inbox (unread replies / needs
    attention / unmatched), overall and per office."""
    # Portable (SQLite has no FILTER): four grouped counts instead of one.
    def _count(where) -> dict[int | None, int]:  # noqa: ANN001
        stmt = select(SmsMessage.office_id, func.count()).where(SmsMessage.tenant_id == tenant_id, *where)
        if office_id is not None:
            stmt = stmt.where(SmsMessage.office_id == office_id)
        return {k: int(v) for k, v in db.execute(stmt.group_by(SmsMessage.office_id)).all()}

    unread = _count([SmsMessage.reply_text.isnot(None), SmsMessage.is_read.is_(False)])
    attention = _count([SmsMessage.needs_attention.is_(True), SmsMessage.is_read.is_(False)])
    unmatched = _count([SmsMessage.patient_id.is_(None), SmsMessage.reply_text.isnot(None),
                        SmsMessage.is_read.is_(False)])
    failed = _count([SmsMessage.send_status.in_(("failed", "undelivered"))])
    all_offices = set(unread) | set(attention) | set(unmatched) | set(failed)
    names = {o.id: o.name for o in db.execute(
        select(Office).where(Office.tenant_id == tenant_id)).scalars()} if all_offices else {}
    per_office = [
        {"office_id": oid, "office_name": names.get(oid) if oid is not None else None,
         "unread_replies": unread.get(oid, 0), "needs_attention": attention.get(oid, 0),
         "unmatched": unmatched.get(oid, 0), "failed": failed.get(oid, 0)}
        for oid in sorted(all_offices, key=lambda x: (x is None, x or 0))
    ]
    return {
        "unread_replies": sum(unread.values()),
        "needs_attention": sum(attention.values()),
        "unmatched": sum(unmatched.values()),
        "failed": sum(failed.values()),
        "offices": per_office,
    }


def mark_all_read(db: Session, tenant_id: int, *, patient_id: int | None, office_id: int | None) -> int:
    stmt = select(SmsMessage).where(
        SmsMessage.tenant_id == tenant_id, SmsMessage.reply_text.isnot(None),
        SmsMessage.is_read.is_(False),
    )
    if patient_id is not None:
        stmt = stmt.where(SmsMessage.patient_id == patient_id)
    if office_id is not None:
        stmt = stmt.where(SmsMessage.office_id == office_id)
    rows = db.execute(stmt).scalars().all()
    now = _now()
    for r in rows:
        r.is_read = True
        r.needs_attention = False
        r.updated_at = now
    db.commit()
    return len(rows)


# ── SMS-9: automated reminders ───────────────────────────────────────────────
_SKIP_STATUSES = ("cancel", "complete", "no show", "noshow", "missed", "checked out", "posted")


def _appt_local_dt(appt: Appointment, tz) -> datetime:  # noqa: ANN001
    return datetime.combine(appt.date, appt.start_time or time(hour=0), tzinfo=tz)


def run_reminders(
    db: Session, *, tenant_id: int | None = None, now: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send every due appointment reminder for tenants with reminders enabled.

    A reminder for lead ``L`` is due when ``appt_at − L h`` has passed but is no
    older than ``SMS_REMINDER_CATCHUP_HOURS`` (so an outage never blasts stale
    texts). De-dup key: ``(appointment_id, 'appointment_reminder', L)`` — both
    checked here and enforced by the deterministic ``client_id``.
    """
    now_utc = (now or datetime.now(UTC))
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    stmt = select(AccountCommunications).where(AccountCommunications.sms_reminders_enabled.is_(True))
    if tenant_id is not None:
        stmt = stmt.where(AccountCommunications.tenant_id == tenant_id)
    comms = db.execute(stmt).scalars().all()
    summary: dict[str, Any] = {"tenants": len(comms), "scanned": 0, "sent": 0, "failed": 0,
                               "skipped": {}, "dry_run": dry_run, "items": []}

    def _skip(reason: str) -> None:
        summary["skipped"][reason] = summary["skipped"].get(reason, 0) + 1

    catchup = timedelta(hours=settings.SMS_REMINDER_CATCHUP_HOURS)
    for comm in comms:
        leads = [int(x) for x in (comm.sms_reminder_lead_hours or DEFAULT_REMINDER_LEAD_HOURS) if int(x) >= 0]
        if not leads:
            continue
        template = db.get(SmsTemplate, comm.sms_reminder_template_id) if comm.sms_reminder_template_id else None
        body_src = template.body if template and template.is_active else DEFAULT_REMINDER_BODY
        offices = {o.id: o for o in db.execute(
            select(Office).where(Office.tenant_id == comm.tenant_id)).scalars()}
        if not offices:
            continue
        horizon_days = max(leads) // 24 + 2
        day_lo = (now_utc - timedelta(days=1)).date()
        day_hi = (now_utc + timedelta(days=horizon_days)).date()
        appts = db.execute(
            select(Appointment).where(
                Appointment.office_id.in_(list(offices)),
                Appointment.patient_id.isnot(None),
                Appointment.is_archived.is_(False),
                Appointment.date >= day_lo, Appointment.date <= day_hi,
            )
        ).scalars().all()
        for appt in appts:
            status = (appt.status or "").lower()
            if any(tok in status for tok in _SKIP_STATUSES):
                continue
            office = offices[appt.office_id]
            tz = office_tz(office.timezone)
            appt_at = _appt_local_dt(appt, tz)
            if appt_at <= now_utc:
                continue
            for lead in leads:
                summary["scanned"] += 1
                send_at = appt_at - timedelta(hours=lead)
                if send_at > now_utc:
                    _skip("not_due")
                    continue
                if send_at < now_utc - catchup:
                    _skip("too_late")
                    continue
                dup = db.execute(
                    select(SmsMessage.id).where(
                        SmsMessage.appointment_id == appt.id,
                        SmsMessage.message_type == "appointment_reminder",
                        SmsMessage.reminder_lead_hours == lead,
                    )
                ).first()
                if dup is not None:
                    _skip("already_sent")
                    continue
                patient = db.get(Patient, appt.patient_id)
                if patient is None or not getattr(patient, "is_active", True):
                    _skip("no_patient")
                    continue
                if patient.no_auto_sms:
                    _skip("opted_out")
                    continue
                to_phone = normalize_e164(patient.cell_phone) or normalize_e164(patient.phone)
                if to_phone is None:
                    _skip("no_phone")
                    continue
                if _quiet_hours_violation(comm, office, now_utc) is not None:
                    _skip("quiet_hours")
                    continue
                ctx = build_merge_context(db, patient=patient, appointment=appt, office=office)
                text, _ = render(body_src, ctx)
                item = {"appointment_id": appt.id, "patient_id": patient.id, "lead_hours": lead,
                        "to_phone": to_phone, "office_id": office.id}
                if dry_run:
                    summary["items"].append({**item, "status": "would_send"})
                    summary["sent"] += 1
                    continue
                try:
                    row = send(db, comm.tenant_id, None, {
                        "patient_id": patient.id, "office_id": office.id,
                        "appointment_id": appt.id, "to_phone": to_phone, "body": text,
                        "message_type": "appointment_reminder",
                        "client_id": f"rem_{appt.id}_{lead}"[:40],
                        "template_id": template.id if template else None,
                        "reminder_lead_hours": lead,
                    }, at=now_utc)
                    summary["sent"] += 1
                    summary["items"].append({**item, "sms_message_id": row.id, "status": row.send_status})
                except AppError as exc:
                    summary["failed"] += 1
                    summary["items"].append({**item, "status": "failed", "error": exc.code})
                    if exc.code == "duplicate_client_id":
                        _skip("already_sent")
    return summary


# ── SMS-10: retention ────────────────────────────────────────────────────────
def purge_expired(db: Session, *, days: int | None = None, dry_run: bool = True) -> dict[str, Any]:
    """Blank message bodies older than the retention window (row + delivery
    metadata are kept so the ledger of *that a text was sent* survives)."""
    days = days if days is not None else settings.SMS_RETENTION_DAYS
    if not days or days <= 0:
        return {"retention_days": days, "affected": 0, "dry_run": dry_run}
    cutoff = _now() - timedelta(days=int(days))
    stmt = select(SmsMessage).where(
        _activity_ts() < cutoff,
        or_(SmsMessage.sent_text.isnot(None), SmsMessage.reply_text.isnot(None)),
    )
    rows = db.execute(stmt).scalars().all()
    if not dry_run:
        for r in rows:
            if r.sent_text is not None:
                r.sent_text = ""
            if r.reply_text is not None:
                r.reply_text = ""
            r.updated_at = _now()
        db.commit()
    return {"retention_days": int(days), "cutoff": cutoff.isoformat(), "affected": len(rows), "dry_run": dry_run}


def metadata() -> dict[str, Any]:
    return {
        "message_types": list(MESSAGE_TYPES),
        "sendable_message_types": list(SENDABLE_TYPES),
        "send_statuses": list(SEND_STATUSES),
        "reply_intents": list(REPLY_INTENTS),
        "directions": list(DIRECTIONS),
        "merge_fields": list(MERGE_FIELDS),
        "max_body_length": MAX_BODY_LENGTH,
        "stop_keywords": sorted(STOP_KEYWORDS),
        "start_keywords": sorted(START_KEYWORDS),
        "reply_window_hours": settings.SMS_REPLY_WINDOW_HOURS,
        "default_reminder_body": DEFAULT_REMINDER_BODY,
        "default_reminder_lead_hours": DEFAULT_REMINDER_LEAD_HOURS,
    }
