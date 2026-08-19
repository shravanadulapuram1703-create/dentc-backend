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


# ── ADJ-1: split one adjustment across specific outstanding procedures ────────
class AdjustmentAllocationLine(BaseModel):
    procedure_id: str = Field(..., description="The outstanding procedure to write down")
    amount: Decimal = Field(..., gt=0)
    provider_id: str | None = None
    alloc_date: date | None = None


class AllocateAdjustmentRequest(BaseModel):
    allocations: list[AdjustmentAllocationLine] = Field(..., min_length=1)
    replace: bool = Field(
        False,
        description="Replace this adjustment's existing allocations instead of adding to them",
    )


class PaymentAllocationRead(ORMModel):
    id: int
    patient_id: int
    payment_id: str | None = None
    adjustment_id: int | None = None
    procedure_id: str | None = None
    claim_id: str | None = None
    provider_id: str | None = None
    amount: Decimal
    alloc_type: str | None = None
    alloc_date: date | None = None


class PatientAdjustmentSummary(ORMModel):
    id: int
    patient_id: int
    procedure_id: str | None = None
    adjustment_date: date
    amount: Decimal
    adjustment_type: str | None = None
    write_off_type: str | None = None
    notes: str | None = None


class ProcedureAllocationsSummary(ORMModel):
    """CHG-5: what has already been applied to one procedure, and by what."""

    procedure_id: str
    patient_id: int
    fee: Decimal
    patient_estimate: Decimal
    insurance_estimate: Decimal
    paid_to_date: Decimal = Field(..., description="Patient payments allocated to the procedure")
    insurance_paid_to_date: Decimal = Field(..., description="Carrier money posted to the procedure")
    adjusted_to_date: Decimal = Field(..., description="Non-void adjustments applied")
    remaining_amount: Decimal = Field(..., description="patient_estimate − paid − adjusted")
    allocations: list[PaymentAllocationRead] = Field(default_factory=list)
    adjustments: list[PatientAdjustmentSummary] = Field(default_factory=list)


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
    # AUD-2: creator/modifier + timestamps backing the ledger "CREATED BY" column.
    provider_id: str | None = None
    provider_name: str | None = None
    created_by: int | None = None
    created_by_name: str | None = None
    created_at: str | None = None
    modified_by: int | None = None
    modified_at: str | None = None


class LedgerResponse(BaseModel):
    patient_id: int
    entries: list[LedgerEntry]
    opening_balance: float = Field(..., description="Running balance before the returned page")
    closing_balance: float = Field(..., description="Running balance after the returned page")
    total: int = Field(..., description="Total ledger entries in the window")
    as_of: str


# ── Account Ledger — fully-denormalised feed (AL-1/2/4/5/7) ───────────────────
class AccountLedgerRow(BaseModel):
    """One fully-denormalised Account-Ledger row (no client-side lookups needed)."""

    entry_date: date | None = None
    source_type: str = Field(..., description="charge | payment | adjustment")
    source_id: str
    code: str | None = Field(None, description="procedure_code | 'PMT' | 'PATADJ'")
    description: str | None = None
    transaction_kind: str = Field(..., description="'P' (debit) | 'C' (credit) — the legacy T column")
    apply_to: str | None = None
    tooth: str | None = None
    surface: str | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    office_id: int | None = None
    office_short_id: str | None = None
    patient_estimate: Decimal | None = None
    insurance_estimate: Decimal | None = None
    billing_status: str | None = None
    unbilled: bool | None = Field(None, description="AL-6 'N' — a procedure with no claim_id")
    user_id: int | None = None
    user_label: str | None = None
    charge: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    amount: Decimal = Field(Decimal("0"), description="Signed: +charge / -credit")
    running_balance: Decimal = Decimal("0")


class AccountLedgerResponse(BaseModel):
    patient_id: int
    rows: list[AccountLedgerRow]
    grand_total: Decimal = Field(..., description="Final running balance over the full account window")
    total: int = Field(..., description="Total rows after the type filter")
    page: int
    size: int
    pages: int
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
    opening_balance: float = Field(0, description="Seeded opening A/R (GAP-AP-12); already in balance/aging")
    total_refunded: float = Field(0, description="Sum of non-void refunds (REF-1); folded into balance")
    credit_balance: float = Field(0, description="Refundable unapplied credit (REF-3); ≥0")
    aging: BalanceAging = Field(default_factory=BalanceAging)
    recent_activity: BalanceRecentActivity = Field(default_factory=BalanceRecentActivity)
    as_of: str = Field(..., description="UTC timestamp the balance was computed")
