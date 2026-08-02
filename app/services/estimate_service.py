"""Charge-time insurance/patient estimate engine (CHG-1 / CHG-7).

Given a patient and one or more procedure codes, derive the insurance-estimate /
patient-estimate split (and the deductible portion, CHG-7) from the patient's
active coverage and the applicable fee schedule — instead of the frontend posting
``insurance_estimate: 0`` / ``patient_estimate: fee``.

The computation is intentionally conservative and self-contained:

* **Fee** — override → the plan's fee-schedule entry → the office default
  fee-schedule entry → the procedure code's ``default_fee``.
* **Coverage %** — the first ``insurance_coverage_rules`` band on the patient's
  primary plan whose ``[start_code, end_code]`` contains the code (0 % if the
  patient has no active plan or no matching band).
* **Deductible** — the plan's remaining deductible is consumed across the lines
  (unless the band waives it), reducing the insured base.
* **Annual max** — the insurance estimate is capped by the plan's remaining max.

Everything is ``Decimal``. No row is written — this is a pure calculator the FE
calls before ``POST /patient-procedures``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import (
    FeeSchedule,
    FeeScheduleAssignment,
    FeeScheduleEntry,
    InsurancePlan,
    InsuranceCoverageRule,
    Office,
    Patient,
    PatientInsurance,
    ProcedureCode,
)

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


def _money(value: Any) -> Decimal:  # noqa: ANN401
    if value is None:
        return _ZERO
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _get_patient(db: Session, patient_id: int, tenant_id: int) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


def _primary_coverage(db: Session, patient_id: int):  # noqa: ANN202
    """The patient's active primary dental slot + its plan, or (None, None)."""
    rows = db.execute(
        select(PatientInsurance).where(
            PatientInsurance.patient_id == patient_id,
            PatientInsurance.is_active.is_(True),
        )
    ).scalars().all()
    if not rows:
        return None, None
    # Prefer an explicit "primary" slot; else the first active slot.
    slot = next(
        (r for r in rows if (r.insurance_type or "").lower() == "primary"), rows[0]
    )
    plan = db.get(InsurancePlan, slot.ins_plan_id) if slot.ins_plan_id else None
    return slot, plan


def _coverage_rules(db: Session, ins_plan_id: int | None) -> list[InsuranceCoverageRule]:
    if not ins_plan_id:
        return []
    return list(db.execute(
        select(InsuranceCoverageRule).where(InsuranceCoverageRule.ins_plan_id == ins_plan_id)
    ).scalars().all())


def _match_rule(rules: list[InsuranceCoverageRule], code: str) -> InsuranceCoverageRule | None:
    for rule in rules:
        start, end = (rule.start_code or ""), (rule.end_code or rule.start_code or "")
        if start and start <= code <= end:
            return rule
    return None


def _fee_schedule_id(db: Session, plan: InsurancePlan | None, office_id: int | None) -> int | None:
    """The fee schedule that applies: plan assignment → plan-linked → office default."""
    if plan is not None:
        assign = db.execute(
            select(FeeScheduleAssignment.fee_schedule_id).where(
                FeeScheduleAssignment.ins_plan_id == plan.id
            )
        ).scalar_one_or_none()
        if assign:
            return assign
        linked = db.execute(
            select(FeeSchedule.id).where(
                FeeSchedule.ins_plan_id == plan.id, FeeSchedule.is_active.is_(True)
            )
        ).scalar_one_or_none()
        if linked:
            return linked
    if office_id:
        office = db.get(Office, office_id)
        if office and office.default_fee_schedule_id:
            return office.default_fee_schedule_id
    return None


def _fee_for(
    db: Session, code: str, fee_schedule_id: int | None, proc: ProcedureCode | None
) -> tuple[Decimal, str]:
    """(fee, source): a fee-schedule entry beats the code default."""
    if fee_schedule_id:
        entry = db.execute(
            select(FeeScheduleEntry).where(
                FeeScheduleEntry.fee_schedule_id == fee_schedule_id,
                FeeScheduleEntry.procedure_code == code,
            )
        ).scalars().first()
        if entry is not None and (entry.patient_fee is not None or entry.insurance_fee is not None):
            fee = entry.patient_fee if entry.patient_fee is not None else entry.insurance_fee
            return _money(fee), "fee_schedule"
    if proc is not None:
        return _money(proc.default_fee), "code_default"
    return _ZERO, "code_default"


def estimate(
    db: Session,
    patient_id: int,
    tenant_id: int,
    *,
    lines: list[dict],
    office_id: int | None = None,
) -> dict:
    """Compute the per-line insurance/patient/deductible split (CHG-1/7)."""
    patient = _get_patient(db, patient_id, tenant_id)
    office_id = office_id or patient.home_office_id

    slot, plan = _primary_coverage(db, patient_id)
    rules = _coverage_rules(db, plan.id if plan else None)
    fee_schedule_id = _fee_schedule_id(db, plan, office_id)

    # Remaining deductible / annual max — prefer the per-patient slot figures, then plan.
    ded_remaining = _money(
        (slot.deductible_remaining if slot and slot.deductible_remaining is not None else None)
        if slot else None
    )
    if slot and slot.deductible_remaining is None and plan is not None:
        ded_remaining = _money(plan.individual_deductible)
    max_remaining = None
    if slot and slot.max_remaining is not None:
        max_remaining = _money(slot.max_remaining)
    elif plan is not None and plan.individual_max is not None:
        max_remaining = _money(plan.individual_max)

    results: list[dict] = []
    total_fee = total_ins = total_pat = total_ded = _ZERO
    ins_budget = max_remaining  # mutable running cap (None = unlimited)

    for line in lines:
        code = line["procedure_code"]
        proc = db.get(ProcedureCode, code)
        override = line.get("fee")
        if override is not None:
            fee, source = _money(override), "override"
        else:
            fee, source = _fee_for(db, code, fee_schedule_id, proc)

        rule = _match_rule(rules, code) if plan else None
        coverage_pct = _money(rule.coverage_pct) if rule and rule.coverage_pct is not None else _ZERO

        # Deductible consumed on this line (unless waived), reduces the insured base.
        line_ded = _ZERO
        if rule is not None and not rule.ded_waived and ded_remaining > _ZERO and coverage_pct > _ZERO:
            line_ded = min(ded_remaining, fee)
            ded_remaining -= line_ded

        insured_base = fee - line_ded
        ins_est = (coverage_pct / _HUNDRED) * insured_base if coverage_pct > _ZERO else _ZERO
        ins_est = _money(ins_est)
        if ins_budget is not None:
            ins_est = min(ins_est, max(ins_budget, _ZERO))
            ins_budget -= ins_est
        pat_est = _money(fee - ins_est)

        results.append({
            "procedure_code": code,
            "fee": fee,
            "coverage_pct": coverage_pct,
            "insurance_estimate": ins_est,
            "patient_estimate": pat_est,
            "estimated_deductible": _money(line_ded),
            "fee_source": source,
        })
        total_fee += fee
        total_ins += ins_est
        total_pat += pat_est
        total_ded += line_ded

    return {
        "patient_id": patient_id,
        "has_active_coverage": plan is not None,
        "lines": results,
        "total_fee": _money(total_fee),
        "insurance_estimate": _money(total_ins),
        "patient_estimate": _money(total_pat),
        "estimated_deductible": _money(total_ded),
    }
