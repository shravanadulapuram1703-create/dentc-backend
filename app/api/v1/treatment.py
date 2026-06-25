"""Treatment-plan service endpoints that supplement generated CRUD."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.treatment import (
    ReEstimateResult,
    TreatmentPlanItemRead,
    TreatmentPlanReport,
    TreatmentPlanSummary,
)
from app.services import treatment_service

router = APIRouter(
    tags=["Treatment Plans"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.get(
    "/treatment-plans/{plan_id}/summary",
    response_model=TreatmentPlanSummary,
    operation_id="get_treatment_plan_summary",
    summary="Roll up a treatment plan's item fees into a summary",
)
def treatment_plan_summary(
    db: DbSession,
    tenant_id: TenantId,
    plan_id: Annotated[str, Path()],
):
    return treatment_service.plan_summary(db, plan_id, tenant_id)


@router.post(
    "/treatment-plans/{plan_id}/re-estimate",
    response_model=ReEstimateResult,
    operation_id="re_estimate_treatment_plan",
    summary="Compute per-item insurance estimates from the patient's coverage (PLAN-3)",
)
def re_estimate_plan(
    db: DbSession,
    tenant_id: TenantId,
    plan_id: Annotated[str, Path()],
    phase: Annotated[int | None, Query(description="Limit to one Phase ID")] = None,
):
    return treatment_service.re_estimate(db, plan_id, tenant_id, phase_id=phase)


@router.get(
    "/treatment-plans/{plan_id}/report",
    response_model=TreatmentPlanReport,
    operation_id="get_treatment_plan_report",
    summary="Server-side treatment-plan report payload (PLAN-6)",
)
def treatment_plan_report(
    db: DbSession,
    tenant_id: TenantId,
    plan_id: Annotated[str, Path()],
):
    return treatment_service.plan_report(db, plan_id, tenant_id)


@router.get(
    "/patients/{patient_id}/treatment-plan-items",
    response_model=list[TreatmentPlanItemRead],
    operation_id="list_patient_treatment_plan_items",
    summary="All of a patient's plan items in one call (PLAN-12)",
)
def patient_treatment_plan_items(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    include_archived: Annotated[bool, Query()] = False,
):
    return treatment_service.list_patient_items(
        db, patient_id, tenant_id, include_archived=include_archived
    )
