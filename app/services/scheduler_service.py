"""Scheduler service: denormalized appointment feed, server-stamped status
transitions, and the patient-context aggregate for cross-module navigation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.db.models import (
    Appointment,
    AppointmentProcedure,
    InsuranceCarrier,
    InsurancePlan,
    InsuranceSubscriber,
    Office,
    Operatory,
    Patient,
    PatientAlert,
    PatientInsurance,
    PatientPayment,
    PatientProcedure,
    Provider,
)
from app.services import balance_service
from app.services.ledger_sign import sum_payment_credit, sum_payment_debit
from app.services.user_admin_service import resolve_user_names

_ELIGIBLE = {"active", "eligible", "verified", "yes"}
_INELIGIBLE = {"inactive", "ineligible", "termed", "terminated", "denied", "no"}


def _age(dob: date | None, today: date) -> int | None:
    if dob is None:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _eligibility(status: str | None) -> str | None:
    if status is None:
        return None
    s = status.strip().lower()
    if s in _ELIGIBLE:
        return "eligible"
    if s in _INELIGIBLE:
        return "ineligible"
    return "unknown"

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


def _batch_balances(db: Session, patient_ids: set[int]) -> dict[int, Decimal]:
    """Account balance (charges − payments) per patient in two aggregate queries."""
    if not patient_ids:
        return {}
    charges = dict(db.execute(
        select(PatientProcedure.patient_id, func.coalesce(func.sum(PatientProcedure.fee), 0))
        .where(PatientProcedure.patient_id.in_(patient_ids),
               PatientProcedure.is_void.is_(False), PatientProcedure.is_archived.is_(False))
        .group_by(PatientProcedure.patient_id)
    ).all())
    payments = dict(db.execute(
        # AL-9: `amount` carries two sign conventions — sum the settled credit.
        select(PatientPayment.patient_id, sum_payment_credit())
        .where(PatientPayment.patient_id.in_(patient_ids), PatientPayment.is_void.is_(False))
        .group_by(PatientPayment.patient_id)
    ).all())
    debits = dict(db.execute(
        select(PatientPayment.patient_id, sum_payment_debit())
        .where(PatientPayment.patient_id.in_(patient_ids), PatientPayment.is_void.is_(False))
        .group_by(PatientPayment.patient_id)
    ).all())
    return {
        pid: Decimal(charges.get(pid, 0)) + Decimal(debits.get(pid, 0))
        - Decimal(payments.get(pid, 0))
        for pid in patient_ids
    }


def _batch_service_summary(db: Session, appt_ids: list[str]) -> dict[str, str]:
    """Comma-joined procedure codes per appointment (the block's service list)."""
    if not appt_ids:
        return {}
    rows = db.execute(
        select(AppointmentProcedure.appointment_id, AppointmentProcedure.procedure_code)
        .where(AppointmentProcedure.appointment_id.in_(appt_ids),
               AppointmentProcedure.is_archived.is_(False))
        .order_by(AppointmentProcedure.appointment_id, AppointmentProcedure.id)
    ).all()
    summary: dict[str, list[str]] = {}
    for appt_id, code in rows:
        summary.setdefault(appt_id, []).append(code)
    return {k: ", ".join(v) for k, v in summary.items()}


def _batch_eligibility(db: Session, patient_ids: set[int]) -> dict[int, str]:
    """Primary-insurance eligibility per patient (best active subscriber status)."""
    if not patient_ids:
        return {}
    rows = db.execute(
        select(PatientInsurance.patient_id, InsuranceSubscriber.elig_status)
        .join(InsuranceSubscriber, InsuranceSubscriber.id == PatientInsurance.subscriber_id)
        .where(PatientInsurance.patient_id.in_(patient_ids), PatientInsurance.is_active.is_(True))
    ).all()
    out: dict[int, str] = {}
    for pid, status in rows:
        mapped = _eligibility(status)
        if mapped and (pid not in out or mapped == "eligible"):
            out[pid] = mapped
    return out


def list_scheduler_appointments(
    db: Session, tenant_id: int, *, date_from: date | None = None,
    date_to: date | None = None, office_id: int | None = None,
    provider_id: str | None = None, status: str | None = None,
    include_archived: bool = False,
) -> list[dict]:
    stmt = (
        select(Appointment, Patient, Provider, Operatory)
        .join(Office, Office.id == Appointment.office_id)
        .outerjoin(Patient, Patient.id == Appointment.patient_id)
        .outerjoin(Provider, Provider.id == Appointment.provider_id)
        .outerjoin(Operatory, Operatory.id == Appointment.operatory_id)
        .where(Office.tenant_id == tenant_id)
    )
    # SCHED-DEL-1: DELETE /appointments/{id} is a *soft* delete. The calendar feed
    # used to hand the tombstones straight back, so a deleted appointment
    # reappeared on every refetch (and every other consumer of this feed had the
    # same defect). Archived rows are excluded by default; a caller that genuinely
    # wants them asks for them.
    if not include_archived:
        stmt = stmt.where(Appointment.is_archived.is_(False))
    if office_id is not None:
        stmt = stmt.where(Appointment.office_id == office_id)
    if provider_id is not None:  # SCHED/MP-7/Reports-G8: server-side provider scoping
        stmt = stmt.where(Appointment.provider_id == provider_id)
    if status is not None:
        stmt = stmt.where(Appointment.status == status)
    if date_from is not None:
        stmt = stmt.where(Appointment.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Appointment.date <= date_to)
    stmt = stmt.order_by(Appointment.date.asc(), Appointment.start_time.asc())

    records = db.execute(stmt).all()

    # Batch enrichment (one query per dimension → no per-block N+1).
    today = datetime.now(timezone.utc).date()
    patient_ids = {a.patient_id for a, *_ in records if a.patient_id is not None}
    appt_ids = [a.id for a, *_ in records]
    alert_pids = {
        pid for (pid,) in db.execute(
            select(PatientAlert.patient_id).where(
                PatientAlert.patient_id.in_(patient_ids), PatientAlert.is_active.is_(True)
            ).distinct()
        ).all()
    } if patient_ids else set()
    balances = _batch_balances(db, patient_ids)
    services = _batch_service_summary(db, appt_ids)
    eligibility = _batch_eligibility(db, patient_ids)
    actor_ids = {a.created_by for a, *_ in records if a.created_by} | {
        a.updated_by for a, *_ in records if a.updated_by}
    names = resolve_user_names(db, actor_ids)

    out: list[dict] = []
    for appt, patient, provider, operatory in records:
        bal = balances.get(appt.patient_id)
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
            "is_posted": appt.is_posted,
            "is_archived": appt.is_archived,
            "posted_on": appt.posted_on,
            "confirmed_on": appt.confirmed_on,
            "checked_in_on": appt.checked_in_on,
            "checked_out_on": appt.checked_out_on,
            # G1/G2/G4/G5 enrichment.
            "has_alert": appt.patient_id in alert_pids if appt.patient_id else False,
            "patient_age": _age(patient.dob, today) if patient else None,
            "patient_gender": patient.gender if patient else None,
            "responsible_party_id": patient.responsible_party_id if patient else None,
            "service_summary": services.get(appt.id),
            "insurance_eligibility": eligibility.get(appt.patient_id) if appt.patient_id else None,
            "account_balance": bal if bal is not None else None,
            "created_by": appt.created_by,
            "created_by_name": names.get(appt.created_by) if appt.created_by else None,
            "updated_by": appt.updated_by,
            "updated_by_name": names.get(appt.updated_by) if appt.updated_by else None,
            "cancellation_note": appt.cancellation_note,
            "cancellation_reason": appt.cancellation_reason,
            "add_to_call_list": appt.add_to_call_list,
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


def update_status(
    db: Session, tenant_id: int, appt_id: str, status: str,
    *, cancellation_note: str | None = None, cancellation_reason: str | None = None,
    add_to_call_list: bool | None = None, actor_id: int | None = None,
) -> Appointment:
    appt = _appointment_in_tenant(db, appt_id, tenant_id)
    normalized = status.strip().lower().replace(" ", "_").replace("-", "_")
    appt.status = status
    stamp_field = _STATUS_STAMP.get(normalized)
    if stamp_field is not None:
        setattr(appt, stamp_field, datetime.now(timezone.utc))
    appt.is_missed = normalized in _MISSED
    appt.is_cancelled = normalized in _CANCELLED
    # SCHED G3: persist cancellation metadata when provided (Cancel dialog).
    if cancellation_note is not None:
        appt.cancellation_note = cancellation_note
    if cancellation_reason is not None:
        appt.cancellation_reason = cancellation_reason
    if add_to_call_list is not None:
        appt.add_to_call_list = add_to_call_list
    if actor_id is not None:
        appt.updated_by = actor_id
    db.commit()
    db.refresh(appt)
    return appt


def restore_appointment(
    db: Session, tenant_id: int, appt_id: str, *, actor_id: int | None = None
) -> Appointment:
    """SCHED-DEL-2: put a soft-deleted appointment back on the calendar.

    Idempotent — restoring a live appointment is a no-op rather than an error, so
    a double-click on Undo does not 409.
    """
    appt = _appointment_in_tenant(db, appt_id, tenant_id)
    if appt.is_archived:
        appt.is_archived = False
        if actor_id is not None:
            appt.updated_by = actor_id
        db.commit()
        db.refresh(appt)
    return appt


def get_patient_context(db: Session, patient_id: int, tenant_id: int) -> dict:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")

    # AL-12: the ledger title row shows "Prim. Ins" and the plan name, so the
    # context carries the plan/group identity alongside the carrier — not just
    # its id.
    insurance_rows = db.execute(
        select(
            PatientInsurance.insurance_type, PatientInsurance.ins_plan_id,
            InsuranceCarrier.name, InsurancePlan.group_number, InsurancePlan.plan_type,
            PatientInsurance.legacy_plan_type,
        )
        .outerjoin(InsurancePlan, InsurancePlan.id == PatientInsurance.ins_plan_id)
        .outerjoin(InsuranceCarrier, InsuranceCarrier.id == InsurancePlan.carrier_id)
        .where(PatientInsurance.patient_id == patient_id, PatientInsurance.is_active.is_(True))
    ).all()

    # PE-3: fold opening A/R buckets in so the Edit form hydrates from one call.
    from app.services import patient_intake_service, patient_overview_service

    insurance = [
        {
            "insurance_type": t, "ins_plan_id": pid, "carrier_name": cname,
            "group_number": gnum, "plan_type": ptype, "legacy_plan_type": legacy_type,
            # The legacy title row prints the plan by carrier + group; there is no
            # separate plan-name column in the migrated schema.
            "plan_name": " ".join(x for x in (cname, gnum) if x) or None,
        }
        for t, pid, cname, gnum, ptype, legacy_type in insurance_rows
    ]
    # AL-12: "Responsible: <name>" in the ledger title row. `responsible_party_id`
    # is a free-form string (numeric FK for app-created, legacy key for migrated),
    # so it goes through the same resolver the Patient Overview uses.
    rp = patient_overview_service.resolve_responsible_party(
        db, tenant_id, patient.responsible_party_id
    )
    responsible_party = None
    if rp is not None:
        responsible_party = {
            "id": rp.id,
            "legacy_id": rp.legacy_id,
            "name": " ".join(p for p in (rp.first_name, rp.last_name) if p).strip() or None,
            "relationship": patient.responsible_party_relationship,
            "home_phone": getattr(rp, "home_phone", None),
        }

    return {
        "patient": patient,
        "balance": balance_service.get_patient_balance(db, patient_id, tenant_id),
        "insurance": insurance,
        # AL-12: the primary plan the title row links to (first active D-tier slot).
        "primary_insurance": next(
            (i for i in insurance if (i["insurance_type"] or "").lower() == "primary"),
            insurance[0] if insurance else None,
        ),
        "responsible_party": responsible_party,
        "responsible_party_id": patient.responsible_party_id,
        "visit": {
            "first_visit": patient.first_visit,
            "last_visit": patient.last_visit,
            "next_recall": patient.next_recall,
        },
        "opening_balance": patient_intake_service.get_opening_balance(db, patient_id, tenant_id),
    }
