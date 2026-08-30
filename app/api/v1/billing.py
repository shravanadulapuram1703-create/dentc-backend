"""Billing service endpoints that supplement the generated CRUD routers."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.billing import (
    AllocateAdjustmentRequest,
    AllocatePaymentRequest,
    ClaimRecalcResult,
    PaymentAllocationRead,
    ProcedureAllocationsSummary,
)
from app.schemas.common import ErrorResponse
from app.schemas.transactions import (
    ClaimStatusHistory,
    ClaimSubmitRequest,
    ClaimSubmitResult,
    CoverageCategoryRead,
    EstimateRequest,
    EstimateResult,
    ExplosionExpandResult,
    FeeQuote,
    InsurancePaymentBatchCreate,
    InsurancePaymentBatchResult,
    InsurancePaymentCreate,
    InsurancePaymentRead,
    InsurancePaymentReverseRequest,
    InsurancePaymentReverseResult,
    OutstandingClaim,
    PatientInsuranceSummary,
    TodaysAppointment,
)
from app.services import billing_service, estimate_service, pricing_service
from app.services import coverage_category_service as covcat

router = APIRouter(
    tags=["Billing"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.post(
    "/patient-payments/{payment_id}/allocate",
    response_model=list[PaymentAllocationRead],
    operation_id="allocate_payment",
    summary="Allocate a payment across procedures/claims (guards over-allocation)",
)
def allocate_payment(
    db: DbSession,
    tenant_id: TenantId,
    payment_id: Annotated[str, Path()],
    body: AllocatePaymentRequest,
):
    return billing_service.allocate_payment(db, payment_id, body.allocations, tenant_id)


# ── ADJ-1: split one adjustment across specific outstanding procedures ───────
@router.post(
    "/patient-adjustments/{adjustment_id}/allocate",
    response_model=list[PaymentAllocationRead],
    operation_id="allocate_adjustment",
    summary="Split an adjustment across specific procedures (guards over-allocation) (ADJ-1)",
)
def allocate_adjustment(
    db: DbSession,
    tenant_id: TenantId,
    adjustment_id: Annotated[int, Path()],
    body: AllocateAdjustmentRequest,
):
    return billing_service.allocate_adjustment(
        db, adjustment_id, body.allocations, tenant_id, replace=body.replace
    )


@router.get(
    "/patient-adjustments/{adjustment_id}/allocations",
    response_model=list[PaymentAllocationRead],
    operation_id="list_adjustment_allocations",
    summary="An adjustment's per-procedure split (ADJ-1)",
)
def list_adjustment_allocations(
    db: DbSession,
    tenant_id: TenantId,
    adjustment_id: Annotated[int, Path()],
):
    return billing_service.list_adjustment_allocations(db, adjustment_id, tenant_id)


# ── CHG-5: what has already been applied to one procedure ────────────────────
@router.get(
    "/patient-procedures/{procedure_id}/allocations-summary",
    response_model=ProcedureAllocationsSummary,
    operation_id="get_procedure_allocations_summary",
    summary="Pat Paid / Pat Adj / Rem Amt for one procedure, with its sources (CHG-5)",
)
def procedure_allocations_summary(
    db: DbSession,
    tenant_id: TenantId,
    procedure_id: Annotated[str, Path()],
):
    return billing_service.procedure_allocations_summary(db, procedure_id, tenant_id)


@router.post(
    "/insurance-claims/{claim_id}/recalculate",
    response_model=ClaimRecalcResult,
    operation_id="recalculate_claim",
    summary="Recompute a claim's billed/estimate totals from its procedures",
)
def recalculate_claim(
    db: DbSession,
    tenant_id: TenantId,
    claim_id: Annotated[str, Path()],
):
    return billing_service.recalculate_claim(db, claim_id, tenant_id)


# ── INS-1: record an insurance payment with remittance identifiers ───────────
@router.post(
    "/ledger-insurance-details/payment",
    response_model=InsurancePaymentRead,
    status_code=201,
    operation_id="record_insurance_payment",
    summary="Record a carrier insurance payment with check/bank/EOB/EFT identifiers (INS-1)",
)
def record_insurance_payment(
    db: DbSession,
    tenant_id: TenantId,
    body: InsurancePaymentCreate,
    current=Depends(get_current_user),
):
    return billing_service.record_insurance_payment(
        db, tenant_id, body.model_dump(exclude_unset=True), actor_id=current.id
    )


# ── INS-PAY-3: post a whole remittance atomically ────────────────────────────
@router.post(
    "/ledger-insurance-details/payment-batch",
    response_model=InsurancePaymentBatchResult,
    status_code=201,
    operation_id="record_insurance_payment_batch",
    summary="Post one remittance across several procedures in a single transaction (INS-PAY-3)",
)
def record_insurance_payment_batch(
    db: DbSession,
    tenant_id: TenantId,
    body: InsurancePaymentBatchCreate,
    current=Depends(get_current_user),
):
    """One cheque covering four procedures used to be four POSTs, and a failure
    on the third left the claim half-paid with nothing able to roll it back.

    Every line lands or none does. When ``payment_amount`` is supplied it is
    reconciled against the sum of the lines to the cent **before** anything is
    written (422 ``remittance_not_reconciled``), so the window's reconciliation
    rule is enforced server-side rather than only in the browser. ``close_claim``
    and the INS-PAY-4 write-off intent are applied in the same transaction.
    """
    return billing_service.record_insurance_payment_batch(
        db, tenant_id, body.model_dump(exclude_unset=True), actor_id=current.id
    )


# ── INS-PAY-2: reverse a posted remittance instead of deleting it ────────────
@router.post(
    "/ledger-insurance-details/{detail_id}/reverse",
    response_model=InsurancePaymentReverseResult,
    operation_id="reverse_insurance_payment",
    summary="Reverse a posted insurance payment and re-derive the claim (INS-PAY-2)",
)
def reverse_insurance_payment(
    db: DbSession,
    tenant_id: TenantId,
    detail_id: Annotated[int, Path()],
    body: InsurancePaymentReverseRequest,
    current=Depends(get_current_user),
):
    """The counterpart to ``/patient-payments/{id}/reverse``, which insurance
    payments never had. The row is kept and marked void with a reason and an
    actor — a ``DELETE`` destroyed the evidence and, worse, left the claim's
    ``total_paid`` holding money no row backed."""
    return billing_service.reverse_insurance_payment(
        db, detail_id, tenant_id, body.model_dump(), actor_id=current.id
    )


# ── INS-PAY-7: the claim picker the Insurance Payment window needs ───────────
@router.get(
    "/patients/{patient_id}/outstanding-claims",
    response_model=list[OutstandingClaim],
    operation_id="list_outstanding_claims",
    summary="Every outstanding claim for a patient with its money roll-ups (INS-PAY-7)",
)
def outstanding_claims(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    include_closed: Annotated[
        bool, Query(description="Also return closed / denied / void claims")
    ] = False,
    date_from: Annotated[
        date | None, Query(description="Earliest date of service (inclusive)")
    ] = None,
    date_to: Annotated[
        date | None, Query(description="Latest date of service (inclusive)")
    ] = None,
):
    """Charges / est ins / deductible used / ins paid / ins adj / remaining per
    claim, aggregated server-side. Building this client-side meant one
    ``/insurance-claims/{id}/detail`` call per claim, because neither roll-up
    exists on ``GET /insurance-claims``."""
    return billing_service.outstanding_claims(
        db, patient_id, tenant_id,
        include_closed=include_closed, date_from=date_from, date_to=date_to,
    )


# ── SVC-1: submit / send a claim ─────────────────────────────────────────────
@router.post(
    "/insurance-claims/{claim_id}/submit",
    response_model=ClaimSubmitResult,
    operation_id="submit_claim",
    summary="Submit a claim (records sent_date/batch/method) (SVC-1)",
)
def submit_claim(
    db: DbSession,
    tenant_id: TenantId,
    claim_id: Annotated[str, Path()],
    body: ClaimSubmitRequest | None = None,
    current=Depends(get_current_user),
):
    payload = (body or ClaimSubmitRequest()).model_dump(exclude_unset=True)
    return billing_service.submit_claim(db, claim_id, tenant_id, payload, actor_id=current.id)


# ── AUD-3: claim status-change history ───────────────────────────────────────
@router.get(
    "/insurance-claims/{claim_id}/status-history",
    response_model=ClaimStatusHistory,
    operation_id="get_claim_status_history",
    summary="Auditable timeline of a claim's status transitions (AUD-3)",
)
def claim_status_history(
    db: DbSession,
    tenant_id: TenantId,
    claim_id: Annotated[str, Path()],
):
    return billing_service.claim_status_history(db, claim_id, tenant_id)


# ── CHG-1 / CHG-7: charge-time estimate engine ───────────────────────────────
@router.post(
    "/patients/{patient_id}/estimate",
    response_model=EstimateResult,
    operation_id="estimate_patient_charges",
    summary="Compute insurance/patient/deductible split from coverage + fees (CHG-1/7)",
)
def estimate_charges(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    body: EstimateRequest,
    office_id: Annotated[int | None, Query()] = None,
):
    lines = [line.model_dump() for line in body.lines]
    if not lines and body.procedure_code:
        lines = [{"procedure_code": body.procedure_code, "fee": body.fee, "provider_id": body.provider_id}]
    if not lines:
        lines = []
    return estimate_service.estimate(db, patient_id, tenant_id, lines=lines, office_id=office_id)


# ── CHG-8: patient insurance summary (carrier names by rank) ─────────────────
@router.get(
    "/patients/{patient_id}/insurance-summary",
    response_model=PatientInsuranceSummary,
    operation_id="get_patient_insurance_summary",
    summary="Primary/secondary carrier names for the check-out screen (CHG-8)",
)
def insurance_summary(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
):
    return billing_service.patient_insurance_summary(db, patient_id, tenant_id)


# ── CHG-9: today's appointment for the check-out flow ────────────────────────
@router.get(
    "/patients/{patient_id}/todays-appointment",
    response_model=TodaysAppointment,
    operation_id="get_patient_todays_appointment",
    summary="Today's appointment id + status so the Transactions screen can check out (CHG-9)",
)
def todays_appointment(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
):
    return billing_service.todays_appointment(db, patient_id, tenant_id)


# ── CHG-4: explosion-code expansion ──────────────────────────────────────────
@router.get(
    "/explosion-codes/{code}/expand",
    response_model=ExplosionExpandResult,
    operation_id="expand_explosion_code",
    summary="Expand a user-defined explosion code into its procedures (CHG-4)",
)
def expand_explosion_code(
    db: DbSession,
    tenant_id: TenantId,
    code: Annotated[str, Path()],
    office_id: Annotated[int | None, Query()] = None,
):
    return billing_service.expand_explosion_code(db, code, tenant_id, office_id=office_id)


# ── FEE-3: server-side fee resolution ───────────────────────────────────────
@router.get(
    "/patients/{patient_id}/fee",
    response_model=FeeQuote,
    operation_id="get_patient_procedure_fee",
    summary="Resolve a procedure's fee for this patient/office/provider (FEE-3)",
)
def patient_procedure_fee(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    procedure_code: Annotated[str, Query(description="The ADA/CDT code to price")],
    office_id: Annotated[int | None, Query()] = None,
    provider_id: Annotated[str | None, Query()] = None,
    ins_plan_id: Annotated[int | None, Query(description="Override the patient's primary plan")] = None,
):
    """The fee the server would apply, plus **which** schedule produced it.

    Fee resolution used to live only in the frontend, so two clients could
    disagree and nothing stopped a charge posting with an arbitrary amount.
    ``conflicts`` is non-empty when two equally-specific assignments price the
    code differently — the UI should say so rather than pick one silently.
    """
    return pricing_service.resolve_procedure_fee(
        db, tenant_id, procedure_code,
        patient_id=patient_id,
        office_id=office_id,
        provider_id=provider_id,
        ins_plan_id=ins_plan_id,
    )


# ── FEE-1: the published ADA -> coverage-category mapping ───────────────────
@router.get(
    "/metadata/coverage-categories",
    response_model=list[CoverageCategoryRead],
    operation_id="list_coverage_categories",
    summary="The ADA/CDT -> insurance coverage-category mapping the estimate engine uses (FEE-1)",
)
def coverage_categories(db: DbSession, tenant_id: TenantId):
    """Published so a practice can audit *why* a code was priced at a given
    percentage, and override the classification per code
    (``PATCH /procedure-codes/{code} {"coverage_category": "03A"}``) when the
    CDT-range default is wrong for their plans."""
    return covcat.catalog(db)
