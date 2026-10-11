"""Fee Schedule service endpoints that supplement the generated CRUD router.

Adds restore (FEE-1) and effective-date versioning (FEE-4). Registered before the
generic ``/fee-schedules`` CRUD so these literal sub-paths resolve first.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.fee_schedule import FeeScheduleRead, NewFeeScheduleVersionRequest
from app.schemas.procedure_setup import FeeScheduleOption
from app.services import estimate_service
from app.services import fee_schedule_service as svc
from app.services import fee_schedule_wizard_service as wizard_svc
from app.services import fee_vocab
from app.services import pricing_health_service
from app.services import pricing_service
from app.services import procedure_setup_service as proc_svc


class QuoteLine(BaseModel):
    procedure_code: str
    provider_id: str | None = None
    fee: float | None = None


class QuoteRequest(BaseModel):
    office_id: int | None = None
    provider_id: str | None = None
    ins_plan_id: int | None = None
    patient_id: int | None = None
    date_of_service: date | None = None
    lines: list[QuoteLine] = Field(default_factory=list)


class BulkEntry(BaseModel):
    procedure_code: str
    patient_fee: float | None = None
    insurance_fee: float | None = None
    amb_code: str | None = None
    is_no_charge: bool | None = None
    effective_date: date | None = None


class BulkEntriesRequest(BaseModel):
    effective_date: date | None = None
    entries: list[BulkEntry] = Field(default_factory=list)


class AdjustRequest(BaseModel):
    mode: str = Field(description="'percent' or 'amount'")
    value: float
    effective_date: date
    codes: list[str] | None = None


class ReassignPatientsRequest(BaseModel):
    to_fee_schedule_id: int
    patient_ids: list[int] | None = None


OnConflict = Literal["error", "rebind", "skip"]


class AssignmentRow(BaseModel):
    """One ``fee_schedule_assignments`` row. At least one of ``ins_plan_id`` /
    ``carrier_id`` / ``provider_id`` / ``specialty_id`` is required;
    ``office_id`` / ``office_group_id`` only narrow it. ``specialty_id`` is a
    taxonomy code or a specialty name (folded onto the code)."""

    model_config = ConfigDict(extra="forbid")

    fee_schedule_id: int | None = Field(
        None, description="Required on /fee-schedule-assignments/bulk; ignored by the wizard")
    ins_plan_id: int | None = None
    carrier_id: int | None = None
    provider_id: str | None = None
    specialty_id: str | None = None
    office_id: int | None = None
    office_group_id: int | None = None


class BulkAssignmentsRequest(BaseModel):
    on_conflict: OnConflict = Field(
        "error", description="An existing row binding the same target to another schedule: "
                             "'error' (409, nothing written), 'rebind' (re-point it), 'skip'")
    dry_run: bool = Field(False, description="Validate and report conflicts; write nothing")
    assignments: list[AssignmentRow] = Field(default_factory=list)


class WizardSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    fee_type: str | None = Field(
        None, description="ucr|standard|plan|carrier, or a legacy radio label (FSW-4) "
                          "such as 'Ins-PPO', which also sets pricing_model")
    pricing_model: str | None = None
    effective_date: date | None = None


class WizardOfficeDefaults(BaseModel):
    """FSW-3: "Office + All Providers" = the office's default fee-schedule pointer."""

    office_ids: list[int] = Field(default_factory=list)
    set_default_fee_schedule: bool = Field(
        False, description="Point offices.default_fee_schedule_id at the new schedule")
    set_ucr_fee_schedule: bool = Field(
        False, description="Point offices.default_ucr_fee_schedule_id at the new schedule")


class FeeScheduleWizardRequest(BaseModel):
    schedule: WizardSchedule
    entries_effective_date: date | None = Field(
        None, description="Defaults to schedule.effective_date, else today")
    copy_from_schedule_id: int | None = Field(
        None, description="Copy From Existing: start from that schedule's current prices")
    entries: list[BulkEntry] = Field(default_factory=list)
    assignments: list[AssignmentRow] = Field(default_factory=list)
    on_conflict: OnConflict = "error"
    office_defaults: WizardOfficeDefaults | None = None
    dry_run: bool = False

router = APIRouter(
    prefix="/fee-schedules",
    tags=["Procedures"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.get(
    "/options",
    response_model=list[FeeScheduleOption],
    operation_id="list_fee_schedule_options",
    summary="Lightweight active fee-schedule id→name/type projection (PROC-6)",
)
def list_fee_schedule_options(db: DbSession, tenant_id: TenantId):
    return proc_svc.fee_schedule_options(db, tenant_id)


@router.post(
    "/{schedule_id}/restore",
    response_model=FeeScheduleRead,
    operation_id="restore_fee_schedule",
    summary="Restore a soft-deleted fee schedule (is_active → true)",
)
def restore_fee_schedule(db: DbSession, tenant_id: TenantId, schedule_id: Annotated[int, Path()]):
    return svc.restore(db, schedule_id, tenant_id)


@router.post(
    "/{schedule_id}/new-version",
    response_model=FeeScheduleRead,
    operation_id="create_fee_schedule_version",
    summary="Clone a fee schedule and its entries under a new effective date",
)
def create_fee_schedule_version(
    db: DbSession,
    tenant_id: TenantId,
    schedule_id: Annotated[int, Path()],
    body: NewFeeScheduleVersionRequest,
):
    return svc.new_version(db, schedule_id, tenant_id, body.effective_date, body.name)


@router.get(
    "/metadata",
    operation_id="get_fee_schedule_metadata",
    summary="The pricing vocabulary + precedence card the Setup screens render (§3.1)",
)
def fee_schedule_metadata():
    """Fee types, pricing models, fee sources, assignment keys, the precedence
    card, and the warning/error code tables — served verbatim from ``fee_vocab``
    so the UI cannot paraphrase the hierarchy wrong."""
    return fee_vocab.metadata()


@router.get(
    "/{schedule_id}/usage",
    operation_id="get_fee_schedule_usage",
    summary="Where a fee schedule is used, and whether it can be retired (§3.5)",
)
def fee_schedule_usage(db: DbSession, tenant_id: TenantId, schedule_id: Annotated[int, Path()]):
    return svc.usage(db, schedule_id, tenant_id)


@router.post(
    "/{schedule_id}/retire",
    response_model=FeeScheduleRead,
    operation_id="retire_fee_schedule",
    summary="Soft-retire a fee schedule (refused while it is still referenced)",
)
def retire_fee_schedule(db: DbSession, tenant_id: TenantId, schedule_id: Annotated[int, Path()]):
    return svc.retire(db, schedule_id, tenant_id)


# ── POST /pricing/quote — a fee (and, with a patient, a split) preview ────────
pricing_router = APIRouter(
    prefix="/pricing",
    tags=["Procedures"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@pricing_router.post(
    "/quote",
    operation_id="quote_procedure_fees",
    summary="Price one or more lines for a context (scheduler / template / add-patient)",
)
def quote_procedure_fees(db: DbSession, tenant_id: TenantId, body: QuoteRequest):
    """With a ``patient_id`` this is the full estimate (fee + coverage split); with
    none it is a fee-only quote for the office/provider/plan/date context, so a
    screen can price before a patient or a date of service exists."""
    lines = [line.model_dump(exclude_none=True) for line in body.lines]
    if body.patient_id is not None:
        return estimate_service.estimate(
            db, body.patient_id, tenant_id, lines=lines,
            office_id=body.office_id, date_of_service=body.date_of_service,
        )
    return pricing_service.quote(
        db, tenant_id, office_id=body.office_id, provider_id=body.provider_id,
        ins_plan_id=body.ins_plan_id, date_of_service=body.date_of_service, lines=lines,
    )


# ── GET /setup/pricing-health — the per-office findings queue (§3.6) ──────────
setup_router = APIRouter(
    prefix="/setup",
    tags=["Procedures"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


@setup_router.get(
    "/pricing-health",
    operation_id="get_pricing_health",
    summary="Coded pricing-setup findings, each naming the screen that owns the fix",
)
def pricing_health(
    db: DbSession,
    tenant_id: TenantId,
    office_id: Annotated[int | None, Query(description="Limit office findings to one office")] = None,
):
    return pricing_health_service.report(db, tenant_id, office_id=office_id)


@router.put(
    "/{schedule_id}/entries/bulk",
    operation_id="bulk_upsert_fee_schedule_entries",
    summary="Upsert many entries at once; a shared effective_date is the New Effective Date workflow",
)
def bulk_upsert_fee_schedule_entries(
    db: DbSession, tenant_id: TenantId, schedule_id: Annotated[int, Path()],
    body: BulkEntriesRequest,
):
    return svc.bulk_upsert_entries(
        db, schedule_id, tenant_id, effective_date=body.effective_date,
        entries=[e.model_dump(exclude_none=True) for e in body.entries],
    )


@router.post(
    "/{schedule_id}/adjust",
    operation_id="adjust_fee_schedule_entries",
    summary="Write a new dated set of prices adjusted from the current ones (percent or amount)",
)
def adjust_fee_schedule_entries(
    db: DbSession, tenant_id: TenantId, schedule_id: Annotated[int, Path()],
    body: AdjustRequest,
):
    return svc.adjust_entries(
        db, schedule_id, tenant_id, mode=body.mode, value=body.value,
        effective_date=body.effective_date, codes=body.codes,
    )


@router.post(
    "/{schedule_id}/reassign-patients",
    operation_id="reassign_fee_schedule_patients",
    summary="Move patients off this schedule onto another (Change Patient Fee Schedule)",
)
def reassign_fee_schedule_patients(
    db: DbSession, tenant_id: TenantId, schedule_id: Annotated[int, Path()],
    body: ReassignPatientsRequest,
):
    return svc.reassign_patients(
        db, schedule_id, tenant_id, to_fee_schedule_id=body.to_fee_schedule_id,
        patient_ids=body.patient_ids,
    )


# ── FSW-1: the New Fee Schedule Wizard in one transaction ────────────────────
# Declared before ``/{schedule_id}/…`` only for readability: POST /wizard cannot
# collide with the generic CRUD, which has no POST /{id}.
@router.post(
    "/wizard",
    status_code=201,
    operation_id="create_fee_schedule_wizard",
    summary="Create a fee schedule with its entries, assignments and office defaults atomically",
)
def create_fee_schedule_wizard(
    db: DbSession, tenant_id: TenantId, user: CurrentUser, body: FeeScheduleWizardRequest,
    response: Response,
):
    """All or nothing: an invalid entry, assignment or office (422) or an
    assignment conflict under ``on_conflict='error'`` (409) writes nothing, and
    ``error.details`` carries the full per-row report. ``dry_run`` returns that
    report with 200 (``ok`` true/false) without writing."""
    payload = body.model_dump()
    payload["entries"] = [e.model_dump(exclude_none=True) for e in body.entries]
    payload["assignments"] = [a.model_dump() for a in body.assignments]
    if body.dry_run:
        response.status_code = 200
    return wizard_svc.create_wizard(db, tenant_id, payload, user_id=user.id)


@router.get(
    "/{schedule_id}/scope",
    operation_id="get_fee_schedule_scope",
    summary="Offices, providers, specialties, payers and office pointers a schedule is bound to",
)
def get_fee_schedule_scope(db: DbSession, tenant_id: TenantId, schedule_id: Annotated[int, Path()]):
    return wizard_svc.scope(db, schedule_id, tenant_id)


@router.post(
    "/{schedule_id}/entries/import",
    operation_id="import_fee_schedule_entries",
    summary="Import fees from the CSV/XLSX template with a row-level report",
)
async def import_fee_schedule_entries(
    db: DbSession,
    tenant_id: TenantId,
    schedule_id: Annotated[int, Path()],
    file: Annotated[UploadFile, File(description=".csv or .xlsx: procedure_code, description, fee, "
                                                 "effective_date [, plan_pays, amb_code, no_charge]")],
    effective_date: Annotated[date | None, Form()] = None,
    dry_run: Annotated[bool, Form()] = False,
    all_or_nothing: Annotated[bool, Form()] = False,
):
    content = await file.read()
    # Sync DB work off the event loop (EDIT-PLAN-7).
    return await run_in_threadpool(
        wizard_svc.import_entries, db, schedule_id, tenant_id,
        filename=file.filename or "", content=content, effective_date=effective_date,
        dry_run=dry_run, all_or_nothing=all_or_nothing,
    )


# ── FSW-2: bulk assignments ──────────────────────────────────────────────────
assignments_router = APIRouter(
    prefix="/fee-schedule-assignments",
    tags=["Procedures"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


@assignments_router.post(
    "/bulk",
    operation_id="bulk_create_fee_schedule_assignments",
    summary="Create / re-bind many fee-schedule assignments in one transaction",
)
def bulk_create_fee_schedule_assignments(
    db: DbSession, tenant_id: TenantId, user: CurrentUser, body: BulkAssignmentsRequest,
):
    """Per-row outcome: created | rebound | unchanged | skipped | conflict | error.
    Any error (422) or, under ``on_conflict='error'``, any conflict (409) rolls
    the batch back with the report in ``error.details``. ``dry_run`` is the
    conflict probe: each conflict names the schedule it is currently bound to."""
    return wizard_svc.bulk_assign(
        db, tenant_id, [a.model_dump() for a in body.assignments],
        on_conflict=body.on_conflict, dry_run=body.dry_run, user_id=user.id,
    )


# ── FSW-5: the specialty catalog ─────────────────────────────────────────────
specialties_router = APIRouter(
    prefix="/provider-specialties",
    tags=["Organization"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}},
)


@specialties_router.get(
    "",
    operation_id="list_provider_specialties",
    summary="Dental taxonomy specialties with the tenant's providers under each",
)
def list_provider_specialties(
    db: DbSession, tenant_id: TenantId,
    include_inactive: Annotated[bool, Query(description="Count inactive providers too")] = False,
):
    return wizard_svc.specialty_catalog(db, tenant_id, include_inactive=include_inactive)
