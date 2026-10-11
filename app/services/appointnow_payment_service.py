"""AppointNow payment-required confirmation flow (AN-27).

The public page promises "if payment is required, the office will send me a
secure payment link, and my appointment will be confirmed only after the
payment has been completed" (AN-26). This module is the behaviour behind that
sentence:

``pending`` ──request-payment──▶ ``awaiting_payment`` ──paid──▶ ``approved``
                                        │                    (books atomically,
                                        │                     AN-5 path)
                                        └──link lapses──▶ ``expired``

* **Config** (AN-27.1) — ``offices.appointnow_requires_payment`` /
  ``_payment_amount``, overridable per ``appointnow_reasons`` row; snapshotted
  onto the request at intake (``requires_payment`` / ``payment_amount``).
* **Request payment** (AN-27.3) — staff send a link (Stripe Checkout when
  ``STRIPE_SECRET_KEY`` is set, otherwise provider ``manual``: no hosted link,
  the patient is told the office will collect, and staff record it with
  ``mark-paid``). The soft-hold is extended to the link's life.
* **Paid** (AN-27.4) — the signed Stripe webhook (or ``mark-paid``) records
  the money **first, in its own commit**, then books through
  :func:`appointnow_service.book_request` inside a savepoint. A booking that
  cannot complete (slot taken meanwhile) leaves the request ``awaiting_payment``
  with ``payment_status='paid'`` and a ``booking_error`` for staff — money is
  never lost to a rollback. The payment is posted to the patient ledger as soon
  as a patient is linked; until then it is *unapplied* on the request.
* **Expiry** (AN-27.5) — the sweep in ``expire_stale_requests`` lapses an
  unpaid link, releases the hold and notifies the patient.
* **Status** (AN-27.6) — token-protected public read.
* **Refund** (AN-27.7) — admin; Stripe refund when it was a Stripe payment,
  plus the ledger counterpart (REF-1/2) when it had been posted. The
  cancellation / refund *policy* (who qualifies, how late) is a product call;
  the endpoint executes whatever staff decide.
"""

from __future__ import annotations

import hmac
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.core.logging import get_logger
from app.db.models import BookingRequest, Office, PatientPayment
from app.integrations import redis_store, stripe_client
from app.services import appointnow_service as an

logger = get_logger(__name__)

PAYMENT_STATUSES = ("not_required", "required", "link_sent", "paid", "expired", "refunded")
_STRIPE_PAID_EVENTS = ("checkout.session.completed", "checkout.session.async_payment_succeeded")
_STRIPE_LAPSED_EVENTS = ("checkout.session.expired", "checkout.session.async_payment_failed")


def _utcnow() -> datetime:
    return datetime.utcnow()


def _office(db: Session, req: BookingRequest) -> Office:
    office = db.get(Office, req.office_id)
    if office is None:
        raise NotFoundError("The request's office no longer exists")
    return office


class _Booking:
    """ApproveInput-shaped steering for :func:`an.book_request`."""

    def __init__(self, options: dict | None) -> None:
        options = options or {}
        self.patient_id = options.get("patient_id")
        self.create_patient = bool(options.get("create_patient"))
        self.provider_id = options.get("provider_id")
        self.operatory_id = options.get("operatory_id")
        self.appointment_id = None
        self.waive_payment = False


# ── helpers shared with appointnow_service ───────────────────────────────────
def close_open_link(req: BookingRequest) -> None:
    """Kill an open link so it cannot be paid after the request moved on (a
    re-sent link, a decline, a waived approval). Best-effort on the Stripe
    side; the row is marked ``expired`` either way."""
    if req.payment_provider == "stripe" and req.payment_link_id and stripe_client.is_configured():
        try:
            stripe_client.expire_checkout_session(req.payment_link_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AppointNow: could not expire Stripe session %s: %s", req.payment_link_id, exc)
    if req.payment_status == "link_sent":
        req.payment_status = "expired"


def post_payment_to_ledger(
    db: Session, office: Office, req: BookingRequest, *, actor_id: int | None
) -> PatientPayment | None:
    """Post the recorded payment as a patient-ledger credit once a patient is
    linked (idempotent — ``ledger_payment_id`` set once). No commit."""
    if (
        req.payment_status != "paid"
        or req.patient_id is None
        or req.ledger_payment_id is not None
        or not req.paid_amount
    ):
        return None
    payment = PatientPayment(
        id=f"AN-{uuid7()}",
        patient_id=req.patient_id,
        office_id=office.id,
        created_office_id=office.id,
        payment_date=_to_office_date(office, req.paid_at or _utcnow()),
        amount=Decimal(req.paid_amount),  # app convention: positive magnitude (AL-9)
        payment_type="patient",
        payment_method=req.payment_method or "credit_card",
        notes=(
            f"AppointNow online payment for request {req.id}"
            + (f" (ref {req.payment_reference})" if req.payment_reference else "")
        ),
        created_by=actor_id,
    )
    db.add(payment)
    db.flush()  # ledger_payment_id is an FK with no relationship() edge
    req.ledger_payment_id = payment.id
    redis_store.cache_delete(f"balance:{office.tenant_id}:{req.patient_id}")
    return payment


def _to_office_date(office: Office, utc_naive: datetime):  # noqa: ANN202
    from datetime import UTC

    return utc_naive.replace(tzinfo=UTC).astimezone(an._office_tz(office)).date()  # noqa: SLF001


def _validate_booking_options(db: Session, office: Office, req: BookingRequest, options) -> dict | None:
    """Fail fast on a bad provider/chair/patient at request time, not hours
    later inside the webhook."""
    if options is None:
        return None
    data = options.model_dump()
    an._resolve_provider_for_booking(db, office, req, data.get("provider_id"))  # noqa: SLF001
    if data.get("operatory_id"):
        an._resolve_operatory_for_booking(db, office, None, data["operatory_id"])  # noqa: SLF001
    if data.get("patient_id") is not None:
        from app.db.models import Patient

        p = db.get(Patient, data["patient_id"])
        if p is None or p.tenant_id != office.tenant_id:
            raise ValidationError("Selected patient is not valid", code="bad_patient")
    return data


# ── AN-27.3: request payment ─────────────────────────────────────────────────
def _return_url(office: Office, req: BookingRequest, result: str) -> str:
    template = settings.APPOINTNOW_PAYMENT_RETURN_URL
    if not template:
        raise AppError(
            "APPOINTNOW_PAYMENT_RETURN_URL is not configured; Stripe needs a page to "
            "send the patient back to.",
            code="payment_return_url_missing", status_code=503,
        )
    return (
        template.replace("{office_code}", office.office_code or "")
        .replace("{request_id}", req.id)
        .replace("{result}", result)
    )


def request_payment(
    db: Session, tenant_id: int, request_id: str, body, *, actor_id: int | None
) -> BookingRequest:
    req = an.get_request(db, tenant_id, request_id)
    if req.status not in an.HOLDING_STATUSES:
        raise ConflictError(f"Request is already {req.status}", code="request_not_pending")
    if req.payment_status in ("paid", "refunded"):
        raise ConflictError(f"Payment is already {req.payment_status}", code="payment_already_settled")
    office = _office(db, req)

    amount = body.amount if body.amount is not None else req.payment_amount
    if amount is None or Decimal(amount) <= 0:
        raise ValidationError(
            "No payment amount: pass amount, or configure one on the office / reason.",
            code="payment_amount_required",
        )
    booking = _validate_booking_options(db, office, req, body.booking)
    ttl = body.expires_in_minutes or settings.APPOINTNOW_PAYMENT_LINK_TTL_MINUTES
    ttl = max(30, min(int(ttl), 1440))  # Stripe Checkout's accepted window
    now = _utcnow()
    expires_utc = now + timedelta(minutes=ttl)
    currency = (req.payment_currency or settings.APPOINTNOW_PAYMENT_CURRENCY).lower()

    if req.payment_status == "link_sent":
        close_open_link(req)  # a re-send must not leave the old link payable

    link_id = link_url = None
    provider = "manual"
    if stripe_client.is_configured():
        provider = "stripe"
        name = " ".join(x for x in (req.first_name, req.last_name) if x)
        try:
            session = stripe_client.create_checkout_session(
                amount=Decimal(amount),
                currency=currency,
                description=(
                    f"{office.name or office.office_code} - "
                    f"{req.reason_label or 'Appointment'} on {req.slot_date:%b %d, %Y}"
                    + (f" ({name})" if name else "")
                ),
                success_url=_return_url(office, req, "success"),
                cancel_url=_return_url(office, req, "cancel"),
                expires_at=int((expires_utc - datetime(1970, 1, 1)).total_seconds()),
                metadata={
                    "appointnow_request_id": req.id,
                    "tenant_id": str(tenant_id),
                    "office_id": str(office.id),
                },
                customer_email=req.email,
                idempotency_key=f"an-pay-{req.id}-{uuid7().hex[:12]}",
            )
        except stripe_client.StripeError as exc:
            raise AppError(
                f"The payment provider refused the link: {exc.message}",
                code="payment_provider_error", status_code=502,
                details={"provider_code": exc.code},
            ) from exc
        link_id, link_url = session.get("id"), session.get("url")

    req.status = "awaiting_payment"
    req.requires_payment = True
    req.payment_status = "link_sent"
    req.payment_amount = Decimal(amount)
    req.payment_currency = currency
    req.payment_provider = provider
    req.payment_link_id = link_id
    req.payment_link_url = link_url
    req.payment_link_sent_at = now
    req.payment_link_sent_via = None
    req.payment_link_expires_at = expires_utc
    req.payment_note = body.note
    req.payment_requested_by = actor_id
    if booking is not None:
        req.payment_booking = booking
    req.booking_error = None
    # Hold the slot for as long as the link can be paid (office-local naive).
    req.hold_expires_at = an._office_now(office) + timedelta(minutes=ttl)  # noqa: SLF001
    req.updated_at = now
    db.commit()
    db.refresh(req)
    an._invalidate_availability_cache(office.id, req.slot_date)  # noqa: SLF001
    an.notify_updated_request(db, office, req)

    result = _notify(db, office, req, "payment_requested")
    if result.get("sent"):
        req.payment_link_sent_via = result.get("channel")
        db.commit()
        db.refresh(req)
    return req


def _notify(db: Session, office: Office, req: BookingRequest, event: str) -> dict:
    try:
        from app.services import appointnow_notification_service as notify

        return notify.notify_contact(db, office, req, event)
    except Exception as exc:  # noqa: BLE001 - a notification never undoes a transition
        logger.warning("AppointNow payment notification skipped (%s): %s", event, exc)
        return {"sent": False}


# ── AN-27.4: payment recorded → book ─────────────────────────────────────────
def _record_paid(
    req: BookingRequest, *, amount: Decimal, reference: str | None, method: str | None,
    provider: str,
) -> None:
    req.payment_status = "paid"
    req.requires_payment = True
    req.paid_at = _utcnow()
    req.paid_amount = Decimal(amount)
    req.payment_reference = reference
    req.payment_method = method or "credit_card"
    req.payment_provider = provider
    req.payment_currency = req.payment_currency or settings.APPOINTNOW_PAYMENT_CURRENCY
    req.updated_at = _utcnow()


def _settle_paid(
    db: Session, office: Office, req: BookingRequest, *, actor_id: int | None, options: dict | None
) -> bool:
    """Book a just-paid request inside a savepoint. The payment is already
    committed, so a refused booking only records ``booking_error``."""
    if req.status != "awaiting_payment" and req.status != "pending":
        req.booking_error = (
            f"Payment received after the request was {req.status}; rebook or refund it."
        )
        db.commit()
        return False
    nested = db.begin_nested()
    try:
        an.book_request(db, office, req, _Booking(options or req.payment_booking), actor_id=actor_id)
        if nested.is_active:  # a patient create inside may already have committed
            nested.commit()
    except AppError as exc:
        if nested.is_active:
            nested.rollback()
        else:
            db.rollback()
        db.refresh(req)
        req.booking_error = f"{exc.code}: {exc.message}"[:500]
        db.commit()
        logger.warning("AppointNow paid request %s could not auto-book: %s", req.id, exc.message)
        return False
    db.commit()
    return True


def _after_paid(db: Session, office: Office, req: BookingRequest, booked: bool) -> None:
    db.refresh(req)
    an._invalidate_availability_cache(office.id, req.slot_date)  # noqa: SLF001
    an.notify_updated_request(db, office, req)
    if booked:
        an._notify_contact(db, office, req, "approved")  # noqa: SLF001


def mark_paid(
    db: Session, tenant_id: int, request_id: str, body, *, actor_id: int | None
) -> BookingRequest:
    """Staff record a payment taken outside the link (phone / terminal), then —
    by default — book it the same way the webhook would."""
    req = an.get_request(db, tenant_id, request_id)
    if req.status not in an.HOLDING_STATUSES:
        raise ConflictError(f"Request is already {req.status}", code="request_not_pending")
    if req.payment_status in ("paid", "refunded"):
        raise ConflictError(f"Payment is already {req.payment_status}", code="payment_already_settled")
    office = _office(db, req)
    amount = body.amount if body.amount is not None else req.payment_amount
    if amount is None:
        raise ValidationError("Pass the amount collected.", code="payment_amount_required")
    options = _validate_booking_options(db, office, req, body.booking)
    if req.payment_status == "link_sent":
        close_open_link(req)  # collected another way — the link must not take it twice
    _record_paid(req, amount=Decimal(amount), reference=body.reference, method=body.method,
                 provider="manual")
    req.status = "awaiting_payment"
    if options is not None:
        req.payment_booking = options
    if req.payment_requested_by is None:
        req.payment_requested_by = actor_id
    db.commit()
    booked = _settle_paid(db, office, req, actor_id=actor_id, options=options) if body.book else False
    _after_paid(db, office, req, booked)
    return req


# ── Stripe webhook ───────────────────────────────────────────────────────────
def handle_stripe_webhook(db: Session, payload: bytes, signature: str | None) -> dict:
    """Signed Stripe event → paid / lapsed. Unknown events and unknown requests
    are acknowledged (200) so Stripe stops retrying; a bad signature is 400."""
    if not stripe_client.verify_webhook_signature(payload, signature):
        raise AppError("Invalid Stripe signature", code="invalid_signature", status_code=400)
    try:
        event = json.loads(payload.decode("utf-8"))
    except ValueError as exc:
        raise AppError("Malformed event body", code="bad_payload", status_code=400) from exc

    etype = event.get("type") or ""
    obj: dict[str, Any] = ((event.get("data") or {}).get("object")) or {}
    request_id = (obj.get("metadata") or {}).get("appointnow_request_id")
    ack = {"received": True, "handled": False, "request_id": request_id, "detail": None}
    if etype not in _STRIPE_PAID_EVENTS + _STRIPE_LAPSED_EVENTS:
        ack["detail"] = f"ignored event {etype}"
        return ack
    req = db.get(BookingRequest, request_id) if request_id else None
    if req is None:
        ack["detail"] = "no matching request"
        return ack
    office = _office(db, req)
    session_id = obj.get("id")

    if etype in _STRIPE_LAPSED_EVENTS:
        # Only the *current* link lapsing expires the request — a superseded
        # link's expiry event is noise.
        if req.payment_status == "link_sent" and req.payment_link_id == session_id:
            req.payment_status = "expired"
            if req.status == "awaiting_payment":
                req.status = "expired"
                req.hold_expires_at = None
            db.commit()
            db.refresh(req)
            an._invalidate_availability_cache(office.id, req.slot_date)  # noqa: SLF001
            an._publish_event(db, office, "expired", req)  # noqa: SLF001
            _notify(db, office, req, "payment_expired")
            ack["handled"] = True
        else:
            ack["detail"] = "superseded link"
        return ack

    if etype == "checkout.session.completed" and obj.get("payment_status") not in ("paid", "no_payment_required"):
        ack["detail"] = "awaiting async payment"
        return ack
    reference = obj.get("payment_intent") or session_id
    if req.payment_status in ("paid", "refunded"):
        if reference and reference == req.payment_reference:
            ack["detail"] = "duplicate delivery"  # Stripe retries — idempotent
            return ack
        # Real money arriving twice (an old link paid in a race): never drop it.
        req.booking_error = (
            f"Second payment received ({reference}, "
            f"{Decimal(obj.get('amount_total') or 0) / 100}) - refund it in Stripe."
        )[:500]
        db.commit()
        logger.warning("AppointNow request %s received a second payment %s", req.id, reference)
        ack["detail"] = "second payment recorded on booking_error"
        return ack

    amount = Decimal(obj.get("amount_total") or 0) / 100 or (req.payment_amount or Decimal(0))
    _record_paid(req, amount=amount, reference=reference, method="credit_card", provider="stripe")
    if session_id:
        req.payment_link_id = session_id
    db.commit()
    booked = _settle_paid(db, office, req, actor_id=req.payment_requested_by, options=None)
    _after_paid(db, office, req, booked)
    ack["handled"] = True
    ack["detail"] = "booked" if booked else "paid; booking needs staff"
    return ack


# ── AN-27.7: refund ──────────────────────────────────────────────────────────
def refund(
    db: Session, tenant_id: int, request_id: str, body, *, actor_id: int | None,
    actor_role: str | None = None,
) -> BookingRequest:
    from app.services import refund_service

    req = an.get_request(db, tenant_id, request_id)
    if req.payment_status != "paid" or not req.paid_amount:
        raise ConflictError("There is no recorded payment to refund.", code="payment_not_refundable",
                            details={"payment_status": req.payment_status})
    office = _office(db, req)
    amount = Decimal(body.amount) if body.amount is not None else Decimal(req.paid_amount)
    if amount > Decimal(req.paid_amount):
        raise ValidationError("Refund exceeds the amount paid.", code="refund_exceeds_payment",
                              details={"paid_amount": str(req.paid_amount)})
    # The ledger half is policy-checked *before* money moves at the provider.
    if req.ledger_payment_id is not None and amount < Decimal(req.paid_amount):
        policy = refund_service.refund_policy(db, tenant_id, office.id)
        refund_service._enforce_policy(policy, amount, actor_role, has_source=True)  # noqa: SLF001

    reference = None
    if req.payment_provider == "stripe" and req.payment_reference:
        if not stripe_client.is_configured():
            raise AppError("Stripe is not configured; cannot refund a Stripe payment.",
                           code="payment_provider_unavailable", status_code=503)
        try:
            result = stripe_client.create_refund(
                payment_intent=req.payment_reference, amount=amount, reason_note=body.reason,
                idempotency_key=f"an-refund-{req.id}",
            )
        except stripe_client.StripeError as exc:
            raise AppError(f"The payment provider refused the refund: {exc.message}",
                           code="payment_provider_error", status_code=502,
                           details={"provider_code": exc.code}) from exc
        reference = result.get("id")

    req.payment_status = "refunded"
    req.refunded_at = _utcnow()
    req.refund_amount = amount
    req.refund_reference = reference
    req.refund_reason = body.reason
    req.refunded_by = actor_id
    req.booking_error = None
    if req.status == "awaiting_payment":
        # Never booked: the refund ends the request and frees the slot.
        req.status = "declined"
        req.decline_reason = body.reason or "Payment refunded"
        req.actioned_by = actor_id
        req.actioned_at = _utcnow()
        req.hold_expires_at = None
    db.commit()

    if req.ledger_payment_id is not None:
        method = req.payment_method or "credit_card"
        try:
            if amount >= Decimal(req.paid_amount):
                refund_service.reverse_payment(
                    db, req.ledger_payment_id, tenant_id,
                    {"reason": body.reason or f"AppointNow refund {req.id}", "refund_method": method},
                    actor_id=actor_id,
                )
            else:
                refund_service.process_refund(
                    db, req.patient_id, tenant_id,
                    {"refund_amount": amount, "source_payment_id": req.ledger_payment_id,
                     "refund_method": method, "reason": body.reason, "office_id": office.id,
                     "reference_number": reference},
                    actor_id=actor_id, actor_role=actor_role,
                )
        except AppError as exc:
            # The provider refund already happened — say so instead of hiding it.
            req.booking_error = f"Refunded at the provider but not on the ledger: {exc.message}"[:500]
            db.commit()
    db.refresh(req)
    an._invalidate_availability_cache(office.id, req.slot_date)  # noqa: SLF001
    an.notify_updated_request(db, office, req)
    _notify(db, office, req, "refunded")
    return req


# ── AN-27.6: patient-facing status ───────────────────────────────────────────
def public_status(db: Session, request_id: str, token: str | None) -> dict:
    req = db.get(BookingRequest, request_id)
    if (
        req is None
        or not token
        or not req.status_token_hash
        or not hmac.compare_digest(an._text_hash(token), req.status_token_hash)  # noqa: SLF001
    ):
        # 404 for both "no such request" and "wrong token" — never 401 (AN-12),
        # and never a hint that the id exists.
        raise NotFoundError("Booking request not found", code="request_not_found")
    office = db.get(Office, req.office_id)
    if office is None or not office.is_active:
        raise NotFoundError("Booking request not found", code="request_not_found")
    an.expire_stale_requests(db, [office])
    db.refresh(req)
    link_open = (
        req.payment_status == "link_sent"
        and req.payment_link_url
        and (req.payment_link_expires_at is None or req.payment_link_expires_at > _utcnow())
    )
    return {
        "id": req.id,
        "office_name": office.name,
        "office_phone": office.phone,
        "status": req.status,
        "confirmed": req.status == "approved",
        "slot": {
            "date": req.slot_date.strftime("%Y-%m-%d"),
            "start_time": an._fmt_time(req.start_time),  # noqa: SLF001
            "end_time": an._fmt_time(req.end_time),  # noqa: SLF001
            "duration_minutes": req.duration_minutes,
            "provider_id": req.provider_id,
            "provider_name": req.provider_name,
        },
        "reason_label": req.reason_label,
        "payment_required": bool(req.requires_payment),
        "payment_status": req.payment_status or "not_required",
        "payment_amount": req.payment_amount,
        "payment_currency": req.payment_currency,
        "payment_link_url": req.payment_link_url if link_open else None,
        "payment_link_expires_at": req.payment_link_expires_at if link_open else None,
        "paid_at": req.paid_at,
    }

