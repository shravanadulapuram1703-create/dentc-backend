"""Fee Schedule service endpoints that supplement the generated CRUD router.

Adds restore (FEE-1) and effective-date versioning (FEE-4). Registered before the
generic ``/fee-schedules`` CRUD so these literal sub-paths resolve first.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.fee_schedule import FeeScheduleRead, NewFeeScheduleVersionRequest
from app.schemas.procedure_setup import FeeScheduleOption
from app.services import estimate_service
from app.services import fee_schedule_service as svc
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
