"""Treatment-plan service endpoints that supplement generated CRUD."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.treatment import TreatmentPlanSummary
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
