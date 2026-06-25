"""Periodontal-charting schemas (addresses the frontend perio dev-report).

These are the *single source* of truth for the perio Create/Update/Read shapes:
both the generic CRUD registry and the supplemental router
(:mod:`app.api.v1.perio`) import from here, so each OpenAPI component name
(``PerioExamRead`` …) is defined exactly once.

What's customised over the plain factory output:
- **PERIO-BE-7** clinical value-range validation via constrained field types
  (PD/CAL 0–20, FGM −10…+10, MGJ 0–20, furcation 0–4, mobility 0–3).
- **PERIO-BE-2** mobility is decimal (half-grades).
- **PERIO-BE-4** ``cal1..6`` are first-class measurements.
- **PERIO-BE-5/6** read models expose audit columns + resolved actor names.
- **PERIO-BE-8** a bulk-upsert item/envelope keyed by ``tooth_no``.
- **PERIO-BE-10** comparison/summary response shapes.
- **PERIO-BE-12** a typed ``auto_advance`` template structure.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, Field, create_model

from app.db import models as m
from app.schemas.common import ORMModel
from app.schemas.factory import build_schemas

# ── PERIO-BE-7: clinical value ranges (constrained field types) ──────────────
PdValue = Annotated[int, Field(ge=0, le=20, description="Probing depth in mm (0–20)")]
CalValue = Annotated[int, Field(ge=0, le=20, description="Clinical attachment level in mm (0–20)")]
FgmValue = Annotated[int, Field(ge=-10, le=10, description="Free gingival margin in mm (−10…+10)")]
MgjValue = Annotated[int, Field(ge=0, le=20, description="Mucogingival junction width in mm (0–20)")]
FurcValue = Annotated[int, Field(ge=0, le=4, description="Furcation class (0–4)")]
MobilityValue = Annotated[
    Decimal,
    Field(ge=0, le=3, max_digits=2, decimal_places=1, description="Mobility grade (0–3, half-grades allowed)"),
]

_SITES = range(1, 7)


def _measurement_fields() -> dict[str, tuple]:
    """Validated, all-optional 6-site measurement fields shared by the detail
    Create/Update and bulk-upsert item schemas."""
    fields: dict[str, tuple] = {}
    for i in _SITES:
        fields[f"pd{i}"] = (Optional[PdValue], None)
        fields[f"fgm{i}"] = (Optional[FgmValue], None)
        fields[f"mgj{i}"] = (Optional[MgjValue], None)
        fields[f"cal{i}"] = (Optional[CalValue], None)
        fields[f"furc{i}"] = (Optional[FurcValue], None)
        fields[f"bleed{i}"] = (Optional[bool], None)
        fields[f"supp{i}"] = (Optional[bool], None)
    fields["mobility_buccal"] = (Optional[MobilityValue], None)
    fields["mobility_lingual"] = (Optional[MobilityValue], None)
    return fields


def _read_measurement_fields() -> dict[str, tuple]:
    """Unconstrained measurement fields for read models (echo whatever is stored)."""
    fields: dict[str, tuple] = {}
    for i in _SITES:
        for prefix in ("pd", "fgm", "mgj", "cal", "furc"):
            fields[f"{prefix}{i}"] = (Optional[int], None)
        fields[f"bleed{i}"] = (Optional[bool], None)
        fields[f"supp{i}"] = (Optional[bool], None)
    fields["mobility_buccal"] = (Optional[Decimal], None)
    fields["mobility_lingual"] = (Optional[Decimal], None)
    return fields


# ── Perio Exam (header) ──────────────────────────────────────────────────────
PerioExamCreate, PerioExamUpdate, _ = build_schemas(m.PerioExam, "PerioExam")


class PerioExamRead(ORMModel):
    """PERIO-BE-6: exam read with audit columns + resolved actor display names."""

    id: int
    patient_id: int
    office_id: Optional[int] = None
    legacy_id: Optional[str] = None
    exam_date: date
    notes: Optional[str] = None
    is_voided: bool
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None


# ── Perio Exam Detail (per-tooth) ────────────────────────────────────────────
PerioExamDetailCreate = create_model(
    "PerioExamDetailCreate",
    exam_id=(int, ...),
    tooth_no=(str, ...),
    **_measurement_fields(),
)

PerioExamDetailUpdate = create_model(
    "PerioExamDetailUpdate",
    tooth_no=(Optional[str], None),
    **_measurement_fields(),
)

PerioExamDetailRead = create_model(
    "PerioExamDetailRead",
    __base__=ORMModel,
    id=(int, ...),
    exam_id=(int, ...),
    tooth_no=(str, ...),
    created_at=(datetime, ...),
    updated_at=(Optional[datetime], None),
    created_by=(Optional[int], None),
    updated_by=(Optional[int], None),
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
    **_read_measurement_fields(),
)


# ── PERIO-BE-8: bulk upsert of a full chart, keyed by tooth_no ───────────────
PerioExamDetailUpsertItem = create_model(
    "PerioExamDetailUpsertItem",
    tooth_no=(str, ...),
    **_measurement_fields(),
)


class PerioExamDetailsBulkUpsert(BaseModel):
    """One transactional write of (part of) a chart. Each item is insert-or-update
    keyed by ``(exam_id, tooth_no)`` — naturally one row per tooth (PERIO-BE-1)."""

    items: list[PerioExamDetailUpsertItem] = Field(..., min_length=1)


# ── PERIO-BE-12: typed template auto-advance order ───────────────────────────
class PerioAutoAdvance(BaseModel):
    """Site-visiting order per arch/surface region. Each value is a direction
    string over the tooth sequence, e.g. ``"01-08"`` (ascending) or ``"08-01"``
    (descending). All eight regions are optional so partial templates are valid."""

    ur_facial: Optional[str] = None
    ur_lingual: Optional[str] = None
    ul_facial: Optional[str] = None
    ul_lingual: Optional[str] = None
    lr_facial: Optional[str] = None
    lr_lingual: Optional[str] = None
    ll_facial: Optional[str] = None
    ll_lingual: Optional[str] = None


class PerioChartTemplateCreate(BaseModel):
    name: str
    show_mgj: Optional[bool] = None
    pd_warning_level: Optional[int] = Field(None, ge=0, le=20)
    cal_warning_level: Optional[int] = Field(None, ge=0, le=20)
    bp_level: Optional[int] = Field(None, ge=0, le=20)
    ip_level: Optional[int] = Field(None, ge=0, le=20)
    fgm_level: Optional[int] = Field(None, ge=0, le=20)
    start_voice: Optional[bool] = None
    auto_advance: Optional[PerioAutoAdvance] = None


class PerioChartTemplateUpdate(BaseModel):
    name: Optional[str] = None
    show_mgj: Optional[bool] = None
    pd_warning_level: Optional[int] = Field(None, ge=0, le=20)
    cal_warning_level: Optional[int] = Field(None, ge=0, le=20)
    bp_level: Optional[int] = Field(None, ge=0, le=20)
    ip_level: Optional[int] = Field(None, ge=0, le=20)
    fgm_level: Optional[int] = Field(None, ge=0, le=20)
    start_voice: Optional[bool] = None
    auto_advance: Optional[PerioAutoAdvance] = None


class PerioChartTemplateRead(ORMModel):
    id: int
    tenant_id: int
    legacy_id: Optional[str] = None
    name: str
    show_mgj: bool
    pd_warning_level: int
    cal_warning_level: int
    bp_level: int
    ip_level: int
    fgm_level: int
    start_voice: bool
    auto_advance: Optional[PerioAutoAdvance] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ── Perio Chart Setting (per-user prefs) ─────────────────────────────────────
PerioChartSettingCreate, PerioChartSettingUpdate, PerioChartSettingRead = build_schemas(
    m.PerioChartSetting, "PerioChartSetting"
)


class PerioChartSettingUpdateMe(BaseModel):
    """PERIO-BE-11: update the caller's own prefs (``user_id`` is taken from the
    token, never the body)."""

    is_forward: Optional[bool] = None
    is_indicator: Optional[bool] = None
    is_mgj: Optional[bool] = None
    pd_level: Optional[int] = Field(None, ge=0, le=20)
    bp_level: Optional[int] = Field(None, ge=0, le=20)
    ip_level: Optional[int] = Field(None, ge=0, le=20)


# ── PERIO-BE-10: comparison / summary across exams ───────────────────────────
class PerioExamSummary(BaseModel):
    """Aggregate clinical metrics for a single exam (computed from its details)."""

    teeth_charted: int
    sites_measured: int
    mean_pd: Optional[float] = None
    max_pd: Optional[int] = None
    sites_pd_4plus: int
    sites_pd_6plus: int
    bleeding_sites: int
    bleeding_pct: Optional[float] = None
    suppuration_sites: int
    mean_cal: Optional[float] = None
    max_cal: Optional[int] = None


class PerioExamComparisonDelta(BaseModel):
    """Change vs the chronologically previous exam in the comparison set."""

    mean_pd: Optional[float] = None
    sites_pd_4plus: Optional[int] = None
    sites_pd_6plus: Optional[int] = None
    bleeding_pct: Optional[float] = None


class PerioExamComparisonEntry(BaseModel):
    exam_id: int
    exam_date: date
    is_voided: bool
    summary: PerioExamSummary
    delta: Optional[PerioExamComparisonDelta] = None


class PerioComparisonResult(BaseModel):
    patient_id: int
    exams: list[PerioExamComparisonEntry]
