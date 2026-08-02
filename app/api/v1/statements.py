"""Patient statement generation & delivery (STMT-1..3).

Mounted before the generic CRUD routers so the literal
``/patients/{id}/statements`` and ``/offices/{id}/statements/batch`` sub-paths win
over ``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from app.api.deps import DbSession, PageParams, TenantId, get_current_user
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.transactions import (
    StatementBatchRequest,
    StatementBatchResult,
    StatementCreate,
    StatementDeliverRequest,
    StatementRead,
)
from app.services import statement_service

router = APIRouter(
    tags=["Billing"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


# ── STMT-1: generate + list a single patient's statements ─────────────────────
@router.post(
    "/patients/{patient_id}/statements",
    response_model=StatementRead,
    status_code=201,
    operation_id="generate_patient_statement",
    summary="Generate a single-patient account statement (STMT-1)",
)
def generate_statement(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    body: StatementCreate | None = None,
    current=Depends(get_current_user),
):
    payload = (body or StatementCreate()).model_dump(exclude_unset=True)
    stmt = statement_service.generate_statement(db, patient_id, tenant_id, payload, actor_id=current.id)
    return statement_service._statement_out(stmt)


@router.get(
    "/patients/{patient_id}/statements",
    response_model=PaginatedResponse[StatementRead],
    operation_id="list_patient_statements",
    summary="List a patient's generated statements (STMT-1)",
)
def list_statements(
    db: DbSession,
    tenant_id: TenantId,
    page: PageParams,
    patient_id: Annotated[int, Path()],
):
    items, total = statement_service.list_statements(
        db, patient_id, tenant_id, page=page.page, size=page.size
    )
    return PaginatedResponse.build(items, total, page.page, page.size)


@router.get(
    "/patients/{patient_id}/statements/{statement_id}",
    response_model=StatementRead,
    operation_id="get_patient_statement",
    summary="Get one generated statement (STMT-1)",
)
def get_statement(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    statement_id: Annotated[int, Path()],
):
    return statement_service._statement_out(
        statement_service.get_statement(db, patient_id, statement_id, tenant_id)
    )


# ── STMT-3: PDF + delivery ───────────────────────────────────────────────────
@router.get(
    "/patients/{patient_id}/statements/{statement_id}/pdf",
    operation_id="get_patient_statement_pdf",
    summary="Render a generated statement to PDF (STMT-3)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Statement PDF"}},
)
def statement_pdf(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    statement_id: Annotated[int, Path()],
):
    pdf = statement_service.render_pdf(db, patient_id, statement_id, tenant_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="statement-{statement_id}.pdf"'},
    )


@router.post(
    "/patients/{patient_id}/statements/{statement_id}/deliver",
    response_model=StatementRead,
    operation_id="deliver_patient_statement",
    summary="Record statement delivery (print/email/download) (STMT-3)",
)
def deliver_statement(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    statement_id: Annotated[int, Path()],
    body: StatementDeliverRequest | None = None,
):
    payload = (body or StatementDeliverRequest()).model_dump(exclude_unset=True)
    return statement_service.deliver(db, patient_id, statement_id, tenant_id, payload)


# ── STMT-2: batch run over an office's outstanding balances ──────────────────
@router.post(
    "/offices/{office_id}/statements/batch",
    response_model=StatementBatchResult,
    operation_id="generate_statement_batch",
    summary="Batch statements for an office's outstanding balances (STMT-2)",
)
def generate_batch(
    db: DbSession,
    tenant_id: TenantId,
    office_id: Annotated[int, Path()],
    body: StatementBatchRequest | None = None,
    current=Depends(get_current_user),
):
    payload = (body or StatementBatchRequest()).model_dump(exclude_unset=True)
    return statement_service.generate_batch(db, office_id, tenant_id, payload, actor_id=current.id)
