"""Persistent default-patient selection (persistent-patient-selection dev-report).

Server-side store for "reopen the user's last selected patient", backing the
per-device localStorage interim. Stored as ``users.last_patient_id`` (PDP-3).

PDP-4 (validation/isolation) is enforced here on both read and write:
- the user is always derived from the auth token (never a client-supplied id);
- the patient must belong to the **caller's tenant** (cross-tenant ids rejected
  on write / treated as null on read — no cross-practice id leak);
- a soft-deleted / archived patient reads back as null (and is cleared) so the
  client never loops on an unopenable patient.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import Patient, User


def _valid_patient(db: Session, patient_id: int, tenant_id: int) -> Patient | None:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.tenant_id != tenant_id or not patient.is_active:
        return None
    return patient


def resolve_last_patient(db: Session, user: User, tenant_id: int) -> int | None:
    """Return the user's valid default patient id, or null. Clears a now-stale
    reference (deleted/archived/cross-tenant) so it doesn't keep being returned."""
    pid = user.last_patient_id
    if pid is None:
        return None
    if _valid_patient(db, pid, tenant_id) is None:
        user.last_patient_id = None  # stale → clear
        db.commit()
        return None
    return pid


def set_last_patient(
    db: Session, user: User, tenant_id: int, patient_id: int | None
) -> int | None:
    """Set (or clear, when ``patient_id`` is null) the user's default patient.
    Rejects a patient that isn't an active member of the caller's tenant."""
    if patient_id is None:
        user.last_patient_id = None
        db.commit()
        return None

    if _valid_patient(db, patient_id, tenant_id) is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    user.last_patient_id = patient_id
    db.commit()
    return patient_id
