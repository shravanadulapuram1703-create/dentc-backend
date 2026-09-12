"""Periodontal-charting business logic that supplements the generic CRUD engine.

Covers the perio dev-report gaps that need real behaviour rather than a plain
table mapping:

- **PERIO-BE-5/6/14** ``attach_actor_names`` — batch-resolve ``created_by`` /
  ``updated_by`` ids (and the exam's ``provider_id``) to display names (no
  N+1); wired into the CRUD engine's ``read_enrich`` hook for exams + details.
- **PERIO-BE-9/14 + tenancy** ``PerioExamCRUD`` — ``date_from``/``date_to``
  aliases for the exam-date range, ``provider_id`` validated against the
  tenant on write, and tenant scoping through the patient (the perio tables
  carry no ``tenant_id``, so the generic engine could not isolate them).
- **PERIO-BE-15 + tenancy** ``PerioExamDetailCRUD`` — ``?exam_ids=`` multi-exam
  filter, tenant scoping through exam -> patient.
- **PERIO-BE-8** ``bulk_upsert_details`` — atomic insert-or-update of a whole
  chart keyed by ``tooth_no``.
- **PERIO-BE-10/15/16/17/18** ``compare_exams`` — per-exam clinical summaries
  + deltas, optional per-tooth rows, percentages over probeable sites, and
  loud failures on unknown / foreign / voided ids.
- **PERIO-BE-11** ``get_or_create_my_settings`` / ``update_my_settings`` — the
  caller's own perio prefs, seeded on first access.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.crud.base import CRUDBase
from app.db.models import (
    Patient,
    PerioChartSetting,
    PerioExam,
    PerioExamDetail,
    Provider,
)
from app.schemas.perio import (
    PerioComparisonResult,
    PerioExamComparisonDelta,
    PerioExamComparisonEntry,
    PerioExamDetailRead,
    PerioExamSummary,
)
from app.services.user_admin_service import resolve_user_names

_SITES = range(1, 7)
_PD_KEYS = tuple(f"pd{i}" for i in _SITES)
_CAL_KEYS = tuple(f"cal{i}" for i in _SITES)
_BLEED_KEYS = tuple(f"bleed{i}" for i in _SITES)
_SUPP_KEYS = tuple(f"supp{i}" for i in _SITES)
#: Per-site numeric measurements — a non-null value is "a finding".
_NUMERIC_PREFIXES = ("pd", "cal", "fgm", "mgj", "furc")
#: Per-site flags — only ``True`` is a finding (the FE writes ``False`` for an
#: unticked box, which records nothing clinically).
_FLAG_PREFIXES = ("bleed", "supp")
SITES_PER_TOOTH = 6


# ── PERIO-BE-5/6/14: resolve display names (read_enrich hook) ────────────────
def _provider_names(db: Session, ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = db.execute(select(Provider.id, Provider.name).where(Provider.id.in_(ids))).all()
    return {pid: name for pid, name in rows}


def attach_actor_names(db: Session, items, tenant_id: int | None = None) -> None:  # noqa: ANN001, ARG001
    """Set transient ``created_by_name`` / ``updated_by_name`` (and, on rows that
    carry a ``provider_id``, ``provider_name``) on perio ORM rows.

    These are non-mapped attributes read by Pydantic ``from_attributes`` when the
    read schema is serialised. Mutates ``items`` in place. ``tenant_id`` is part
    of the engine's enrich signature but unused (perio rows aren't tenant-columned).
    """
    rows = list(items)
    wanted: set[int] = set()
    provider_ids: set[str] = set()
    for row in rows:
        if getattr(row, "created_by", None) is not None:
            wanted.add(row.created_by)
        if getattr(row, "updated_by", None) is not None:
            wanted.add(row.updated_by)
        if getattr(row, "provider_id", None):
            provider_ids.add(row.provider_id)
    names = resolve_user_names(db, wanted)
    providers = _provider_names(db, provider_ids)
    for row in rows:
        row.created_by_name = names.get(row.created_by) if row.created_by is not None else None
        row.updated_by_name = names.get(row.updated_by) if row.updated_by is not None else None
        if hasattr(row, "provider_id"):
            row.provider_name = providers.get(row.provider_id) if row.provider_id else None


# ── tenant-safe parent lookups ───────────────────────────────────────────────
def _tenant_patient_ids(tenant_id: int):
    """Subquery of the patient ids in ``tenant_id`` — the only handle the perio
    tables have on tenancy."""
    return select(Patient.id).where(Patient.tenant_id == tenant_id)


def _get_exam_in_tenant(db: Session, exam_id: int, tenant_id: int) -> PerioExam:
    """Load an exam and verify it belongs to a patient in ``tenant_id``.

    Perio tables aren't tenant-columned, so isolation is enforced through the
    patient → tenant link here (the generic engine can't, for these children)."""
    exam = db.get(PerioExam, exam_id)
    if exam is not None:
        patient = db.get(Patient, exam.patient_id)
        if patient is not None and patient.tenant_id == tenant_id:
            return exam
    raise NotFoundError(
        f"PerioExam '{exam_id}' was not found",
        details={"code": "perio_exam_not_found", "exam_id": exam_id},
    )


def _verify_patient_in_tenant(db: Session, patient_id: int, tenant_id: int) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


def _validate_provider(
    db: Session, provider_id: str | None, tenant_id: int | None, *, moving: bool
) -> None:
    """PERIO-BE-14: ``provider_id`` must be a provider of this tenant. An
    inactive provider only blocks a *move* (``moving``) — an exam already
    credited to a since-retired provider stays editable, as with labs."""
    if provider_id is None:
        return
    provider = db.get(Provider, provider_id)
    if provider is None or (tenant_id is not None and provider.tenant_id != tenant_id):
        raise ValidationError(
            f"Provider '{provider_id}' was not found",
            details={"code": "provider_not_found", "field": "provider_id", "provider_id": provider_id},
        )
    if moving and not provider.is_active:
        raise ValidationError(
            f"Provider '{provider_id}' is inactive",
            details={"code": "provider_inactive", "field": "provider_id", "provider_id": provider_id},
        )


class PerioExamCRUD(CRUDBase[PerioExam]):
    """Exam header rules the generic engine cannot express.

    - Tenant scoping through the patient (no ``tenant_id`` column) — without
      it any tenant could read / void / edit any exam by id.
    - ``date_from`` / ``date_to`` (PERIO-BE-9) as aliases of the engine's
      ``exam_date_from`` / ``exam_date_to``: the FE probed the short names
      and read a silently ignored filter as "no data".
    - ``provider_id`` (PERIO-BE-14) validated against the tenant on every write.
    - A create names a patient of this tenant (404 otherwise).
    """

    custom_filter_fields = ("date_from", "date_to")

    def _scope_tenant(self, stmt, tenant_id: int | None):  # noqa: ANN001
        if tenant_id is None:
            return stmt
        return stmt.where(PerioExam.patient_id.in_(_tenant_patient_ids(tenant_id)))

    def _extra_list_clauses(self, filters: dict[str, Any]) -> list:
        clauses = []
        lo, hi = filters.get("date_from"), filters.get("date_to")
        if lo is not None:
            clauses.append(PerioExam.exam_date >= lo)
        if hi is not None:
            clauses.append(PerioExam.exam_date <= hi)
        return clauses

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        if tenant_id is not None and data.get("patient_id") is not None:
            _verify_patient_in_tenant(db, data["patient_id"], tenant_id)
        _validate_provider(db, data.get("provider_id"), tenant_id, moving=True)
        return super().create(db, data, tenant_id=tenant_id, created_by=created_by)

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        if data.get("provider_id") is not None:
            current = self.get(db, obj_id, tenant_id=tenant_id)
            _validate_provider(
                db, data["provider_id"], tenant_id,
                moving=data["provider_id"] != current.provider_id,
            )
        return super().update(db, obj_id, data, tenant_id=tenant_id, updated_by=updated_by)


def _parse_id_list(raw: str | None) -> list[int] | None:
    if raw is None:
        return None
    out: list[int] = []
    for chunk in str(raw).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(int(chunk))
        except ValueError:
            continue
    return out


class PerioExamDetailCRUD(CRUDBase[PerioExamDetail]):
    """Per-tooth rows: tenant scoping through exam -> patient, and
    ``?exam_ids=1,2,3`` (PERIO-BE-15) so a multi-date comparison reads every
    exam's rows in one call — a repeated ``exam_id`` key was last-wins.
    An empty / unparseable ``exam_ids`` matches nothing rather than
    un-filtering (the PT-SEARCH-1 rule)."""

    custom_filter_fields = ("exam_ids",)

    def _scope_tenant(self, stmt, tenant_id: int | None):  # noqa: ANN001
        if tenant_id is None:
            return stmt
        return stmt.where(
            PerioExamDetail.exam_id.in_(
                select(PerioExam.id).where(PerioExam.patient_id.in_(_tenant_patient_ids(tenant_id)))
            )
        )

    def _extra_list_clauses(self, filters: dict[str, Any]) -> list:
        ids = _parse_id_list(filters.get("exam_ids"))
        if ids is None:
            return []
        if not ids:
            return [PerioExamDetail.id.is_(None)]
        return [PerioExamDetail.exam_id.in_(ids)]

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        if tenant_id is not None and data.get("exam_id") is not None:
            _get_exam_in_tenant(db, data["exam_id"], tenant_id)
        return super().create(db, data, tenant_id=tenant_id, created_by=created_by)


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


# ── PERIO-BE-10/16: comparison / summary across exams ────────────────────────
def _pct(numerator: int, denominator: int) -> float | None:
    """``numerator / denominator × 100`` rounded to 0.1 and clamped to 0–100;
    ``None`` when there is nothing to divide by (PERIO-BE-16)."""
    if denominator <= 0:
        return None
    return max(0.0, min(100.0, round(numerator / denominator * 100, 1)))


def _site_has_finding(detail: PerioExamDetail, site: int) -> bool:
    for prefix in _NUMERIC_PREFIXES:
        if getattr(detail, f"{prefix}{site}") is not None:
            return True
    return any(getattr(detail, f"{prefix}{site}") for prefix in _FLAG_PREFIXES)


def _summarize(details: list[PerioExamDetail]) -> PerioExamSummary:
    pd_values: list[int] = []
    cal_values: list[int] = []
    bleeding = 0
    suppuration = 0
    sites_with_findings = 0
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
        sites_with_findings += sum(1 for site in _SITES if _site_has_finding(d, site))

    teeth = len(details)
    probeable = teeth * SITES_PER_TOOTH
    sites_measured = len(pd_values)
    return PerioExamSummary(
        teeth_charted=teeth,
        probeable_sites=probeable,
        sites_measured=sites_measured,
        sites_with_findings=sites_with_findings,
        mean_pd=round(sum(pd_values) / sites_measured, 2) if pd_values else None,
        max_pd=max(pd_values) if pd_values else None,
        sites_pd_4plus=sum(1 for v in pd_values if v >= 4),
        sites_pd_6plus=sum(1 for v in pd_values if v >= 6),
        bleeding_sites=bleeding,
        bleeding_pct=_pct(bleeding, probeable),
        suppuration_sites=suppuration,
        suppuration_pct=_pct(suppuration, probeable),
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
        bleeding_sites=curr.bleeding_sites - prev.bleeding_sites,
        bleeding_pct=diff(prev.bleeding_pct, curr.bleeding_pct),
        suppuration_sites=curr.suppuration_sites - prev.suppuration_sites,
        suppuration_pct=diff(prev.suppuration_pct, curr.suppuration_pct),
        mean_cal=diff(prev.mean_cal, curr.mean_cal),
    )


def tooth_sort_key(tooth_no: str) -> tuple[int, int, str]:
    """Universal numbering sorts numerically (``"10"`` after ``"9"``); anything
    else (primary letters, supernumerary codes) sorts after, alphabetically."""
    t = (tooth_no or "").strip()
    if t.isdigit():
        return (0, int(t), "")
    return (1, 0, t.upper())


def compare_exams(
    db: Session,
    patient_id: int,
    exam_ids: list[int],
    tenant_id: int,
    *,
    include_details: bool = False,
    include_voided: bool = False,
) -> PerioComparisonResult:
    """Summarise the given exams (oldest→newest) with deltas vs the prior
    **live** exam.

    PERIO-BE-17: every requested id must resolve — 404 ``perio_exam_not_found``
    for an id that does not exist (in this tenant), 422
    ``exam_not_owned_by_patient`` for another patient's exam. Nothing is
    silently dropped, so "no such exam" can never read as "no data".
    PERIO-BE-18: a voided exam is 422 ``perio_exam_voided`` unless
    ``include_voided``; when included it is returned flagged, carries no
    ``delta`` and is never the baseline for the next exam's ``delta``.
    PERIO-BE-15: ``include_details`` embeds each exam's tooth rows.
    """
    _verify_patient_in_tenant(db, patient_id, tenant_id)
    wanted = list(dict.fromkeys(exam_ids))  # de-duplicate, keep request order
    if not wanted:
        return PerioComparisonResult(
            patient_id=patient_id, include_details=include_details,
            include_voided=include_voided, exams=[],
        )

    rows = db.execute(select(PerioExam).where(PerioExam.id.in_(wanted))).scalars().all()
    by_id = {e.id: e for e in rows}
    owner_ids = {e.patient_id for e in rows}
    in_tenant: set[int] = set(
        db.execute(
            select(Patient.id).where(Patient.id.in_(owner_ids), Patient.tenant_id == tenant_id)
        ).scalars()
    ) if owner_ids else set()

    for exam_id in wanted:
        exam = by_id.get(exam_id)
        if exam is None or exam.patient_id not in in_tenant:
            raise NotFoundError(
                f"PerioExam '{exam_id}' was not found",
                details={"code": "perio_exam_not_found", "exam_id": exam_id},
            )
        if exam.patient_id != patient_id:
            raise ValidationError(
                f"PerioExam '{exam_id}' does not belong to patient '{patient_id}'",
                details={
                    "code": "exam_not_owned_by_patient",
                    "exam_id": exam_id,
                    "patient_id": patient_id,
                },
            )
        if exam.is_voided and not include_voided:
            raise ValidationError(
                f"PerioExam '{exam_id}' is voided (pass include_voided=true to compare it)",
                details={"code": "perio_exam_voided", "exam_id": exam_id},
            )

    exams = sorted(rows, key=lambda e: (e.exam_date, e.id))
    attach_actor_names(db, exams)

    # One statement for every exam's rows (was one per exam).
    details_by_exam: dict[int, list[PerioExamDetail]] = {e.id: [] for e in exams}
    all_details = db.execute(
        select(PerioExamDetail).where(PerioExamDetail.exam_id.in_(wanted))
    ).scalars().all()
    for d in all_details:
        details_by_exam[d.exam_id].append(d)
    if include_details:
        attach_actor_names(db, all_details)

    entries: list[PerioExamComparisonEntry] = []
    prev_live: tuple[int, PerioExamSummary] | None = None
    for exam in exams:
        details = sorted(details_by_exam[exam.id], key=lambda d: tooth_sort_key(d.tooth_no))
        summary = _summarize(details)
        delta = None
        delta_vs = None
        if not exam.is_voided and prev_live is not None:
            delta_vs, prev_summary = prev_live
            delta = _delta(prev_summary, summary)
        entries.append(
            PerioExamComparisonEntry(
                exam_id=exam.id,
                exam_date=exam.exam_date,
                is_voided=exam.is_voided,
                provider_id=exam.provider_id,
                provider_name=exam.provider_name,
                summary=summary,
                delta=delta,
                delta_vs_exam_id=delta_vs,
                details=(
                    [PerioExamDetailRead.model_validate(d) for d in details]
                    if include_details else None
                ),
            )
        )
        if not exam.is_voided:
            prev_live = (exam.id, summary)

    return PerioComparisonResult(
        patient_id=patient_id,
        include_details=include_details,
        include_voided=include_voided,
        exams=entries,
    )


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
