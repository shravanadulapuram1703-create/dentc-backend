"""Scheduling domain models.

appointments · appointment_procedures · labs
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class Lab(Base, IntPKMixin, TimestampMixin):
    """LAB-1: the dental-lab vendor catalog behind Lab Tracking's "Lab" column.

    A lab case is an appointment with lab fields (there is no lab-case row), and
    until now the appointment could not say *which* lab the case went to — the
    only free-text lab identity column is ``lab_dds``, the dentist. This is the
    picker's source and what the cost report groups by. Tenant-scoped, with an
    optional home office (NULL = every office); the appointment references it
    by FK (``appointments.lab_vendor_id``), never by name, so a renamed vendor
    keeps its history.
    """

    __tablename__ = "labs"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    name: Mapped[str] = mapped_column(String(200), index=True)
    # Optional short code (legacy lab slips carry one); free text.
    code: Mapped[str | None] = mapped_column(String(50))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    fax: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    # Default turnaround the FE can use to pre-fill "Due On" from "Sent On".
    default_turnaround_days: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    operatory_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("operatories.id"))
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20), index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    duration: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="Scheduled")
    is_missed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_posted: Mapped[bool] = mapped_column(Boolean, default=False)
    procedure_label: Mapped[str | None] = mapped_column(String(200))
    is_new_patient: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    has_lab: Mapped[bool] = mapped_column(Boolean, default=False)
    lab_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # APPT-5: the LAB section's "DDS" input — the dentist the lab case is for.
    # Free text rather than a providers FK: legacy lab slips carry initials or an
    # outside dentist's name, neither of which resolves to a provider row.
    lab_dds: Mapped[str | None] = mapped_column(String(100))
    # LAB-1: which lab the case went to (FK into the ``labs`` catalog). Distinct
    # from ``lab_dds`` on purpose — that column is the *dentist*, this the vendor.
    lab_vendor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("labs.id"), index=True)
    # LAB-1: legacy "Short Notice" flag — the case is a rush job.
    lab_short_notice: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    lab_sent_on: Mapped[date | None]
    lab_due_on: Mapped[date | None]
    lab_received_on: Mapped[date | None]
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    campaign_id: Mapped[str | None] = mapped_column(String(100))
    treatment_plan_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("treatment_plans.id"))
    confirmed_on: Mapped[datetime | None]
    checked_in_on: Mapped[datetime | None]
    checked_out_on: Mapped[datetime | None]
    # SCHED G8: when the appointment was posted to the ledger (paired with is_posted).
    posted_on: Mapped[datetime | None]
    # SCHED G3: cancellation metadata captured by the Cancel dialog (M03 p.16).
    cancellation_note: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(String(50))
    add_to_call_list: Mapped[bool] = mapped_column(Boolean, default=False)
    # SCHED G5: who created / last modified (pop-out attribution).
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class AppointmentProcedure(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "appointment_procedures"

    appointment_id: Mapped[str] = mapped_column(String(50), ForeignKey("appointments.id"), index=True)
    procedure_code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    treatment_plan_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("treatment_plans.id"))
    # PLAN-APPT-2: the *item* this line books (the plan id alone cannot tell two
    # identical open items apart). Setting it is what flips the item to
    # ``scheduled``; archiving the line / cancelling the appointment releases it.
    treatment_plan_item_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("treatment_plan_items.id"), index=True
    )
    tooth: Mapped[str | None] = mapped_column(String(10))
    surface: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(String(500))
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    insurance_estimate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    # SCHED G6: patient portion per line (COB-aware when set; else derived on read).
    est_patient: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    billing_order: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="Planned")
    # APPT-PROC-1: per-line chair time. Nullable so "not set" stays distinct from
    # "zero minutes" — Calc Time falls back to procedure_codes.default_duration_minutes.
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    # APPT-PROC-2: legacy "P. Units" — how many provider units the line consumes.
    provider_units: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # APPT-PROC-3: billing intent for the line — "P" patient / "I" insurance.
    bill_to: Mapped[str | None] = mapped_column(String(1))
    material_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chart_materials.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
