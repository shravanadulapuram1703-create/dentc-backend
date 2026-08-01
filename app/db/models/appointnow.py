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

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
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
    # pending | approved | declined | expired
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

    # ── contact (external patient, not yet a PMS patient) ────────────────────
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    is_new_patient: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

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
