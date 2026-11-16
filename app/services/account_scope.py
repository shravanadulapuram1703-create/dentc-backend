"""Who is on the account (AL-11).

The legacy **Account Ledger** and the legacy **BALANCES** table are scoped to the
*account* — every patient on the anchor's ``account_id`` (RP-3) — not to the single
patient. ``patients.responsible_party_id`` is a free-form string
(migrated guarantor keys are legacy ids, app-created ones are the numeric
``responsible_parties.id``), so members are matched on the **raw string**, exactly
as ``patient_overview_service`` / ``patient_intake_service`` already do.

A patient with no ``responsible_party_id`` is an account of one — that is a real
state (self-guarantor rows exist in the migrated data), not an error.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import Patient


def load_patient(db: Session, patient_id: int, tenant_id: int) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


def patient_name(patient: Patient) -> str:
    return " ".join(p for p in (patient.first_name, patient.last_name) if p).strip()


def account_members(db: Session, patient: Patient, tenant_id: int) -> list[Patient]:
    """Every account member, anchor patient first, then by name.

    Ordered deterministically so a server-paginated merged feed is stable across
    calls (the running balance is recomputed per page request).
    """
    # RP-3: membership is ``patients.account_id`` — no longer "everyone holding
    # the same responsible_party_id string", which merged unrelated families
    # whenever a self-guarantor's patient id equalled an RP row id (RP-1).
    if patient.account_id is None:
        return [patient]
    rows = list(db.execute(
        select(Patient).where(
            Patient.tenant_id == tenant_id,
            Patient.account_id == patient.account_id,
        )
    ).scalars().all())
    if not any(p.id == patient.id for p in rows):
        rows.append(patient)
    rows.sort(key=lambda p: (p.id != patient.id, (p.last_name or ""), (p.first_name or ""), p.id))
    return rows
