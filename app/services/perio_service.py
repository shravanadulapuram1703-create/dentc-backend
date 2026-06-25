"""Periodontal-charting business logic that supplements the generic CRUD engine.

Covers the perio dev-report gaps that need real behaviour rather than a plain
table mapping:

- **PERIO-BE-5/6** ``attach_actor_names`` — batch-resolve ``created_by`` /
  ``updated_by`` ids to display names (no N+1); wired into the CRUD engine's
  ``read_enrich`` hook for perio exams + details.
- **PERIO-BE-8** ``bulk_upsert_details`` — atomic insert-or-update of a whole
  chart keyed by ``tooth_no``.
- **PERIO-BE-10** ``compare_exams`` — per-exam clinical summaries + deltas.
- **PERIO-BE-11** ``get_or_create_my_settings`` / ``update_my_settings`` — the
  caller's own perio prefs, seeded on first access.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import (
    Patient,
    PerioChartSetting,
    PerioExam,
    PerioExamDetail,
)
from app.schemas.perio import (
    PerioComparisonResult,
    PerioExamComparisonDelta,
    PerioExamComparisonEntry,
    PerioExamSummary,
)
from app.services.user_admin_service import resolve_user_names

_PD_KEYS = tuple(f"pd{i}" for i in range(1, 7))
_CAL_KEYS = tuple(f"cal{i}" for i in range(1, 7))
_BLEED_KEYS = tuple(f"bleed{i}" for i in range(1, 7))
_SUPP_KEYS = tuple(f"supp{i}" for i in range(1, 7))


# ── PERIO-BE-5/6: resolve actor display names (read_enrich hook) ─────────────
def attach_actor_names(db: Session, items, tenant_id: int | None = None) -> None:  # noqa: ANN001, ARG001
    """Set transient ``created_by_name`` / ``updated_by_name`` on perio ORM rows.

    These are non-mapped attributes read by Pydantic ``from_attributes`` when the
    read schema is serialised. Mutates ``items`` in place. ``tenant_id`` is part
    of the engine's enrich signature but unused (perio rows aren't tenant-columned).
    """
    rows = list(items)
    wanted: set[int] = set()
    for row in rows:
        if getattr(row, "created_by", None) is not None:
            wanted.add(row.created_by)
        if getattr(row, "updated_by", None) is not None:
            wanted.add(row.updated_by)
    names = resolve_user_names(db, wanted)
    for row in rows:
        row.created_by_name = names.get(row.created_by) if row.created_by is not None else None
        row.updated_by_name = names.get(row.updated_by) if row.updated_by is not None else None


# ── tenant-safe parent lookups ───────────────────────────────────────────────
def _get_exam_in_tenant(db: Session, exam_id: int, tenant_id: int) -> PerioExam:
    """Load an exam and verify it belongs to a patient in ``tenant_id``.

    Perio tables aren't tenant-columned, so isolation is enforced through the
    patient → tenant link here (the generic engine can't, for these children)."""
    exam = db.get(PerioExam, exam_id)
    if exam is not None:
        patient = db.get(Patient, exam.patient_id)
        if patient is not None and patient.tenant_id == tenant_id:
            return exam
    raise NotFoundError(f"PerioExam '{exam_id}' was not found")


def _verify_patient_in_tenant(db: Session, patient_id: int, tenant_id: int) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


# ── PERIO-BE-8: atomic bulk upsert of a chart ────────────────────────────────
def bulk_upsert_details(
    db: Session,
    exam_id: int,
    items: list,
    tenant_id: int,
    actor_id: int | None,
) -> list[PerioExamDetail]:
    """Insert-or-update every supplied tooth row for ``exam_id`` in one
    transaction. Keyed by ``tooth_no`` so it enforces one row per tooth and is
    atomic (all-or-nothing)."""
    _get_exam_in_tenant(db, exam_id, tenant_id)

    existing = {
        row.tooth_no: row
        for row in db.execute(
            select(PerioExamDetail).where(PerioExamDetail.exam_id == exam_id)
        ).scalars()
    }

    result: list[PerioExamDetail] = []
    for item in items:
        data = item.model_dump(exclude_unset=True)
        tooth_no = data.pop("tooth_no")
        row = existing.get(tooth_no)
        if row is not None:
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_by = actor_id
        else:
            row = PerioExamDetail(
                exam_id=exam_id, tooth_no=tooth_no, created_by=actor_id, **data
            )
            db.add(row)
            existing[tooth_no] = row
        result.append(row)

    db.commit()
    for row in result:
        db.refresh(row)
    attach_actor_names(db, result)
    return result


# ── PERIO-BE-10: comparison / summary across exams ───────────────────────────
def _summarize(details: list[PerioExamDetail]) -> PerioExamSummary:
    pd_values: list[int] = []
    cal_values: list[int] = []
    bleeding = 0
    suppuration = 0
    for d in details:
        for key in _PD_KEYS:
            v = getattr(d, key)
            if v is not None:
                pd_values.append(v)
        for key in _CAL_KEYS:
            v = getattr(d, key)
            if v is not None:
                cal_values.append(v)
        for key in _BLEED_KEYS:
            if getattr(d, key):
                bleeding += 1
        for key in _SUPP_KEYS:
            if getattr(d, key):
                suppuration += 1

    sites_measured = len(pd_values)
    return PerioExamSummary(
        teeth_charted=len(details),
        sites_measured=sites_measured,
        mean_pd=round(sum(pd_values) / sites_measured, 2) if pd_values else None,
        max_pd=max(pd_values) if pd_values else None,
        sites_pd_4plus=sum(1 for v in pd_values if v >= 4),
        sites_pd_6plus=sum(1 for v in pd_values if v >= 6),
        bleeding_sites=bleeding,
        bleeding_pct=round(bleeding / sites_measured * 100, 1) if sites_measured else None,
        suppuration_sites=suppuration,
        mean_cal=round(sum(cal_values) / len(cal_values), 2) if cal_values else None,
        max_cal=max(cal_values) if cal_values else None,
    )


def _delta(prev: PerioExamSummary, curr: PerioExamSummary) -> PerioExamComparisonDelta:
    def diff(a: float | int | None, b: float | int | None):
        if a is None or b is None:
            return None
        return round(b - a, 2)

    return PerioExamComparisonDelta(
        mean_pd=diff(prev.mean_pd, curr.mean_pd),
        sites_pd_4plus=curr.sites_pd_4plus - prev.sites_pd_4plus,
        sites_pd_6plus=curr.sites_pd_6plus - prev.sites_pd_6plus,
        bleeding_pct=diff(prev.bleeding_pct, curr.bleeding_pct),
    )


def compare_exams(
    db: Session, patient_id: int, exam_ids: list[int], tenant_id: int
) -> PerioComparisonResult:
    """Summarise the given exams (oldest→newest) with deltas vs the prior exam."""
    _verify_patient_in_tenant(db, patient_id, tenant_id)

    exams = db.execute(
        select(PerioExam)
        .where(PerioExam.patient_id == patient_id, PerioExam.id.in_(exam_ids))
        .order_by(PerioExam.exam_date.asc(), PerioExam.id.asc())
    ).scalars().all()

    entries: list[PerioExamComparisonEntry] = []
    prev_summary: PerioExamSummary | None = None
    for exam in exams:
        details = db.execute(
            select(PerioExamDetail).where(PerioExamDetail.exam_id == exam.id)
        ).scalars().all()
        summary = _summarize(list(details))
        entries.append(
            PerioExamComparisonEntry(
                exam_id=exam.id,
                exam_date=exam.exam_date,
                is_voided=exam.is_voided,
                summary=summary,
                delta=_delta(prev_summary, summary) if prev_summary is not None else None,
            )
        )
        prev_summary = summary

    return PerioComparisonResult(patient_id=patient_id, exams=entries)


# ── PERIO-BE-11: caller's own perio chart settings ───────────────────────────
def get_or_create_my_settings(db: Session, user_id: int) -> PerioChartSetting:
    row = db.execute(
        select(PerioChartSetting).where(PerioChartSetting.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        row = PerioChartSetting(user_id=user_id)  # model defaults seed the row
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_my_settings(db: Session, user_id: int, data: dict) -> PerioChartSetting:
    row = get_or_create_my_settings(db, user_id)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row
