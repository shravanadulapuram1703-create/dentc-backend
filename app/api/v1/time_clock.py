"""Time Clock routes (TC-BE-1…14).

Hand-written rather than generated from the registry: authorization here is by
*caller* (TC-BE-5 — a non-manager sees and punches only their own rows), which
the generic CRUD engine cannot express on list/get/delete. The five classic
routes keep the operation ids the registry used to emit
(``list_time_clock_entries``, ``create_time_clock_entry``, …) so the generated
client does not churn. Logic: :mod:`app.services.time_clock_service`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from app.api.deps import CurrentUser, DbSession, PageParams, TenantId
from app.core import concurrency
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.time_clock import (
    AutoCloseResult,
    ClockInRequest,
    ClockOutRequest,
    TimeClockEntryCreate,
    TimeClockEntryEditRead,
    TimeClockEntryRead,
    TimeClockEntryUpdate,
    TimeClockMetadata,
    TimeClockPeriodCreate,
    TimeClockPeriodRead,
    TimeClockPeriodUpdate,
    TimeClockReport,
    TimeClockSettingsRead,
    TimeClockSettingsUpdate,
)
from app.services import print_service
from app.services import time_clock_service as svc
from app.services.office_scope_service import OfficeContext, OfficeScopeDep

_ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}

router = APIRouter(prefix="/time-clock-entries", tags=["Staff"], responses=_ERRORS)
admin_router = APIRouter(prefix="/time-clock", tags=["Staff"], responses=_ERRORS)
report_router = APIRouter(prefix="/reports/time-clock", tags=["Staff"], responses=_ERRORS)

EntryId = Annotated[int, Path(description="time clock entry identifier")]
PeriodId = Annotated[int, Path(description="pay period identifier")]


def _caller(db: DbSession, current: CurrentUser) -> svc.Caller:
    return svc.caller_access(db, current)


Caller = Annotated[svc.Caller, Depends(_caller)]


def _read(db, tenant_id: int, entry) -> object:  # noqa: ANN001
    svc.enrich_entries(db, [entry], tenant_id)
    return entry


# ── TC-BE-1: server-stamped punches ──────────────────────────────────────────
@router.post(
    "/clock-in",
    response_model=TimeClockEntryRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="clock_in_time_clock",
    summary="Clock in — the server stamps now() (TC-BE-1/2)",
    description=(
        "Opens a shift for the **caller**; the time is the server's clock, never the client's. "
        "`office_id` defaults to `X-Office-ID`. **409 `already_clocked_in`** (the open entry in "
        "`error.details.entry`) when a shift is already running. A shift left open past the "
        "practice's `auto_close_after_hours` is first flagged as a missing clock-out (TC-BE-10), "
        "so yesterday's forgotten punch never blocks today's."
    ),
)
def clock_in(db: DbSession, tenant_id: TenantId, current: CurrentUser, office: OfficeContext,
             body: ClockInRequest | None = None):
    body = body or ClockInRequest()
    entry = svc.clock_in(db, tenant_id, current, office, office_id=body.office_id,
                         entry_type=body.entry_type, notes=body.notes)
    return _read(db, tenant_id, entry)


@router.post(
    "/clock-out",
    response_model=TimeClockEntryRead,
    operation_id="clock_out_time_clock",
    summary="Clock out — closes the caller's open shift at now() (TC-BE-1/2)",
    description=(
        "**409 `not_clocked_in`** when the caller has no running shift. A shift past the "
        "auto-close threshold is flagged as a missing clock-out instead of paying the elapsed "
        "hours (`error.details.auto_closed_entry`)."
    ),
)
def clock_out(db: DbSession, tenant_id: TenantId, current: CurrentUser, body: ClockOutRequest | None = None):
    body = body or ClockOutRequest()
    return _read(db, tenant_id, svc.clock_out(db, tenant_id, current, notes=body.notes))


@router.get(
    "/me/active",
    response_model=TimeClockEntryRead,
    operation_id="get_my_active_time_clock_entry",
    summary="The caller's running shift — 200, or 204 when not clocked in",
    responses={204: {"description": "Not clocked in"}},
)
def my_active(db: DbSession, tenant_id: TenantId, current: CurrentUser):
    entry = svc.active_entry(db, tenant_id, current)
    if entry is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return _read(db, tenant_id, entry)


# ── list / get (TC-BE-4/5/11) ────────────────────────────────────────────────
@router.get(
    "",
    response_model=PaginatedResponse[TimeClockEntryRead],
    operation_id="list_time_clock_entries",
    summary="List time clock entries",
    description=(
        "A non-manager always gets **their own** rows (another `user_id` is 403 "
        "`time_clock_forbidden`); managers follow the usual office scope (`office_id`, "
        "`office_ids`, `all_offices`). `clock_in_from` / `clock_in_to` take an ISO date "
        "(a whole office-local day, inclusive) or datetime; a bare date is read in `tz`, else the "
        "`office_id` office's zone, else the `X-Office-ID` office's. Soft-deleted rows are hidden "
        "unless `include_deleted=true` (managers). `search` matches the employee name / username "
        "and notes. Sort: clock_in (default), clock_out, created_at, updated_at, total_hours, user_id."
    ),
)
def list_entries(  # noqa: PLR0913
    db: DbSession,
    tenant_id: TenantId,
    page: PageParams,
    caller: Caller,
    scope: OfficeScopeDep,
    user_id: Annotated[int | None, Query(description="Filter by user_id")] = None,
    office_id: Annotated[int | None, Query(description="Filter by office_id")] = None,
    clock_in_from: Annotated[str | None, Query(description="clock_in >= (ISO date or datetime)")] = None,
    clock_in_to: Annotated[str | None, Query(description="clock_in <= (ISO date = whole day, or datetime)")] = None,
    tz: Annotated[str | None, Query(description="IANA zone for bare-date bounds")] = None,
    entry_type: Annotated[str | None, Query(description="work | break | lunch")] = None,
    source: Annotated[str | None, Query(description="punch | manual | legacy")] = None,
    is_open: Annotated[bool | None, Query(description="Running shifts only (true) / closed (false)")] = None,
    auto_closed: Annotated[bool | None, Query()] = None,
    is_edited: Annotated[bool | None, Query()] = None,
    is_active: Annotated[bool | None, Query(description="false = deleted rows only (managers)")] = None,
    include_deleted: Annotated[bool, Query(description="Include soft-deleted rows (managers)")] = False,
):
    items, total = svc.list_entries(
        db, tenant_id, caller, scope, page=page.page, size=page.size, sort=page.sort,
        order=page.order, search=page.search, user_id=user_id, office_id=office_id,
        clock_in_from=clock_in_from, clock_in_to=clock_in_to, tz=tz, entry_type=entry_type,
        source=source, is_open=is_open, auto_closed=auto_closed, is_edited=is_edited,
        include_deleted=include_deleted, is_active=is_active,
    )
    svc.enrich_entries(db, items, tenant_id)
    return PaginatedResponse.build(items, total, page.page, page.size)


@router.post(
    "",
    response_model=TimeClockEntryRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_time_clock_entry",
    summary="Create a time clock entry (manager) — or a self punch (transitional)",
    description=(
        "Managers (owner / admin / manager, or the Time Clock Editor right) add any user's entry "
        "with explicit times; `total_hours` is computed and the client value ignored. For anyone "
        "else, a self entry with no `clock_out` is treated as **clock-in** (server time, the body's "
        "`clock_in` discarded) — the path today's FE uses until it moves to `/clock-in`; any other "
        "body is 403 `time_clock_manager_required`."
    ),
)
def create_entry(db: DbSession, tenant_id: TenantId, caller: Caller, office: OfficeContext,
                 body: TimeClockEntryCreate):
    concurrency.reset()
    entry = svc.create_entry(db, tenant_id, caller, office, body.model_dump(exclude_unset=True))
    return _read(db, tenant_id, entry)


@router.get(
    "/{entry_id}",
    response_model=TimeClockEntryRead,
    operation_id="get_time_clock_entry",
    summary="Get time clock entry by id",
)
def get_entry(db: DbSession, tenant_id: TenantId, caller: Caller, entry_id: EntryId, response: Response):
    entry = _read(db, tenant_id, svc.get_entry(db, tenant_id, entry_id, caller))
    etag = concurrency.etag_for(entry)
    if etag:
        response.headers["ETag"] = etag
    return entry


@router.patch(
    "/{entry_id}",
    response_model=TimeClockEntryRead,
    operation_id="update_time_clock_entry",
    summary="Correct a time clock entry (manager)",
    description=(
        "Records the change in the entry's history (TC-BE-6) and keeps the first pre-edit times in "
        "`original_clock_in` / `original_clock_out`. `reason` is required for another user's entry "
        "when the practice sets `require_edit_reason`. 422 `clock_out_before_clock_in`, "
        "`punch_in_future`, `shift_too_long`; 409 `period_locked`, `already_clocked_in`. Honours "
        "`If-Match` / `If-Unmodified-Since` / `expected_updated_at` (412). A non-manager's "
        "`{clock_out}` on their own running shift is treated as **clock-out** at server time."
    ),
    responses={412: {"model": ErrorResponse}},
)
def update_entry(db: DbSession, tenant_id: TenantId, caller: Caller, office: OfficeContext,
                 entry_id: EntryId, body: TimeClockEntryUpdate, request: Request, response: Response):
    kwargs = {}
    if "expected_updated_at" in body.model_fields_set:
        kwargs["expected_updated_at"] = body.expected_updated_at
    concurrency.set_precondition(
        if_match=request.headers.get("if-match"),
        if_unmodified_since=request.headers.get("if-unmodified-since"),
        **kwargs,
    )
    entry = svc.update_entry(db, tenant_id, caller, office, entry_id, body.model_dump(exclude_unset=True))
    entry = _read(db, tenant_id, entry)
    etag = concurrency.etag_for(entry)
    if etag:
        response.headers["ETag"] = etag
    return entry


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_time_clock_entry",
    summary="Delete a time clock entry (manager, soft)",
    description="Soft delete (TC-BE-6): the row stays, flagged `is_active=false` with who / when / why.",
    responses={412: {"model": ErrorResponse}},
)
def delete_entry(db: DbSession, tenant_id: TenantId, caller: Caller, entry_id: EntryId, request: Request,
                 reason: Annotated[str | None, Query(max_length=500)] = None):
    concurrency.from_headers(request.headers)
    svc.delete_entry(db, tenant_id, caller, entry_id, reason=reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{entry_id}/restore",
    response_model=TimeClockEntryRead,
    operation_id="restore_time_clock_entry",
    summary="Restore a soft-deleted time clock entry (manager)",
)
def restore_entry(db: DbSession, tenant_id: TenantId, caller: Caller, entry_id: EntryId,
                  reason: Annotated[str | None, Query(max_length=500)] = None):
    return _read(db, tenant_id, svc.restore_entry(db, tenant_id, caller, entry_id, reason=reason))


@router.get(
    "/{entry_id}/history",
    response_model=list[TimeClockEntryEditRead],
    operation_id="get_time_clock_entry_history",
    summary="Who changed this punch, when, why, and the times before / after (TC-BE-6)",
)
def entry_history(db: DbSession, tenant_id: TenantId, caller: Caller, entry_id: EntryId):
    return svc.entry_history(db, tenant_id, caller, entry_id)


# ── settings / metadata / sweep (TC-BE-7/10) ─────────────────────────────────
@admin_router.get(
    "/metadata",
    response_model=TimeClockMetadata,
    operation_id="get_time_clock_metadata",
    summary="Vocabularies, practice settings, the caller's capabilities and overtime rule",
)
def get_metadata(db: DbSession, tenant_id: TenantId, caller: Caller):
    return svc.metadata(db, tenant_id, caller)


@admin_router.get(
    "/settings",
    response_model=TimeClockSettingsRead,
    operation_id="get_time_clock_settings",
    summary="Practice-level time-clock defaults (TC-BE-7/10)",
)
def get_settings(db: DbSession, tenant_id: TenantId):
    return svc.settings_dict(db, tenant_id)


@admin_router.put(
    "/settings",
    response_model=TimeClockSettingsRead,
    operation_id="update_time_clock_settings",
    summary="Update the practice-level time-clock defaults (manager)",
)
def put_settings(db: DbSession, tenant_id: TenantId, caller: Caller, body: TimeClockSettingsUpdate):
    svc.require_editor(caller)
    return svc.update_settings(db, tenant_id, body.model_dump(exclude_unset=True), actor_id=caller.id)


@admin_router.post(
    "/auto-close",
    response_model=AutoCloseResult,
    operation_id="auto_close_time_clock_entries",
    summary="Flag / close shifts left open past the threshold (TC-BE-10, manager)",
)
def run_auto_close(db: DbSession, tenant_id: TenantId, caller: Caller,
                   dry_run: Annotated[bool, Query()] = True):
    svc.require_editor(caller)
    return svc.auto_close_stale(db, tenant_id=tenant_id, dry_run=dry_run)


# ── pay periods (TC-BE-14) ───────────────────────────────────────────────────
@admin_router.get(
    "/periods",
    response_model=list[TimeClockPeriodRead],
    operation_id="list_time_clock_periods",
    summary="Pay periods (TC-BE-14)",
)
def list_periods(
    db: DbSession, tenant_id: TenantId, caller: Caller,
    office_id: Annotated[int | None, Query()] = None,
    locked: Annotated[bool | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
    svc.require_view_all(caller)
    return svc.list_periods(db, tenant_id, office_id=office_id, locked=locked,
                            date_from=date_from, date_to=date_to)


@admin_router.post(
    "/periods",
    response_model=TimeClockPeriodRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_time_clock_period",
    summary="Create a pay period (manager); 409 period_overlap",
)
def create_period(db: DbSession, tenant_id: TenantId, caller: Caller, body: TimeClockPeriodCreate):
    return svc.create_period(db, tenant_id, caller, body.model_dump())


@admin_router.patch(
    "/periods/{period_id}",
    response_model=TimeClockPeriodRead,
    operation_id="update_time_clock_period",
    summary="Edit a pay period's dates / notes (manager)",
)
def update_period(db: DbSession, tenant_id: TenantId, caller: Caller, period_id: PeriodId,
                  body: TimeClockPeriodUpdate):
    return svc.update_period(db, tenant_id, caller, period_id, body.model_dump(exclude_unset=True))


@admin_router.post(
    "/periods/{period_id}/{action}",
    response_model=TimeClockPeriodRead,
    operation_id="set_time_clock_period_state",
    summary="approve | lock | unlock | reopen a pay period (manager)",
    description="A locked period refuses every entry change inside it with 409 `period_locked`.",
)
def set_period_state(db: DbSession, tenant_id: TenantId, caller: Caller, period_id: PeriodId,
                     action: Literal["approve", "lock", "unlock", "reopen"]):
    return svc.set_period_state(db, tenant_id, caller, period_id, action)


@admin_router.delete(
    "/periods/{period_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_time_clock_period",
    summary="Delete an unlocked pay period (manager)",
)
def delete_period(db: DbSession, tenant_id: TenantId, caller: Caller, period_id: PeriodId):
    svc.delete_period(db, tenant_id, caller, period_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── the hours report (TC-BE-8/13) ────────────────────────────────────────────
def _report_params(
    date_from: Annotated[date, Query(alias="from", description="First work date (office-local)")],
    date_to: Annotated[date, Query(alias="to", description="Last work date, inclusive")],
    user_id: Annotated[int | None, Query()] = None,
    office_id: Annotated[int | None, Query()] = None,
    overtime_method: Annotated[str | None, Query(
        description="Override for this run: none | weekly | daily | daily_weekly",
    )] = None,
    include_wages: Annotated[bool, Query(description="TC-BE-13 (owner / admin only)")] = False,
) -> dict:
    return {"date_from": date_from, "date_to": date_to, "user_id": user_id, "office_id": office_id,
            "overtime_method": overtime_method, "include_wages": include_wages}


ReportParams = Annotated[dict, Depends(_report_params)]


def _audit(db, request: Request, tenant_id: int, user_id: int, report: str, params: dict) -> None:  # noqa: ANN001
    print_service.record_print(
        db, tenant_id=tenant_id, user_id=user_id, patient_id=None, report=report,
        path=str(request.url.path), params=params, resource_type="time_clock_report",
    )


@report_router.get(
    "",
    response_model=TimeClockReport,
    operation_id="get_time_clock_report",
    summary="Hours report — per user, per day, regular / overtime / total (TC-BE-8)",
    description=(
        "Days are the office-local date of clock-in. Overtime follows each user's configured "
        "rule (user config → practice default) unless `overtime_method` overrides it for the run; "
        "weekly overtime counts the part of the first week before `from`. Break / lunch entries "
        "are reported as `break_hours`, never paid. Non-managers get their own card only."
    ),
)
def get_report(db: DbSession, tenant_id: TenantId, caller: Caller, scope: OfficeScopeDep, params: ReportParams,
               include_entries: Annotated[bool, Query()] = True):
    return svc.build_report(db, tenant_id, caller, scope, include_entries=include_entries, **params)


@report_router.get(
    "/report.csv",
    operation_id="get_time_clock_report_csv",
    summary="Hours report as CSV — layout=summary | detail",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def get_report_csv(db: DbSession, tenant_id: TenantId, caller: Caller, scope: OfficeScopeDep,
                   params: ReportParams, request: Request,
                   layout: Annotated[Literal["summary", "detail"], Query()] = "summary"):
    report = svc.build_report(db, tenant_id, caller, scope, include_entries=layout == "detail", **params)
    _audit(db, request, tenant_id, caller.id, f"time_clock_{layout}_csv", params)
    name = f"time-clock-{params['date_from']}-{params['date_to']}-{layout}.csv"
    return Response(content=svc.report_csv(report, layout=layout), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@report_router.get(
    "/report.pdf",
    operation_id="get_time_clock_report_pdf",
    summary="Hours report as PDF (summary + optional per-employee detail)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_report_pdf(db: DbSession, tenant_id: TenantId, caller: Caller, scope: OfficeScopeDep,
                   params: ReportParams, request: Request,
                   detail: Annotated[bool, Query()] = True):
    report = svc.build_report(db, tenant_id, caller, scope, include_entries=detail, **params)
    _audit(db, request, tenant_id, caller.id, "time_clock_pdf", params)
    pdf = svc.report_pdf(db, tenant_id, report, office_id=params["office_id"], detail=detail)
    name = f"time-clock-{params['date_from']}-{params['date_to']}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})
