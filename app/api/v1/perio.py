"""Periodontal-charting supplemental endpoints (perio dev-report gaps).

Generic CRUD over the 5 perio resources already covers per-row reads/writes.
These add the operations the charting UI needs that the engine can't express:

- **PERIO-BE-8** ``PUT /perio-exams/{exam_id}/details`` — atomic bulk upsert of a
  whole chart keyed by ``tooth_no`` (one row per tooth, all-or-nothing).
- **PERIO-BE-10/15/17/18** ``GET /perio-exams/compare`` — per-exam clinical
  summaries + deltas, server-side; ``include_details=true`` embeds the per-tooth
  rows so the tooth-by-tooth table is one call; an unknown / foreign / voided
  id is an error, never silently dropped.
- **PERIO-BE-11** ``GET|PUT /perio-chart-settings/me`` — the caller's own prefs,
  seeded on first access (no need to know your own user id).

Registered *before* the generic perio CRUD so the literal sub-paths (``/compare``,
``/me``, ``/{exam_id}/details``) resolve before ``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.perio import (
    PerioChartSettingRead,
    PerioChartSettingUpdateMe,
    PerioComparisonResult,
    PerioExamDetailRead,
    PerioExamDetailsBulkUpsert,
)
from app.services import perio_service

router = APIRouter(
    tags=["Clinical"],
    dependencies=[Depends(get_current_user)],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)


@router.put(
    "/perio-exams/{exam_id}/details",
    response_model=list[PerioExamDetailRead],
    operation_id="bulk_upsert_perio_exam_details",
    summary="Atomically insert-or-update a chart's tooth rows (PERIO-BE-8)",
)
def bulk_upsert_perio_exam_details(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    body: PerioExamDetailsBulkUpsert,
    exam_id: Annotated[int, Path(description="Perio exam id")],
):
    return perio_service.bulk_upsert_details(
        db, exam_id, body.items, tenant_id, current.id
    )


@router.get(
    "/perio-exams/compare",
    response_model=PerioComparisonResult,
    operation_id="compare_perio_exams",
    summary="Summarise + delta perio exams across dates (PERIO-BE-10)",
)
def compare_perio_exams(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Query(description="Patient to compare exams for")],
    exam_ids: Annotated[list[int], Query(description="Exam ids to compare (repeat the key)")],
    include_details: Annotated[
        bool,
        Query(description="PERIO-BE-15: embed each exam's per-tooth detail rows, sorted by tooth"),
    ] = False,
    include_voided: Annotated[
        bool,
        Query(
            description=(
                "PERIO-BE-18: allow voided exams in the set. Without it a voided id is 422 "
                "``perio_exam_voided``; with it the entry is returned flagged and skipped as a "
                "delta baseline"
            )
        ),
    ] = False,
):
    """Errors (PERIO-BE-17): 404 ``perio_exam_not_found`` for an id that does not
    exist in this tenant, 422 ``exam_not_owned_by_patient`` for another patient's
    exam — ``details.exam_id`` names the offender in both."""
    return perio_service.compare_exams(
        db, patient_id, exam_ids, tenant_id,
        include_details=include_details, include_voided=include_voided,
    )


@router.get(
    "/perio-chart-settings/me",
    response_model=PerioChartSettingRead,
    operation_id="get_my_perio_chart_settings",
    summary="Get the caller's perio chart settings, seeding defaults (PERIO-BE-11)",
)
def get_my_perio_chart_settings(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
):
    return perio_service.get_or_create_my_settings(db, current.id)


@router.put(
    "/perio-chart-settings/me",
    response_model=PerioChartSettingRead,
    operation_id="update_my_perio_chart_settings",
    summary="Update the caller's perio chart settings (PERIO-BE-11)",
)
def update_my_perio_chart_settings(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    body: PerioChartSettingUpdateMe,
):
    data = body.model_dump(exclude_unset=True)
    return perio_service.update_my_settings(db, current.id, data)
