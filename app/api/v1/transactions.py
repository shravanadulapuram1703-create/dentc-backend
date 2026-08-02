"""Transactions dashboard + unified cross-patient feed (DASH-1..5, SRCH-1/3).

Office-level financial aggregation and the global searchable transaction feed —
neither of which existed. Mounted before the generic CRUD routers so the literal
``/offices/{office_id}/financial-summary`` etc. win over ``/offices/{item_id}``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.transactions import (
    AdjustmentSummary,
    CollectionsSummary,
    InsuranceReceivables,
    OfficeFinancialSummary,
    TransactionFeed,
)
from app.services import transactions_service

router = APIRouter(
    tags=["Billing"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)

OfficeId = Annotated[int, Path(description="Office id")]
PeriodQ = Annotated[
    Literal["today", "week", "month", "year", "custom"], Query(description="Aggregation period")
]


# ── DASH-1 ────────────────────────────────────────────────────────────────────
@router.get(
    "/offices/{office_id}/financial-summary",
    response_model=OfficeFinancialSummary,
    operation_id="get_office_financial_summary",
    summary="Office outstanding / patient / insurance balances (DASH-1)",
)
def financial_summary(db: DbSession, tenant_id: TenantId, office_id: OfficeId):
    return transactions_service.office_financial_summary(db, office_id, tenant_id)


# ── DASH-2 ────────────────────────────────────────────────────────────────────
@router.get(
    "/offices/{office_id}/collections",
    response_model=CollectionsSummary,
    operation_id="get_office_collections",
    summary="Collections total for a period (DASH-2)",
)
def collections(
    db: DbSession,
    tenant_id: TenantId,
    office_id: OfficeId,
    period: PeriodQ = "today",
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
    return transactions_service.collections_summary(
        db, office_id, tenant_id, period=period, date_from=date_from, date_to=date_to
    )


# ── DASH-3 ────────────────────────────────────────────────────────────────────
@router.get(
    "/offices/{office_id}/insurance-receivables",
    response_model=InsuranceReceivables,
    operation_id="get_office_insurance_receivables",
    summary="Outstanding insurance A/R, total + by carrier (DASH-3)",
)
def insurance_receivables(db: DbSession, tenant_id: TenantId, office_id: OfficeId):
    return transactions_service.insurance_receivables(db, office_id, tenant_id)


# ── DASH-4 ────────────────────────────────────────────────────────────────────
@router.get(
    "/offices/{office_id}/adjustment-summary",
    response_model=AdjustmentSummary,
    operation_id="get_office_adjustment_summary",
    summary="Adjustment / write-off / refund totals for a period (DASH-4)",
)
def adjustment_summary(
    db: DbSession,
    tenant_id: TenantId,
    office_id: OfficeId,
    period: PeriodQ = "month",
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
    return transactions_service.adjustment_summary(
        db, office_id, tenant_id, period=period, date_from=date_from, date_to=date_to
    )


def _feed(
    db, tenant_id, *, office_id, search, transaction_type, status, date_from, date_to,
    amount_min, amount_max, transaction_number, page, size,
):  # noqa: ANN001, ANN202
    return transactions_service.transaction_feed(
        db, tenant_id, office_id=office_id, search=search, transaction_type=transaction_type,
        status=status, date_from=date_from, date_to=date_to, amount_min=amount_min,
        amount_max=amount_max, transaction_number=transaction_number, page=page, size=size,
    )


# ── DASH-5 ────────────────────────────────────────────────────────────────────
@router.get(
    "/offices/{office_id}/transactions",
    response_model=TransactionFeed,
    operation_id="get_office_transactions",
    summary="Office-scoped cross-patient transaction feed (DASH-5)",
)
def office_transactions(
    db: DbSession,
    tenant_id: TenantId,
    office_id: OfficeId,
    search: Annotated[str | None, Query()] = None,
    type: Annotated[  # noqa: A002 - matches the FE query key
        Literal["all", "charge", "payment", "adjustment", "refund", "claim"], Query()
    ] = "all",
    status: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    amount_min: Annotated[Decimal | None, Query()] = None,
    amount_max: Annotated[Decimal | None, Query()] = None,
    transaction_number: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return _feed(
        db, tenant_id, office_id=office_id, search=search, transaction_type=type, status=status,
        date_from=date_from, date_to=date_to, amount_min=amount_min, amount_max=amount_max,
        transaction_number=transaction_number, page=page, size=size,
    )


# ── SRCH-1/3: tenant-wide unified feed ───────────────────────────────────────
@router.get(
    "/transactions",
    response_model=TransactionFeed,
    operation_id="search_transactions",
    summary="Unified cross-patient transaction feed/search (SRCH-1/3)",
)
def search_transactions(
    db: DbSession,
    tenant_id: TenantId,
    search: Annotated[str | None, Query()] = None,
    type: Annotated[  # noqa: A002
        Literal["all", "charge", "payment", "adjustment", "refund", "claim"], Query()
    ] = "all",
    status: Annotated[str | None, Query()] = None,
    office_id: Annotated[int | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    amount_min: Annotated[Decimal | None, Query()] = None,
    amount_max: Annotated[Decimal | None, Query()] = None,
    transaction_number: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return _feed(
        db, tenant_id, office_id=office_id, search=search, transaction_type=type, status=status,
        date_from=date_from, date_to=date_to, amount_min=amount_min, amount_max=amount_max,
        transaction_number=transaction_number, page=page, size=size,
    )
