"""Restorative-charting schemas (frontend restorative dev-report).

Covers the supplemental endpoints: per-patient chart settings (REST-3), per-tooth
note upsert (REST-4), atomic bulk condition write with a server-assigned group_id,
and the aggregate ``GET /patients/{id}/chart`` payload. Generic CRUD over
``chart-status-templates`` / ``chart-tooth-notes`` is driven from the registry.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.db import models as m
from app.schemas.common import ORMModel
from app.schemas.factory import build_schemas

# Distinct-name read schemas (avoid clashing with the generic CRUD components).
_ConditionRead = build_schemas(m.ChartCondition, "ChartConditionRow")[2]
_ProcedureRead = build_schemas(m.PatientProcedure, "ChartAggProcedure")[2]
_PlanItemRead = build_schemas(m.TreatmentPlanItem, "ChartAggPlanItem")[2]
_ToothNoteRead = build_schemas(m.ChartToothNote, "ChartAggToothNote")[2]
_ProgressNoteRead = build_schemas(m.ProgressNote, "ChartAggProgressNote")[2]


# ── REST-3: per-patient chart settings ───────────────────────────────────────
class ChartSettingsRead(ORMModel):
    patient_id: int
    numbering_system: str = "UNIVERSAL"
    wisdom_visible: bool = True
    occlusal_visible: bool = True
    show_base: bool = True
    show_healthy_pulp: bool = False
    edentulous: bool = False
    arch_mode: str = "both"
    updated_by: Optional[int] = None
    updated_at: Optional[datetime] = None


class ChartSettingsUpsert(BaseModel):
    patient_id: int
    numbering_system: Optional[str] = None
    wisdom_visible: Optional[bool] = None
    occlusal_visible: Optional[bool] = None
    show_base: Optional[bool] = None
    show_healthy_pulp: Optional[bool] = None
    edentulous: Optional[bool] = None
    arch_mode: Optional[str] = None


# ── REST-4: per-tooth note upsert ────────────────────────────────────────────
class ChartToothNoteUpsert(BaseModel):
    patient_id: int
    tooth: str
    note: Optional[str] = None


# ── bulk condition write (atomic; server-assigned group_id) ──────────────────
class ChartConditionBulkItem(BaseModel):
    tooth: Optional[str] = None
    area: Optional[str] = None
    surface: Optional[str] = None
    region: Optional[str] = None
    condition_code: Optional[str] = None
    procedure_code: Optional[str] = None
    material_id: Optional[int] = None
    provider_id: Optional[str] = None
    office_id: Optional[int] = None
    chart_as: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    activity_date: Optional[date] = None
    # first-class qualifiers (REST-1/7/9)
    grade: Optional[str] = None
    segment: Optional[str] = None
    root_segment: Optional[str] = None
    tooth_status: Optional[str] = None
    root_scope: Optional[str] = None
    rct_fill: Optional[str] = None
    watch_dir: Optional[str] = None
    watch_x: Optional[int] = None
    watch_y: Optional[int] = None
    status: Optional[str] = None


class BulkChartConditionsRequest(BaseModel):
    patient_id: int
    # Omit to have the server assign one (groups a bridge/denture span); supply to
    # extend an existing group.
    group_id: Optional[str] = None
    conditions: list[ChartConditionBulkItem] = Field(..., min_length=1)


class BulkChartConditionsResult(BaseModel):
    group_id: str
    conditions: list[_ConditionRead]  # type: ignore[valid-type]


# ── aggregate GET /patients/{id}/chart ───────────────────────────────────────
class ChartAggregate(BaseModel):
    patient_id: int
    settings: ChartSettingsRead
    conditions: list[_ConditionRead]  # type: ignore[valid-type]
    procedures: list[_ProcedureRead]  # type: ignore[valid-type]
    plan_items: list[_PlanItemRead]  # type: ignore[valid-type]
    tooth_notes: list[_ToothNoteRead]  # type: ignore[valid-type]
    drawings: list[_ProgressNoteRead]  # type: ignore[valid-type]
