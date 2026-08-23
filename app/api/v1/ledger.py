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
    summary=(
        "Denormalised account-ledger feed (charges+payments+adjustments+claims) "
        "with running balance (AL-1/2/4/5/7/8/9/11)"
    ),
)
def get_account_ledger(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    scope: Annotated[
        Literal["patient", "account"],
        Query(description=(
            "AL-11: 'patient' = this patient only; 'account' = every patient sharing "
            "the responsible_party_id, merged and server-paged"
        )),
    ] = "patient",
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    transaction_type: Annotated[
        Literal["all", "charge", "payment", "adjustment", "claim"],
        Query(description="Type filter (AL-4); 'claim' needs include_claims=true"),
    ] = "all",
    include_claims: Annotated[
        bool,
        Query(description=(
            "AL-8: interleave claim status events (Sent/Paid/Closed) as source_type='claim'. "
            "Informational — they never move the running balance"
        )),
    ] = False,
    include_archived: Annotated[
        bool, Query(description="Include rows from the legacy archive export (is_archived)")
    ] = False,
    sort_by: Annotated[
        Literal["date", "code", "provider", "amount", "patient"],
        Query(description="Sort column (AL-5)"),
    ] = "date",
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
):
    return ledger_service.get_account_ledger(
        db, patient_id, tenant_id, scope=scope, date_from=date_from, date_to=date_to,
        transaction_type=transaction_type, include_claims=include_claims,
        include_archived=include_archived, sort_by=sort_by, order=order, page=page, size=size,
    )
