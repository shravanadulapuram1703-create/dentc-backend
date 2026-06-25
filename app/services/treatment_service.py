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
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.crud.base import CRUDBase
from app.db.models import (
    InsuranceCoverageRule,
    InsurancePlan,
    Patient,
    PatientInsurance,
    TreatmentPlan,
    TreatmentPlanInsuranceDetail,
    TreatmentPlanItem,
)
from app.schemas.treatment import (
    PlanReportItem,
    PlanReportPatient,
    ReEstimateLine,
    ReEstimateResult,
    TreatmentPlanReport,
    TreatmentPlanSummary,
)

_CENTS = Decimal("0.01")


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


# ── PLAN-13/14: item soft-delete that cascades to its insurance-details ───────
class TreatmentPlanItemCRUD(CRUDBase):
    def delete(self, db: Session, obj_id, *, tenant_id=None) -> None:  # noqa: ANN001
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        # Archive the item's insurance-details so none stay active or block re-deletes.
        db.execute(
            update(TreatmentPlanInsuranceDetail)
            .where(TreatmentPlanInsuranceDetail.plan_item_id == obj_id)
            .values(is_archived=True)
        )
        setattr(obj, self.soft_delete_field, self.soft_delete_value)  # is_archived = True
        self._commit(db)


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


# ── PLAN-12: a patient's items across all plans (single query) ───────────────
def list_patient_items(
    db: Session, patient_id: int, tenant_id: int, *, include_archived: bool = False
) -> list[TreatmentPlanItem]:
    _require_patient(db, patient_id, tenant_id)
    stmt = (
        select(TreatmentPlanItem)
        .join(TreatmentPlan, TreatmentPlan.id == TreatmentPlanItem.plan_id)
        .where(TreatmentPlan.patient_id == patient_id)
    )
    if not include_archived:
        stmt = stmt.where(TreatmentPlanItem.is_archived.is_(False))
    stmt = stmt.order_by(TreatmentPlanItem.plan_id, TreatmentPlanItem.priority, TreatmentPlanItem.id)
    return list(db.execute(stmt).scalars().all())


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
