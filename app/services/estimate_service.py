"""Charge-time insurance/patient estimate engine (CHG-1 / CHG-7).

Given a patient and one or more procedure codes, derive the insurance-estimate /
patient-estimate split (and the deductible portion, CHG-7) from the patient's
active coverage and the applicable fee schedule — instead of the frontend posting
``insurance_estimate: 0`` / ``patient_estimate: fee``.

The computation is intentionally conservative and self-contained:

* **Fee** — override → :func:`pricing_service.resolve_procedure_fee` (FEE-3),
  which walks ``fee_schedule_assignments`` by specificity, then the plan-linked
  schedule, then the office default, then the code's ``default_fee``. Sharing
  the resolver with ``GET /patients/{id}/fee`` is the point: a quote and an
  estimate can no longer disagree about what a code costs.
* **Coverage %** — the ``insurance_coverage_rules`` band on the patient's
  primary plan that matches the code (0 % if the patient has no active plan or
  no matching band). A band is matched **either** as an ADA code range
  (``D0100``–``D0999``, which is how a minority of plans are set up) **or** by
  the code's coverage category (FEE-1) — ``01A``, ``03``, ``11B`` — which is how
  every migrated plan is set up. Before FEE-1 only the first form existed, so
  the engine matched nothing and quoted 0 % insurance on real coverage.
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
    InsurancePlan,
    InsuranceCoverageRule,
    Patient,
    PatientInsurance,
)
from app.services import coverage_category_service as covcat
from app.services import pricing_service

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


def _match_rule(
    rules: list[InsuranceCoverageRule], code: str, coverage_category: str | None
) -> InsuranceCoverageRule | None:
    """The best band for ``code`` on this plan, or ``None``.

    Two band shapes coexist in the migrated data and both are honoured:

    * an **ADA range** (``start_code='D0100'``, ``end_code='D0999'``) — matched
      numerically inside the letter family, so ``D0330`` falls in ``D0100``–
      ``D0999`` but ``D2740`` does not;
    * a **coverage category** (``start_code='03A'``) — matched against the
      code's own category (FEE-1). An exact category match beats a match on its
      parent, so a plan that itemises "Restorative: Crowns" at 50 % prices a
      crown at 50 % even though it also bands "Restorative" at 80 %.

    Ranked rather than first-wins because the rows come back in insertion order,
    which would otherwise make the answer depend on how the plan was typed in.
    """
    best: InsuranceCoverageRule | None = None
    best_score = -1
    for rule in rules:
        start, end = (rule.start_code or ""), (rule.end_code or rule.start_code or "")
        score: int | None = None
        if covcat.is_ada_code(start):
            # An ADA-range band. A single-code band (start == end) is the most
            # specific thing a plan can say about a code.
            if covcat.in_range(code, start, end):
                score = 3 if start == end else 1
        else:
            score = covcat.category_matches(start, coverage_category)
        if score is not None and score > best_score:
            best, best_score = rule, score
    return best


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
    # FEE-1: one batched lookup of every line's coverage category, so a 20-line
    # treatment plan does not fan out 20 queries to classify its codes.
    categories = covcat.categories_for(db, [line["procedure_code"] for line in lines])
    # FEE-3: one pricing context for the whole estimate. It carries the resolved
    # plan/carrier/office-group and memoises the matching fee-schedule
    # assignments, so a 20-line plan does not re-read them 20 times.
    ctx = pricing_service.build_context(
        db, patient_id=patient_id, office_id=office_id,
        ins_plan_id=plan.id if plan is not None else None,
    )

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
        override = line.get("fee")
        fee_schedule_id = None
        if override is not None:
            fee, source = _money(override), "override"
        else:
            # FEE-3: the same resolver ``GET /patients/{id}/fee`` answers with.
            # A per-line provider overrides the shared context (a provider-scoped
            # assignment is a real thing); otherwise the shared one is reused.
            line_ctx = ctx
            if line.get("provider_id"):
                line_ctx = pricing_service.build_context(
                    db, patient_id=patient_id, office_id=office_id,
                    provider_id=line["provider_id"],
                    ins_plan_id=plan.id if plan is not None else None,
                )
            quote = pricing_service.resolve_procedure_fee(
                db, tenant_id, code, ctx=line_ctx,
            )
            fee, source = quote["fee"], quote["fee_source"]
            fee_schedule_id = quote["fee_schedule_id"]

        category = categories.get(code)
        rule = _match_rule(rules, code, category) if plan else None
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
            "fee_schedule_id": fee_schedule_id,
            "coverage_category": category,
            "coverage_category_description": covcat.describe(category),
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
