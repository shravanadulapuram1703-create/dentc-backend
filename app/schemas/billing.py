"""Billing service schemas (payment allocation, claim recalculation)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AllocationLine(BaseModel):
    amount: Decimal = Field(..., gt=0)
    procedure_id: str | None = None
    claim_id: str | None = None
    ins_plan_id: int | None = None
    provider_id: str | None = None
    alloc_type: str | None = None
    alloc_date: date | None = None


class AllocatePaymentRequest(BaseModel):
    allocations: list[AllocationLine] = Field(..., min_length=1)


class PaymentAllocationRead(ORMModel):
    id: int
    patient_id: int
    payment_id: str | None = None
    procedure_id: str | None = None
    claim_id: str | None = None
    amount: Decimal
    alloc_type: str | None = None
    alloc_date: date | None = None


class ClaimRecalcResult(ORMModel):
    id: str
    claim_number: str
    status: str
    total_billed: Decimal
    total_paid: Decimal
    est_insurance: Decimal
    procedure_count: int


class PatientBalance(BaseModel):
    """Computed account balance (charges − payments). Phase 3 cached aggregate."""

    patient_id: int = Field(..., examples=[1024])
    total_charged: float = Field(..., examples=[2450.00])
    total_paid: float = Field(..., examples=[1800.00])
    balance: float = Field(..., examples=[650.00])
    as_of: str = Field(..., description="UTC timestamp the balance was computed")
