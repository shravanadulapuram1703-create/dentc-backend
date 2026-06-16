"""Fee Schedule service endpoints that supplement the generated CRUD router.

Adds restore (FEE-1) and effective-date versioning (FEE-4). Registered before the
generic ``/fee-schedules`` CRUD so these literal sub-paths resolve first.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.fee_schedule import FeeScheduleRead, NewFeeScheduleVersionRequest
from app.schemas.procedure_setup import FeeScheduleOption
from app.services import fee_schedule_service as svc
from app.services import procedure_setup_service as proc_svc

router = APIRouter(
    prefix="/fee-schedules",
    tags=["Procedures"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.get(
    "/options",
    response_model=list[FeeScheduleOption],
    operation_id="list_fee_schedule_options",
    summary="Lightweight active fee-schedule id→name/type projection (PROC-6)",
)
def list_fee_schedule_options(db: DbSession, tenant_id: TenantId):
    return proc_svc.fee_schedule_options(db, tenant_id)


@router.post(
    "/{schedule_id}/restore",
    response_model=FeeScheduleRead,
    operation_id="restore_fee_schedule",
    summary="Restore a soft-deleted fee schedule (is_active → true)",
)
def restore_fee_schedule(db: DbSession, tenant_id: TenantId, schedule_id: Annotated[int, Path()]):
    return svc.restore(db, schedule_id, tenant_id)


@router.post(
    "/{schedule_id}/new-version",
    response_model=FeeScheduleRead,
    operation_id="create_fee_schedule_version",
    summary="Clone a fee schedule and its entries under a new effective date",
)
def create_fee_schedule_version(
    db: DbSession,
    tenant_id: TenantId,
    schedule_id: Annotated[int, Path()],
    body: NewFeeScheduleVersionRequest,
):
    return svc.new_version(db, schedule_id, tenant_id, body.effective_date, body.name)
