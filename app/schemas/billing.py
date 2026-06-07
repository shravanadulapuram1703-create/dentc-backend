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


class BalanceAging(BaseModel):
    """Gross procedure charges bucketed by age of date_of_service (days)."""

    current: float = Field(0, description="0–30 days")
    b30: float = Field(0, description="31–60 days")
    b60: float = Field(0, description="61–90 days")
    b90: float = Field(0, description="91–120 days")
    b120: float = Field(0, description="120+ days")


class BalanceRecentActivity(BaseModel):
    today: float = Field(0, description="Sum of today's non-void payments")
    last_ins: str | None = Field(None, description="Date of most recent insurance payment")
    last_pat: str | None = Field(None, description="Date of most recent patient payment")
    last_ins_amount: float = Field(0, description="Amount of the most recent insurance payment")
    last_pat_amount: float = Field(0, description="Amount of the most recent patient payment")


class LedgerEntry(BaseModel):
    entry_date: str
    entry_type: str = Field(..., description="procedure | payment")
    source_id: str
    description: str | None = None
    charge: float = 0
    credit: float = 0
    running_balance: float = 0
    procedure_code: str | None = None
    tooth: str | None = None
    payment_type: str | None = None
    status: str | None = None


class LedgerResponse(BaseModel):
    patient_id: int
    entries: list[LedgerEntry]
    opening_balance: float = Field(..., description="Running balance before the returned page")
    closing_balance: float = Field(..., description="Running balance after the returned page")
    total: int = Field(..., description="Total ledger entries in the window")
    as_of: str


class PatientBalance(BaseModel):
    """Computed account balance (charges − payments). Phase 3 cached aggregate.

    The first three fields are the original contract; the rest are additive C-3
    enrichments and are always present.
    """

    patient_id: int = Field(..., examples=[1024])
    total_charged: float = Field(..., examples=[2450.00])
    total_paid: float = Field(..., examples=[1800.00])
    balance: float = Field(..., examples=[650.00])
    account_balance: float = Field(..., description="Alias of balance for the FE", examples=[650.00])
    estimated_insurance: float = Field(0, examples=[400.00])
    estimated_patient: float = Field(0, examples=[250.00])
    patient_balance: float = Field(0, description="Charges − payments − estimated insurance")
    insurance_balance: float = Field(0, description="Outstanding expected-insurance portion")
    today_charges: float = Field(0, description="Sum of today's non-void procedure charges")
    aging: BalanceAging = Field(default_factory=BalanceAging)
    recent_activity: BalanceRecentActivity = Field(default_factory=BalanceRecentActivity)
    as_of: str = Field(..., description="UTC timestamp the balance was computed")
