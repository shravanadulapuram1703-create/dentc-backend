"""Treatment-planning domain models.

treatment_plans · treatment_plan_items
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
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
    notes: Mapped[str | None] = mapped_column(Text)
