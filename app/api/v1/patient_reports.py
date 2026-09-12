"""Server-rendered patient reports (PRINT-1) + the day-totals block (PRINT-6).

``GET /patients/{id}/reports/{overview|ledger|transactions|insurance}`` return
``application/pdf`` composed from the canonical data with the same query
parameters the screens already send, so each frontend ``*Print.ts`` builder can
become ``window.open(url)``. Every print is recorded in ``audit_logs``
(``action='PRINT'``).

Mounted before the generic CRUD routers so the literal ``/patients/{id}/reports``
sub-path wins over ``/{item_id}``.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.print import DayTotals
from app.services import print_service

router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)

PatientPath = Annotated[int, Path(description="Patient id")]
_PDF = {200: {"content": {"application/pdf": {}}, "description": "Rendered report"}}


def _pdf_response(pdf: bytes, filename: str) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def _audit(db, request: Request, tenant_id: int, user, patient_id: int, report: str, **params) -> None:  # noqa: ANN001
    print_service.record_print(
        db, tenant_id=tenant_id, user_id=getattr(user, "id", None), patient_id=patient_id,
        report=report, path=str(request.url.path), params=params,
    )


@router.get(
    "/{patient_id}/reports/overview",
    operation_id="get_patient_overview_report",
    summary="Patient Overview as a printable PDF (PRINT-1)",
    response_class=Response,
    responses=_PDF,
)
def overview_report(
    request: Request, db: DbSession, tenant_id: TenantId, current: CurrentUser, patient_id: PatientPath,
):
    pdf = print_service.render_overview(db, patient_id, tenant_id)
    _audit(db, request, tenant_id, current, patient_id, "overview")
    return _pdf_response(pdf, f"patient-overview-{patient_id}.pdf")


@router.get(
    "/{patient_id}/reports/ledger",
    operation_id="get_patient_ledger_report",
    summary="Account / Patient Ledger statement as a printable PDF (PRINT-1/3)",
    response_class=Response,
    responses=_PDF,
)
def ledger_report(
    request: Request, db: DbSession, tenant_id: TenantId, current: CurrentUser, patient_id: PatientPath,
    scope: Annotated[Literal["patient", "account"], Query(description="AL-11 scope")] = "patient",
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    transaction_type: Annotated[
        Literal["all", "charge", "payment", "adjustment", "claim"], Query(description="Type filter (AL-4)")
    ] = "all",
    include_claims: Annotated[bool, Query(description="AL-8: interleave claim status events")] = False,
    include_archived: Annotated[bool, Query(description="Include legacy archived rows")] = False,
    sort_by: Annotated[Literal["date", "code", "provider", "amount", "patient"], Query()] = "date",
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
):
    pdf = print_service.render_ledger(
        db, patient_id, tenant_id, scope=scope, date_from=date_from, date_to=date_to,
        transaction_type=transaction_type, include_claims=include_claims,
        include_archived=include_archived, sort_by=sort_by, order=order,
    )
    _audit(db, request, tenant_id, current, patient_id, "ledger", scope=scope, date_from=date_from,
           date_to=date_to, transaction_type=transaction_type, include_claims=include_claims,
           sort_by=sort_by, order=order)
    return _pdf_response(pdf, f"{scope}-ledger-{patient_id}.pdf")


@router.get(
    "/{patient_id}/reports/transactions",
    operation_id="get_patient_transactions_report",
    summary="Transactions Entry day sheet as a printable PDF (PRINT-1/6)",
    response_class=Response,
    responses=_PDF,
)
def transactions_report(
    request: Request, db: DbSession, tenant_id: TenantId, current: CurrentUser, patient_id: PatientPath,
    date: Annotated[date | None, Query(description="Transaction date; defaults to today in the home office's timezone")] = None,  # noqa: A002
):
    pdf = print_service.render_transactions(db, patient_id, tenant_id, date)
    _audit(db, request, tenant_id, current, patient_id, "transactions", date=date)
    return _pdf_response(pdf, f"transactions-{patient_id}-{date or 'today'}.pdf")


@router.get(
    "/{patient_id}/reports/insurance",
    operation_id="get_patient_insurance_report",
    summary="Insurance Details (one slot) as a printable PDF (PRINT-1/7/8)",
    response_class=Response,
    responses=_PDF,
)
def insurance_report(
    request: Request, db: DbSession, tenant_id: TenantId, current: CurrentUser, patient_id: PatientPath,
    category: Annotated[Literal["D", "M"], Query(description="D = dental, M = medical (legacy_plan_type)")] = "D",
    order: Annotated[
        Literal["primary", "secondary", "tertiary", "quaternary"], Query(description="insurance_type rank")
    ] = "primary",
):
    pdf = print_service.render_insurance(db, patient_id, tenant_id, category=category, order=order)
    _audit(db, request, tenant_id, current, patient_id, "insurance", category=category, order=order)
    return _pdf_response(pdf, f"insurance-{category}-{order}-{patient_id}.pdf")


@router.get(
    "/{patient_id}/day-totals",
    response_model=DayTotals,
    operation_id="get_patient_day_totals",
    summary="Today's charges / est ins / est pat / est deductible for one date (PRINT-6, CHG-7)",
)
def day_totals(
    db: DbSession, tenant_id: TenantId, patient_id: PatientPath,
    date: Annotated[date | None, Query(description="Defaults to today in the home office's timezone")] = None,  # noqa: A002
):
    return print_service.day_totals(db, patient_id, tenant_id, date)
