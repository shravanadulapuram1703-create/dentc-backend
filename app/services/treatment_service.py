"""Treatment-plan business logic: roll up item-level fees into a plan summary."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import Patient, TreatmentPlan, TreatmentPlanItem
from app.schemas.treatment import TreatmentPlanSummary


def plan_summary(db: Session, plan_id: str, tenant_id: int) -> TreatmentPlanSummary:
    plan = db.get(TreatmentPlan, plan_id)
    if plan is None:
        raise NotFoundError(f"TreatmentPlan '{plan_id}' was not found")
    patient = db.get(Patient, plan.patient_id)
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError(f"TreatmentPlan '{plan_id}' was not found")

    items = db.execute(
        select(TreatmentPlanItem).where(TreatmentPlanItem.plan_id == plan_id)
    ).scalars().all()

    total_fee = sum((i.fee for i in items), Decimal("0"))
    total_ins = sum((i.insurance_estimate for i in items), Decimal("0"))
    return TreatmentPlanSummary(
        plan_id=plan.id,
        name=plan.name,
        status=plan.status,
        item_count=len(items),
        total_fee=total_fee,
        total_insurance_estimate=total_ins,
        total_patient_estimate=total_fee - total_ins,
    )
