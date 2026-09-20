"""Dashboard aggregates (OFF-SCOPE-18).

The dashboard KPIs were computed client-side after page caps, and an "All
offices" view meant the browser looping the office roll-ups. This is the
server-side aggregate the report asks for:

``GET /dashboard/summary?office_id=&all_offices=&date=`` resolves the target
offices from the caller's office scope — one office, an explicit set, an office
group, the caller's assigned offices (the default), or the whole tenant with
``all_offices=true`` (which needs ``offices:view_all`` / ``reports:all_offices``)
— and sums the existing DASH-1/DASH-2 office roll-ups across them. The loop is on
the server; the client never fans out.
"""

from __future__ import annotations

from datetime import date as _date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import DbSession, TenantId, get_current_user
from app.db.models import Office
from app.schemas.common import ErrorResponse
from app.services import office_scope_service as oss
from app.services import transactions_service

router = APIRouter(
    prefix="/dashboard",
    tags=["Reports"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


def _tenant_office_ids(db, tenant_id: int) -> list[int]:  # noqa: ANN001
    return list(db.execute(
        select(Office.id).where(Office.tenant_id == tenant_id, Office.is_active.is_(True))
    ).scalars().all())


def _resolve_targets(db, tenant_id: int, scope: oss.OfficeScope, office_id: int | None) -> list[int]:  # noqa: ANN001
    if office_id is not None:
        oss.validate_target_office(scope, office_id)
        return [office_id]
    if scope.office_ids_param:
        for oid in scope.office_ids_param:
            oss.validate_target_office(scope, oid, field="office_ids")
        return list(scope.office_ids_param)
    if scope.office_group_id is not None:
        ids = oss.office_group_office_ids(db, tenant_id, scope.office_group_id)
        if not scope.unrestricted():
            ids = ids & scope.assigned_ids
        return sorted(ids)
    if scope.all_offices:
        oss.require_all_offices(scope, reports=True)
        return _tenant_office_ids(db, tenant_id)
    # Default: the caller's assigned offices (whole tenant when unrestricted).
    if scope.unrestricted():
        return _tenant_office_ids(db, tenant_id)
    return sorted(scope.assigned_ids)


@router.get(
    "/summary",
    operation_id="get_dashboard_summary",
    summary="Office(s) financial dashboard, aggregated server-side (OFF-SCOPE-18)",
)
def dashboard_summary(
    db: DbSession,
    tenant_id: TenantId,
    scope: oss.OfficeScopeDep,
    office_id: Annotated[int | None, Query(description="A single office (validated against your assignments)")] = None,
    date: Annotated[_date | None, Query(description="Collections day (default: today)")] = None,
):
    targets = _resolve_targets(db, tenant_id, scope, office_id)
    period = "today" if date is None else "custom"
    agg = {
        "outstanding_balance": Decimal(0),
        "patient_balance": Decimal(0),
        "insurance_receivable": Decimal(0),
        "credit_balance": Decimal(0),
        "patient_count": 0,
    }
    collections = {
        "patient_payments": Decimal(0),
        "insurance_payments": Decimal(0),
        "total_collections": Decimal(0),
        "payment_count": 0,
    }
    for oid in targets:
        s = transactions_service.office_financial_summary(db, oid, tenant_id)
        for key in ("outstanding_balance", "patient_balance", "insurance_receivable",
                    "credit_balance", "patient_count"):
            agg[key] += s[key]
        c = transactions_service.collections_summary(
            db, oid, tenant_id, period=period, date_from=date, date_to=date,
        )
        for key in ("patient_payments", "insurance_payments", "total_collections", "payment_count"):
            collections[key] += c[key]
    return {
        "office_ids": targets,
        "all_offices": scope.all_offices,
        "date": date,
        **agg,
        "collections": collections,
    }
