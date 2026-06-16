"""Procedure Code service endpoints that supplement the generated CRUD router.

Adds the KPI stats roll-up (PROC-5) and the per-code insurance rules sub-resource
(PROC-3). Registered before the generic ``/procedure-codes`` CRUD so the literal
``/stats`` path resolves before ``/{item_id}`` (the code string).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.procedure_setup import (
    ProcedureCodeStats,
    ProcedureInsuranceRuleCreate,
    ProcedureInsuranceRuleRead,
    ProcedureInsuranceRuleUpdate,
)
from app.services import procedure_setup_service as svc

router = APIRouter(
    prefix="/procedure-codes",
    tags=["Procedures"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.get(
    "/stats",
    response_model=ProcedureCodeStats,
    operation_id="get_procedure_code_stats",
    summary="Catalog KPI counts (total / active / inactive / ortho / by-category)",
)
def get_procedure_code_stats(db: DbSession, tenant_id: TenantId):
    return svc.stats(db)


CodeScope = Annotated[str, Path(description="Procedure code")]


def _require_code(code: CodeScope, db: DbSession) -> str:
    svc.get_code(db, code)
    return code


CodePath = Annotated[str, Depends(_require_code)]


@router.get(
    "/{code}/insurance-rules",
    response_model=list[ProcedureInsuranceRuleRead],
    operation_id="list_procedure_insurance_rules",
)
def list_procedure_insurance_rules(db: DbSession, tenant_id: TenantId, code: CodePath):
    return svc.list_insurance_rules(db, tenant_id, code)


@router.post(
    "/{code}/insurance-rules",
    response_model=ProcedureInsuranceRuleRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_procedure_insurance_rule",
)
def create_procedure_insurance_rule(
    db: DbSession, tenant_id: TenantId, code: CodePath,
    body: ProcedureInsuranceRuleCreate, current: CurrentUser,
):
    return svc.create_insurance_rule(db, tenant_id, code, body.model_dump(exclude_unset=True), current.id)


@router.patch(
    "/{code}/insurance-rules/{rule_id}",
    response_model=ProcedureInsuranceRuleRead,
    operation_id="update_procedure_insurance_rule",
)
def update_procedure_insurance_rule(
    db: DbSession, tenant_id: TenantId, code: CodePath, rule_id: int,
    body: ProcedureInsuranceRuleUpdate, current: CurrentUser,
):
    return svc.update_insurance_rule(db, tenant_id, code, rule_id, body.model_dump(exclude_unset=True), current.id)


@router.delete(
    "/{code}/insurance-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_procedure_insurance_rule",
)
def delete_procedure_insurance_rule(db: DbSession, tenant_id: TenantId, code: CodePath, rule_id: int):
    svc.delete_insurance_rule(db, tenant_id, code, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
