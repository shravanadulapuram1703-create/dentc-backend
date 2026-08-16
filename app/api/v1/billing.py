"""Billing service endpoints that supplement the generated CRUD routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.billing import (
    AllocatePaymentRequest,
    ClaimRecalcResult,
    PaymentAllocationRead,
)
from app.schemas.common import ErrorResponse
from app.schemas.transactions import (
    ClaimStatusHistory,
    ClaimSubmitRequest,
    ClaimSubmitResult,
    EstimateRequest,
    EstimateResult,
    ExplosionExpandResult,
    InsurancePaymentCreate,
    InsurancePaymentRead,
    PatientInsuranceSummary,
    TodaysAppointment,
)
from app.services import billing_service, estimate_service

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
