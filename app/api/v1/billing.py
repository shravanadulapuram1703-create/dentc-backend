"""Billing service endpoints that supplement the generated CRUD routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.billing import (
    AllocatePaymentRequest,
    ClaimRecalcResult,
    PaymentAllocationRead,
)
from app.schemas.common import ErrorResponse
from app.services import billing_service

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
