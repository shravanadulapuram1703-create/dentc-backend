"""Treatment-planning domain models.

treatment_plans · treatment_plan_items · treatment_plan_item_icd_codes ·
treatment_plan_insurance_details
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class TreatmentPlan(Base, TimestampMixin):
    __tablename__ = "treatment_plans"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="Active")
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class TreatmentPlanItem(Base, TimestampMixin):
    __tablename__ = "treatment_plan_items"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(50), ForeignKey("treatment_plans.id"), index=True)
    procedure_code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    description: Mapped[str | None] = mapped_column(String(500))
    tooth: Mapped[str | None] = mapped_column(String(10))
    surface: Mapped[str | None] = mapped_column(String(50))
    # PROC-INT-5: mirror patient_procedures — a planned quadrant / lab procedure
    # used to lose the quadrant and material chosen in ADD PROCEDURE DETAILS until
    # it was posted. A charge posted from the item adopts both.
    quadrant: Mapped[str | None] = mapped_column(String(10))
    material_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chart_materials.id"))
    priority: Mapped[int] = mapped_column(Integer, default=1)
    # PLAN-1: first-class Phase ID (was stop-gapped into billing_order, freeing it
    # to mean billing order again).
    phase_id: Mapped[int | None] = mapped_column(Integer)
    fee: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    insurance_estimate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    # PLAN-10: optional planned discount on the line.
    discount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    billing_order: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="diagnosed")
    diagnosed_by: Mapped[str | None] = mapped_column(String(200))
    # PLAN-5: dedicated performing provider (distinct from diagnosed_by).
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    # PLAN-2: editable clinical dates (created_at is no longer overloaded as Diag Date).
    diagnosed_date: Mapped[date | None]
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    # PLAN-14: soft-delete parity with patient_procedures / chart_conditions. Also
    # resolves PLAN-13 (a soft-deleted item keeps its FK so insurance-details never
    # block the delete).
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    # ── Edit Treatment window (PLAN-17/18/19/25/27/28/29, PLAN-11) ────────────
    # PLAN-17: the legacy NOTES box. Lives on the item, not on the insurance
    # detail row — an uninsured patient's note had been forcing an empty
    # insurance row into existence just to hold text.
    notes: Mapped[str | None] = mapped_column(Text)
    # PLAN-18: when the procedure was accepted / scheduled. ``accepted_date`` is
    # stamped the first time the status becomes ``accepted`` unless supplied;
    # ``scheduled_date`` follows the appointment the item is booked on.
    accepted_date: Mapped[date | None]
    scheduled_date: Mapped[date | None]
    # PLAN-19 / PLAN-APPT-7: per-item chair time, overriding the code's
    # ``default_duration_minutes``. Nullable so "unset" stays distinct from 0.
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    # PLAN-25: Created By / Modified By as users (stamped by the CRUD engine).
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # PLAN-27: "Referral Type" / "Referring Dentist" on the procedure.
    referral_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("referrals.id"))
    referral_type: Mapped[str | None] = mapped_column(String(20))
    # PLAN-28: posting flags honoured by POST /treatment-plan-items/{id}/post.
    update_end_date_at_posting: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    re_estimate_at_posting: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # PLAN-29: which fee schedule priced ``fee`` (stamped at create / re-estimate
    # when the server resolved it; a client may also state it).
    fee_schedule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("fee_schedules.id"))
    # PLAN-11: the Treatment Counselor who presented / owns the case for this line.
    counselor_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # PLAN-APPT-1: the status the item held before it was booked, so cancelling /
    # deleting the appointment can put it back exactly where it was.
    status_before_scheduled: Mapped[str | None] = mapped_column(String(20))


class TreatmentPlanItemIcdCode(Base, IntPKMixin, CreatedAtMixin):
    """PLAN-26: item <-> ICD-10 diagnosis link ("Dental Cross Coding Information")."""

    __tablename__ = "treatment_plan_item_icd_codes"
    __table_args__ = (
        UniqueConstraint("plan_item_id", "icd_code_id", name="uq_treatment_plan_item_icd_code"),
    )

    plan_item_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("treatment_plan_items.id", ondelete="CASCADE"), index=True
    )
    icd_code_id: Mapped[int] = mapped_column(Integer, ForeignKey("icd_codes.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=1)


class TreatmentPlanInsuranceDetail(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "treatment_plan_insurance_details"

    plan_item_id: Mapped[str] = mapped_column(String(50), ForeignKey("treatment_plan_items.id"), index=True)
    ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    billing_order: Mapped[str | None] = mapped_column(String(10))
    estimated_ins: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    estimated_pat: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    deductible: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    coverage_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    annual_max_rem: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    preauth_number: Mapped[str | None] = mapped_column(String(100))
    preauth_date: Mapped[date | None]
    preauth_expires: Mapped[date | None]
    preauth_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # PLAN-9: the Pre Auth Status radios (Sent / Closed). ``preauth_status_at`` is
    # server-stamped whenever the status moves.
    preauth_status: Mapped[str | None] = mapped_column(String(20))
    preauth_status_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
