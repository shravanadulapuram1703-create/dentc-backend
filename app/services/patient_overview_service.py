"""Patient Overview aggregate (PO-1) + family appointments (PO-4).

One call composes the whole legacy Patient Overview screen — patient, balance,
responsible party (resolved for migrated legacy ids too), account roster,
appointments, recalls, resolved insurance slots, referrals and contracts — so the
screen stops firing ~20 requests per load.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import (
    Appointment,
    InsuranceCarrier,
    InsurancePlan,
    InsuranceSubscriber,
    Patient,
    PatientInsPaymentPlan,
    PatientInsurance,
    PatientPaymentPlan,
    PatientRecall,
    PatientRegPlan,
    Referral,
    ResponsibleParty,
)
from app.services import balance_service, patient_intake_service
from app.services.enrich_service import enrich_patient_office


def _dump(obj) -> dict | None:  # noqa: ANN001
    if obj is None:
        return None
    return {c.key: getattr(obj, c.key) for c in sa_inspect(obj).mapper.column_attrs}


def resolve_responsible_party(db: Session, tenant_id: int, rp_key: str | None) -> ResponsibleParty | None:
    """Resolve ``patients.responsible_party_id`` (a string) to a row — by numeric
    FK first, then by ``legacy_id`` (PO-2). Returns None if unresolvable (migrated
    guarantor not yet imported) or self-linked to the patient's own id."""
    if not rp_key:
        return None
    row = None
    if rp_key.isdigit():
        row = db.execute(
            select(ResponsibleParty).where(
                ResponsibleParty.id == int(rp_key), ResponsibleParty.tenant_id == tenant_id
            )
        ).scalar_one_or_none()
    if row is None:
        row = db.execute(
            select(ResponsibleParty).where(
                ResponsibleParty.legacy_id == rp_key, ResponsibleParty.tenant_id == tenant_id
            )
        ).scalar_one_or_none()
    return row


def _insurance(db: Session, patient_id: int) -> list[dict]:
    rows = db.execute(
        select(
            PatientInsurance, InsurancePlan.group_number, InsuranceCarrier.name,
            InsuranceSubscriber.sub_first_name, InsuranceSubscriber.sub_last_name,
        )
        .outerjoin(InsurancePlan, InsurancePlan.id == PatientInsurance.ins_plan_id)
        .outerjoin(InsuranceCarrier, InsuranceCarrier.id == InsurancePlan.carrier_id)
        .outerjoin(InsuranceSubscriber, InsuranceSubscriber.id == PatientInsurance.subscriber_id)
        .where(PatientInsurance.patient_id == patient_id)
    ).all()
    out = []
    for pi, group_number, carrier_name, sub_first, sub_last in rows:
        d = _dump(pi)
        d["carrier_name"] = carrier_name
        d["group_number"] = group_number
        d["subscriber_name"] = ", ".join(x for x in (sub_last, sub_first) if x) or None
        out.append(d)
    return out


def get_patient_overview(db: Session, patient_id: int, tenant_id: int) -> dict:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    enrich_patient_office(db, [patient], tenant_id)

    today = date.today()
    last_visit, next_visit = patient_intake_service._visits(db, patient_id, today)

    appts = db.execute(
        select(Appointment).where(
            Appointment.patient_id == patient_id, Appointment.is_archived.is_(False)
        ).order_by(Appointment.date.desc()).limit(100)
    ).scalars().all()
    recalls = db.execute(
        select(PatientRecall).where(
            PatientRecall.patient_id == patient_id, PatientRecall.is_active.is_(True)
        ).order_by(PatientRecall.due_date)
    ).scalars().all()
    referrals = db.execute(
        select(Referral).where(Referral.patient_id == patient_id)
    ).scalars().all()

    contracts = {
        "reg_plans": [_dump(r) for r in db.execute(
            select(PatientRegPlan).where(PatientRegPlan.patient_id == patient_id)).scalars()],
        "payment_plans": [_dump(r) for r in db.execute(
            select(PatientPaymentPlan).where(PatientPaymentPlan.patient_id == patient_id)).scalars()],
        "ins_payment_plans": [_dump(r) for r in db.execute(
            select(PatientInsPaymentPlan).where(PatientInsPaymentPlan.patient_id == patient_id)).scalars()],
    }

    rp = resolve_responsible_party(db, tenant_id, patient.responsible_party_id)
    members = patient_intake_service.get_responsible_party_roster(
        db, patient.responsible_party_id, tenant_id
    ) if patient.responsible_party_id else []

    return {
        "patient": patient,
        "balance": balance_service.get_patient_balance(db, patient_id, tenant_id),
        "visit": {
            "first_visit": patient.first_visit, "last_visit": last_visit or patient.last_visit,
            "next_visit": next_visit, "next_recall": patient.next_recall,
        },
        "responsible_party": _dump(rp),
        "account_members": members,
        "appointments": [_dump(a) for a in appts],
        "recalls": [_dump(r) for r in recalls],
        "insurance": _insurance(db, patient_id),
        "referrals": [_dump(r) for r in referrals],
        "contracts": contracts,
    }


# ── PO-4: family (account-scoped) appointments ────────────────────────────────
def get_family_appointments(
    db: Session, tenant_id: int, responsible_party_id: str, *, upcoming_only: bool = False
) -> list[dict]:
    """Appointments across every patient on an account (legacy VIEW FUTURE FAMILY
    APPT). Scopes by the raw ``responsible_party_id`` string so migrated accounts work."""
    member_ids = list(db.execute(
        select(Patient.id).where(
            Patient.tenant_id == tenant_id,
            Patient.responsible_party_id == str(responsible_party_id),
        )
    ).scalars())
    if not member_ids:
        return []
    stmt = select(Appointment).where(
        Appointment.patient_id.in_(member_ids), Appointment.is_archived.is_(False)
    )
    if upcoming_only:
        stmt = stmt.where(Appointment.date >= date.today())
    appts = db.execute(stmt.order_by(Appointment.date, Appointment.start_time)).scalars().all()
    return [_dump(a) for a in appts]
