"""Treatment-plan business logic.

- ``plan_summary`` — roll item fees into a plan total (excludes archived items).
- **PLAN-12** ``list_patient_items`` — all of a patient's plan items in one query
  (no N+1, tenant/patient scoped via the plan join).
- **PLAN-3** ``re_estimate`` — compute per-item insurance benefit from the
  patient's active coverage (coverage %, deductible, annual-max remaining) and
  write ``insurance_estimate`` + the insurance-detail store. The band matcher is
  the **ranked, coverage-category-aware** one from ``estimate_service`` (FEE-1) —
  the first version compared ``D2740`` lexically against ``03A``–``03A`` and
  returned 0 % on every migrated plan. ``use_new_fees`` re-prices each line
  through ``pricing_service`` and records the schedule (PLAN-29).
- **PLAN-6** ``plan_report`` — server-side report payload (header + lines + totals).
- **PLAN-13/14** ``TreatmentPlanItemCRUD`` — item delete is a soft-delete that
  also archives the item's insurance-details (so a detail FK can never make an
  item undeletable).
- **Edit Treatment window (PLAN-17/18/19/25/26/27/28/29, PLAN-11)** — the item
  CRUD validates the referral / counselor / fee-schedule references against the
  tenant, reconciles the ICD-10 link set (``icd_code_ids``), stamps
  ``accepted_date`` the first time a line is accepted, prices an omitted fee
  server-side, and defaults ``provider_id`` from ``diagnosed_by`` (PLAN-APPT-3).
- **PROC-INT-1/2** the item <-> charge link. ``patient_procedures.treatment_plan_item_id``
  is the canonical FK; :func:`bind_item_to_charge` / :func:`release_item` are the
  only two places that move an item into and out of ``status='completed'``, and
  the CRUD refuses a client writing that status by hand unless a live charge
  backs it (``status_requires_charge``) or un-completing an item a live charge
  still references (``item_has_posted_charge``). :func:`post_item_to_ledger` is
  Post to Ledger server-side: one transaction creates the charge *and* closes the
  item, where the client used to do two requests that could half-fail. It honours
  the PLAN-28 posting flags.
- **PLAN-APPT-1/2** the item <-> appointment link. ``appointment_procedures.
  treatment_plan_item_id`` is the FK; :func:`schedule_item` /
  :func:`release_scheduled_item` move an item into and out of ``status='scheduled'``
  (remembering ``status_before_scheduled`` so a cancelled appointment puts the
  line back exactly where it was). The appointment-side CRUD hooks live in
  ``appointment_service``; :func:`book_from_plan` is the atomic PLAN-APPT-5
  endpoint.
- **PROC-INT-8** every item write runs the tooth/surface/quadrant rules in
  ``procedure_rules_service`` (same engine as ``patient_procedures``).
- **PROC-INT-3** every item write announces ``procedures.changed``.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.datetimes import office_today
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.crud.base import CRUDBase
from app.db.models import (
    Appointment,
    AppointmentProcedure,
    FeeSchedule,
    IcdCode,
    InsuranceCoverageRule,
    InsurancePlan,
    Office,
    Operatory,
    Patient,
    PatientInsurance,
    PatientProcedure,
    ProcedureCode,
    Provider,
    ProviderOffice,
    Referral,
    TreatmentPlan,
    TreatmentPlanInsuranceDetail,
    TreatmentPlanItem,
    TreatmentPlanItemIcdCode,
    User,
)
from app.schemas.treatment import (
    ACCEPTED_STATUS,
    COMPLETED_STATUS,
    SCHEDULED_STATUS,
    BookedProcedureRead,
    BookFromPlanResult,
    ItemIcdCodeRead,
    PlanReportItem,
    PlanReportPatient,
    ReEstimateLine,
    ReEstimateResult,
    TreatmentPlanItemRead,
    TreatmentPlanReport,
    TreatmentPlanSummary,
)
from app.services import coverage_category_service as covcat
from app.services import pricing_service, procedure_events
from app.services.estimate_service import match_coverage_rule
from app.services.procedure_rules_service import apply_entry_rules
from app.services.user_admin_service import resolve_user_names

_CENTS = Decimal("0.01")
ITEM_SOURCE = "treatment_plan_items"
#: The status an item returns to when the charge that completed it is voided.
#: The pre-completion status is not stored, and "accepted" is the only state an
#: item can honestly be in once it has been treated at least once.
RELEASED_STATUS = ACCEPTED_STATUS
#: PLAN-APPT-7 / APPT-PROC-1: chair time for a line with no duration anywhere.
DEFAULT_ITEM_DURATION_MINUTES = 30
#: PLAN-9 vocabulary, published on the insurance-detail write path.
PREAUTH_STATUSES = ("sent", "closed")
#: PLAN-27 vocabulary — the same two directions ``referrals.referral_type`` uses.
REFERRAL_TYPES = ("in", "out")
#: Line status the booking flow writes on ``appointment_procedures`` (legacy
#: ``TP`` = treatment-planned; the frontend seeds its TREATMENTS grid with it).
BOOKED_LINE_STATUS = "TP"


def _require_plan(db: Session, plan_id: str, tenant_id: int) -> TreatmentPlan:
    plan = db.get(TreatmentPlan, plan_id)
    if plan is None:
        raise NotFoundError(f"TreatmentPlan '{plan_id}' was not found")
    patient = db.get(Patient, plan.patient_id)
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError(f"TreatmentPlan '{plan_id}' was not found")
    return plan


def _require_patient(db: Session, patient_id: int, tenant_id: int) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


def tenant_item_ids(tenant_id: int):  # noqa: ANN201
    """Subquery of every item id belonging to ``tenant_id`` (items carry no
    ``tenant_id`` column — tenancy flows item -> plan -> patient)."""
    return (
        select(TreatmentPlanItem.id)
        .join(TreatmentPlan, TreatmentPlan.id == TreatmentPlanItem.plan_id)
        .join(Patient, Patient.id == TreatmentPlan.patient_id)
        .where(Patient.tenant_id == tenant_id)
    )


# ── item <-> charge link (PROC-INT-1/2) ──────────────────────────────────────
def live_charges_for_items(db: Session, item_ids: list[str]) -> dict[str, PatientProcedure]:
    """item_id -> the newest non-void charge referencing it (batched)."""
    if not item_ids:
        return {}
    rows = db.execute(
        select(PatientProcedure)
        .where(
            PatientProcedure.treatment_plan_item_id.in_(item_ids),
            PatientProcedure.is_void.is_(False),
        )
        .order_by(PatientProcedure.created_at.asc(), PatientProcedure.id.asc())
    ).scalars().all()
    out: dict[str, PatientProcedure] = {}
    for row in rows:
        out[row.treatment_plan_item_id] = row  # later rows win -> newest
    return out


def item_has_live_charge(db: Session, item_id: str, *, exclude_procedure_id: str | None = None) -> bool:
    stmt = select(func.count()).select_from(PatientProcedure).where(
        PatientProcedure.treatment_plan_item_id == item_id,
        PatientProcedure.is_void.is_(False),
    )
    if exclude_procedure_id is not None:
        stmt = stmt.where(PatientProcedure.id != exclude_procedure_id)
    return (db.execute(stmt).scalar_one() or 0) > 0


def resolve_item_for_charge(
    db: Session, item_id: str, *, patient_id: int, treatment_plan_id: str | None
) -> TreatmentPlanItem:
    """The item a charge wants to fulfil, checked against the charge's patient
    and (when given) plan. A mis-pointed item id would complete another
    patient's treatment, so both mismatches are 422s, not silent writes."""
    item = db.get(TreatmentPlanItem, item_id)
    if item is None:
        raise ValidationError(
            f"Treatment plan item '{item_id}' was not found",
            details={"code": "plan_item_not_found", "field": "treatment_plan_item_id"},
        )
    plan = db.get(TreatmentPlan, item.plan_id)
    if plan is None or plan.patient_id != patient_id:
        raise ValidationError(
            "The treatment plan item belongs to a different patient",
            details={"code": "plan_item_patient_mismatch", "field": "treatment_plan_item_id"},
        )
    if treatment_plan_id and treatment_plan_id != item.plan_id:
        raise ValidationError(
            "treatment_plan_id does not match the item's plan",
            details={"code": "plan_item_plan_mismatch", "field": "treatment_plan_id",
                     "item_plan_id": item.plan_id},
        )
    return item


def bind_item_to_charge(db: Session, item: TreatmentPlanItem, charge: PatientProcedure) -> None:
    """Flip the item to ``completed`` and let it adopt what the charge knows
    (service date, provider, tooth/surface/quadrant/material) where it was blank.
    No commit — the caller owns the transaction."""
    item.status = COMPLETED_STATUS
    item.status_before_scheduled = None
    if item.end_date is None:
        item.end_date = charge.date_of_service
    if item.provider_id is None and charge.provider_id:
        item.provider_id = charge.provider_id
    for field in ("tooth", "surface", "quadrant", "material_id"):
        if getattr(item, field) is None and getattr(charge, field) is not None:
            setattr(item, field, getattr(charge, field))
    if item.is_archived:
        item.is_archived = False  # a charge against an archived item un-archives it


def release_item(db: Session, item_id: str | None, *, exclude_procedure_id: str | None) -> None:
    """Undo :func:`bind_item_to_charge` when the charge is voided / re-pointed,
    unless another live charge still fulfils the item. No commit."""
    if not item_id:
        return
    if item_has_live_charge(db, item_id, exclude_procedure_id=exclude_procedure_id):
        return
    item = db.get(TreatmentPlanItem, item_id)
    if item is None or item.status != COMPLETED_STATUS:
        return
    item.status = RELEASED_STATUS
    item.end_date = None


# ── item <-> appointment link (PLAN-APPT-1/2) ────────────────────────────────
def appointment_is_live(appt: Appointment | None) -> bool:
    return appt is not None and not appt.is_archived and not appt.is_cancelled


def live_appointment_links(
    db: Session, item_ids: list[str], *, exclude_line_id: int | None = None,
    exclude_appointment_id: str | None = None,
) -> dict[str, list[Appointment]]:
    """item_id -> live appointments (soonest first) whose non-archived lines
    book the item. A cancelled / archived appointment does not count."""
    if not item_ids:
        return {}
    stmt = (
        select(AppointmentProcedure.treatment_plan_item_id, Appointment)
        .join(Appointment, Appointment.id == AppointmentProcedure.appointment_id)
        .where(
            AppointmentProcedure.treatment_plan_item_id.in_(item_ids),
            AppointmentProcedure.is_archived.is_(False),
            Appointment.is_archived.is_(False),
            Appointment.is_cancelled.is_(False),
        )
        .order_by(Appointment.date.asc(), Appointment.start_time.asc(), Appointment.id.asc())
    )
    if exclude_line_id is not None:
        stmt = stmt.where(AppointmentProcedure.id != exclude_line_id)
    if exclude_appointment_id is not None:
        stmt = stmt.where(Appointment.id != exclude_appointment_id)
    out: dict[str, list[Appointment]] = {}
    seen: set[tuple[str, str]] = set()
    for item_id, appt in db.execute(stmt).all():
        if (item_id, appt.id) in seen:
            continue
        seen.add((item_id, appt.id))
        out.setdefault(item_id, []).append(appt)
    return out


def resolve_item_for_appointment(
    db: Session, item_id: str, *, patient_id: int | None, treatment_plan_id: str | None
) -> TreatmentPlanItem:
    """The item an appointment line books. Same patient/plan checks as a charge,
    plus: an archived or completed item cannot be booked (422)."""
    item = resolve_item_for_charge(
        db, item_id, patient_id=patient_id, treatment_plan_id=treatment_plan_id
    )
    if item.is_archived:
        raise ValidationError(
            "This item has been deleted; restore it before booking",
            details={"code": "item_archived", "field": "treatment_plan_item_id"},
        )
    if item.status == COMPLETED_STATUS:
        raise ValidationError(
            "This item has already been completed (a charge was posted against it)",
            details={"code": "item_completed", "field": "treatment_plan_item_id"},
        )
    return item


def schedule_item(db: Session, item: TreatmentPlanItem, appt: Appointment) -> None:
    """PLAN-APPT-1: mark the item ``scheduled`` on ``appt``, remembering the
    status it came from. Idempotent; never touches a completed item. No commit."""
    if item.status == COMPLETED_STATUS:
        return
    if item.status != SCHEDULED_STATUS:
        item.status_before_scheduled = item.status
        item.status = SCHEDULED_STATUS
    if item.scheduled_date is None or appt.date < item.scheduled_date:
        item.scheduled_date = appt.date
    if item.provider_id is None and appt.provider_id:
        item.provider_id = appt.provider_id


def release_scheduled_item(
    db: Session, item_id: str | None, *, exclude_line_id: int | None = None,
    exclude_appointment_id: str | None = None,
) -> None:
    """Undo :func:`schedule_item` when the booking goes away (line archived /
    re-pointed, appointment cancelled or deleted). If another live booking
    remains the item stays scheduled and ``scheduled_date`` follows the soonest
    one. No commit."""
    if not item_id:
        return
    item = db.get(TreatmentPlanItem, item_id)
    if item is None or item.status == COMPLETED_STATUS:
        return
    remaining = live_appointment_links(
        db, [item_id], exclude_line_id=exclude_line_id,
        exclude_appointment_id=exclude_appointment_id,
    ).get(item_id, [])
    if remaining:
        item.scheduled_date = remaining[0].date
        return
    if item.status == SCHEDULED_STATUS:
        item.status = item.status_before_scheduled or RELEASED_STATUS
    item.status_before_scheduled = None
    item.scheduled_date = None


def _appointment_item_ids(db: Session, appt_id: str) -> list[str]:
    return list(db.execute(
        select(AppointmentProcedure.treatment_plan_item_id).where(
            AppointmentProcedure.appointment_id == appt_id,
            AppointmentProcedure.is_archived.is_(False),
            AppointmentProcedure.treatment_plan_item_id.is_not(None),
        ).distinct()
    ).scalars().all())


def schedule_items_for_appointment(db: Session, appt: Appointment) -> list[str]:
    """Every item booked by ``appt``'s live lines becomes ``scheduled``. No commit."""
    ids = _appointment_item_ids(db, appt.id)
    for item_id in ids:
        item = db.get(TreatmentPlanItem, item_id)
        if item is not None and not item.is_archived:
            schedule_item(db, item, appt)
    return ids


def unschedule_items_for_appointment(db: Session, appt: Appointment) -> list[str]:
    """Release every item ``appt`` books (the appointment itself is excluded from
    the "other live bookings" check because it is the one going away). No commit."""
    ids = _appointment_item_ids(db, appt.id)
    for item_id in ids:
        release_scheduled_item(db, item_id, exclude_appointment_id=appt.id)
    return ids


def resync_items_for_appointment(db: Session, appt: Appointment) -> None:
    """After an appointment moves (date change) keep ``scheduled_date`` honest."""
    for item_id in _appointment_item_ids(db, appt.id):
        release_scheduled_item(db, item_id)  # recomputes the soonest live date


# ── read enrich (PROC-INT-1, PLAN-25/26/27/29, PLAN-APPT-2) ──────────────────
def _icd_links(db: Session, item_ids: list[str]) -> dict[str, list[ItemIcdCodeRead]]:
    if not item_ids:
        return {}
    rows = db.execute(
        select(TreatmentPlanItemIcdCode, IcdCode)
        .join(IcdCode, IcdCode.id == TreatmentPlanItemIcdCode.icd_code_id)
        .where(TreatmentPlanItemIcdCode.plan_item_id.in_(item_ids))
        .order_by(TreatmentPlanItemIcdCode.ordinal.asc(), TreatmentPlanItemIcdCode.id.asc())
    ).all()
    out: dict[str, list[ItemIcdCodeRead]] = {}
    for link, icd in rows:
        out.setdefault(link.plan_item_id, []).append(ItemIcdCodeRead(
            id=icd.id, code=icd.code, icd10=icd.icd10, description=icd.description,
            ordinal=link.ordinal,
        ))
    return out


def _referral_label(r: Referral) -> str:
    person = " ".join(x for x in (r.first_name, r.last_name) if x).strip()
    return person or r.practice_name or r.contact_name or f"Referral {r.id}"


def enrich_treatment_plan_item(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    """One query per lookup for the whole page: the live charge (PROC-INT-1),
    live bookings (PLAN-APPT-2), ICD links (PLAN-26), actor / counselor names
    (PLAN-25 / PLAN-11), fee-schedule name (PLAN-29), referral label (PLAN-27)."""
    rows = list(items)
    ids = [r.id for r in rows]
    charges = live_charges_for_items(db, ids)
    links = live_appointment_links(db, ids)
    icd = _icd_links(db, ids)
    user_ids = {
        uid for r in rows
        for uid in (getattr(r, "created_by", None), getattr(r, "updated_by", None),
                    getattr(r, "counselor_user_id", None))
        if uid is not None
    }
    names = resolve_user_names(db, user_ids)
    fs_ids = {r.fee_schedule_id for r in rows if getattr(r, "fee_schedule_id", None)}
    fs_names = {
        f.id: f.name for f in db.execute(select(FeeSchedule).where(FeeSchedule.id.in_(fs_ids))).scalars()
    } if fs_ids else {}
    ref_ids = {r.referral_id for r in rows if getattr(r, "referral_id", None)}
    ref_names = {
        r.id: _referral_label(r)
        for r in db.execute(select(Referral).where(Referral.id.in_(ref_ids))).scalars()
    } if ref_ids else {}
    for row in rows:
        charge = charges.get(row.id)
        row.procedure_id = charge.id if charge is not None else None
        appts = links.get(row.id, [])
        row.appointment_id = appts[0].id if appts else None
        row.appointment_ids = [a.id for a in appts]
        codes = icd.get(row.id, [])
        row.icd_codes = codes
        row.icd_code_ids = [c.id for c in codes]
        row.created_by_name = names.get(row.created_by) if row.created_by is not None else None
        row.updated_by_name = names.get(row.updated_by) if row.updated_by is not None else None
        row.counselor_name = (
            names.get(row.counselor_user_id) if row.counselor_user_id is not None else None
        )
        row.fee_schedule_name = fs_names.get(row.fee_schedule_id) if row.fee_schedule_id else None
        row.referral_name = ref_names.get(row.referral_id) if row.referral_id else None


def _item_patient_id(db: Session, item: TreatmentPlanItem) -> int | None:
    plan = db.get(TreatmentPlan, item.plan_id)
    return plan.patient_id if plan is not None else None


def _reject_status_change(db: Session, current: TreatmentPlanItem, new_status: str) -> None:
    if new_status == current.status:
        return
    has_charge = item_has_live_charge(db, current.id)
    if new_status == COMPLETED_STATUS and not has_charge:
        raise ValidationError(
            "An item becomes 'completed' when a charge is posted against it "
            "(patient_procedures.treatment_plan_item_id), not by setting the status",
            details={"code": "status_requires_charge", "field": "status"},
        )
    if current.status == COMPLETED_STATUS and has_charge:
        raise ValidationError(
            "A posted charge still references this item; void the charge to reopen it",
            details={"code": "item_has_posted_charge", "field": "status"},
        )


# ── Edit Treatment window: reference validation, defaults, ICD links ────────
def _plan_office_tz(db: Session, plan: TreatmentPlan | None) -> str | None:
    if plan is None or plan.office_id is None:
        return None
    office = db.get(Office, plan.office_id)
    return getattr(office, "timezone", None)


def _validate_item_refs(db: Session, payload: dict, tenant_id: int | None) -> None:
    """422 on a reference that is missing or belongs to another tenant. Only the
    keys present in the payload are checked, so a partial PATCH is safe."""
    if tenant_id is None:
        return
    if payload.get("referral_id") is not None:
        ref = db.get(Referral, payload["referral_id"])
        if ref is None or ref.tenant_id != tenant_id:
            raise ValidationError(
                f"Referral '{payload['referral_id']}' was not found",
                details={"code": "referral_not_found", "field": "referral_id"},
            )
    if payload.get("referral_type") is not None:
        rt = str(payload["referral_type"]).strip().lower()
        if rt not in REFERRAL_TYPES:
            raise ValidationError(
                f"referral_type must be one of {list(REFERRAL_TYPES)}",
                details={"code": "invalid_referral_type", "field": "referral_type"},
            )
        payload["referral_type"] = rt
    if payload.get("counselor_user_id") is not None:
        user = db.get(User, payload["counselor_user_id"])
        if user is None or user.tenant_id != tenant_id:
            raise ValidationError(
                f"User '{payload['counselor_user_id']}' was not found",
                details={"code": "counselor_not_found", "field": "counselor_user_id"},
            )
    if payload.get("fee_schedule_id") is not None:
        fs = db.get(FeeSchedule, payload["fee_schedule_id"])
        if fs is None or fs.tenant_id != tenant_id:
            raise ValidationError(
                f"Fee schedule '{payload['fee_schedule_id']}' was not found",
                details={"code": "fee_schedule_not_found", "field": "fee_schedule_id"},
            )
    if payload.get("provider_id") is not None:
        prov = db.get(Provider, payload["provider_id"])
        if prov is None or prov.tenant_id != tenant_id:
            raise ValidationError(
                f"Provider '{payload['provider_id']}' was not found",
                details={"code": "provider_not_found", "field": "provider_id"},
            )


def resolve_provider_from_label(db: Session, label: str | None, tenant_id: int | None) -> str | None:
    """PLAN-APPT-3: ``diagnosed_by`` holds either a provider id or (on migrated
    rows, via ``s27b``) the Denticon PROVIDERID — i.e. ``providers.legacy_id``."""
    if not label or tenant_id is None:
        return None
    label = label.strip()
    prov = db.get(Provider, label)
    if prov is not None and prov.tenant_id == tenant_id:
        return prov.id
    return db.execute(
        select(Provider.id).where(Provider.tenant_id == tenant_id, Provider.legacy_id == label)
        .order_by(Provider.is_active.desc(), Provider.id.asc()).limit(1)
    ).scalar_one_or_none()


def _default_provider(db: Session, payload: dict, plan: TreatmentPlan | None, tenant_id: int | None) -> None:
    """PLAN-APPT-3: a new item with no ``provider_id`` takes the diagnosing
    provider, else the provider the rest of the plan uses, else the patient's
    preferred provider. Stays nullable — refusing the save would break the
    add-procedure panel, which does not always know a provider."""
    if payload.get("provider_id") is not None or tenant_id is None or plan is None:
        return
    pid = resolve_provider_from_label(db, payload.get("diagnosed_by"), tenant_id)
    if pid is None:
        pid = db.execute(
            select(TreatmentPlanItem.provider_id)
            .where(TreatmentPlanItem.plan_id == plan.id,
                   TreatmentPlanItem.provider_id.is_not(None),
                   TreatmentPlanItem.is_archived.is_(False))
            .group_by(TreatmentPlanItem.provider_id)
            .order_by(func.count().desc(), TreatmentPlanItem.provider_id.asc())
            .limit(1)
        ).scalar_one_or_none()
    if pid is None:
        patient = db.get(Patient, plan.patient_id)
        pid = getattr(patient, "preferred_provider_id", None)
    if pid is not None:
        payload["provider_id"] = pid


def _price_item(db: Session, payload: dict, plan: TreatmentPlan | None, tenant_id: int | None) -> None:
    """PLAN-29 / FEE-3: an omitted ``fee`` is priced through the same resolver a
    charge uses and the schedule is recorded; an explicit fee always wins, and
    the schedule is recorded beside it only when it is the schedule that would
    have produced that exact amount (so "Fee Schedule Used" never lies)."""
    if tenant_id is None or plan is None or not payload.get("procedure_code"):
        return
    if payload.get("fee") is not None and payload.get("fee_schedule_id") is not None:
        return
    try:
        quote = pricing_service.resolve_procedure_fee(
            db, tenant_id, payload["procedure_code"],
            patient_id=plan.patient_id, office_id=plan.office_id,
            provider_id=payload.get("provider_id"),
        )
    except NotFoundError:
        return
    if payload.get("fee") is None:
        payload["fee"] = quote["fee"]
        if quote.get("fee_schedule_id"):
            payload["fee_schedule_id"] = quote["fee_schedule_id"]
    elif quote.get("fee_schedule_id") and Decimal(str(quote["fee"])) == Decimal(str(payload["fee"])):
        payload["fee_schedule_id"] = quote["fee_schedule_id"]


def _stamp_accepted(payload: dict, current: TreatmentPlanItem | None, tz: str | None) -> None:
    """PLAN-18: ``accepted_date`` = the day the line first became accepted,
    unless the caller states one."""
    if payload.get("status") != ACCEPTED_STATUS or "accepted_date" in payload:
        return
    if current is not None and (current.status == ACCEPTED_STATUS or current.accepted_date is not None):
        return
    payload["accepted_date"] = office_today(tz)


def _validate_icd_ids(db: Session, icd_ids: list[int]) -> list[int]:
    ordered: list[int] = []
    for i in icd_ids:
        if i not in ordered:
            ordered.append(int(i))
    if not ordered:
        return []
    found = set(db.execute(select(IcdCode.id).where(IcdCode.id.in_(ordered))).scalars().all())
    missing = [i for i in ordered if i not in found]
    if missing:
        raise ValidationError(
            f"Unknown ICD code id(s): {missing}",
            details={"code": "icd_code_not_found", "field": "icd_code_ids", "missing": missing},
        )
    return ordered


def _set_icd_codes(db: Session, item_id: str, icd_ids: list[int]) -> None:
    """Reconcile the item's diagnosis set to ``icd_ids`` (ordered). No commit."""
    existing = {
        link.icd_code_id: link
        for link in db.execute(
            select(TreatmentPlanItemIcdCode).where(TreatmentPlanItemIcdCode.plan_item_id == item_id)
        ).scalars()
    }
    for code_id, link in existing.items():
        if code_id not in icd_ids:
            db.delete(link)
    for ordinal, code_id in enumerate(icd_ids, start=1):
        link = existing.get(code_id)
        if link is None:
            db.add(TreatmentPlanItemIcdCode(plan_item_id=item_id, icd_code_id=code_id, ordinal=ordinal))
        elif link.ordinal != ordinal:
            link.ordinal = ordinal


def set_item_icd_codes(db: Session, item_id: str, tenant_id: int, icd_ids: list[int]) -> TreatmentPlanItem:
    """PUT-style replace of the ICD-10 set (``[]`` = clear all). Commits."""
    item = db.get(TreatmentPlanItem, item_id)
    if item is None:
        raise NotFoundError(f"TreatmentPlanItem '{item_id}' was not found")
    _require_plan(db, item.plan_id, tenant_id)
    ordered = _validate_icd_ids(db, icd_ids)
    _set_icd_codes(db, item_id, ordered)
    db.commit()
    db.refresh(item)
    return item


# ── PLAN-13/14 + PROC-INT-2/3/8 + Edit Treatment: item CRUD ─────────────────
class TreatmentPlanItemCRUD(CRUDBase):
    def _scope_tenant(self, stmt, tenant_id: int | None):  # noqa: ANN001
        if tenant_id is None:
            return stmt
        return stmt.where(TreatmentPlanItem.id.in_(tenant_item_ids(tenant_id)))

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        payload = apply_entry_rules(db, data)
        icd_ids = payload.pop("icd_code_ids", None)
        plan = _require_plan(db, payload["plan_id"], tenant_id) if tenant_id is not None \
            else db.get(TreatmentPlan, payload["plan_id"])
        if payload.get("status") == COMPLETED_STATUS:
            raise ValidationError(
                "A new item cannot be 'completed' — post a charge against it instead",
                details={"code": "status_requires_charge", "field": "status"},
            )
        _validate_item_refs(db, payload, tenant_id)
        _default_provider(db, payload, plan, tenant_id)
        _price_item(db, payload, plan, tenant_id)
        if payload.get("fee") is None:
            payload["fee"] = Decimal("0")
        _stamp_accepted(payload, None, _plan_office_tz(db, plan))
        ordered = _validate_icd_ids(db, icd_ids) if icd_ids is not None else None

        # Same steps as CRUDBase.create, inlined so the ICD links land in the
        # same transaction as the item.
        if created_by is not None and self._is_int_col("created_by"):
            payload.setdefault("created_by", created_by)
        obj = self.model(**payload)
        db.add(obj)
        if ordered:
            db.flush()
            _set_icd_codes(db, obj.id, ordered)
        self._commit(db)
        db.refresh(obj)
        self._audit(obj, after=dict(payload))
        procedure_events.announce(
            tenant_id, plan.patient_id if plan else None, source=ITEM_SOURCE, action="created",
            entity_id=obj.id, treatment_plan_id=obj.plan_id, treatment_plan_item_id=obj.id,
            actor_user_id=created_by,
        )
        return obj

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        current = self.get(db, obj_id, tenant_id=tenant_id)
        payload = apply_entry_rules(db, data, current)
        icd_ids = payload.pop("icd_code_ids", None)
        if "status" in payload and payload["status"] is not None:
            _reject_status_change(db, current, payload["status"])
        patient_id = _item_patient_id(db, current)
        plan = db.get(TreatmentPlan, current.plan_id)
        if payload.get("plan_id") and payload["plan_id"] != current.plan_id:
            target = db.get(TreatmentPlan, payload["plan_id"])
            if target is None or target.patient_id != patient_id:
                raise ValidationError(
                    "An item can only move to another plan of the same patient",
                    details={"code": "plan_patient_mismatch", "field": "plan_id"},
                )
        _validate_item_refs(db, payload, tenant_id)
        _stamp_accepted(payload, current, _plan_office_tz(db, plan))
        if icd_ids is not None:
            _set_icd_codes(db, current.id, _validate_icd_ids(db, icd_ids))
        obj = super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)
        procedure_events.announce(
            tenant_id, patient_id, source=ITEM_SOURCE, action="updated",
            entity_id=obj.id, treatment_plan_id=obj.plan_id, treatment_plan_item_id=obj.id,
            actor_user_id=updated_by,
        )
        return obj

    def delete(self, db: Session, obj_id, *, tenant_id=None) -> None:  # noqa: ANN001
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        patient_id = _item_patient_id(db, obj)
        # Archive the item's insurance-details so none stay active or block re-deletes.
        db.execute(
            update(TreatmentPlanInsuranceDetail)
            .where(TreatmentPlanInsuranceDetail.plan_item_id == obj_id)
            .values(is_archived=True)
        )
        setattr(obj, self.soft_delete_field, self.soft_delete_value)  # is_archived = True
        self._commit(db)
        procedure_events.announce(
            tenant_id, patient_id, source=ITEM_SOURCE, action="deleted",
            entity_id=obj.id, treatment_plan_id=obj.plan_id, treatment_plan_item_id=obj.id,
        )


# ── PLAN-9 + tenancy: insurance-detail CRUD ─────────────────────────────────
def normalise_preauth_status(value: Any) -> str | None:  # noqa: ANN401
    if value is None:
        return None
    text = str(value).strip().lower()
    if text == "":
        return None
    if text not in PREAUTH_STATUSES:
        raise ValidationError(
            f"preauth_status must be one of {list(PREAUTH_STATUSES)}",
            details={"code": "invalid_preauth_status", "field": "preauth_status"},
        )
    return text


class TreatmentPlanInsuranceDetailCRUD(CRUDBase):
    """``treatment_plan_insurance_details`` carries no ``tenant_id`` — before this
    any tenant could read / write any detail row by id. Tenancy flows through the
    owning item. PLAN-9: ``preauth_status`` is normalised and its change stamped."""

    def _scope_tenant(self, stmt, tenant_id: int | None):  # noqa: ANN001
        if tenant_id is None:
            return stmt
        return stmt.where(TreatmentPlanInsuranceDetail.plan_item_id.in_(tenant_item_ids(tenant_id)))

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        payload = dict(data)
        if tenant_id is not None:
            item = db.get(TreatmentPlanItem, payload.get("plan_item_id"))
            if item is None:
                raise ValidationError(
                    f"Treatment plan item '{payload.get('plan_item_id')}' was not found",
                    details={"code": "plan_item_not_found", "field": "plan_item_id"},
                )
            _require_plan(db, item.plan_id, tenant_id)
        if "preauth_status" in payload:
            payload["preauth_status"] = normalise_preauth_status(payload["preauth_status"])
            if payload["preauth_status"] is not None:
                payload["preauth_status_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        current = self.get(db, obj_id, tenant_id=tenant_id)
        payload = dict(data)
        if "preauth_status" in payload:
            payload["preauth_status"] = normalise_preauth_status(payload["preauth_status"])
            if payload["preauth_status"] != current.preauth_status:
                payload["preauth_status_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        return super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)


# ── summary ───────────────────────────────────────────────────────────────────
def plan_summary(db: Session, plan_id: str, tenant_id: int) -> TreatmentPlanSummary:
    plan = _require_plan(db, plan_id, tenant_id)
    items = db.execute(
        select(TreatmentPlanItem).where(
            TreatmentPlanItem.plan_id == plan_id,
            TreatmentPlanItem.is_archived.is_(False),
        )
    ).scalars().all()

    total_fee = sum((i.fee for i in items), Decimal("0"))
    total_ins = sum((i.insurance_estimate for i in items), Decimal("0"))
    return TreatmentPlanSummary(
        plan_id=plan.id,
        name=plan.name,
        status=plan.status,
        item_count=len(items),
        total_fee=total_fee,
        total_insurance_estimate=total_ins,
        total_patient_estimate=total_fee - total_ins,
    )


# ── PLAN-12 / PROC-INT-4: a patient's items across all plans, paged ──────────
def list_patient_items(
    db: Session,
    patient_id: int,
    tenant_id: int,
    *,
    include_archived: bool = False,
    plan_id: str | None = None,
    status: str | None = None,
    procedure_code: str | None = None,
    include_completed: bool = True,
    page: int = 1,
    size: int = 200,
) -> tuple[list[TreatmentPlanItem], int]:
    """One query over every plan of the patient (tenant-scoped via the plan
    join). Returns ``(items, total)`` so the route can wrap it in the standard
    paginated envelope — the bare array ignored ``size`` (PROC-INT-4)."""
    _require_patient(db, patient_id, tenant_id)
    stmt = (
        select(TreatmentPlanItem)
        .join(TreatmentPlan, TreatmentPlan.id == TreatmentPlanItem.plan_id)
        .where(TreatmentPlan.patient_id == patient_id)
    )
    if not include_archived:
        stmt = stmt.where(TreatmentPlanItem.is_archived.is_(False))
    if plan_id:
        stmt = stmt.where(TreatmentPlanItem.plan_id == plan_id)
    if status:
        stmt = stmt.where(TreatmentPlanItem.status == status)
    elif not include_completed:
        stmt = stmt.where(TreatmentPlanItem.status != COMPLETED_STATUS)
    if procedure_code:
        stmt = stmt.where(TreatmentPlanItem.procedure_code == procedure_code)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = (
        stmt.order_by(TreatmentPlanItem.plan_id, TreatmentPlanItem.priority, TreatmentPlanItem.id)
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(db.execute(stmt).scalars().all()), int(total)


# ── PROC-INT-1/2 + PLAN-28: Post to Ledger, server-side and atomic ───────────
def _estimate_single_item(
    db: Session, tenant_id: int, patient_id: int, item: TreatmentPlanItem, fee: Decimal,
    office_id: int | None,
) -> Decimal | None:
    """PLAN-28 ``re_estimate_at_posting``: the charge-side estimate engine
    (CHG-1/7) run for this one line, against the patient's coverage *today*."""
    from app.services import estimate_service  # local: estimate_service is import-light

    try:
        result = estimate_service.estimate(
            db, patient_id, tenant_id,
            lines=[{"procedure_code": item.procedure_code, "fee": fee,
                    "provider_id": item.provider_id}],
            office_id=office_id,
        )
    except NotFoundError:
        return None
    lines = result.get("lines") or []
    return Decimal(str(lines[0]["insurance_estimate"])) if lines else None


def post_item_to_ledger(
    db: Session,
    item_id: str,
    tenant_id: int,
    body: dict[str, Any],
    *,
    created_by: int | None = None,
) -> PatientProcedure:
    """Create the charge that fulfils ``item_id`` and close the item in one
    transaction. The charge inherits the item (code, tooth, surface, quadrant,
    material, fee, estimate, provider, duration) and the plan/patient (office);
    anything in ``body`` overrides. 409 if a live charge already fulfils the item.

    PLAN-28: ``update_end_date_at_posting`` forces ``end_date`` to the service
    date even when one was set; ``re_estimate_at_posting`` recomputes the
    insurance estimate from today's coverage before the charge is priced. Both
    read the item's stored flag unless the body overrides them."""
    item = db.get(TreatmentPlanItem, item_id)
    if item is None:
        raise NotFoundError(f"TreatmentPlanItem '{item_id}' was not found")
    plan = _require_plan(db, item.plan_id, tenant_id)
    patient = db.get(Patient, plan.patient_id)
    if item.is_archived:
        raise ValidationError(
            "This item has been deleted; restore it before posting",
            details={"code": "item_archived", "field": "treatment_plan_item_id"},
        )
    existing = live_charges_for_items(db, [item.id]).get(item.id)
    if existing is not None:
        raise ConflictError(
            "A charge has already been posted for this item",
            details={"code": "item_already_posted", "procedure_id": existing.id},
        )

    provider_id = body.get("provider_id") or item.provider_id
    if not provider_id:
        raise ValidationError(
            "A treating provider is required to post a charge",
            details={"code": "provider_required", "field": "provider_id"},
        )
    office_id = body.get("office_id") or plan.office_id or patient.home_office_id
    if not office_id:
        raise ValidationError(
            "An office is required to post a charge",
            details={"code": "office_required", "field": "office_id"},
        )
    office = db.get(Office, office_id)
    service_date: date_type = body.get("date_of_service") or office_today(
        getattr(office, "timezone", None)
    )
    update_end = body.get("update_end_date_at_posting")
    update_end = bool(item.update_end_date_at_posting) if update_end is None else bool(update_end)
    re_est = body.get("re_estimate_at_posting")
    re_est = bool(item.re_estimate_at_posting) if re_est is None else bool(re_est)

    fee = body.get("fee")
    fee = item.fee if fee is None else fee
    ins = body.get("insurance_estimate")
    if ins is None and re_est:
        ins = _estimate_single_item(db, tenant_id, plan.patient_id, item, Decimal(fee), office_id)
    ins = (item.insurance_estimate or Decimal("0")) if ins is None else ins
    pat = body.get("patient_estimate")
    pat = (Decimal(fee) - Decimal(ins)) if pat is None else pat

    if update_end:
        # bind_item_to_charge only fills a blank end_date; the flag means "always".
        item.end_date = None
    if re_est:
        item.insurance_estimate = Decimal(ins)

    data: dict[str, Any] = {
        "id": body.get("procedure_id") or f"PP-{uuid7()}",
        "patient_id": plan.patient_id,
        "procedure_code": item.procedure_code,
        "date_of_service": service_date,
        "provider_id": provider_id,
        "office_id": office_id,
        "tooth": item.tooth,
        "surface": item.surface,
        "quadrant": item.quadrant,
        "material_id": item.material_id,
        "fee": fee,
        "insurance_estimate": ins,
        "patient_estimate": pat,
        "apply_to": body.get("apply_to") or "P",
        "billing_order": body.get("billing_order") or item.billing_order,
        "hygienist_id": body.get("hygienist_id"),
        "appointment_id": body.get("appointment_id"),
        "notes": body.get("notes"),
        "duration_minutes": item.duration_minutes,  # PLAN-19
        "fee_schedule_id": item.fee_schedule_id,  # PLAN-29
        "treatment_plan_id": plan.id,
        "treatment_plan_item_id": item.id,
    }
    data = {k: v for k, v in data.items() if v is not None}
    # Local import: patient_procedure_service imports this module for the link helpers.
    from app.services.patient_procedure_service import patient_procedure_crud

    return patient_procedure_crud.create(db, data, tenant_id=tenant_id, created_by=created_by)


# ── PLAN-3: insurance re-estimate ────────────────────────────────────────────
def _active_insurance(db: Session, patient_id: int) -> PatientInsurance | None:
    rows = db.execute(
        select(PatientInsurance).where(
            PatientInsurance.patient_id == patient_id,
            PatientInsurance.is_active.is_(True),
            PatientInsurance.ins_plan_id.is_not(None),
        )
    ).scalars().all()
    primary = next((r for r in rows if (r.insurance_type or "").lower() == "primary"), None)
    return primary or (rows[0] if rows else None)


def _upsert_detail(db: Session, item: TreatmentPlanItem, ins_plan_id, ins, pat,
                   ded_applied, cov_pct, max_left) -> None:  # noqa: ANN001
    detail = db.execute(
        select(TreatmentPlanInsuranceDetail)
        .where(
            TreatmentPlanInsuranceDetail.plan_item_id == item.id,
            TreatmentPlanInsuranceDetail.is_archived.is_(False),
        )
        .order_by(TreatmentPlanInsuranceDetail.id.asc())
    ).scalars().first()
    if detail is None:
        detail = TreatmentPlanInsuranceDetail(plan_item_id=item.id)
        db.add(detail)
    detail.ins_plan_id = ins_plan_id
    detail.estimated_ins = ins
    detail.estimated_pat = pat
    detail.deductible = ded_applied
    detail.coverage_pct = cov_pct
    detail.annual_max_rem = max_left
    detail.is_archived = False


def re_estimate(
    db: Session, plan_id: str, tenant_id: int, *, phase_id: int | None = None,
    use_new_fees: bool = False,
) -> ReEstimateResult:
    plan = _require_plan(db, plan_id, tenant_id)
    pins = _active_insurance(db, plan.patient_id)

    insured = pins is not None
    ins_plan_id = pins.ins_plan_id if pins else None
    rules: list[InsuranceCoverageRule] = []
    ded_left = Decimal("0")
    max_left: Decimal | None = None  # None = no annual maximum / unlimited
    if insured:
        plan_ins = db.get(InsurancePlan, ins_plan_id)
        ded = pins.deductible_remaining
        if ded is None and plan_ins is not None:
            ded = plan_ins.individual_deductible
        ded_left = ded or Decimal("0")
        mx = pins.max_remaining
        if mx is None and plan_ins is not None:
            mx = plan_ins.individual_max
        max_left = mx  # may stay None (unlimited)
        rules = list(db.execute(
            select(InsuranceCoverageRule).where(InsuranceCoverageRule.ins_plan_id == ins_plan_id)
        ).scalars().all())

    stmt = select(TreatmentPlanItem).where(
        TreatmentPlanItem.plan_id == plan_id,
        TreatmentPlanItem.is_archived.is_(False),
    )
    if phase_id is not None:
        stmt = stmt.where(TreatmentPlanItem.phase_id == phase_id)
    items = db.execute(
        stmt.order_by(TreatmentPlanItem.priority.asc(), TreatmentPlanItem.created_at.asc())
    ).scalars().all()

    # FEE-1: one batched classification of every line's coverage category.
    categories = covcat.categories_for(db, [it.procedure_code for it in items]) if insured else {}
    # PLAN-29 / "Use New Fees": one pricing context for the whole plan.
    ctx = None
    if use_new_fees:
        ctx = pricing_service.build_context(
            db, patient_id=plan.patient_id, office_id=plan.office_id, ins_plan_id=ins_plan_id,
        )

    lines: list[ReEstimateLine] = []
    tot_fee = tot_ins = tot_pat = Decimal("0")
    for it in items:
        fee_schedule_id = None
        fee_source = None
        if use_new_fees:
            try:
                quote = pricing_service.resolve_procedure_fee(
                    db, tenant_id, it.procedure_code, ctx=ctx,
                )
            except NotFoundError:
                quote = None
            if quote is not None:
                it.fee = Decimal(str(quote["fee"]))
                fee_schedule_id = quote.get("fee_schedule_id")
                fee_source = quote.get("fee_source")
                if fee_schedule_id:
                    it.fee_schedule_id = fee_schedule_id
        fee = it.fee or Decimal("0")

        rule = match_coverage_rule(rules, it.procedure_code, categories.get(it.procedure_code)) \
            if insured else None
        cov_pct = Decimal(str(rule.coverage_pct)) if rule is not None and rule.coverage_pct is not None \
            else Decimal("0")
        ded_waived = bool(rule.ded_waived) if rule is not None else False

        ded_applied = Decimal("0")
        base = fee
        if insured and rule is not None and not ded_waived and ded_left > 0 and cov_pct > 0:
            ded_applied = min(ded_left, fee)
            base = fee - ded_applied
            ded_left -= ded_applied

        ins = Decimal("0")
        if insured:
            ins = (base * cov_pct / Decimal("100")).quantize(_CENTS, rounding=ROUND_HALF_UP)
            if max_left is not None:
                ins = min(ins, max(max_left, Decimal("0")))
                max_left -= ins
        pat = fee - ins

        it.insurance_estimate = ins
        _upsert_detail(db, it, ins_plan_id, ins, pat, ded_applied, cov_pct, max_left)

        lines.append(ReEstimateLine(
            item_id=it.id, procedure_code=it.procedure_code, fee=fee,
            coverage_pct=cov_pct, deductible_applied=ded_applied,
            insurance_estimate=ins, patient_estimate=pat,
            coverage_category=categories.get(it.procedure_code),
            rule_start_code=rule.start_code if rule is not None else None,
            fee_schedule_id=fee_schedule_id, fee_source=fee_source,
        ))
        tot_fee += fee
        tot_ins += ins
        tot_pat += pat

    db.commit()
    return ReEstimateResult(
        plan_id=plan.id, insured=insured, ins_plan_id=ins_plan_id, phase_id=phase_id,
        use_new_fees=use_new_fees,
        deductible_remaining_after=ded_left if insured else None,
        annual_max_remaining_after=max_left,
        total_fee=tot_fee, total_insurance_estimate=tot_ins, total_patient_estimate=tot_pat,
        lines=lines,
    )


# ── PLAN-6: server-side report payload ───────────────────────────────────────
def plan_report(db: Session, plan_id: str, tenant_id: int) -> TreatmentPlanReport:
    plan = _require_plan(db, plan_id, tenant_id)
    patient = db.get(Patient, plan.patient_id)
    items = db.execute(
        select(TreatmentPlanItem)
        .where(TreatmentPlanItem.plan_id == plan_id, TreatmentPlanItem.is_archived.is_(False))
        .order_by(TreatmentPlanItem.priority.asc(), TreatmentPlanItem.created_at.asc())
    ).scalars().all()
    # PLAN-21: the deductible applied per line (from the live detail row).
    deductibles: dict[str, Decimal | None] = {}
    if items:
        for det in db.execute(
            select(TreatmentPlanInsuranceDetail).where(
                TreatmentPlanInsuranceDetail.plan_item_id.in_([i.id for i in items]),
                TreatmentPlanInsuranceDetail.is_archived.is_(False),
            ).order_by(TreatmentPlanInsuranceDetail.id.asc())
        ).scalars():
            deductibles.setdefault(det.plan_item_id, det.deductible)

    report_items: list[PlanReportItem] = []
    tot_fee = tot_ins = tot_pat = tot_disc = Decimal("0")
    for it in items:
        fee = it.fee or Decimal("0")
        ins = it.insurance_estimate or Decimal("0")
        disc = it.discount or Decimal("0")
        pat = fee - ins
        report_items.append(PlanReportItem(
            id=it.id, procedure_code=it.procedure_code, description=it.description,
            tooth=it.tooth, surface=it.surface, priority=it.priority, phase_id=it.phase_id,
            status=it.status, fee=fee, discount=it.discount, insurance_estimate=ins,
            patient_estimate=pat, diagnosed_by=it.diagnosed_by, provider_id=it.provider_id,
            diagnosed_date=it.diagnosed_date, deductible_applied=deductibles.get(it.id),
        ))
        tot_fee += fee
        tot_ins += ins
        tot_pat += pat
        tot_disc += disc

    return TreatmentPlanReport(
        plan_id=plan.id, name=plan.name, status=plan.status,
        patient=PlanReportPatient(
            id=patient.id, chart_no=patient.chart_no, first_name=patient.first_name,
            last_name=patient.last_name, dob=patient.dob,
        ),
        item_count=len(items), total_fee=tot_fee, total_discount=tot_disc,
        total_insurance_estimate=tot_ins, total_patient_estimate=tot_pat,
        items=report_items,
    )


# ── PLAN-APPT-5: atomic book-from-plan ───────────────────────────────────────
def item_duration_minutes(db: Session, item: TreatmentPlanItem, code_cache: dict | None = None) -> int:
    """PLAN-19 / PLAN-APPT-7: the item's own duration, else the code default, else 30."""
    if item.duration_minutes is not None:
        return int(item.duration_minutes)
    cache = code_cache if code_cache is not None else {}
    if item.procedure_code not in cache:
        cache[item.procedure_code] = db.get(ProcedureCode, item.procedure_code)
    code = cache[item.procedure_code]
    default = getattr(code, "default_duration_minutes", None) if code is not None else None
    return int(default) if default else DEFAULT_ITEM_DURATION_MINUTES


def _provider_serves_office(db: Session, provider: Provider, office_id: int) -> bool:
    if provider.office_id == office_id:
        return True
    return db.execute(
        select(func.count()).select_from(ProviderOffice).where(
            ProviderOffice.provider_id == provider.id, ProviderOffice.office_id == office_id,
        )
    ).scalar_one() > 0


def default_operatory_for(
    db: Session, provider: Provider, office_id: int
) -> tuple[Operatory | None, str]:
    """PLAN-APPT-4: the provider's declared default chair when it is in this
    office, else the office chair whose column provider is this provider."""
    if provider.default_operatory_id:
        op = db.get(Operatory, provider.default_operatory_id)
        if op is not None and op.office_id == office_id and op.is_active:
            return op, "provider_default"
    op = db.execute(
        select(Operatory).where(
            Operatory.office_id == office_id, Operatory.provider_id == provider.id,
            Operatory.is_active.is_(True),
        ).order_by(Operatory.display_order.asc(), Operatory.id.asc()).limit(1)
    ).scalar_one_or_none()
    return (op, "provider_column") if op is not None else (None, "none")


def book_from_plan(
    db: Session, plan_id: str, tenant_id: int, body: dict[str, Any], *, created_by: int | None = None
) -> BookFromPlanResult:
    """One transaction: the appointment, one ``appointment_procedures`` line per
    item (linked by ``treatment_plan_item_id``), and every item flipped to
    ``scheduled``. Nothing is written if any line fails."""
    plan = _require_plan(db, plan_id, tenant_id)
    patient = db.get(Patient, plan.patient_id)
    item_ids = list(dict.fromkeys(body.get("item_ids") or []))
    if not item_ids:
        raise ValidationError("item_ids is required", details={"code": "items_required", "field": "item_ids"})
    items = {
        it.id: it for it in db.execute(
            select(TreatmentPlanItem).where(TreatmentPlanItem.id.in_(item_ids))
        ).scalars()
    }
    ordered: list[TreatmentPlanItem] = []
    for item_id in item_ids:
        it = items.get(item_id)
        if it is None or it.plan_id != plan.id:
            raise ValidationError(
                f"Item '{item_id}' is not on this treatment plan",
                details={"code": "plan_item_plan_mismatch", "field": "item_ids", "item_id": item_id},
            )
        if it.is_archived:
            raise ValidationError(
                f"Item '{item_id}' has been deleted",
                details={"code": "item_archived", "field": "item_ids", "item_id": item_id},
            )
        if it.status == COMPLETED_STATUS:
            raise ValidationError(
                f"Item '{item_id}' is already completed",
                details={"code": "item_completed", "field": "item_ids", "item_id": item_id},
            )
        ordered.append(it)
    already = live_appointment_links(db, item_ids)
    if already:
        raise ConflictError(
            "One or more items are already booked on a live appointment",
            details={"code": "item_already_scheduled",
                     "bookings": {k: [a.id for a in v] for k, v in already.items()}},
        )

    # ── office ──
    office_id = body.get("office_id") or plan.office_id or patient.home_office_id
    if not office_id:
        raise ValidationError(
            "An office is required to book", details={"code": "office_required", "field": "office_id"},
        )
    office = db.get(Office, office_id)
    if office is None or office.tenant_id != tenant_id:
        raise ValidationError(
            f"Office '{office_id}' was not found", details={"code": "office_not_found", "field": "office_id"},
        )

    # ── operatory (explicit) ──
    operatory: Operatory | None = None
    operatory_source = "none"
    if body.get("operatory_id"):
        operatory = db.get(Operatory, body["operatory_id"])
        if operatory is None or operatory.office_id != office.id:
            raise ValidationError(
                "The operatory is not in the booking office",
                details={"code": "operatory_office_mismatch", "field": "operatory_id"},
            )
        operatory_source = "request"

    # ── provider (PLAN-APPT-3 chain) ──
    provider_id = body.get("provider_id")
    provider_source = "request"
    if not provider_id:
        provider_id, provider_source = ordered[0].provider_id, "item"
    if not provider_id:
        provider_id = next((it.provider_id for it in ordered if it.provider_id), None)
        provider_source = "plan_items"
    if not provider_id and operatory is not None and operatory.provider_id:
        provider_id, provider_source = operatory.provider_id, "operatory"
    if not provider_id and getattr(patient, "preferred_provider_id", None):
        provider_id, provider_source = patient.preferred_provider_id, "patient_preferred"
    if not provider_id:
        raise ValidationError(
            "No provider on the selected items — pass provider_id",
            details={"code": "provider_required", "field": "provider_id"},
        )
    provider = db.get(Provider, provider_id)
    if provider is None or provider.tenant_id != tenant_id:
        raise ValidationError(
            f"Provider '{provider_id}' was not found",
            details={"code": "provider_not_found", "field": "provider_id"},
        )

    # ── operatory (defaulted, PLAN-APPT-4) ──
    if operatory is None:
        operatory, operatory_source = default_operatory_for(db, provider, office.id)

    # ── time ──
    code_cache: dict = {}
    duration = body.get("duration") or sum(item_duration_minutes(db, it, code_cache) for it in ordered)
    start = body["start_time"]
    end_dt = datetime.combine(body["date"], start) + timedelta(minutes=int(duration))
    appt = Appointment(
        id=body.get("appointment_id") or f"APPT-{uuid7()}",
        patient_id=patient.id,
        provider_id=provider.id,
        operatory_id=operatory.id if operatory is not None else None,
        office_id=office.id,
        date=body["date"],
        start_time=start,
        end_time=end_dt.time(),
        duration=int(duration),
        status=body.get("status") or "Scheduled",
        procedure_label=", ".join(dict.fromkeys(it.procedure_code for it in ordered)),
        notes=body.get("notes"),
        treatment_plan_id=plan.id,
        created_by=created_by,
    )
    if db.get(Appointment, appt.id) is not None:
        raise ConflictError(
            f"Appointment '{appt.id}' already exists", details={"code": "appointment_exists"},
        )
    db.add(appt)
    db.flush()

    lines: list[AppointmentProcedure] = []
    for it in ordered:
        fee = it.fee or Decimal("0")
        ins = it.insurance_estimate or Decimal("0")
        line = AppointmentProcedure(
            appointment_id=appt.id,
            procedure_code=it.procedure_code,
            provider_id=it.provider_id or provider.id,
            treatment_plan_id=plan.id,
            treatment_plan_item_id=it.id,
            tooth=it.tooth,
            surface=it.surface,
            description=it.description,
            fee=fee,
            insurance_estimate=ins,
            est_patient=fee - ins,
            billing_order=it.billing_order,
            status=BOOKED_LINE_STATUS,
            duration_minutes=item_duration_minutes(db, it, code_cache),
            material_id=it.material_id,
        )
        db.add(line)
        lines.append(line)
        schedule_item(db, it, appt)
    db.commit()
    for obj in (appt, *lines, *ordered):
        db.refresh(obj)
    enrich_treatment_plan_item(db, ordered, tenant_id)
    for it in ordered:
        procedure_events.announce(
            tenant_id, patient.id, source=ITEM_SOURCE, action="scheduled",
            entity_id=it.id, treatment_plan_id=plan.id, treatment_plan_item_id=it.id,
            actor_user_id=created_by,
        )
    return BookFromPlanResult(
        appointment_id=appt.id, patient_id=patient.id, office_id=office.id,
        provider_id=provider.id, operatory_id=appt.operatory_id,
        date=appt.date, start_time=appt.start_time, end_time=appt.end_time,
        duration=appt.duration, status=appt.status,
        provider_source=provider_source, operatory_source=operatory_source,
        procedures=[BookedProcedureRead.model_validate(line, from_attributes=True) for line in lines],
        items=[TreatmentPlanItemRead.model_validate(it, from_attributes=True) for it in ordered],
    )


# ── EDIT-PLAN-3: the treatment plans an insurance-plan edit touches ──────────
def affected_by_insurance_plan_clause(ins_plan_id: int):
    """WHERE clause for treatment plans a change to ``ins_plan_id``'s coverage
    would re-price: the patient's **active** slot is that plan (what
    :func:`re_estimate` actually reads), or an open item's insurance detail
    was estimated against it (the slot has since moved — the stale estimate
    still names the old plan)."""
    covered_patients = select(PatientInsurance.patient_id).where(
        PatientInsurance.ins_plan_id == ins_plan_id,
        PatientInsurance.is_active.is_(True),
    )
    estimated_plans = (
        select(TreatmentPlanItem.plan_id)
        .join(
            TreatmentPlanInsuranceDetail,
            TreatmentPlanInsuranceDetail.plan_item_id == TreatmentPlanItem.id,
        )
        .where(
            TreatmentPlanInsuranceDetail.ins_plan_id == ins_plan_id,
            TreatmentPlanInsuranceDetail.is_archived.is_(False),
            TreatmentPlanItem.is_archived.is_(False),
            TreatmentPlanItem.status != COMPLETED_STATUS,
        )
    )
    return or_(
        TreatmentPlan.patient_id.in_(covered_patients),
        TreatmentPlan.id.in_(estimated_plans),
    )


class TreatmentPlanCRUD(CRUDBase[TreatmentPlan]):
    """EDIT-PLAN-3: ``GET /treatment-plans?ins_plan_id=`` — the plans a
    coverage edit affects, so the frontend can offer "re-estimate N pending
    treatment plans" (``GET /insurance-plans/{id}/affected-treatment-plans``
    is the same set with per-plan counts)."""

    custom_filter_fields = ("ins_plan_id",)

    def _extra_list_clauses(self, filters: dict[str, Any]) -> list:
        ins_plan_id = filters.get("ins_plan_id")
        if ins_plan_id is None:
            return []
        return [affected_by_insurance_plan_clause(int(ins_plan_id))]
