"""Scheduling domain models.

appointments · appointment_procedures
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


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
    tooth: Mapped[str | None] = mapped_column(String(10))
    surface: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(String(500))
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    insurance_estimate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    # SCHED G6: patient portion per line (COB-aware when set; else derived on read).
    est_patient: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    billing_order: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="Planned")
    material_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chart_materials.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
