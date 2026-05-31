"""Patient ledger feed (Phase 3 / C-3, optional aggregate).

Composes the patient's procedures (charges) and payments (credits) into a single
date-ordered feed with a server-computed ``running_balance`` in ``Decimal``. The
data already exists across resources — this endpoint exists for correctness
(precise running balance) and convenience; the FE could otherwise compose it from
the now-filterable ``patient-procedures`` + ``patient-payments`` lists.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import Patient, PatientPayment, PatientProcedure

# Stable secondary sort within a date: charges post before credits.
_TYPE_ORDER = {"procedure": 0, "payment": 1}


def _f(value) -> float:  # noqa: ANN001
    return float(value or 0)


def get_patient_ledger(
    db: Session,
    patient_id: int,
    tenant_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    patient = db.execute(
        select(Patient.id).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")

    proc_stmt = select(PatientProcedure).where(
        PatientProcedure.patient_id == patient_id,
        PatientProcedure.is_void.is_(False),
        PatientProcedure.is_archived.is_(False),
    )
    if date_from is not None:
        proc_stmt = proc_stmt.where(PatientProcedure.date_of_service >= date_from)
    if date_to is not None:
        proc_stmt = proc_stmt.where(PatientProcedure.date_of_service <= date_to)

    pay_stmt = select(PatientPayment).where(
        PatientPayment.patient_id == patient_id,
        PatientPayment.is_void.is_(False),
    )
    if date_from is not None:
        pay_stmt = pay_stmt.where(PatientPayment.payment_date >= date_from)
    if date_to is not None:
        pay_stmt = pay_stmt.where(PatientPayment.payment_date <= date_to)

    entries: list[dict] = []
    for p in db.execute(proc_stmt).scalars():
        entries.append({
            "entry_date": p.date_of_service.isoformat() if p.date_of_service else "",
            "entry_type": "procedure",
            "source_id": p.id,
            "description": p.notes or p.procedure_code,
            "charge": _f(p.fee),
            "credit": 0.0,
            "procedure_code": p.procedure_code,
            "tooth": p.tooth,
            "payment_type": None,
            "status": p.billing_status,
        })
    for pay in db.execute(pay_stmt).scalars():
        entries.append({
            "entry_date": pay.payment_date.isoformat() if pay.payment_date else "",
            "entry_type": "payment",
            "source_id": pay.id,
            "description": pay.notes or pay.payment_type,
            "charge": 0.0,
            "credit": _f(pay.amount),
            "procedure_code": None,
            "tooth": None,
            "payment_type": pay.payment_type,
            "status": None,
        })

    entries.sort(key=lambda e: (e["entry_date"], _TYPE_ORDER.get(e["entry_type"], 9), str(e["source_id"])))

    # Running balance over the FULL window (Decimal), computed before slicing.
    running = Decimal(0)
    for e in entries:
        running += Decimal(str(e["charge"])) - Decimal(str(e["credit"]))
        e["running_balance"] = float(running)

    total = len(entries)
    start = (page - 1) * size
    end = start + size
    page_entries = entries[start:end]

    opening = entries[start - 1]["running_balance"] if start > 0 and start <= total else 0.0
    closing = page_entries[-1]["running_balance"] if page_entries else opening

    return {
        "patient_id": patient_id,
        "entries": page_entries,
        "opening_balance": float(opening),
        "closing_balance": float(closing),
        "total": total,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
