"""AppointNow — external online booking models.

Two tables back the public booking surface + staff request inbox:

- ``appointnow_reasons``  N per office — customisable reason catalog (id → chair
  time). When an office has no rows the service serves a built-in default catalog
  so a fresh office still books (the frontend's ``APPOINTMENT_REASONS`` fallback).
- ``booking_requests``    the public intake queue (pending → approved / declined /
  expired).

``booking_requests`` carries a **UUIDv7 string PK** so the staff inbox can page
chronologically by id (byte-order == time-order, same trick as messaging), and a
soft-hold (``hold_expires_at``) so two visitors can't grab the same slot at once
(AN-8). Tenant + office are stored **directly** rather than resolved from a JWT —
the public intake path is anonymous and resolves the tenant from ``office_code``.

Suggested indexes (AN-13): ``(tenant_id, office_id, status, created_at)`` for the
inbox/badge and ``(tenant_id, office_id, slot_date)`` for availability sweeps.
"""

from __future__ import annotations

from datetime import date, datetime, time

from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPKMixin, TimestampMixin


class AppointNowReason(Base, IntPKMixin, TimestampMixin):
    """Per-office booking-reason catalog (drives chair-time duration)."""

    __tablename__ = "appointnow_reasons"
    __table_args__ = (
        UniqueConstraint("office_id", "reason_code", name="uq_appointnow_reasons_office_code"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    # Stable id sent on the wire (SubmitRequestInput.reason_id / AppointmentReason.id).
    reason_code: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(200))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    # When true, the reason can only be booked against a specific provider.
    requires_provider: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # AN-27: per-reason payment requirement. NULL = inherit the office setting
    # (``offices.appointnow_requires_payment`` / ``_payment_amount``), so a
    # practice can require a deposit only for, say, a new-patient exam.
    requires_payment: Mapped[bool | None] = mapped_column(Boolean)
    payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))


class BookingRequest(Base, TimestampMixin):
    """A public booking request awaiting staff approval."""

    __tablename__ = "booking_requests"
    __table_args__ = (
        # AN-13: inbox/badge listing scoped by office+status, newest first.
        Index("ix_booking_requests_office_status", "tenant_id", "office_id", "status", "created_at"),
        # AN-8/AN-13: availability + expiry sweeps by requested slot date.
        Index("ix_booking_requests_office_slot", "tenant_id", "office_id", "slot_date"),
    )

    # UUIDv7 string — time-sortable, so the inbox pages by id without a secondary key.
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    # pending | awaiting_payment (AN-27) | approved | declined | expired
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # ── reason ───────────────────────────────────────────────────────────────
    reason_id: Mapped[str | None] = mapped_column(String(50))
    reason_label: Mapped[str | None] = mapped_column(String(200))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)

    # ── requested slot ───────────────────────────────────────────────────────
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    provider_name: Mapped[str | None] = mapped_column(String(255))
    slot_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    # AN-28: the chair the patient picked (null = any / emergency).
    operatory_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("operatories.id"))
    # AN-29: emergency requests skip the open-slot check; the time is a preference.
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # ── contact (external patient, not yet a PMS patient) ────────────────────
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    is_new_patient: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    # AN-16: the intake acknowledgements are legal text the patient ticked
    # (``BOOKING_DISCLAIMER_TEXT`` / ``BOOKING_CONSENT_TEXT`` on the public page)
    # and must be auditable as *columns* — the frontend had been folding them
    # into ``notes`` because ``ContactInput`` silently dropped them.
    insurance_info: Mapped[str | None] = mapped_column(String(500))
    disclaimer_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    # AN-26: the third acknowledgement (``BOOKING_PAYMENT_TEXT``). NULL on rows
    # created before the question existed — "not asked", never "refused".
    payment_terms_accepted: Mapped[bool | None] = mapped_column(Boolean)
    # AN-26: proof of *which wording* was agreed to. ``{"disclaimer": sha256,
    # "consent": sha256, "payment": sha256}`` over the exact text shown; each
    # text is kept once in ``booking_acknowledgement_texts``. ``version`` is the
    # client's own label for the wording set; ``acknowledged_at`` the server time.
    acknowledgement_hashes: Mapped[dict | None] = mapped_column(JSON)
    acknowledgement_version: Mapped[str | None] = mapped_column(String(50))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)

    # ── reschedule (AN-14) ───────────────────────────────────────────────────
    # The slot the PATIENT first asked for, set on the first staff reschedule
    # only (``slot_*`` then holds the new time). Null = never rescheduled.
    original_slot_date: Mapped[date | None] = mapped_column(Date)
    original_start_time: Mapped[time | None] = mapped_column(Time)
    original_end_time: Mapped[time | None] = mapped_column(Time)
    original_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    original_provider_id: Mapped[str | None] = mapped_column(String(50))
    original_provider_name: Mapped[str | None] = mapped_column(String(255))
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)
    rescheduled_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    rescheduled_at: Mapped[datetime | None] = mapped_column(DateTime)

    # AN-21: last outbound notification to the *contact* (approve/decline/
    # reschedule). ``via`` is ``sms`` | ``email``; null = nothing was sent.
    contact_notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    contact_notified_via: Mapped[str | None] = mapped_column(String(10))

    # ── hold / lifecycle ─────────────────────────────────────────────────────
    # AN-8: while > now, the slot is locked against concurrent requests.
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Set on approve (AN-5): the real appointment booked into the scheduler.
    appointment_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("appointments.id"))
    # AN-9: matched/created patient on approve (null while carried in the label/notes).
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"))
    decline_reason: Mapped[str | None] = mapped_column(Text)
    actioned_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Abuse audit only (never returned on the public read).
    source_ip: Mapped[str | None] = mapped_column(String(64))
    # AN-27.6: sha256 of the patient's status token (the token itself is shown
    # once, on the public submit response, and never stored).
    status_token_hash: Mapped[str | None] = mapped_column(String(64))

    # ── payment (AN-27) ──────────────────────────────────────────────────────
    # Snapshotted from reason → office config at intake, so a later Setup change
    # does not re-price a request the patient already saw.
    requires_payment: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_false()
    )
    # not_required | required | link_sent | paid | expired | refunded
    payment_status: Mapped[str] = mapped_column(
        String(20), default="not_required", server_default="not_required"
    )
    payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    payment_currency: Mapped[str | None] = mapped_column(String(3))
    payment_provider: Mapped[str | None] = mapped_column(String(20))  # stripe | manual
    payment_link_id: Mapped[str | None] = mapped_column(String(255), index=True)
    payment_link_url: Mapped[str | None] = mapped_column(Text)
    payment_link_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    payment_link_sent_via: Mapped[str | None] = mapped_column(String(10))
    payment_link_expires_at: Mapped[datetime | None] = mapped_column(DateTime)  # UTC
    payment_note: Mapped[str | None] = mapped_column(Text)
    payment_requested_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # What staff chose on "Request payment" for the booking the payment will
    # trigger (provider/operatory/patient — the ApproveInput fields).
    payment_booking: Mapped[dict | None] = mapped_column(JSON)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    payment_reference: Mapped[str | None] = mapped_column(String(255))
    payment_method: Mapped[str | None] = mapped_column(String(50))
    # The ledger credit, once a patient is linked. NULL while paid = unapplied
    # (the contact is not a PMS patient yet).
    ledger_payment_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("patient_payments.id"))
    # Set when the post-payment auto-booking could not complete (slot taken
    # meanwhile) — staff then approve by hand; the money is never lost.
    booking_error: Mapped[str | None] = mapped_column(String(500))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime)
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    refund_reference: Mapped[str | None] = mapped_column(String(255))
    refund_reason: Mapped[str | None] = mapped_column(Text)
    refunded_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class BookingAcknowledgementText(Base):
    """AN-26: every distinct acknowledgement wording a patient agreed to, kept
    once and keyed by its sha256 — ``booking_requests.acknowledgement_hashes``
    points here, so the office can reproduce the exact text years later even
    after the public page's copy has changed."""

    __tablename__ = "booking_acknowledgement_texts"

    text_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # disclaimer | consent | payment
    text: Mapped[str] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(String(50))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
