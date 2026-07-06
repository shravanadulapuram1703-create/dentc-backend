"""Utilities module — execution + audit endpoints (UTIL-1/2/3).

Authorization is enforced server-side (UTIL-3): running a utility requires an
admin role. Every run is persisted for the tenant-wide audit trail (UTIL-2).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user, require_roles
from app.schemas.common import ErrorResponse
from app.schemas.utilities import UtilityAuditList, UtilityRunRead, UtilityRunRequest
from app.services import utility_service

router = APIRouter(
    prefix="/utilities",
    tags=["Utilities"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.post("/{utility_id}/run", response_model=UtilityRunRead, status_code=201,
             operation_id="run_utility", dependencies=[Depends(require_roles("admin"))],
             responses={409: {"model": ErrorResponse}},
             summary="Submit a utility execution (UTIL-1/3) — records an audited run")
def run_utility(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                utility_id: Annotated[str, Path()], body: UtilityRunRequest | None = None):
    req = body or UtilityRunRequest()
    return utility_service.submit_run(
        db, tenant_id, current, utility_id, office_id=req.office_id, parameters=req.parameters
    )


@router.get("/jobs/{job_id}", response_model=UtilityRunRead, operation_id="get_utility_job",
            summary="Get a utility run's status / logs (UTIL-1)")
def get_utility_job(db: DbSession, tenant_id: TenantId, job_id: Annotated[int, Path()]):
    return utility_service.get_run(db, tenant_id, job_id)


@router.get("/audit", response_model=UtilityAuditList, operation_id="list_utility_audit",
            summary="Tenant-wide utility execution/audit history (UTIL-2)")
def list_utility_audit(
    db: DbSession, tenant_id: TenantId,
    utility_id: Annotated[str | None, Query()] = None,
    office_id: Annotated[int | None, Query()] = None,
    run_by: Annotated[int | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
    runs = utility_service.list_audit(
        db, tenant_id, utility_id=utility_id, office_id=office_id, run_by=run_by,
        date_from=date_from, date_to=date_to,
    )
    return UtilityAuditList(runs=runs)
