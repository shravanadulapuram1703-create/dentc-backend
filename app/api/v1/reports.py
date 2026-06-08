"""Reports module endpoints — practice-wide aggregation (FE dev-report gaps 1/2/3).

Server-side roll-ups so the Reports frontend stops fanning out CRUD list
endpoints (which truncate for large practices). All routes are tenant-scoped and
accept an optional ``office_id``; results are briefly Redis-cached in the service.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.reports import (
    AccountsReceivable,
    Aging,
    ReportSummary,
    ReportTrends,
)
from app.services import report_service

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)

_OfficeId = Annotated[int | None, Query(description="Scope to one office; omit for all offices")]


@router.get(
    "/summary",
    response_model=ReportSummary,
    operation_id="get_report_summary",
    summary="Executive KPIs (production, collections, patients, appointments, AR) for a window",
)
def get_summary(
    db: DbSession,
    tenant_id: TenantId,
    date_from: Annotated[date, Query(description="Window start (inclusive)")],
    date_to: Annotated[date, Query(description="Window end (inclusive)")],
    office_id: _OfficeId = None,
):
    return report_service.get_summary(db, tenant_id, office_id, date_from, date_to)


@router.get(
    "/trends",
    response_model=ReportTrends,
    operation_id="get_report_trends",
    summary="Production / collections / new-patient time series bucketed by interval",
)
def get_trends(
    db: DbSession,
    tenant_id: TenantId,
    date_from: Annotated[date, Query(description="Window start (inclusive)")],
    date_to: Annotated[date, Query(description="Window end (inclusive)")],
    interval: Annotated[Literal["day", "week", "month"], Query()] = "day",
    office_id: _OfficeId = None,
):
    return report_service.get_trends(db, tenant_id, office_id, date_from, date_to, interval)


@router.get(
    "/accounts-receivable",
    response_model=AccountsReceivable,
    operation_id="get_report_accounts_receivable",
    summary="Practice-wide outstanding AR (charges − payments − adjustments) as of a date",
)
def get_accounts_receivable(
    db: DbSession,
    tenant_id: TenantId,
    office_id: _OfficeId = None,
    as_of: Annotated[date | None, Query(description="Point in time; defaults to today")] = None,
):
    return report_service.get_accounts_receivable(db, tenant_id, office_id, as_of)


@router.get(
    "/aging",
    response_model=Aging,
    operation_id="get_report_aging",
    summary="Receivables aged into 30/60/90/120+ buckets as of a date",
)
def get_aging(
    db: DbSession,
    tenant_id: TenantId,
    office_id: _OfficeId = None,
    as_of: Annotated[date | None, Query(description="Point in time; defaults to today")] = None,
):
    return report_service.get_aging(db, tenant_id, office_id, as_of)
