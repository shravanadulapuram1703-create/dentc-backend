"""Lab Tracking (M12) — the non-CRUD surface (LAB-2/4/5 + the labs probe).

- GET /appointments/lab-cases                 office-wide / per-patient lab cases,
                                              denormalised + paged + status counts
- GET /appointments/lab-cases/cost-report     the legacy Lab Cost Report (JSON)
- GET /appointments/lab-cases/report.pdf      the legacy Lab Report (PDF)
- GET /appointments/lab-cases/cost-report.pdf Lab Cost Report (PDF)
- GET /appointments/lab-cases/export.csv      Excel-friendly export of the cases
- GET /labs/name-availability                 duplicate-name probe for the catalog
- GET /metadata/lab-tracking-rules            the published rule table

Mounted before the scheduler + generic CRUD routers so the literal
``/appointments/lab-cases`` wins over ``/appointments/{item_id}``.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.deps import CurrentUser, DbSession, PageParams, TenantId, get_current_user
from app.schemas.appointment import (
    LabCaseListResponse,
    LabCostReport,
    LabNameAvailability,
    LabStatusFilter,
)
from app.schemas.common import ErrorResponse
from app.services import lab_tracking_service as svc
from app.services import print_service

router = APIRouter(
    tags=["Appointments"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
metadata_router = APIRouter(
    tags=["Metadata"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}},
)

_PDF = {200: {"content": {"application/pdf": {}}, "description": "Rendered report"}}
_CSV = {200: {"content": {"text/csv": {}}, "description": "CSV export"}}


def lab_case_filters(  # noqa: PLR0913
    office_id: Annotated[int | None, Query(description="Scope to one office (LAB-5)")] = None,
    patient_id: Annotated[int | None, Query(description="Scope to one patient (the Lab Tracking tab)")] = None,
    provider_id: Annotated[str | None, Query()] = None,
    lab_vendor_id: Annotated[int | None, Query(description="Scope to one lab (see /labs)")] = None,
    lab_short_notice: Annotated[bool | None, Query()] = None,
    lab_status: Annotated[LabStatusFilter | None, Query(
        description="Derived status; not_received = sent OR overdue (the legacy Lab Report filter)",
    )] = None,
    date_from: Annotated[date | None, Query(description="Appointment date >=")] = None,
    date_to: Annotated[date | None, Query(description="Appointment date <=")] = None,
    lab_sent_from: Annotated[date | None, Query()] = None,
    lab_sent_to: Annotated[date | None, Query()] = None,
    lab_due_from: Annotated[date | None, Query()] = None,
    lab_due_to: Annotated[date | None, Query()] = None,
    lab_received_from: Annotated[date | None, Query()] = None,
    lab_received_to: Annotated[date | None, Query()] = None,
    include_archived: Annotated[bool, Query(
        description="LAB-11: include soft-deleted appointments. Off by default.",
    )] = False,
    as_of: Annotated[date | None, Query(
        description="The 'today' the status derivation uses. Defaults to the office's local "
                    "date when office_id is given, else UTC.",
    )] = None,
) -> dict[str, Any]:
    return {
        "office_id": office_id, "patient_id": patient_id, "provider_id": provider_id,
        "lab_vendor_id": lab_vendor_id, "short_notice": lab_short_notice, "lab_status": lab_status,
        "date_from": date_from, "date_to": date_to, "lab_sent_from": lab_sent_from,
        "lab_sent_to": lab_sent_to, "lab_due_from": lab_due_from, "lab_due_to": lab_due_to,
        "lab_received_from": lab_received_from, "lab_received_to": lab_received_to,
        "include_archived": include_archived, "as_of": as_of,
    }


LabCaseFilters = Annotated[dict[str, Any], Depends(lab_case_filters)]


def _audit(db, request: Request, tenant_id: int, user, report: str, params: dict) -> None:  # noqa: ANN001
    print_service.record_print(
        db, tenant_id=tenant_id, user_id=getattr(user, "id", None), patient_id=params.get("patient_id"),
        report=report, path=str(request.url.path), params=params, resource_type="lab_report",
    )


# ── LAB-2 / LAB-5 ────────────────────────────────────────────────────────────
@router.get(
    "/appointments/lab-cases",
    response_model=LabCaseListResponse,
    operation_id="list_lab_cases",
    summary="Lab cases (has_lab appointments) — denormalised, filtered, server-paged (LAB-2/5)",
    description=(
        "Office-wide or per-patient lab tracking in one call: patient / provider / office / "
        "lab names resolved, `lab_status` derived server-side, per-status `counts` computed "
        "over every filter except `lab_status` (so the review tabs keep their badges), and "
        "`total_cost` over the selected set. `sort` accepts date (default), lab_sent_on, "
        "lab_due_on, lab_received_on, lab_cost, patient_name, provider_name, lab_vendor_name, "
        "created_at, updated_at. `search` matches patient name / chart no / id, description, "
        "DDS and lab name."
    ),
)
def list_lab_cases(db: DbSession, tenant_id: TenantId, page: PageParams, filters: LabCaseFilters):
    return svc.list_lab_cases(
        db, tenant_id, page=page.page, size=page.size, sort=page.sort, order=page.order,
        search=page.search, **filters,
    )


# ── LAB-4 ────────────────────────────────────────────────────────────────────
@router.get(
    "/appointments/lab-cases/cost-report",
    response_model=LabCostReport,
    operation_id="get_lab_cost_report",
    summary="Lab Cost Report — lab_cost totals over a date range, grouped (LAB-4)",
)
def lab_cost_report(  # noqa: PLR0913
    db: DbSession, tenant_id: TenantId,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    date_basis: Annotated[Literal["appointment", "sent", "due", "received"], Query(
        description="Which date the range applies to",
    )] = "appointment",
    group_by: Annotated[Literal["vendor", "provider", "office", "month", "dds"], Query()] = "vendor",
    office_id: Annotated[int | None, Query()] = None,
    provider_id: Annotated[str | None, Query()] = None,
    lab_vendor_id: Annotated[int | None, Query()] = None,
    include_archived: Annotated[bool, Query()] = False,
):
    return svc.lab_cost_report(
        db, tenant_id, date_from=date_from, date_to=date_to, date_basis=date_basis,
        group_by=group_by, office_id=office_id, provider_id=provider_id,
        lab_vendor_id=lab_vendor_id, include_archived=include_archived,
    )


@router.get(
    "/appointments/lab-cases/report.pdf",
    operation_id="print_lab_report",
    summary="Lab Report (Not Sent / Not Received / Received / all) as a PDF (LAB-4)",
    response_class=Response,
    responses=_PDF,
)
def print_lab_report(
    request: Request, db: DbSession, tenant_id: TenantId, current: CurrentUser,
    filters: LabCaseFilters,
    sort: Annotated[str | None, Query()] = None,
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
):
    as_of = filters.get("as_of") or svc.resolve_as_of(db, filters.get("office_id"))
    rows = svc.all_lab_cases(db, tenant_id, sort=sort, order=order, **{**filters, "as_of": as_of})
    pdf = svc.render_lab_report_pdf(
        db, tenant_id, rows, office_id=filters.get("office_id"), lab_status=filters.get("lab_status"),
        date_from=filters.get("date_from"), date_to=filters.get("date_to"), as_of=as_of,
    )
    _audit(db, request, tenant_id, current, "lab_report", filters)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="lab-report.pdf"'})


@router.get(
    "/appointments/lab-cases/cost-report.pdf",
    operation_id="print_lab_cost_report",
    summary="Lab Cost Report as a PDF (LAB-4)",
    response_class=Response,
    responses=_PDF,
)
def print_lab_cost_report(  # noqa: PLR0913
    request: Request, db: DbSession, tenant_id: TenantId, current: CurrentUser,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    date_basis: Annotated[Literal["appointment", "sent", "due", "received"], Query()] = "appointment",
    group_by: Annotated[Literal["vendor", "provider", "office", "month", "dds"], Query()] = "vendor",
    office_id: Annotated[int | None, Query()] = None,
    provider_id: Annotated[str | None, Query()] = None,
    lab_vendor_id: Annotated[int | None, Query()] = None,
    include_archived: Annotated[bool, Query()] = False,
):
    data = svc.lab_cost_report(
        db, tenant_id, date_from=date_from, date_to=date_to, date_basis=date_basis,
        group_by=group_by, office_id=office_id, provider_id=provider_id,
        lab_vendor_id=lab_vendor_id, include_archived=include_archived,
    )
    pdf = svc.render_lab_cost_report_pdf(db, tenant_id, data, office_id=office_id)
    _audit(db, request, tenant_id, current, "lab_cost_report", {
        "date_from": date_from, "date_to": date_to, "date_basis": date_basis, "group_by": group_by,
        "office_id": office_id, "provider_id": provider_id, "lab_vendor_id": lab_vendor_id,
    })
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="lab-cost-report.pdf"'})


@router.get(
    "/appointments/lab-cases/export.csv",
    operation_id="export_lab_cases_csv",
    summary="Lab cases as CSV (Excel export, LAB-4)",
    response_class=Response,
    responses=_CSV,
)
def export_lab_cases_csv(
    request: Request, db: DbSession, tenant_id: TenantId, current: CurrentUser,
    filters: LabCaseFilters,
    sort: Annotated[str | None, Query()] = None,
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
):
    rows = svc.all_lab_cases(db, tenant_id, sort=sort, order=order, **filters)
    _audit(db, request, tenant_id, current, "lab_cases_csv", filters)
    return Response(content=svc.lab_cases_csv(rows), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="lab-cases.csv"'})


# ── labs catalog probe ───────────────────────────────────────────────────────
@router.get(
    "/labs/name-availability",
    response_model=LabNameAvailability,
    operation_id="get_lab_name_availability",
    summary="Is this lab name free? (the same check POST /labs enforces with a 409)",
)
def lab_name_availability(
    db: DbSession, tenant_id: TenantId,
    name: Annotated[str, Query(min_length=1)],
    exclude_id: Annotated[int | None, Query(description="Ignore this lab (editing it)")] = None,
):
    matches = svc.lab_name_matches(db, tenant_id, name, exclude_id=exclude_id)
    return {
        "name": " ".join(name.split()),
        "available": not matches,
        "conflicts": [{"id": m.id, "name": m.name, "office_id": m.office_id} for m in matches],
    }


# ── published rules ──────────────────────────────────────────────────────────
@metadata_router.get(
    "/metadata/lab-tracking-rules",
    operation_id="get_lab_tracking_rules",
    summary="Lab-field semantics, status derivation, implications and error codes (LAB-1/8/9)",
)
def lab_tracking_rules() -> dict:
    return svc.lab_tracking_rules()
