"""Refunds & reversals (REF-1..4).

Mounted before the generic CRUD routers so the literal ``/patients/{id}/refunds``
and ``/patient-payments/{id}/reverse`` sub-paths win over ``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import DbSession, PageParams, TenantId, get_current_user
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.transactions import (
    RefundableBalance,
    RefundCreate,
    RefundPolicy,
    RefundRead,
    RefundResult,
    ReverseRequest,
    ReverseResult,
)
from app.services import refund_service

router = APIRouter(
    tags=["Billing"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


# ── REF-4: refund policy ─────────────────────────────────────────────────────
@router.get(
    "/metadata/refund-policy",
    response_model=RefundPolicy,
    operation_id="get_refund_policy",
    summary="Refund authorisation thresholds/policy (REF-4)",
)
def refund_policy(
    db: DbSession,
    tenant_id: TenantId,
    office_id: Annotated[int | None, Query()] = None,
):
    return refund_service.refund_policy(db, tenant_id, office_id)


# ── REF-3: refundable balance ────────────────────────────────────────────────
@router.get(
    "/patients/{patient_id}/refundable-balance",
    response_model=RefundableBalance,
    operation_id="get_patient_refundable_balance",
    summary="Refundable (unapplied credit) amount before issuing a refund (REF-3)",
)
def refundable_balance(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    return refund_service.refundable_balance(db, patient_id, tenant_id)


# ── REF-1: process a refund + list ───────────────────────────────────────────
@router.post(
    "/patients/{patient_id}/refunds",
    response_model=RefundResult,
    status_code=201,
    operation_id="create_patient_refund",
    summary="Issue a refund to a patient (REF-1)",
)
def create_refund(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    body: RefundCreate,
    current=Depends(get_current_user),
):
    return refund_service.process_refund(
        db, patient_id, tenant_id, body.model_dump(exclude_unset=True),
        actor_id=current.id, actor_role=current.role,
    )


@router.get(
    "/patients/{patient_id}/refunds",
    response_model=PaginatedResponse[RefundRead],
    operation_id="list_patient_refunds",
    summary="List a patient's refunds (REF-1)",
)
def list_refunds(
    db: DbSession,
    tenant_id: TenantId,
    page: PageParams,
    patient_id: Annotated[int, Path()],
):
    items, total = refund_service.list_refunds(
        db, patient_id, tenant_id, page=page.page, size=page.size
    )
    return PaginatedResponse.build(items, total, page.page, page.size)


# ── REF-2: reverse a payment / adjustment ────────────────────────────────────
@router.post(
    "/patient-payments/{payment_id}/reverse",
    response_model=ReverseResult,
    operation_id="reverse_patient_payment",
    summary="Reverse a payment posted in error (REF-2)",
)
def reverse_payment(
    db: DbSession,
    tenant_id: TenantId,
    payment_id: Annotated[str, Path()],
    body: ReverseRequest,
    current=Depends(get_current_user),
):
    return refund_service.reverse_payment(
        db, payment_id, tenant_id, body.model_dump(exclude_unset=True), actor_id=current.id
    )


@router.post(
    "/patient-adjustments/{adjustment_id}/reverse",
    response_model=ReverseResult,
    operation_id="reverse_patient_adjustment",
    summary="Reverse an adjustment posted in error (REF-2)",
)
def reverse_adjustment(
    db: DbSession,
    tenant_id: TenantId,
    adjustment_id: Annotated[int, Path()],
    body: ReverseRequest,
    current=Depends(get_current_user),
):
    return refund_service.reverse_adjustment(
        db, adjustment_id, tenant_id, body.model_dump(exclude_unset=True), actor_id=current.id
    )
