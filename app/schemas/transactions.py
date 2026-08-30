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

from datetime import date, datetime
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
    fee_source: str = Field(
        "code_default",
        description="override | assignment | plan_schedule | office_default | code_default",
    )
    fee_schedule_id: int | None = Field(None, description="The schedule the fee came from (FEE-3)")
    # FEE-1: which coverage band the percentage was read off, so a surprising
    # estimate can be traced to a category rather than looking arbitrary.
    coverage_category: str | None = None
    coverage_category_description: str | None = None


class EstimateResult(BaseModel):
    patient_id: int
    has_active_coverage: bool
    lines: list[EstimateLineResult]
    total_fee: Decimal = Field(Decimal("0"))
    insurance_estimate: Decimal = Field(Decimal("0"))
    patient_estimate: Decimal = Field(Decimal("0"))
    estimated_deductible: Decimal = Field(Decimal("0"))


# ── INS-1: record an insurance payment with remittance identifiers ───────────
class _RemittanceIdentifiers(BaseModel):
    """What the EOB says about the cheque, as opposed to the procedure."""

    payment_date: date | None = None
    payment_method: str | None = Field(None, examples=["check", "eft", "credit_card"])
    check_number: str | None = None
    bank_number: str | None = None
    eob_number: str | None = None
    eft_trace_number: str | None = None
    # INS-PAY-1: the remittance note the legacy window collects. It used to be
    # appended to the *claim's* notes with a synthetic prefix, so one line's note
    # applied to the whole claim and could not be read back apart from it.
    notes: str | None = None


class _CoverageAmounts(BaseModel):
    """Per-tier money on one procedure line.

    INS-PAY-5: the tiers are symmetric. ``sec_deductible`` and every tertiary
    field bar ``ter_ins_paid`` used to be missing, so a secondary remittance
    could not carry a deductible and a tertiary one could not be posted at all.
    """

    prim_ins_plan_id: int | None = None
    prim_estimated: Decimal | None = None
    prim_deductible: Decimal | None = None
    prim_ins_paid: Decimal | None = None
    prim_ins_adjust: Decimal | None = None
    sec_ins_plan_id: int | None = None
    sec_estimated: Decimal | None = None
    sec_deductible: Decimal | None = None
    sec_ins_paid: Decimal | None = None
    sec_ins_adjust: Decimal | None = None
    ter_ins_plan_id: int | None = None
    ter_estimated: Decimal | None = None
    ter_deductible: Decimal | None = None
    ter_ins_paid: Decimal | None = None
    ter_ins_adjust: Decimal | None = None


class InsurancePaymentCreate(_RemittanceIdentifiers, _CoverageAmounts):
    patient_id: int
    claim_id: str | None = None
    procedure_id: str | None = None
    office_id: int | None = None


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
    notes: str | None = None
    prim_deductible: Decimal | None = None
    prim_ins_paid: Decimal | None = None
    prim_ins_adjust: Decimal | None = None
    sec_deductible: Decimal | None = None
    sec_ins_paid: Decimal | None = None
    sec_ins_adjust: Decimal | None = None
    ter_deductible: Decimal | None = None
    ter_ins_paid: Decimal | None = None
    ter_ins_adjust: Decimal | None = None
    is_void: bool = False
    void_reason: str | None = None
    created_by: int | None = None


# ── INS-PAY-3: one cheque, several procedures, one transaction ───────────────
class InsurancePaymentLine(_CoverageAmounts):
    """One procedure's share of the remittance.

    A line may override any identifier from the header (a single deposit
    occasionally covers two cheques), but normally inherits all of them.
    """

    procedure_id: str | None = None
    office_id: int | None = None
    payment_method: str | None = None
    check_number: str | None = None
    bank_number: str | None = None
    eob_number: str | None = None
    eft_trace_number: str | None = None
    notes: str | None = None


class InsurancePaymentBatchCreate(_RemittanceIdentifiers):
    patient_id: int
    claim_id: str | None = None
    office_id: int | None = None
    lines: list[InsurancePaymentLine] = Field(min_length=1)
    #: Optional, and checked to the cent when present: the cheque total the lines
    #: must add up to. Sending it makes the server enforce the window's
    #: reconciliation rule, so an import cannot post an unbalanced remittance.
    payment_amount: Decimal | None = None
    #: INS-PAY-4 — what the user typed in "Enter Adjustment". The money itself
    #: still rides the lines; this records the intent behind the distribution.
    write_off_mode: Literal["amount", "percent"] | None = None
    write_off_value: Decimal | None = None
    #: Tick "Close Claim" and the claim is closed in the same transaction.
    close_claim: bool = False


class ClaimMoneyTotals(BaseModel):
    id: str
    claim_number: str
    status: str
    total_billed: Decimal
    total_paid: Decimal
    est_insurance: Decimal
    #: The pre-existing (migrated) share of ``total_paid`` — see INS-PAY-2.
    opening_paid: Decimal | None = None
    write_off_amount: Decimal | None = None
    write_off_mode: str | None = None
    write_off_value: Decimal | None = None


class InsurancePaymentBatchResult(BaseModel):
    lines: list[InsurancePaymentRead]
    allocated: Decimal
    adjusted: Decimal
    claim: ClaimMoneyTotals | None = None


# ── INS-PAY-2: reverse a posted remittance ───────────────────────────────────
class InsurancePaymentReverseRequest(BaseModel):
    reason: str = Field(min_length=1, examples=["Posted against the wrong claim"])


class InsurancePaymentReverseResult(BaseModel):
    id: int
    claim_id: str | None = None
    reversed_amount: Decimal
    reason: str
    voided_at: datetime | None = None
    claim: ClaimMoneyTotals | None = None


# ── INS-PAY-7: the outstanding-claims picker ─────────────────────────────────
class OutstandingClaim(BaseModel):
    claim_id: str
    claim_number: str
    status: str
    claim_type: str | None = None
    billing_order: str | None = None
    office_id: int | None = None
    carrier_id: int | None = None
    carrier_name: str | None = None
    ins_plan_id: int | None = None
    billing_provider_id: str | None = None
    treating_provider_id: str | None = None
    date_of_service_from: date | None = None
    date_of_service_to: date | None = None
    submitted_date: date | None = None
    procedure_count: int = 0
    total_charges: Decimal = Field(Decimal("0"))
    est_insurance: Decimal = Field(Decimal("0"))
    deductible_used: Decimal = Field(Decimal("0"))
    ins_paid: Decimal = Field(Decimal("0"))
    ins_adjusted: Decimal = Field(Decimal("0"))
    remaining: Decimal = Field(Decimal("0"))


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


# ── FEE-3: server-side fee resolution ───────────────────────────────────────
class FeeConflict(BaseModel):
    """An equally-specific fee-schedule assignment that priced the code differently."""

    fee_schedule_id: int
    fee_schedule_name: str | None = None
    fee: Decimal
    specificity: int


class FeeQuoteContext(BaseModel):
    office_id: int | None = None
    provider_id: str | None = None
    ins_plan_id: int | None = None
    carrier_id: int | None = None
    office_group_id: int | None = None
    specialty_id: str | None = None


class FeeQuote(BaseModel):
    procedure_code: str
    fee: Decimal = Field(Decimal("0"), description="The resolved patient-side fee")
    insurance_fee: Decimal = Field(Decimal("0"), description="The schedule's payer-side amount")
    ucr_fee: Decimal | None = Field(None, description="The office UCR schedule's fee, if configured")
    fee_schedule_id: int | None = None
    fee_schedule_name: str | None = None
    fee_source: str = Field(
        "code_default",
        description="assignment | plan_schedule | office_default | code_default",
    )
    specificity: int = Field(0, description="How many keys the winning assignment set")
    conflicts: list[FeeConflict] = Field(default_factory=list)
    context: FeeQuoteContext = Field(default_factory=FeeQuoteContext)


# ── FEE-1: the published ADA -> coverage-category mapping ───────────────────
class CoverageCategoryRange(BaseModel):
    start_code: str
    end_code: str


class CoverageCategoryRead(BaseModel):
    code: str = Field(description='The legacy coverage-category code, e.g. "01A"')
    description: str
    parent_code: str | None = Field(None, description='"03A" -> "03"; null for a top-level category')
    cdt_ranges: list[CoverageCategoryRange] = Field(default_factory=list)
    procedure_code_count: int = 0
