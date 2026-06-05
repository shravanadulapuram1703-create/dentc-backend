"""Scheduler service: denormalized appointment feed, server-stamped status
transitions, and the patient-context aggregate for cross-module navigation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.db.models import (
    Appointment,
    InsuranceCarrier,
    InsurancePlan,
    Office,
    Operatory,
    Patient,
    PatientInsurance,
    Provider,
)
from app.services import balance_service

# Status (normalised) -> timestamp column the server stamps on transition (gap #5).
_STATUS_STAMP = {
    "confirmed": "confirmed_on",
    "in_reception": "checked_in_on",
    "in_chair": "checked_in_on",
    "checked_in": "checked_in_on",
    "arrived": "checked_in_on",
    "checked_out": "checked_out_on",
    "completed": "checked_out_on",
}
_MISSED = {"missed", "no_show"}
_CANCELLED = {"cancelled", "canceled"}


def _patient_name(p: Patient | None) -> str | None:
    if p is None:
        return None
    name = ", ".join(x for x in (p.last_name, p.first_name) if x)
    return name or p.chart_no or f"Patient {p.id}"


def list_scheduler_appointments(
    db: Session, tenant_id: int, *, date_from: date | None = None,
    date_to: date | None = None, office_id: int | None = None,
) -> list[dict]:
    stmt = (
        select(Appointment, Patient, Provider, Operatory)
        .join(Office, Office.id == Appointment.office_id)
        .outerjoin(Patient, Patient.id == Appointment.patient_id)
        .outerjoin(Provider, Provider.id == Appointment.provider_id)
        .outerjoin(Operatory, Operatory.id == Appointment.operatory_id)
        .where(Office.tenant_id == tenant_id)
    )
    if office_id is not None:
        stmt = stmt.where(Appointment.office_id == office_id)
    if date_from is not None:
        stmt = stmt.where(Appointment.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Appointment.date <= date_to)
    stmt = stmt.order_by(Appointment.date.asc(), Appointment.start_time.asc())

    out: list[dict] = []
    for appt, patient, provider, operatory in db.execute(stmt).all():
        out.append({
            "id": appt.id,
            "patient_id": appt.patient_id,
            "patient_name": _patient_name(patient),
            "provider_id": appt.provider_id,
            "provider_name": provider.name if provider else None,
            "operatory_id": appt.operatory_id,
            "operatory_name": operatory.name if operatory else None,
            "office_id": appt.office_id,
            "date": appt.date,
            "start_time": appt.start_time,
            "end_time": appt.end_time,
            "duration": appt.duration,
            "status": appt.status,
            "procedure_label": appt.procedure_label,
            "is_missed": appt.is_missed,
            "is_cancelled": appt.is_cancelled,
            "is_blocked": appt.is_blocked,
            "confirmed_on": appt.confirmed_on,
            "checked_in_on": appt.checked_in_on,
            "checked_out_on": appt.checked_out_on,
        })
    return out


def _appointment_in_tenant(db: Session, appt_id: str, tenant_id: int) -> Appointment:
    appt = db.get(Appointment, appt_id)
    if appt is None:
        raise NotFoundError(f"Appointment '{appt_id}' was not found")
    office = db.get(Office, appt.office_id)
    if office is None or office.tenant_id != tenant_id:
        raise ForbiddenError("Appointment does not belong to the authenticated tenant")
    return appt


def update_status(db: Session, tenant_id: int, appt_id: str, status: str) -> Appointment:
    appt = _appointment_in_tenant(db, appt_id, tenant_id)
    normalized = status.strip().lower().replace(" ", "_").replace("-", "_")
    appt.status = status
    stamp_field = _STATUS_STAMP.get(normalized)
    if stamp_field is not None:
        setattr(appt, stamp_field, datetime.now(timezone.utc))
    appt.is_missed = normalized in _MISSED
    appt.is_cancelled = normalized in _CANCELLED
    db.commit()
    db.refresh(appt)
    return appt


def get_patient_context(db: Session, patient_id: int, tenant_id: int) -> dict:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")

    insurance_rows = db.execute(
        select(PatientInsurance.insurance_type, PatientInsurance.ins_plan_id, InsuranceCarrier.name)
        .outerjoin(InsurancePlan, InsurancePlan.id == PatientInsurance.ins_plan_id)
        .outerjoin(InsuranceCarrier, InsuranceCarrier.id == InsurancePlan.carrier_id)
        .where(PatientInsurance.patient_id == patient_id, PatientInsurance.is_active.is_(True))
    ).all()

    return {
        "patient": patient,
        "balance": balance_service.get_patient_balance(db, patient_id, tenant_id),
        "insurance": [
            {"insurance_type": t, "ins_plan_id": pid, "carrier_name": cname}
            for t, pid, cname in insurance_rows
        ],
        "visit": {
            "first_visit": patient.first_visit,
            "last_visit": patient.last_visit,
            "next_recall": patient.next_recall,
        },
    }
