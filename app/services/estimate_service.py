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

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.datetimes import office_today
from app.core.exceptions import NotFoundError
from app.db.models import (
    InsurancePlan,
    InsuranceCoverageRule,
    Office,
    Patient,
    PatientInsurance,
    ProcedureCode,
)
from app.services import coverage_category_service as covcat
from app.services import fee_vocab
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


#: Public name for the ranked band matcher — ``treatment_service.re_estimate``
#: prices a plan through the same function so the estimate and the plan can
#: never disagree on which band a code falls in (FEE-1).
match_coverage_rule = _match_rule


def estimate(
    db: Session,
    patient_id: int,
    tenant_id: int,
    *,
    lines: list[dict],
    office_id: int | None = None,
    date_of_service=None,  # noqa: ANN001 — dt.date | None, only read by the v2 path
    include_secondary: bool = False,
) -> dict:
    """Compute the per-line insurance/patient/deductible split (CHG-1/7).

    Dispatches on ``settings.PRICING_ENGINE_V2``. Flag off = the previous engine
    (unchanged). Flag on = :func:`estimate_lines`, which shares one coverage-slot
    picker and one arithmetic with every other pricing surface, adds the copay and
    self-pay benefit models, applies the annual-max cap *before* burning
    deductible, and can layer a secondary plan.
    """
    if settings.PRICING_ENGINE_V2:
        return _estimate_v2(
            db, patient_id, tenant_id, lines=lines, office_id=office_id,
            date_of_service=date_of_service, include_secondary=include_secondary,
        )
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


# ── v2 split engine (PRICING_ENGINE_V2) ──────────────────────────────────────


class CoverageTier:
    """One active dental coverage slot, with its plan, rules and running balances.

    ``ded_remaining`` / ``max_remaining`` / ``ortho_remaining`` prefer the
    per-patient slot figure and fall back to the plan limit **only when the slot
    value is NULL** — a stored ``0`` means the benefit is exhausted, which is not
    the same as "unknown".
    """

    __slots__ = ("rank", "slot", "plan", "rules", "ded_remaining", "max_remaining",
                 "ortho_remaining")

    def __init__(self, rank, slot, plan, rules):  # noqa: ANN001
        self.rank = rank
        self.slot = slot
        self.plan = plan
        self.rules = rules
        self.ded_remaining = _money(
            slot.deductible_remaining if slot.deductible_remaining is not None
            else (plan.individual_deductible if plan else None)
        )
        self.max_remaining = (
            _money(slot.max_remaining) if slot.max_remaining is not None
            else (_money(plan.individual_max) if plan and plan.individual_max is not None else None)
        )
        self.ortho_remaining = (
            _money(slot.ortho_remaining) if slot.ortho_remaining is not None
            else (_money(plan.ortho_max) if plan and plan.ortho_max is not None else None)
        )


def coverage_context(db: Session, patient_id: int) -> list[CoverageTier]:
    """The patient's active **dental** coverage, primary first.

    The single definition of "the patient's coverage" for pricing — the resolver,
    the estimate engine and the printed day sheet all read this, replacing three
    slightly different pickers. A medical (``legacy_plan_type='M'``) slot never
    prices dental; a slot with no plan is skipped.
    """
    rows = db.execute(
        select(PatientInsurance).where(
            PatientInsurance.patient_id == patient_id,
            PatientInsurance.is_active.is_(True),
        )
    ).scalars().all()

    tiers: list[CoverageTier] = []
    for slot in rows:
        if slot.ins_plan_id is None:
            continue
        if (slot.legacy_plan_type or "").upper() == fee_vocab.MEDICAL_PLAN_TYPE:
            continue
        plan = db.get(InsurancePlan, slot.ins_plan_id)
        if plan is None:
            continue
        tiers.append(CoverageTier(
            rank=(slot.insurance_type or "primary").lower(),
            slot=slot, plan=plan, rules=_coverage_rules(db, plan.id),
        ))

    def _order(tier: CoverageTier) -> int:
        try:
            return fee_vocab.COVERAGE_TIERS.index(tier.rank)
        except ValueError:
            return len(fee_vocab.COVERAGE_TIERS)

    tiers.sort(key=_order)
    return tiers


def _tier_percentage(tier: CoverageTier, code: str, category: str | None):  # noqa: ANN202
    """``(rule, coverage_pct)`` for a code on one tier's plan."""
    rule = _match_rule(tier.rules, code, category)
    pct = _money(rule.coverage_pct) if rule and rule.coverage_pct is not None else _ZERO
    return rule, pct


def _split_amounts(
    fee: Decimal,
    *,
    model: str,
    payer_amount,  # noqa: ANN001
    primary: CoverageTier | None,
    secondary: CoverageTier | None,
    category: str | None,
    code: str,
    is_ortho: bool,
    exempt: bool,
    include_secondary: bool,
    warnings: list[str],
):  # noqa: ANN201
    """The per-line split arithmetic, shared by the estimate engine and the
    write path (:func:`apply_split`) so a quoted split and a posted split can
    never disagree. Mutates the tier running balances (deductible / annual max)
    and returns ``(coverage_pct, prim_ins, sec_ins, line_ded, coverage_rule_id)``.

    * ``copay`` → Model B: the copay list states the plan-pays dollar amount.
    * a primary tier → Model A: percentage of the allowed amount, annual max
      checked before the deductible is burned.
    * no primary tier → Model C: insurance zero, patient owes the fee.
    """
    coverage_pct = _ZERO
    prim_ins = sec_ins = line_ded = _ZERO
    rule_id: int | None = None

    if model == "copay":
        # Model B — the copay list states the split; no percentage applies.
        prim_ins = _money(payer_amount) if payer_amount is not None else _ZERO
        if secondary is not None:
            warnings.append("secondary_not_estimated")
    elif primary is not None:
        # Model A — percentage of the allowed amount.
        rule, coverage_pct = _tier_percentage(primary, code, category)
        if rule is not None:
            rule_id = rule.id
        if rule is not None and coverage_pct > _ZERO:
            cap = primary.ortho_remaining if is_ortho else primary.max_remaining
            if cap is not None and cap <= _ZERO and not exempt:
                prim_ins = _ZERO  # benefit exhausted — no payment, no deductible burned
            else:
                if not rule.ded_waived and primary.ded_remaining > _ZERO:
                    line_ded = min(primary.ded_remaining, fee)
                    primary.ded_remaining -= line_ded
                prim_ins = _money((fee - line_ded) * coverage_pct / _HUNDRED)
                if cap is not None and not exempt:
                    prim_ins = min(prim_ins, max(cap, _ZERO))
                    if is_ortho:
                        primary.ortho_remaining -= prim_ins
                    else:
                        primary.max_remaining -= prim_ins
        if include_secondary and secondary is not None:
            sec_ins = _secondary_estimate(secondary, code, category, fee, prim_ins, exempt, is_ortho)
    # Model C (no primary tier): insurance stays zero, patient owes the fee.
    return coverage_pct, prim_ins, sec_ins, line_ded, rule_id


def estimate_lines(
    db: Session,
    tenant_id: int,
    *,
    tiers: list[CoverageTier],
    pricing_ctx,  # noqa: ANN001 — pricing_service.PricingContext
    lines: list[dict],
    date_of_service=None,  # noqa: ANN001
    include_secondary: bool = False,
) -> list[dict]:
    """The single split arithmetic. One line per input line, in input order.

    Benefit model is decided by the **schedule that priced the line**:

    * ``copay`` schedule -> Model B: the list states both dollar parts, so
      ``insurance_estimate`` is the plan-pays amount and the patient owes the
      copay. No percentage, no deductible, no annual max.
    * otherwise, with active coverage -> Model A: the plan's coverage percentage
      splits the allowed amount. The annual max is checked **first** — an
      exhausted benefit pays nothing and burns no deductible — then the
      deductible, then ``round((fee - ded) * pct)`` capped by what is left.
    * no active coverage -> Model C: the patient owes the whole fee.

    Deductible and annual max are consumed across the lines of this call (running
    balances seeded from the tiers), so a multi-line estimate matches the sum of
    the same lines priced one at a time.
    """
    primary = tiers[0] if tiers else None
    secondary = tiers[1] if len(tiers) > 1 else None
    categories = covcat.categories_for(db, [line["procedure_code"] for line in lines])

    results: list[dict] = []
    for line in lines:
        code = line["procedure_code"]
        override = line.get("fee")
        warnings: list[str] = []
        if override is not None:
            fee = _money(override)
            source, model = "override", ("percentage" if primary else "self_pay")
            fee_schedule_id = fee_schedule_name = fee_effective_date = None
            ucr_fee = expected_write_off = None
            payer_amount = None
        else:
            line_ctx = pricing_ctx
            if line.get("provider_id") and line["provider_id"] != pricing_ctx.provider_id:
                line_ctx = pricing_service.build_context(
                    db, office_id=pricing_ctx.office_id, provider_id=line["provider_id"],
                    ins_plan_id=pricing_ctx.ins_plan_id, date_of_service=date_of_service,
                )
            quote = pricing_service.resolve_procedure_fee(
                db, tenant_id, code, ctx=line_ctx, date_of_service=date_of_service,
            )
            fee = _money(quote["fee"])
            source = quote["fee_source"]
            fee_schedule_id = quote["fee_schedule_id"]
            fee_schedule_name = quote.get("fee_schedule_name")
            fee_effective_date = quote.get("fee_effective_date")
            ucr_fee = quote.get("ucr_fee")
            expected_write_off = quote.get("expected_write_off")
            payer_amount = quote.get("payer_amount")
            warnings = list(quote.get("warnings") or [])
            model = quote.get("pricing_model") or "percentage"

        category = categories.get(code)
        proc = db.get(ProcedureCode, code)
        is_ortho = bool(getattr(proc, "is_ortho", False))
        exempt = bool(getattr(proc, "exempt_from_dental_max", False))

        coverage_pct, prim_ins, sec_ins, line_ded, _rule_id = _split_amounts(
            fee, model=model, payer_amount=payer_amount, primary=primary,
            secondary=secondary, category=category, code=code, is_ortho=is_ortho,
            exempt=exempt, include_secondary=include_secondary, warnings=warnings,
        )

        insurance_estimate = _money(prim_ins + sec_ins)
        patient_estimate = _money(max(fee - insurance_estimate, _ZERO))
        results.append({
            "procedure_code": code,
            "fee": fee,
            "coverage_pct": coverage_pct,
            "coverage_rule_id": _rule_id,
            "insurance_estimate": insurance_estimate,
            "primary_insurance_estimate": _money(prim_ins),
            "sec_insurance_estimate": _money(sec_ins),
            "patient_estimate": patient_estimate,
            "estimated_deductible": _money(line_ded),
            "fee_source": source,
            "fee_schedule_id": fee_schedule_id,
            "fee_schedule_name": fee_schedule_name,
            "fee_effective_date": fee_effective_date,
            "ucr_fee": ucr_fee,
            "expected_write_off": expected_write_off,
            "benefit_model": model if primary or model == "copay" else "self_pay",
            "coverage_category": category,
            "coverage_category_description": covcat.describe(category),
            "is_unpriced": bool(override is None and source == "unpriced"),
            "warnings": warnings,
        })
    return results


def _secondary_estimate(secondary, code, category, fee, prim_ins, exempt, is_ortho):  # noqa: ANN001
    """Standard coordination of benefits, or non-duplication when the secondary
    plan is flagged. Never pays more than the balance the primary left."""
    rule, pct = _tier_percentage(secondary, code, category)
    if rule is None or pct <= _ZERO:
        return _ZERO
    sec_ded = _ZERO
    if not rule.ded_waived and secondary.ded_remaining > _ZERO:
        sec_ded = min(secondary.ded_remaining, fee)
        secondary.ded_remaining -= sec_ded
    normal = _money((fee - sec_ded) * pct / _HUNDRED)
    if getattr(secondary.plan, "is_non_dup_benefits", False):
        # Non-duplication: pay only the excess of this plan's benefit over the
        # primary's payment.
        sec = max(_ZERO, normal - prim_ins)
    else:
        # Standard COB: cover the remaining balance up to this plan's benefit.
        sec = min(normal, _money(fee - prim_ins))
    cap = secondary.ortho_remaining if is_ortho else secondary.max_remaining
    if cap is not None and not exempt:
        sec = min(sec, max(cap, _ZERO))
        if is_ortho:
            secondary.ortho_remaining -= sec
        else:
            secondary.max_remaining -= sec
    return _money(max(sec, _ZERO))


def _estimate_v2(
    db: Session,
    patient_id: int,
    tenant_id: int,
    *,
    lines: list[dict],
    office_id: int | None = None,
    date_of_service=None,  # noqa: ANN001
    include_secondary: bool = False,
) -> dict:
    patient = _get_patient(db, patient_id, tenant_id)
    office_id = office_id or patient.home_office_id
    tiers = coverage_context(db, patient_id)
    primary = tiers[0] if tiers else None
    pricing_ctx = pricing_service.build_context(
        db, patient_id=patient_id, office_id=office_id,
        ins_plan_id=primary.plan.id if primary else None,
        date_of_service=date_of_service,
    )
    results = estimate_lines(
        db, tenant_id, tiers=tiers, pricing_ctx=pricing_ctx, lines=lines,
        date_of_service=date_of_service, include_secondary=include_secondary,
    )
    total_fee = sum((r["fee"] for r in results), _ZERO)
    total_ins = sum((r["insurance_estimate"] for r in results), _ZERO)
    total_pat = sum((r["patient_estimate"] for r in results), _ZERO)
    total_ded = sum((r["estimated_deductible"] for r in results), _ZERO)
    return {
        "patient_id": patient_id,
        "has_active_coverage": primary is not None,
        "coverage_tiers": [t.rank for t in tiers],
        "lines": results,
        "total_fee": _money(total_fee),
        "insurance_estimate": _money(total_ins),
        "patient_estimate": _money(total_pat),
        "estimated_deductible": _money(total_ded),
    }


# ── write path: the single pricing/split helper (PRICING_ENGINE_V2) ───────────


def _price_legacy(db: Session, data: dict, tenant_id: int | None) -> dict:
    """The pre-R1 charge pricer, unchanged: fill ``fee`` (and blank
    ``fee_schedule_id`` / ``ucr_fee``) from the resolver only when the caller
    omitted ``fee``. Writes no split. This is what runs while
    ``PRICING_ENGINE_V2`` is off, so the shipped frontend sees no change."""
    if data.get("fee") is not None or tenant_id is None:
        return data
    code = data.get("procedure_code")
    if not code:
        return data
    quote = pricing_service.resolve_procedure_fee(
        db, tenant_id, code,
        patient_id=data.get("patient_id"),
        office_id=data.get("office_id"),
        provider_id=data.get("provider_id"),
    )
    data["fee"] = quote["fee"]
    if data.get("fee_schedule_id") is None and quote.get("fee_schedule_id"):
        data["fee_schedule_id"] = quote["fee_schedule_id"]
    if data.get("ucr_fee") is None and quote.get("ucr_fee") is not None:
        data["ucr_fee"] = quote["ucr_fee"]
    return data


def _fill_split(
    db: Session,
    data: dict,
    *,
    fee: Decimal,
    code: str,
    quote: dict,
    patient_id: int | None,
) -> None:
    """Compute this one charge's split against the patient's coverage and write
    the server-owned money columns onto ``data``. ``patient_estimate`` and the
    insurance/deductible figures are **always** overwritten — they are never read
    from a client payload (§3.4)."""
    tiers = coverage_context(db, patient_id) if patient_id else []
    primary = tiers[0] if tiers else None
    secondary = tiers[1] if len(tiers) > 1 else None
    category = covcat.categories_for(db, [code]).get(code)
    proc = db.get(ProcedureCode, code)
    is_ortho = bool(getattr(proc, "is_ortho", False))
    exempt = bool(getattr(proc, "exempt_from_dental_max", False))
    model = quote.get("pricing_model") or "percentage"
    payer_amount = quote.get("payer_amount")
    warnings: list[str] = []

    coverage_pct, prim_ins, sec_ins, line_ded, rule_id = _split_amounts(
        fee, model=model, payer_amount=payer_amount, primary=primary,
        secondary=secondary, category=category, code=code, is_ortho=is_ortho,
        exempt=exempt, include_secondary=False, warnings=warnings,
    )
    insurance_estimate = _money(prim_ins + sec_ins)
    data["insurance_estimate"] = insurance_estimate
    data["sec_insurance_estimate"] = _money(sec_ins)
    data["patient_estimate"] = _money(max(fee - insurance_estimate, _ZERO))
    data["estimated_deductible"] = _money(line_ded)
    data["coverage_pct"] = coverage_pct
    if rule_id is not None:
        data["coverage_rule_id"] = rule_id


def _apply_split_create(
    db: Session, data: dict, tenant_id: int, *, fee_override: bool
) -> dict:
    code = data.get("procedure_code")
    if not code or tenant_id is None:
        return data
    dos = data.get("date_of_service")
    explicit_fee = data.get("fee") is not None
    quote = pricing_service.resolve_procedure_fee(
        db, tenant_id, code,
        patient_id=data.get("patient_id"),
        office_id=data.get("office_id"),
        provider_id=data.get("provider_id"),
        date_of_service=dos,
    )
    if explicit_fee:
        # Compatibility window (R1–R2): a client-supplied fee is honoured, tagged
        # so the health report can count it, and the split is still recomputed
        # server-side. A true override (``fee_override``) carries no schedule.
        fee = _money(data["fee"])
        source = "override" if fee_override else "client_legacy"
    else:
        fee = _money(quote["fee"])
        source = quote["fee_source"]

    data["fee"] = fee
    data["fee_source"] = source
    if not (explicit_fee and fee_override):
        if data.get("fee_schedule_id") is None and quote.get("fee_schedule_id"):
            data["fee_schedule_id"] = quote["fee_schedule_id"]
        if data.get("fee_effective_date") is None and quote.get("fee_effective_date"):
            # The resolver returns this ISO-formatted (it feeds JSON responses);
            # the charge column is a real DATE, so coerce before persisting.
            data["fee_effective_date"] = _as_date(quote["fee_effective_date"])
    # UCR is an office-level list, independent of what the office chose to charge,
    # so it is recorded even for an override (write-off = ucr − fee).
    if data.get("ucr_fee") is None and quote.get("ucr_fee") is not None:
        data["ucr_fee"] = quote["ucr_fee"]

    _fill_split(db, data, fee=fee, code=code, quote=quote,
                patient_id=data.get("patient_id"))
    return data


def _apply_split_update(
    db: Session, data: dict, tenant_id: int, *, current, fee_override: bool
) -> dict:  # noqa: ANN001
    """A PATCH never re-prices implicitly (that is the explicit reprice action).
    A **fee** change on an **unclaimed** charge re-runs the split only, so the
    insurance/patient columns stay consistent with the edited fee."""
    if "fee" not in data or data["fee"] is None:
        return data
    if current.claim_id:
        return data
    code = data.get("procedure_code", current.procedure_code)
    if not code:
        return data
    patient_id = data.get("patient_id", current.patient_id)
    dos = data.get("date_of_service", current.date_of_service)
    quote = pricing_service.resolve_procedure_fee(
        db, tenant_id, code,
        patient_id=patient_id,
        office_id=data.get("office_id", current.office_id),
        provider_id=data.get("provider_id", current.provider_id),
        date_of_service=dos,
    )
    fee = _money(data["fee"])
    data["fee_source"] = "override" if fee_override else (
        data.get("fee_source") or "client_legacy"
    )
    _fill_split(db, data, fee=fee, code=code, quote=quote, patient_id=patient_id)
    return data


def _fill_split_only(
    db: Session,
    data: dict,
    tenant_id: int,
    *,
    current,  # noqa: ANN001
    patient_id: int | None,
    office_id: int | None,
    date_of_service,  # noqa: ANN001
) -> dict:
    """Split-only mode for the treatment-plan-item write path.

    The item's ``fee`` / ``fee_schedule_id`` / ``fee_source`` /
    ``fee_effective_date`` are owned by ``treatment_service._price_item``
    (PLAN-29: an explicit fee records the schedule only when it is the schedule
    that would have produced that exact amount). This fills only the coverage
    split — through the same :func:`_split_amounts` arithmetic the charge path
    uses — from the item's already-resolved fee, so item and charge splits can
    never disagree. ``patient_id`` / ``office_id`` come from the item's plan
    (the item row carries neither).

    On a PATCH it recomputes only when the payload actually changes ``fee``, so
    an unrelated edit never clobbers a plan-level ``re_estimate`` result.
    """
    if current is not None and "fee" not in data:
        return data
    fee_val = data.get("fee")
    if fee_val is None and current is not None:
        fee_val = current.fee
    if fee_val is None:
        return data
    code = data.get("procedure_code") or (current.procedure_code if current is not None else None)
    if not code:
        return data
    pid = patient_id if patient_id is not None else data.get("patient_id")
    quote = pricing_service.resolve_procedure_fee(
        db, tenant_id, code, patient_id=pid, office_id=office_id,
        provider_id=data.get("provider_id"), date_of_service=date_of_service,
    )
    # UCR is office-level provenance a plan item never got today; fill it when blank.
    if data.get("ucr_fee") is None and quote.get("ucr_fee") is not None:
        data["ucr_fee"] = quote["ucr_fee"]
    _fill_split(db, data, fee=_money(fee_val), code=code, quote=quote, patient_id=pid)
    # A treatment_plan_item stores ``insurance_estimate`` but derives the patient
    # portion (the detail row carries ``estimated_pat``); there is no
    # ``patient_estimate`` column, so it must not reach the ORM.
    data.pop("patient_estimate", None)
    return data


def apply_split(
    db: Session,
    data: dict,
    tenant_id: int | None,
    *,
    current=None,  # noqa: ANN001 — an ORM row on update, None on create
    price_fee: bool = True,
    patient_id: int | None = None,
    office_id: int | None = None,
    date_of_service=None,  # noqa: ANN001
) -> dict:
    """The one charge/plan-item write-path pricing helper (§3.3/§3.4).

    ``PRICING_ENGINE_V2`` **off** → today's behaviour exactly: price a
    fee-less **create** through the resolver, and never touch pricing on a
    PATCH (or on any split-only call). **On** → resolve the fee + provenance and
    fill the insurance / patient / deductible split through the shared
    :func:`_split_amounts` arithmetic, honouring the override discipline in
    ``client_legacy`` compatibility mode. ``patient_estimate`` is never read
    from ``data``.

    ``price_fee=False`` is **split-only** mode for the treatment-plan-item path:
    the fee and its provenance are left to the caller (PLAN-29) and only the
    coverage split is filled, from the item's already-resolved ``fee`` and the
    ``patient_id`` / ``office_id`` of the item's plan. ``fee_override`` is a
    transient payload flag (not a column); it is consumed here so it never
    reaches the ORM.
    """
    fee_override = _bool(data.pop("fee_override", None))
    if not settings.PRICING_ENGINE_V2:
        # Flag dark: price a fee-less charge create (today's behaviour); never
        # touch a PATCH, and never write a split (charge or item).
        if current is None and price_fee:
            return _price_legacy(db, data, tenant_id)
        return data
    if tenant_id is None:
        return data
    if not price_fee:
        return _fill_split_only(
            db, data, tenant_id, current=current, patient_id=patient_id,
            office_id=office_id, date_of_service=date_of_service,
        )
    if current is None:
        return _apply_split_create(db, data, tenant_id, fee_override=fee_override)
    return _apply_split_update(db, data, tenant_id, current=current, fee_override=fee_override)


def _bool(value: Any) -> bool:  # noqa: ANN401
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(value)


def _as_date(value: Any):  # noqa: ANN401, ANN202
    """Coerce the resolver's ISO-formatted ``fee_effective_date`` back to a
    ``date`` for the DATE column (``datetime`` is a ``date`` subclass, so a real
    date passes through)."""
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
