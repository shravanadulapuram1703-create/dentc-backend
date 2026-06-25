"""Restorative-charting supplemental routes (frontend restorative dev-report).

Generic CRUD covers chart-conditions, chart-status-templates, chart-tooth-notes.
These add the get-or-default / upsert / bulk / aggregate operations the chart needs:

- **REST-3** ``GET|PUT /chart-settings`` — per-patient view state (GET returns
  defaults when none).
- **REST-4** ``PUT /chart-tooth-notes/upsert`` — one note per (patient, tooth).
- bulk ``POST /chart-conditions/bulk`` — atomic span write with server group_id.
- aggregate ``GET /patients/{id}/chart`` — full chart state in one call.

Registered before generic CRUD so the literal sub-paths win over ``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.restorative import (
    BulkChartConditionsRequest,
    BulkChartConditionsResult,
    ChartAggregate,
    ChartSettingsRead,
    ChartSettingsUpsert,
    ChartToothNoteUpsert,
)
from app.services import restorative_service as svc

_auth = [Depends(get_current_user)]
_errs = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

router = APIRouter(tags=["Clinical"], dependencies=_auth, responses=_errs)


# ── REST-3: chart settings ───────────────────────────────────────────────────
@router.get("/chart-settings", response_model=ChartSettingsRead, operation_id="get_chart_settings",
            summary="Per-patient chart view settings (defaults if none) (REST-3)")
def get_chart_settings(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Query()]):
    return svc.get_settings(db, patient_id, tenant_id)


@router.put("/chart-settings", response_model=ChartSettingsRead, operation_id="upsert_chart_settings",
            summary="Upsert per-patient chart view settings (REST-3)")
def upsert_chart_settings(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                          body: ChartSettingsUpsert):
    return svc.upsert_settings(db, body.model_dump(), tenant_id, current.id)


# ── REST-4: per-tooth note upsert ────────────────────────────────────────────
@router.put("/chart-tooth-notes/upsert", response_model=ChartToothNoteUpsert,
            operation_id="upsert_chart_tooth_note",
            summary="Upsert a per-tooth note by (patient, tooth) (REST-4)")
def upsert_chart_tooth_note(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                            body: ChartToothNoteUpsert):
    row = svc.upsert_tooth_note(db, body.model_dump(), tenant_id, current.id)
    return ChartToothNoteUpsert(patient_id=row.patient_id, tooth=row.tooth, note=row.note)


# ── bulk condition write ─────────────────────────────────────────────────────
@router.post("/chart-conditions/bulk", response_model=BulkChartConditionsResult,
             status_code=status.HTTP_201_CREATED, operation_id="bulk_create_chart_conditions",
             summary="Atomically create a span of conditions with a shared group_id")
def bulk_create_chart_conditions(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                                 body: BulkChartConditionsRequest):
    gid, rows = svc.bulk_create_conditions(
        db, body.patient_id, body.group_id, body.conditions, tenant_id, current.id
    )
    return BulkChartConditionsResult(group_id=gid, conditions=rows)


# ── aggregate chart ──────────────────────────────────────────────────────────
@router.get("/patients/{patient_id}/chart", response_model=ChartAggregate,
            operation_id="get_patient_chart",
            summary="Full restorative chart state for a patient in one call")
def get_patient_chart(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    return svc.patient_chart(db, patient_id, tenant_id)
