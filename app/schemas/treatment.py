"""Treatment-plan schemas (service summary + the dev-report customisations).

Custom item Create/Update/Read (single source, imported by the registry) add the
new fields (PLAN-1 ``phase_id``, PLAN-2 dates, PLAN-5 ``provider_id``, PLAN-10
``discount``, PLAN-14 ``is_archived``) and a server-side status enum. Plus the
re-estimate (PLAN-3) and report (PLAN-6) response shapes.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.common import ORMModel

# Canonical item statuses (legacy D/A/U/H/Alt/RO). Server-side enum (report §LOW).
ItemStatus = Literal[
    "diagnosed", "accepted", "unaccepted", "hold", "alternative", "referred_out"
]


class TreatmentPlanSummary(BaseModel):
    plan_id: str
    name: str
    status: str
    item_count: int
    total_fee: Decimal
    total_insurance_estimate: Decimal
    total_patient_estimate: Decimal


# ── Treatment-plan item (custom over the factory) ────────────────────────────
class TreatmentPlanItemCreate(BaseModel):
    id: str
    plan_id: str
    procedure_code: str
    fee: Decimal
    description: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    priority: Optional[int] = None
    phase_id: Optional[int] = None  # PLAN-1
    insurance_estimate: Optional[Decimal] = None
    discount: Optional[Decimal] = None  # PLAN-10
    billing_order: Optional[str] = None
    status: Optional[ItemStatus] = None
    diagnosed_by: Optional[str] = None
    provider_id: Optional[str] = None  # PLAN-5
    diagnosed_date: Optional[date] = None  # PLAN-2
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class TreatmentPlanItemUpdate(BaseModel):
    plan_id: Optional[str] = None  # re-parent (Change IDs → Tx Plan)
    procedure_code: Optional[str] = None
    fee: Optional[Decimal] = None
    description: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    priority: Optional[int] = None
    phase_id: Optional[int] = None
    insurance_estimate: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    billing_order: Optional[str] = None
    status: Optional[ItemStatus] = None
    diagnosed_by: Optional[str] = None
    provider_id: Optional[str] = None
    diagnosed_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_archived: Optional[bool] = None


class TreatmentPlanItemRead(ORMModel):
    id: str
    plan_id: str
    procedure_code: str
    description: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    priority: int
    phase_id: Optional[int] = None
    fee: Decimal
    insurance_estimate: Decimal
    discount: Optional[Decimal] = None
    billing_order: Optional[str] = None
    status: str
    diagnosed_by: Optional[str] = None
    provider_id: Optional[str] = None
    diagnosed_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_archived: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


# ── PLAN-3: insurance re-estimate ────────────────────────────────────────────
class ReEstimateLine(BaseModel):
    item_id: str
    procedure_code: str
    fee: Decimal
    coverage_pct: Decimal
    deductible_applied: Decimal
    insurance_estimate: Decimal
    patient_estimate: Decimal


class ReEstimateResult(BaseModel):
    plan_id: str
    insured: bool
    ins_plan_id: Optional[int] = None
    phase_id: Optional[int] = None
    deductible_remaining_after: Optional[Decimal] = None
    annual_max_remaining_after: Optional[Decimal] = None
    total_fee: Decimal
    total_insurance_estimate: Decimal
    total_patient_estimate: Decimal
    lines: list[ReEstimateLine]


# ── PLAN-6: server-side report payload ───────────────────────────────────────
class PlanReportPatient(BaseModel):
    id: int
    chart_no: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[date] = None


class PlanReportItem(BaseModel):
    id: str
    procedure_code: str
    description: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    priority: int
    phase_id: Optional[int] = None
    status: str
    fee: Decimal
    discount: Optional[Decimal] = None
    insurance_estimate: Decimal
    patient_estimate: Decimal
    diagnosed_by: Optional[str] = None
    provider_id: Optional[str] = None
    diagnosed_date: Optional[date] = None


class TreatmentPlanReport(BaseModel):
    plan_id: str
    name: str
    status: str
    patient: PlanReportPatient
    item_count: int
    total_fee: Decimal
    total_discount: Decimal
    total_insurance_estimate: Decimal
    total_patient_estimate: Decimal
    items: list[PlanReportItem]
