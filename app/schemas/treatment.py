"""Treatment-plan service schemas."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class TreatmentPlanSummary(BaseModel):
    plan_id: str
    name: str
    status: str
    item_count: int
    total_fee: Decimal
    total_insurance_estimate: Decimal
    total_patient_estimate: Decimal
