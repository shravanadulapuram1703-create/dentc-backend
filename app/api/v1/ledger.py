"""Patient ledger feed endpoint (Phase 3 / C-3, optional aggregate)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.billing import AccountLedgerResponse, LedgerResponse
from app.services import ledger_service

router = APIRouter(prefix="/patients", tags=["Billing"], dependencies=[Depends(get_current_user)])


@router.get(
    "/{patient_id}/ledger",
    response_model=LedgerResponse,
    operation_id="get_patient_ledger",
    summary="Get a patient's ledger feed with running balance (sortable/filterable, LED-1)",
)
def get_ledger(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    transaction_type: Annotated[
        Literal["all", "procedure", "charge", "payment"],
        Query(description="Filter by transaction type (LED-1)"),
    ] = "all",
    status: Annotated[str | None, Query(description="Filter by billing status (LED-1)")] = None,
    sort_by: Annotated[
        Literal["date", "amount", "code", "provider", "status"],
        Query(description="Sort column (LED-1)"),
    ] = "date",
    sort_order: Annotated[Literal["asc", "desc"], Query()] = "asc",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
):
    return ledger_service.get_patient_ledger(
        db, patient_id, tenant_id, date_from=date_from, date_to=date_to,
        transaction_type=transaction_type, status=status, sort_by=sort_by,
        sort_order=sort_order, page=page, size=size,
    )


@router.get(
    "/{patient_id}/account-ledger",
    response_model=AccountLedgerResponse,
    operation_id="get_patient_account_ledger",
    summary="Denormalised account-ledger feed (charges+payments+adjustments) with running balance (AL-1/2/4/5/7)",
)
def get_account_ledger(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    transaction_type: Annotated[
        Literal["all", "charge", "payment", "adjustment"], Query(description="Type filter (AL-4)")
    ] = "all",
    sort_by: Annotated[
        Literal["date", "code", "provider", "amount"], Query(description="Sort column (AL-5)")
    ] = "date",
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
):
    return ledger_service.get_account_ledger(
        db, patient_id, tenant_id, date_from=date_from, date_to=date_to,
        transaction_type=transaction_type, sort_by=sort_by, order=order, page=page, size=size,
    )
