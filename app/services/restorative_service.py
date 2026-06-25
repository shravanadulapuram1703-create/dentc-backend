"""Restorative-charting business logic (frontend restorative dev-report).

- **REST-3** ``get_settings`` / ``upsert_settings`` — per-patient chart view state
  (returns defaults when none exist yet).
- **REST-4** ``upsert_tooth_note`` — one note per (patient, tooth).
- bulk condition write — atomic multi-row insert with a server-assigned
  ``group_id`` (bridge/denture span).
- aggregate ``patient_chart`` — conditions + procedures + plan items + tooth notes
  + drawings + settings in one payload (cuts the 4–6 open round-trips).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import (
    ChartCondition,
    ChartSettings,
    ChartToothNote,
    Patient,
    PatientProcedure,
    ProgressNote,
    TreatmentPlan,
    TreatmentPlanItem,
)


def _require_patient(db: Session, patient_id: int, tenant_id: int) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


# ── REST-3: chart settings ───────────────────────────────────────────────────
def get_settings(db: Session, patient_id: int, tenant_id: int) -> ChartSettings:
    """Return the patient's chart settings, or a transient default row (not
    persisted) when none exist yet — so the toolbar always has a value."""
    _require_patient(db, patient_id, tenant_id)
    row = db.get(ChartSettings, patient_id)
    # Transient default object (not persisted) — Python column defaults only apply
    # at INSERT, so set them explicitly for the never-saved case.
    return row or ChartSettings(
        patient_id=patient_id, numbering_system="UNIVERSAL", wisdom_visible=True,
        occlusal_visible=True, show_base=True, show_healthy_pulp=False,
        edentulous=False, arch_mode="both",
    )


def upsert_settings(db: Session, data: dict, tenant_id: int, actor_id: int | None) -> ChartSettings:
    patient_id = data["patient_id"]
    _require_patient(db, patient_id, tenant_id)
    row = db.get(ChartSettings, patient_id)
    if row is None:
        row = ChartSettings(patient_id=patient_id)
        db.add(row)
    for key, value in data.items():
        if key != "patient_id" and value is not None:
            setattr(row, key, value)
    row.updated_by = actor_id
    db.commit()
    db.refresh(row)
    return row


# ── REST-4: per-tooth note upsert ────────────────────────────────────────────
def upsert_tooth_note(db: Session, data: dict, tenant_id: int, actor_id: int | None) -> ChartToothNote:
    patient_id = data["patient_id"]
    _require_patient(db, patient_id, tenant_id)
    row = db.execute(
        select(ChartToothNote).where(
            ChartToothNote.patient_id == patient_id, ChartToothNote.tooth == data["tooth"]
        )
    ).scalar_one_or_none()
    if row is None:
        row = ChartToothNote(patient_id=patient_id, tooth=data["tooth"])
        db.add(row)
    row.note = data.get("note")
    row.updated_by = actor_id
    db.commit()
    db.refresh(row)
    return row


# ── bulk condition write (atomic; server-assigned group_id) ──────────────────
def bulk_create_conditions(
    db: Session, patient_id: int, group_id: str | None, conditions: list,
    tenant_id: int, actor_id: int | None,
) -> tuple[str, list[ChartCondition]]:
    _require_patient(db, patient_id, tenant_id)
    gid = group_id or uuid.uuid4().hex
    rows: list[ChartCondition] = []
    for item in conditions:
        data = item.model_dump(exclude_unset=True)
        row = ChartCondition(
            patient_id=patient_id, group_id=gid, updated_by=actor_id, **data
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return gid, rows


# ── aggregate chart payload ──────────────────────────────────────────────────
def patient_chart(db: Session, patient_id: int, tenant_id: int) -> dict:
    _require_patient(db, patient_id, tenant_id)

    conditions = db.execute(
        select(ChartCondition)
        .where(ChartCondition.patient_id == patient_id, ChartCondition.is_inactive.is_(False))
        .order_by(ChartCondition.tooth, ChartCondition.id)
    ).scalars().all()

    procedures = db.execute(
        select(PatientProcedure)
        .where(PatientProcedure.patient_id == patient_id, PatientProcedure.is_void.is_(False))
        .order_by(PatientProcedure.date_of_service.desc())
    ).scalars().all()

    plan_items = db.execute(
        select(TreatmentPlanItem)
        .join(TreatmentPlan, TreatmentPlan.id == TreatmentPlanItem.plan_id)
        .where(TreatmentPlan.patient_id == patient_id, TreatmentPlanItem.is_archived.is_(False))
        .order_by(TreatmentPlanItem.plan_id, TreatmentPlanItem.priority)
    ).scalars().all()

    tooth_notes = db.execute(
        select(ChartToothNote).where(ChartToothNote.patient_id == patient_id)
        .order_by(ChartToothNote.tooth)
    ).scalars().all()

    # REST-10: persisted freehand drawings (progress notes that carry strokes).
    drawings = db.execute(
        select(ProgressNote)
        .where(
            ProgressNote.patient_id == patient_id,
            ProgressNote.is_deleted.is_(False),
            ProgressNote.drawing_strokes.is_not(None),
        )
        .order_by(ProgressNote.created_at.desc())
    ).scalars().all()

    return {
        "patient_id": patient_id,
        "settings": get_settings(db, patient_id, tenant_id),
        "conditions": list(conditions),
        "procedures": list(procedures),
        "plan_items": list(plan_items),
        "tooth_notes": list(tooth_notes),
        "drawings": list(drawings),
    }
