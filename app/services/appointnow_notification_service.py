"""AppointNow outbound notifications (AN-21).

Two audiences, both **best-effort** — a notification can never fail or undo the
request transition that already committed, and with no transport configured
(no ``SENDGRID_API_KEY``, no ``RC_APP_CLIENT_ID``/etc.) everything is log-only
so dev/tests need no credentials:

* **The office**, on a new public request — one e-mail to the office's
  notification address (``offices.email`` → ``account_communications.
  comm_contact_email`` → ``account_settings.email``) via SendGrid. The staff
  inbox / push event is the primary channel; this is for practices that do not
  keep the PMS open.
* **The contact**, on approve / decline / reschedule — SMS first when the
  patient ticked the contact consent (``consent_accepted`` is exactly "I consent
  to receive calls and text messages regarding my appointment"), RingCentral is
  configured, the number normalises to E.164 and the office is **outside quiet
  hours** (the same window the SMS module applies to automated texts — an
  approval at 22:30 must not wake anyone); otherwise e-mail when the request has
  an address. The channel used is stamped on the row
  (``contact_notified_at`` / ``contact_notified_via``) so staff can see whether
  the patient was told.

The contact is an *external* person, usually not yet a ``patients`` row, so the
text is sent through :mod:`ringcentral_client` directly with the office's
resolved sender (``sms_service.resolve_sender``) rather than through
``sms_service.send`` (which is keyed on ``patient_id`` and writes the patient
SMS log).
"""

from __future__ import annotations

from datetime import UTC, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import AccountCommunications, AccountSettings, BookingRequest, Office
from app.integrations import ringcentral_client, sendgrid_client
from app.services import sms_service
from app.services.sms_phone import normalize_e164

logger = get_logger(__name__)

CONTACT_EVENTS = ("approved", "declined", "rescheduled")


# ── formatting ───────────────────────────────────────────────────────────────
def _fmt_when(day, start: time | None) -> str:  # noqa: ANN001
    when = day.strftime("%a, %b %d").replace(" 0", " ")
    if start is not None:
        hour = start.hour % 12 or 12
        when += f" at {hour}:{start.minute:02d} {'PM' if start.hour >= 12 else 'AM'}"
    return when


def _office_label(office: Office) -> str:
    return office.name or office.office_code or "Your dental office"


def _office_phone(office: Office) -> str | None:
    return office.phone or None


def contact_message(office: Office, req: BookingRequest, event: str) -> tuple[str, str]:
    """``(subject, body_text)`` for the contact, per event."""
    who = _office_label(office)
    when = _fmt_when(req.slot_date, req.start_time)
    with_provider = f" with {req.provider_name}" if req.provider_name else ""
    phone = _office_phone(office)
    call = f" Call {phone} if you need to change it." if phone else ""
    if event == "approved":
        subject = f"{who}: your appointment is confirmed"
        body = f"{who}: your appointment request for {when}{with_provider} has been confirmed.{call}"
    elif event == "declined":
        subject = f"{who}: about your appointment request"
        reason = f" ({req.decline_reason.strip()})" if req.decline_reason else ""
        body = (
            f"{who}: we could not accommodate your appointment request for {when}{reason}."
            + (f" Please call {phone} to find another time." if phone else " Please contact us to find another time.")
        )
    elif event == "rescheduled":
        subject = f"{who}: your requested appointment time has changed"
        body = (
            f"{who}: your appointment request has been moved to {when}{with_provider}."
            + (f" Call {phone} if this time does not work." if phone else " Contact us if this time does not work.")
        )
    else:  # pragma: no cover - guarded by CONTACT_EVENTS
        raise ValueError(f"unknown contact event {event!r}")
    return subject, body


# ── office e-mail on a new request ───────────────────────────────────────────
def office_notification_email(db: Session, office: Office) -> str | None:
    if office.email:
        return office.email
    comm = db.execute(
        select(AccountCommunications).where(AccountCommunications.tenant_id == office.tenant_id)
    ).scalar_one_or_none()
    if comm is not None and comm.comm_contact_email:
        return comm.comm_contact_email
    acct = db.execute(
        select(AccountSettings).where(AccountSettings.tenant_id == office.tenant_id)
    ).scalar_one_or_none()
    return acct.email if acct is not None and acct.email else None


def notify_office_new_request(db: Session, office: Office, req: BookingRequest) -> dict:
    """E-mail the office that a request arrived. Returns ``{sent, channel, reason}``."""
    to_email = office_notification_email(db, office)
    name = " ".join(x for x in (req.first_name, req.last_name) if x) or "A patient"
    when = _fmt_when(req.slot_date, req.start_time)
    subject = f"New online booking request — {name}"
    lines = [
        f"{name} requested an appointment through AppointNow ({_office_label(office)}).",
        "",
        f"Reason: {req.reason_label or req.reason_id or '-'}",
        f"Requested: {when}" + (f" with {req.provider_name}" if req.provider_name else ""),
        f"Phone: {req.phone or '-'}",
        f"Email: {req.email or '-'}",
        f"New patient: {'yes' if req.is_new_patient else 'no'}",
    ]
    if req.insurance_info:
        lines.append(f"Insurance: {req.insurance_info}")
    if req.notes:
        lines += ["", "Notes:", req.notes]
    lines += ["", f"Request id: {req.id}", "Open Appointments → AppointNow to approve or decline."]
    body = "\n".join(lines)
    if not to_email:
        logger.info("AppointNow office e-mail skipped (no address) office=%s req=%s", office.id, req.id)
        return {"sent": False, "channel": "email", "reason": "no_office_email"}
    if not sendgrid_client.is_configured():
        logger.info("AppointNow office e-mail (log-only) to=%s subject=%r", to_email, subject)
        return {"sent": False, "channel": "email", "reason": "not_configured"}
    try:
        sendgrid_client.send_mail(
            to_email=to_email, subject=subject, body_html=None, body_text=body,
            from_name=_office_label(office),
            custom_args={"appointnow_request_id": req.id, "kind": "office_new_request"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("AppointNow office e-mail failed to=%s: %s", to_email, exc)
        return {"sent": False, "channel": "email", "reason": "send_failed"}
    return {"sent": True, "channel": "email", "reason": None}


# ── contact notification on approve / decline / reschedule ───────────────────
def _sms_allowed_now(db: Session, office: Office) -> bool:
    comm = db.execute(
        select(AccountCommunications).where(AccountCommunications.tenant_id == office.tenant_id)
    ).scalar_one_or_none()
    return sms_service._quiet_hours_violation(comm, office) is None  # noqa: SLF001


def notify_contact(db: Session, office: Office, req: BookingRequest, event: str) -> dict:
    """SMS (consented + configured + not quiet hours) else e-mail. Stamps the
    row with the channel used. Returns ``{sent, channel, reason}``."""
    if event not in CONTACT_EVENTS:
        return {"sent": False, "channel": None, "reason": "unsupported_event"}
    subject, body = contact_message(office, req, event)

    to_phone = normalize_e164(req.phone) if req.phone else None
    sms_reason: str | None = None
    if not req.consent_accepted:
        sms_reason = "no_consent"
    elif to_phone is None:
        sms_reason = "bad_phone"
    elif not ringcentral_client.is_configured():
        sms_reason = "not_configured"
    elif not _sms_allowed_now(db, office):
        sms_reason = "quiet_hours"
    else:
        sender = sms_service.resolve_sender(db, office.tenant_id, office.id)
        try:
            ringcentral_client.send_message(
                to=to_phone, body=body,
                from_phone=sender.get("from_phone"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("AppointNow contact SMS failed req=%s: %s", req.id, exc)
            sms_reason = "send_failed"
        else:
            _stamp(db, req, "sms")
            return {"sent": True, "channel": "sms", "reason": None}

    if req.email:
        if not sendgrid_client.is_configured():
            logger.info("AppointNow contact e-mail (log-only) req=%s to=%s event=%s (sms: %s)",
                        req.id, req.email, event, sms_reason)
            return {"sent": False, "channel": "email", "reason": "not_configured"}
        try:
            sendgrid_client.send_mail(
                to_email=req.email, subject=subject, body_html=None, body_text=body,
                from_name=_office_label(office),
                custom_args={"appointnow_request_id": req.id, "kind": f"contact_{event}"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("AppointNow contact e-mail failed req=%s: %s", req.id, exc)
            return {"sent": False, "channel": "email", "reason": "send_failed"}
        _stamp(db, req, "email")
        return {"sent": True, "channel": "email", "reason": None}

    logger.info("AppointNow contact notification skipped req=%s event=%s (sms: %s, no e-mail)",
                req.id, event, sms_reason)
    return {"sent": False, "channel": None, "reason": sms_reason or "no_channel"}


def _stamp(db: Session, req: BookingRequest, channel: str) -> None:
    req.contact_notified_at = datetime.now(UTC).replace(tzinfo=None)
    req.contact_notified_via = channel
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("AppointNow notification stamp failed req=%s: %s", req.id, exc)
        db.rollback()
