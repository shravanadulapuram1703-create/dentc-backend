"""Transactions-module schemas (dashboard, search, refunds, statements, estimate).

Covers the verified backend gaps in
``transactions/transactions_backend_devreport.md``: office financial dashboards
(DASH-1..5), the unified cross-patient feed/search (SRCH-1/3), refunds & reversals
(REF-1..4), patient statements (STMT-1..3), the charge-time estimate engine
(CHG-1/7), insurance-payment remittance (INS-1), claim submit (SVC-1) and status
history (AUD-3), and explosion codes (CHG-4).

All monetary fields are ``Decimal``; all id fields serialise as they are stored.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

Period = Literal["today", "week", "month", "year", "custom"]


# ── DASH-1: office financial summary ─────────────────────────────────────────
class OfficeFinancialSummary(BaseModel):
    office_id: int
    outstanding_balance: Decimal = Field(..., description="Total account balance across all patients")
    patient_balance: Decimal = Field(..., description="Patient-responsible portion")
    insurance_receivable: Decimal = Field(..., description="Outstanding expected-insurance portion")
    credit_balance: Decimal = Field(Decimal("0"), description="Total unapplied credit (negative balances)")
    patient_count: int = Field(0, description="Patients with a non-zero balance")
    as_of: str


# ── DASH-2: collections summary ──────────────────────────────────────────────
class CollectionsSummary(BaseModel):
    office_id: int
    period: str
    date_from: date
    date_to: date
    patient_payments: Decimal = Field(Decimal("0"))
    insurance_payments: Decimal = Field(Decimal("0"))
    total_collections: Decimal = Field(Decimal("0"))
    payment_count: int = 0
    as_of: str


# ── DASH-3: insurance receivables (A/R) ──────────────────────────────────────
class CarrierReceivable(BaseModel):
    carrier_id: int | None = None
    carrier_name: str | None = None
    outstanding: Decimal = Field(Decimal("0"))
    claim_count: int = 0


class InsuranceReceivables(BaseModel):
    office_id: int
    total_outstanding: Decimal = Field(Decimal("0"))
    open_claim_count: int = 0
    by_carrier: list[CarrierReceivable] = Field(default_factory=list)
    as_of: str


# ── DASH-4: refund / adjustment / write-off totals ───────────────────────────
class AdjustmentSummary(BaseModel):
    office_id: int
    period: str
    date_from: date
    date_to: date
    adjustment_total: Decimal = Field(Decimal("0"))
    write_off_total: Decimal = Field(Decimal("0"))
    refund_total: Decimal = Field(Decimal("0"))
    write_off_by_type: dict[str, Decimal] = Field(default_factory=dict)
    as_of: str


# ── SRCH-1/3 · DASH-5: unified cross-patient transaction feed ─────────────────
class TransactionRow(BaseModel):
    transaction_number: str = Field(..., description="Stable per-source id, e.g. 'PROC:P123'")
    transaction_type: str = Field(..., description="charge | payment | adjustment | refund | claim")
    source_id: str
    entry_date: date | None = None
    patient_id: int | None = None
    patient_name: str | None = None
    office_id: int | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    code: str | None = None
    description: str | None = None
    amount: Decimal = Field(Decimal("0"), description="Signed: +debit / −credit")
    status: str | None = None


class TransactionFeed(BaseModel):
    rows: list[TransactionRow]
    total: int
    page: int
    size: int
    pages: int
    as_of: str


# ── REF-1: process refund ────────────────────────────────────────────────────
class RefundCreate(BaseModel):
    refund_amount: Decimal = Field(..., gt=0)
    refund_method: str | None = Field(None, examples=["check", "eft", "credit_card", "cash"])
    reason: str | None = None
    reason_code: str | None = Field(None, examples=["overpayment", "duplicate", "cancellation"])
    source_payment_id: str | None = None
    office_id: int | None = None
    refund_date: date | None = None
    check_number: str | None = None
    reference_number: str | None = None
    authorized_by: int | None = Field(None, description="Overrides the token user as the authoriser")
    notes: str | None = None


class RefundRead(ORMModel):
    id: int
    patient_id: int
    office_id: int | None = None
    refund_date: date
    amount: Decimal
    refund_method: str | None = None
    reason: str | None = None
    reason_code: str | None = None
    source_payment_id: str | None = None
    reversed_type: str | None = None
    reversed_id: str | None = None
    check_number: str | None = None
    reference_number: str | None = None
    authorized_by: int | None = None
    authorized_by_name: str | None = None
    notes: str | None = None
    is_void: bool = False


class RefundResult(BaseModel):
    refund: RefundRead
    balance: dict = Field(..., description="Recomputed patient balance after the refund")


# ── REF-2: reverse a payment / adjustment ────────────────────────────────────
class ReverseRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    authorized_by: int | None = None
    refund_method: str | None = Field(
        None, description="If set, also issue a matching refund for the reversed amount"
    )


class ReverseResult(BaseModel):
    reversed_type: str
    reversed_id: str
    reason: str
    refund: RefundRead | None = None
    balance: dict


# ── REF-3: refundable-credit lookup ──────────────────────────────────────────
class RefundableBalance(BaseModel):
    patient_id: int
    account_balance: Decimal = Field(..., description="Charges − payments + refunds (signed)")
    credit_balance: Decimal = Field(..., description="Unapplied credit available to refund (≥0)")
    unallocated_payments: Decimal = Field(Decimal("0"), description="Payments not tied to an allocation")
    refundable_amount: Decimal = Field(..., description="Max amount that may be refunded now")
    as_of: str


# ── REF-4: refund policy ─────────────────────────────────────────────────────
class RefundPolicy(BaseModel):
    manager_approval_threshold: Decimal = Field(
        ..., description="Refunds strictly above this amount need manager approval"
    )
    max_refund_without_source: Decimal = Field(
        ..., description="Cap for a refund not tied to a source payment"
    )
    allow_over_credit: bool = Field(False, description="Whether a refund may exceed the credit balance")
    approver_roles: list[str] = Field(default_factory=lambda: ["admin", "super_admin"])


# ── CHG-1 / CHG-7: charge-time estimate engine ───────────────────────────────
class EstimateLine(BaseModel):
    procedure_code: str
    fee: Decimal | None = Field(None, description="Override; defaults to the fee-schedule / code fee")
    provider_id: str | None = None
    tooth: str | None = None


class EstimateRequest(BaseModel):
    # Single-procedure or batch. If ``lines`` is empty, the top-level fields form one line.
    procedure_code: str | None = None
    fee: Decimal | None = None
    provider_id: str | None = None
    lines: list[EstimateLine] = Field(default_factory=list)


class EstimateLineResult(BaseModel):
    procedure_code: str
    fee: Decimal
    coverage_pct: Decimal = Field(Decimal("0"))
    insurance_estimate: Decimal = Field(Decimal("0"))
    patient_estimate: Decimal = Field(Decimal("0"))
    estimated_deductible: Decimal = Field(Decimal("0"))
    fee_source: str = Field("code_default", description="fee_schedule | code_default | override")


class EstimateResult(BaseModel):
    patient_id: int
    has_active_coverage: bool
    lines: list[EstimateLineResult]
    total_fee: Decimal = Field(Decimal("0"))
    insurance_estimate: Decimal = Field(Decimal("0"))
    patient_estimate: Decimal = Field(Decimal("0"))
    estimated_deductible: Decimal = Field(Decimal("0"))


# ── INS-1: record an insurance payment with remittance identifiers ───────────
class InsurancePaymentCreate(BaseModel):
    patient_id: int
    claim_id: str | None = None
    procedure_id: str | None = None
    office_id: int | None = None
    payment_date: date | None = None
    payment_method: str | None = Field(None, examples=["check", "eft", "credit_card"])
    check_number: str | None = None
    bank_number: str | None = None
    eob_number: str | None = None
    eft_trace_number: str | None = None
    prim_ins_plan_id: int | None = None
    sec_ins_plan_id: int | None = None
    prim_estimated: Decimal | None = None
    prim_ins_paid: Decimal | None = None
    prim_ins_adjust: Decimal | None = None
    prim_deductible: Decimal | None = None
    sec_estimated: Decimal | None = None
    sec_ins_paid: Decimal | None = None
    sec_ins_adjust: Decimal | None = None


class InsurancePaymentRead(ORMModel):
    id: int
    patient_id: int
    claim_id: str | None = None
    procedure_id: str | None = None
    office_id: int | None = None
    payment_date: date | None = None
    payment_method: str | None = None
    check_number: str | None = None
    bank_number: str | None = None
    eob_number: str | None = None
    eft_trace_number: str | None = None
    prim_ins_paid: Decimal | None = None
    prim_ins_adjust: Decimal | None = None
    sec_ins_paid: Decimal | None = None
    sec_ins_adjust: Decimal | None = None
    created_by: int | None = None


# ── SVC-1: submit a claim ────────────────────────────────────────────────────
class ClaimSubmitRequest(BaseModel):
    send_method: str = Field("electronic", examples=["electronic", "paper"])
    sent_date: date | None = None
    batch_id: str | None = None
    is_preauth: bool = False


class ClaimSubmitResult(BaseModel):
    claim_id: str
    claim_number: str
    status: str
    batch_id: str
    sent_date: date
    send_method: str
    submission_id: int


# ── AUD-3: claim status history ──────────────────────────────────────────────
class ClaimStatusEvent(BaseModel):
    status: str | None = None
    changed_at: str | None = None
    changed_by: int | None = None
    changed_by_name: str | None = None
    method: str | None = None
    source: str = Field("audit_log", description="audit_log | claim_field")


class ClaimStatusHistory(BaseModel):
    claim_id: str
    claim_number: str | None = None
    current_status: str | None = None
    events: list[ClaimStatusEvent]


# ── STMT-1/2: patient statement generation ───────────────────────────────────
class StatementCreate(BaseModel):
    office_id: int | None = None
    statement_date: date | None = None
    date_from: date | None = None
    date_to: date | None = None
    message: str | None = None


class StatementRead(ORMModel):
    id: int
    patient_id: int
    office_id: int | None = None
    statement_date: date
    period_start: date | None = None
    period_end: date | None = None
    opening_balance: Decimal
    total_charges: Decimal
    total_payments: Decimal
    total_adjustments: Decimal
    closing_balance: Decimal
    aging_current: Decimal
    aging_30: Decimal
    aging_60: Decimal
    aging_90: Decimal
    aging_120: Decimal
    message: str | None = None
    batch_id: str | None = None
    delivery_method: str | None = None
    delivery_status: str
    delivered_to: str | None = None
    delivered_at: date | None = None


class StatementBatchRequest(BaseModel):
    statement_date: date | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_balance: Decimal = Field(Decimal("0.01"), description="Only patients whose balance exceeds this")
    only_aged: bool = Field(False, description="Only patients with a 30+ day aged balance")


class StatementBatchResult(BaseModel):
    office_id: int
    batch_id: str
    generated: int
    statements: list[StatementRead]


class StatementDeliverRequest(BaseModel):
    method: Literal["email", "print", "download"] = "email"
    email: str | None = Field(None, description="Overrides the patient's email for email delivery")


# ── CHG-8: patient insurance summary ─────────────────────────────────────────
class InsuranceSummaryRank(BaseModel):
    rank: str = Field(..., description="primary | secondary | tertiary | …")
    ins_plan_id: int | None = None
    carrier_id: int | None = None
    carrier_name: str | None = None
    group_number: str | None = None
    is_active: bool = True


class PatientInsuranceSummary(BaseModel):
    patient_id: int
    primary: InsuranceSummaryRank | None = None
    secondary: InsuranceSummaryRank | None = None
    plans: list[InsuranceSummaryRank] = Field(default_factory=list)


# ── CHG-9: today's appointment for the check-out flow ────────────────────────
class TodaysAppointment(BaseModel):
    patient_id: int
    appointment_id: str | None = None
    appt_date: date | None = None
    start_time: str | None = None
    status: str | None = None
    provider_id: str | None = None
    operatory_id: str | None = None
    has_appointment: bool = False


# ── CHG-4: explosion-code expansion ──────────────────────────────────────────
class ExpandedProcedure(BaseModel):
    procedure_code: str
    description: str | None = None
    default_fee: Decimal | None = None
    tooth: str | None = None
    surface: str | None = None
    display_order: int = 0


class ExplosionExpandResult(BaseModel):
    explosion_code: str
    description: str | None = None
    procedures: list[ExpandedProcedure]
