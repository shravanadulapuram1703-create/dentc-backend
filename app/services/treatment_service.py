"""Treatment-plan business logic.

- ``plan_summary`` — roll item fees into a plan total (excludes archived items).
- **PLAN-12** ``list_patient_items`` — all of a patient's plan items in one query
  (no N+1, tenant/patient scoped via the plan join).
- **PLAN-3** ``re_estimate`` — compute per-item insurance benefit from the
  patient's active coverage (coverage %, deductible, annual-max remaining) and
  write ``insurance_estimate`` + the insurance-detail store.
- **PLAN-6** ``plan_report`` — server-side report payload (header + lines + totals).
- **PLAN-13/14** ``TreatmentPlanItemCRUD`` — item delete is a soft-delete that
  also archives the item's insurance-details (so a detail FK can never make an
  item undeletable).
- **PROC-INT-1/2** the item <-> charge link. ``patient_procedures.treatment_plan_item_id``
  is the canonical FK; :func:`bind_item_to_charge` / :func:`release_item` are the
  only two places that move an item into and out of ``status='completed'``, and
  the CRUD refuses a client writing that status by hand unless a live charge
  backs it (``status_requires_charge``) or un-completing an item a live charge
  still references (``item_has_posted_charge``). :func:`post_item_to_ledger` is
  Post to Ledger server-side: one transaction creates the charge *and* closes the
  item, where the client used to do two requests that could half-fail.
- **PROC-INT-8** every item write runs the tooth/surface/quadrant rules in
  ``procedure_rules_service`` (same engine as ``patient_procedures``).
- **PROC-INT-3** every item write announces ``procedures.changed``.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.datetimes import office_today
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.crud.base import CRUDBase
from app.db.models import (
    InsuranceCoverageRule,
    InsurancePlan,
    Office,
    Patient,
    PatientInsurance,
    PatientProcedure,
    TreatmentPlan,
    TreatmentPlanInsuranceDetail,
    TreatmentPlanItem,
)
from app.schemas.treatment import (
    COMPLETED_STATUS,
    PlanReportItem,
    PlanReportPatient,
    ReEstimateLine,
    ReEstimateResult,
    TreatmentPlanReport,
    TreatmentPlanSummary,
)
from app.services import procedure_events
from app.services.procedure_rules_service import apply_entry_rules

_CENTS = Decimal("0.01")
ITEM_SOURCE = "treatment_plan_items"
#: The status an item returns to when the charge that completed it is voided.
#: The pre-completion status is not stored, and "accepted" is the only state an
#: item can honestly be in once it has been treated at least once.
RELEASED_STATUS = "accepted"


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


def enrich_treatment_plan_item(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    """PROC-INT-1: ``procedure_id`` = the live charge fulfilling the item (one query per page)."""
    rows = list(items)
    charges = live_charges_for_items(db, [r.id for r in rows])
    for row in rows:
        charge = charges.get(row.id)
        row.procedure_id = charge.id if charge is not None else None


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


# ── PLAN-13/14 + PROC-INT-2/3/8: item CRUD with rules, link guards, events ───
class TreatmentPlanItemCRUD(CRUDBase):
    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        payload = apply_entry_rules(db, data)
        plan = _require_plan(db, payload["plan_id"], tenant_id) if tenant_id is not None \
            else db.get(TreatmentPlan, payload["plan_id"])
        if payload.get("status") == COMPLETED_STATUS:
            raise ValidationError(
                "A new item cannot be 'completed' — post a charge against it instead",
                details={"code": "status_requires_charge", "field": "status"},
            )
        obj = super().create(db, payload, tenant_id=tenant_id, created_by=created_by)
        procedure_events.announce(
            tenant_id, plan.patient_id if plan else None, source=ITEM_SOURCE, action="created",
            entity_id=obj.id, treatment_plan_id=obj.plan_id, treatment_plan_item_id=obj.id,
            actor_user_id=created_by,
        )
        return obj

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        current = self.get(db, obj_id, tenant_id=tenant_id)
        payload = apply_entry_rules(db, data, current)
        if "status" in payload and payload["status"] is not None:
            _reject_status_change(db, current, payload["status"])
        patient_id = _item_patient_id(db, current)
        if payload.get("plan_id") and payload["plan_id"] != current.plan_id:
            target = db.get(TreatmentPlan, payload["plan_id"])
            if target is None or target.patient_id != patient_id:
                raise ValidationError(
                    "An item can only move to another plan of the same patient",
                    details={"code": "plan_patient_mismatch", "field": "plan_id"},
                )
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


# ── PROC-INT-1/2: Post to Ledger, server-side and atomic ─────────────────────
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
    material, fee, estimate, provider) and the plan/patient (office); anything
    in ``body`` overrides. 409 if a live charge already fulfils the item."""
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
    fee = body.get("fee")
    fee = item.fee if fee is None else fee
    ins = body.get("insurance_estimate")
    ins = (item.insurance_estimate or Decimal("0")) if ins is None else ins
    pat = body.get("patient_estimate")
    pat = (Decimal(fee) - Decimal(ins)) if pat is None else pat

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
        "treatment_plan_id": plan.id,
        "treatment_plan_item_id": item.id,
    }
    data = {k: v for k, v in data.items() if v is not None}
    # Local import: patient_procedure_service imports this module for the link helpers.
    from app.services.patient_procedure_service import patient_procedure_crud

    return patient_procedure_crud.create(db, data, tenant_id=tenant_id, created_by=created_by)


# ── PLAN-3: insurance re-estimate ────────────────────────────────────────────
def _match_rule(rules: list[InsuranceCoverageRule], code: str) -> tuple[Decimal, bool]:
    """Coverage % + deductible-waived for a procedure code. ADA codes share a
    fixed ``D####`` shape, so lexical comparison against the rule range works."""
    for r in rules:
        if r.start_code and r.end_code and r.start_code <= code <= r.end_code:
            return (r.coverage_pct or Decimal("0"), bool(r.ded_waived))
    return (Decimal("0"), False)


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
    db: Session, plan_id: str, tenant_id: int, *, phase_id: int | None = None
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

    lines: list[ReEstimateLine] = []
    tot_fee = tot_ins = tot_pat = Decimal("0")
    for it in items:
        fee = it.fee or Decimal("0")
        cov_pct, ded_waived = _match_rule(rules, it.procedure_code) if insured else (Decimal("0"), False)

        ded_applied = Decimal("0")
        base = fee
        if insured and not ded_waived and ded_left > 0:
            ded_applied = min(ded_left, fee)
            base = fee - ded_applied
            ded_left -= ded_applied

        ins = Decimal("0")
        if insured:
            ins = (base * cov_pct / Decimal("100")).quantize(_CENTS, rounding=ROUND_HALF_UP)
            if max_left is not None:
                ins = min(ins, max_left)
                max_left -= ins
        pat = fee - ins

        it.insurance_estimate = ins
        _upsert_detail(db, it, ins_plan_id, ins, pat, ded_applied, cov_pct, max_left)

        lines.append(ReEstimateLine(
            item_id=it.id, procedure_code=it.procedure_code, fee=fee,
            coverage_pct=cov_pct, deductible_applied=ded_applied,
            insurance_estimate=ins, patient_estimate=pat,
        ))
        tot_fee += fee
        tot_ins += ins
        tot_pat += pat

    db.commit()
    return ReEstimateResult(
        plan_id=plan.id, insured=insured, ins_plan_id=ins_plan_id, phase_id=phase_id,
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
            diagnosed_date=it.diagnosed_date,
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
