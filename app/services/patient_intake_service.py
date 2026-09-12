"""Add-Patient intake extras: opening balances (GAP-AP-12) and the atomic
composite register transaction (GAP-AP-13/15/18).

Opening balances live in their own table (``patient_opening_balances``) rather
than on the patient row and surface through the computed
``/patients/{id}/balance`` (see ``balance_service``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models import (
    Appointment,
    InsuranceCarrier,
    InsurancePlan,
    InsuranceSubscriber,
    Patient,
    PatientInsurance,
    PatientOpeningBalance,
    PatientRecall,
    ResponsibleParty,
)
from app.integrations import redis_store
from app.services import balance_service, patient_extra_service, patient_rules_service
from app.services import medical_history_service as mh
from app.services.patient_service import assign_chart_no

_BUCKETS = ("current", "over_30", "over_60", "over_90", "over_120")


def _require_patient(db: Session, patient_id: int, tenant_id: int) -> None:
    if db.execute(
        select(Patient.id).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none() is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")


def _f(value: Any) -> float:
    return float(value or 0)


def serialize_opening_balance(row: PatientOpeningBalance) -> dict:
    buckets = {b: _f(getattr(row, b)) for b in _BUCKETS}
    return {
        "patient_id": row.patient_id,
        "as_of_date": row.as_of_date,
        **buckets,
        "total": round(sum(buckets.values()), 2),
        "notes": row.notes,
    }


def get_opening_balance(db: Session, patient_id: int, tenant_id: int) -> dict:
    _require_patient(db, patient_id, tenant_id)
    row = db.execute(
        select(PatientOpeningBalance).where(PatientOpeningBalance.patient_id == patient_id)
    ).scalar_one_or_none()
    if row is None:
        return {"patient_id": patient_id, "as_of_date": None,
                **{b: 0.0 for b in _BUCKETS}, "total": 0.0, "notes": None}
    return serialize_opening_balance(row)


def upsert_opening_balance(
    db: Session, patient_id: int, tenant_id: int, data: dict, *, user_id: int | None = None
) -> dict:
    """Create or replace the patient's opening A/R (one row per patient)."""
    _require_patient(db, patient_id, tenant_id)
    row = db.execute(
        select(PatientOpeningBalance).where(PatientOpeningBalance.patient_id == patient_id)
    ).scalar_one_or_none()
    values = {b: Decimal(str(data.get(b, 0) or 0)) for b in _BUCKETS}
    if row is None:
        row = PatientOpeningBalance(
            tenant_id=tenant_id, patient_id=patient_id, created_by=user_id,
            as_of_date=data.get("as_of_date"), notes=data.get("notes"), **values,
        )
        db.add(row)
    else:
        row.as_of_date = data.get("as_of_date")
        row.notes = data.get("notes")
        for b in _BUCKETS:
            setattr(row, b, values[b])
    db.commit()
    db.refresh(row)
    # Invalidate the cached computed balance so the seeded A/R shows immediately.
    redis_store.cache_delete(f"balance:{tenant_id}:{patient_id}")
    return serialize_opening_balance(row)


# ── Composite register (atomic) ───────────────────────────────────────────────
def register_patient(db: Session, tenant_id: int, req, *, user_id: int | None = None) -> dict:
    """Create the patient and every provided related record in one transaction.

    A failure anywhere rolls the whole thing back, so registration never leaves a
    patient with only some of its related records (the client-chained flow could).
    The rollback is explicit rather than left to the session's close: a later
    slot's 422 (GAP-AP-24) or a flush-time constraint error (GAP-AP-26) must
    leave the session clean for whoever holds it next — the error handler that
    turns the exception into a 4xx cannot reach the session to do it.
    """
    try:
        return _register_patient(db, tenant_id, req, user_id=user_id)
    except Exception:
        db.rollback()
        raise


def _register_patient(db: Session, tenant_id: int, req, *, user_id: int | None) -> dict:
    raw = req.patient.model_dump(exclude_unset=True)
    # GAP-AP-21: the override is accepted at either level — the FE's retry
    # sets the top-level flag; a client reusing PatientCreate may set the inner one.
    force_create = bool(getattr(req, "force_create", False) or raw.pop("force_create", False))

    rp = req.responsible_party
    if rp is not None:
        if rp.relationship:
            raw["responsible_party_relationship"] = rp.relationship
        elif rp.is_self:
            raw["responsible_party_relationship"] = patient_rules_service.RESP_PARTY_REL_SELF
        # Link an already-existing guarantor now; is_self / inline person resolved
        # after the patient has an id.
        if not rp.is_self and rp.person is None and rp.responsible_party_id:
            raw["responsible_party_id"] = rp.responsible_party_id

    # Add/Edit Patient checkbox integrity: contradictory Patient Type tags are
    # rejected and the implied Patient Status flags forced, before the duplicate
    # check — registration must not be able to route around the rules that
    # PATCH /patients/{id} enforces. (Also folds the GAP-AP-25 relationship code
    # and the GAP-AP-19 middle initial.)
    payload = patient_rules_service.normalize_patient_payload(raw)

    # KAN-108: Quick Save posts straight here, so the duplicate guard has to live
    # server-side — a client that forgets to call /patients/check-duplicate must
    # not be able to create a duplicate silently. GAP-AP-21: the same function
    # guards the plain POST /patients.
    patient_extra_service.raise_if_duplicate(db, tenant_id, payload, force_create=force_create)

    payload["tenant_id"] = tenant_id
    if user_id is not None:
        payload.setdefault("created_by", user_id)

    patient = Patient(**payload)
    db.add(patient)
    db.flush()  # obtain id for chart_no + child FKs
    assign_chart_no(db, patient)

    if rp is not None:
        if rp.is_self:
            patient.responsible_party_id = str(patient.id)
        elif rp.person is not None:
            # LEG-10: create the non-self guarantor and link it in the same txn.
            person = rp.person.model_dump(exclude_unset=True)
            patient_rules_service.fold_middle_name(person)
            guarantor = ResponsibleParty(tenant_id=tenant_id, created_by=user_id, **person)
            db.add(guarantor)
            db.flush()
            patient.responsible_party_id = str(guarantor.id)

    # GAP-AP-22: alerts and questionnaire answers go through the same reconcile
    # the composite Medical History write and the bulk endpoints use, so the
    # MH-12 contradiction rules, the MA-3 catalog fill, the MH-8 change log and
    # the MH-14 flash-alert propagation all hold on a registration too (the
    # bare inserts here used to bypass every one of them).
    alerts = mh.apply_alert_answers(
        db, tenant_id, patient.id, [a.model_dump(exclude_unset=True) for a in req.medical_alerts],
        user_id=user_id, allow_contradictions=bool(getattr(req, "allow_contradictions", False)),
    ) if req.medical_alerts else {"rows": [], "contradictions": []}
    answers = mh.apply_questionnaire_answers(
        db, tenant_id, patient.id,
        [q.model_dump(exclude_unset=True) for q in req.questionnaire_responses],
        user_id=user_id,
    ) if req.questionnaire_responses else {"rows": []}

    recall_rows = [
        PatientRecall(
            patient_id=patient.id, created_by=user_id, office_id=r.office_id,
            recall_type=r.recall_type, procedure_code=r.procedure_code,
            due_date=r.due_date, interval_months=r.interval_months,
            # GAP-AP-23 / LEG-17
            interval_unit=r.interval_unit, scheduled_date=r.scheduled_date,
            scheduled_time=r.scheduled_time,
            notes=r.notes,
        )
        for r in req.recalls
    ]
    db.add_all(recall_rows)
    db.flush()

    insurance_out = _register_insurance(db, tenant_id, patient.id, list(req.insurance or []))

    opening_seeded = False
    if req.opening_balance is not None:
        ob = req.opening_balance
        db.add(PatientOpeningBalance(
            tenant_id=tenant_id, patient_id=patient.id, created_by=user_id,
            as_of_date=ob.as_of_date, notes=ob.notes,
            **{b: Decimal(str(getattr(ob, b) or 0)) for b in _BUCKETS},
        ))
        opening_seeded = True

    if req.medical_alerts:
        mh.sync_flash_alerts(db, tenant_id, patient.id, user_id=user_id)
    db.commit()
    db.refresh(patient)
    return {
        "patient_id": patient.id,
        "chart_no": patient.chart_no,
        "responsible_party_id": patient.responsible_party_id,
        "medical_alert_ids": [a.id for a in alerts["rows"]],
        "questionnaire_response_ids": [q.id for q in answers["rows"]],
        "recall_ids": [r.id for r in recall_rows],
        "insurance": insurance_out,
        "opening_balance_seeded": opening_seeded,
        "contradictions": alerts.get("contradictions") or [],
    }


def _rank_index(insurance_type: str | None) -> int:
    rank = str(insurance_type or "").strip().lower()
    ranks = patient_rules_service.INSURANCE_RANKS
    return ranks.index(rank) if rank in ranks else len(ranks)


def _register_insurance(db: Session, tenant_id: int, patient_id: int, slots: list) -> list[dict]:
    """GAP-AP-24: subscriber + ``patient_insurance`` link per slot, inside the
    registration transaction.

    Slots are applied primary-first regardless of payload order so the Coverage
    Type rank rule (``validate_coverage_slot``, secondary needs primary) judges
    the set the user built rather than the order the form serialised it in.
    Every failure is a 422 that names the slot (``details.index``) — the
    orphaned-subscriber case (BUG-3's side effect) cannot happen because the
    whole transaction rolls back.
    """
    out: list[tuple[int, dict]] = []
    ordered = sorted(enumerate(slots), key=lambda pair: _rank_index(pair[1].link.insurance_type))
    for index, slot in ordered:
        link = slot.link.model_dump(exclude_unset=True)
        if slot.subscriber is not None:
            sub = slot.subscriber.model_dump(exclude_unset=True)
            plan_id = sub.get("ins_plan_id")
            if db.execute(
                select(InsurancePlan.id).where(
                    InsurancePlan.id == plan_id, InsurancePlan.tenant_id == tenant_id
                )
            ).scalar_one_or_none() is None:
                raise ValidationError(
                    f"Insurance plan '{plan_id}' was not found.",
                    code="insurance_plan_not_found",
                    details={"field": "insurance.subscriber.ins_plan_id", "index": index,
                             "ins_plan_id": plan_id},
                )
            subscriber = InsuranceSubscriber(
                tenant_id=tenant_id,
                subscriber_patient_id=patient_id if slot.subscriber_is_patient else None,
                **sub,
            )
            db.add(subscriber)
            db.flush()
        else:
            subscriber = db.execute(
                select(InsuranceSubscriber).where(
                    InsuranceSubscriber.id == slot.subscriber_id,
                    InsuranceSubscriber.tenant_id == tenant_id,
                )
            ).scalar_one_or_none()
            if subscriber is None:
                raise ValidationError(
                    f"Insurance subscriber '{slot.subscriber_id}' was not found.",
                    code="insurance_subscriber_not_found",
                    details={"field": "insurance.subscriber_id", "index": index,
                             "subscriber_id": slot.subscriber_id},
                )
        link.setdefault("ins_plan_id", subscriber.ins_plan_id)
        try:
            patient_rules_service.validate_coverage_slot(
                db, patient_id=patient_id,
                legacy_plan_type=link.get("legacy_plan_type"),
                insurance_type=link.get("insurance_type"),
                is_active=bool(link.get("is_active", True)),
            )
        except ValidationError as exc:
            exc.details = {**(exc.details or {}), "index": index}
            raise
        row = PatientInsurance(patient_id=patient_id, subscriber_id=subscriber.id, **link)
        db.add(row)
        db.flush()
        out.append((index, {
            "subscriber_id": subscriber.id, "patient_insurance_id": row.id,
            "ins_plan_id": row.ins_plan_id, "legacy_plan_type": row.legacy_plan_type,
            "insurance_type": row.insurance_type,
        }))
    # Report in payload order so the caller can pair results with its slots.
    return [result for _, result in sorted(out, key=lambda pair: pair[0])]


# ── Account plans (LEG-5) ─────────────────────────────────────────────────────
def get_account_plans(db: Session, patient_id: int, tenant_id: int) -> list[dict]:
    """Distinct insurance plans already on this patient's *account* — the patient
    plus anyone sharing their responsible party — so a dependent can reuse the
    guarantor's existing plan (legacy "Account Plans" scope)."""
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")

    account_ids = {patient_id}
    if patient.responsible_party_id:
        account_ids.update(db.execute(
            select(Patient.id).where(
                Patient.tenant_id == tenant_id,
                Patient.responsible_party_id == patient.responsible_party_id,
            )
        ).scalars())

    plan_ids = set(db.execute(
        select(PatientInsurance.ins_plan_id).where(
            PatientInsurance.patient_id.in_(account_ids),
            PatientInsurance.ins_plan_id.is_not(None),
        )
    ).scalars())
    if not plan_ids:
        return []

    plans = db.execute(
        select(InsurancePlan).where(
            InsurancePlan.id.in_(plan_ids), InsurancePlan.tenant_id == tenant_id
        )
    ).scalars().all()
    carrier_ids = {p.carrier_id for p in plans if p.carrier_id is not None}
    carriers = {c.id: c.name for c in db.execute(
        select(InsuranceCarrier).where(InsuranceCarrier.id.in_(carrier_ids))
    ).scalars()} if carrier_ids else {}

    return [{
        "id": p.id, "carrier_id": p.carrier_id, "carrier_name": carriers.get(p.carrier_id),
        "employer_id": p.employer_id, "group_number": p.group_number,
        "plan_type": p.plan_type, "coverage_type": p.coverage_type,
        "individual_max": _f(p.individual_max) if p.individual_max is not None else None,
        "individual_deductible": _f(p.individual_deductible) if p.individual_deductible is not None else None,
    } for p in plans]


# ── Responsible-party roster (LEG-14 / PO-3) ──────────────────────────────────
def _age(dob: date | None, today: date) -> int | None:
    if dob is None:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _visits(db: Session, patient_id: int, today: date) -> tuple[date | None, date | None]:
    """(last_visit, next_visit) from non-archived appointments (PO-3/PO-8-derived)."""
    last = db.execute(
        select(func.max(Appointment.date)).where(
            Appointment.patient_id == patient_id, Appointment.is_archived.is_(False),
            Appointment.date < today,
        )
    ).scalar_one()
    nxt = db.execute(
        select(func.min(Appointment.date)).where(
            Appointment.patient_id == patient_id, Appointment.is_archived.is_(False),
            Appointment.date >= today,
        )
    ).scalar_one()
    return last, nxt


def _scheduled_recall(db: Session, patient_id: int) -> date | None:
    return db.execute(
        select(func.min(func.coalesce(PatientRecall.scheduled_date, PatientRecall.due_date)))
        .where(PatientRecall.patient_id == patient_id, PatientRecall.is_active.is_(True))
    ).scalar_one()


def _member_row(db: Session, tenant_id: int, p: Patient, today: date) -> dict:
    """One roster row with the aging/estimate/visit block the Overview grids need."""
    try:
        bal = balance_service.get_patient_balance(db, p.id, tenant_id)
    except Exception:  # noqa: BLE001 — a balance failure must not sink the roster
        bal = {}
    last_visit, next_visit = _visits(db, p.id, today)
    scheduled_recall = _scheduled_recall(db, p.id)
    return {
        "patient_id": p.id, "chart_no": p.chart_no,
        "first_name": p.first_name, "last_name": p.last_name,
        "age": _age(p.dob, today), "sex": p.gender, "is_active": p.is_active,
        "balance": _f(bal.get("balance")),
        "recall_date": scheduled_recall, "scheduled_recall": scheduled_recall,
        "next_visit": next_visit, "last_visit": last_visit,
        "estimated_patient": _f(bal.get("estimated_patient")),
        "estimated_insurance": _f(bal.get("estimated_insurance")),
        "aging": bal.get("aging") or {},
    }


def get_responsible_party_roster(db: Session, rp_key: str, tenant_id: int) -> list[dict]:
    """Every patient the guarantor is responsible for, with age / sex / balance +
    aging / estimates / visits / scheduled recall — the legacy Step-2 "Responsible
    for following Patients" account roster.

    PO-3: matches on the **raw** ``responsible_party_id`` string, so it works for
    both new-system numeric FKs and migrated legacy guarantor ids (no 404 — an
    unknown key simply yields an empty roster)."""
    patients = db.execute(
        select(Patient).where(
            Patient.tenant_id == tenant_id,
            Patient.responsible_party_id == str(rp_key),
        ).order_by(Patient.last_name, Patient.first_name).limit(50)
    ).scalars().all()

    today = date.today()
    return [_member_row(db, tenant_id, p, today) for p in patients]
