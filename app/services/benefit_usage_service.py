"""TX-MAX-3: what a coverage slot has actually left this benefit year.

``patient_insurance.max_remaining`` / ``deductible_remaining`` are imported or
hand-typed snapshots — nothing decrements them when a claim pays — so "annual
max reached" only ever worked if staff edited the slot, and a ``0`` typed in
March kept the patient "maxed out" forever, across every later benefit year.

The rule, in one place (every estimate surface reads it through
``estimate_service.coverage_context``):

* **Benefit year** — starts on the plan's anniversary
  (``anniversary_month``/``anniversary_day``, else ``anniversary_date``'s
  month/day, else 1 January) and runs twelve months.
* **Benefits used** — Σ over the slot's claims in the benefit year (by date of
  service): ``total_paid`` once the claim is settled (``paid``/``closed``),
  ``max(total_paid, est_insurance)`` while it is open. Pre-determinations and
  void/denied/rejected/cancelled claims never count. A claim belongs to the
  slot by ``ins_plan_id``; a claim with no plan id (most migrated claims) by the
  plan's carrier, a ``secondary`` claim only to a secondary slot.
* **Remaining** — ``individual_max − benefits_used``. The slot column is still
  honoured as a staff/import assertion and **caps** the derived figure (it is
  an upper bound: history the system cannot see can only have used *more*) —
  but only when the column was written *inside the current benefit year*. A
  column last written before the year started describes a year that is over,
  so it is ignored and the plan's full limit applies. No claim history → the
  current-year column, else the plan limit (unchanged behaviour).
* **Deductible** — the same staleness rule (a stale ``deductible_remaining``
  resets to ``individual_deductible``); its consumption by claims is not
  derived (claims carry no deductible total).
* **Ortho** — lifetime by default, so ``ortho_remaining`` is never reset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.datetimes import office_today
from app.db.models import InsuranceClaim, InsurancePlan, PatientInsurance

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")

#: A claim in one of these states never paid and never will — it uses no benefit.
VOID_CLAIM_STATUSES: frozenset[str] = frozenset({
    "void", "voided", "cancelled", "canceled", "denied", "rejected",
})
#: Settled: the carrier's payment is final, the estimate no longer matters.
SETTLED_CLAIM_STATUSES: frozenset[str] = frozenset({"paid", "closed"})


def _money(value) -> Decimal:  # noqa: ANN001
    if value is None:
        return _ZERO
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _safe_date(year: int, month: int, day: int) -> date:
    """``date(year, month, day)`` with the day clamped to the month (29 Feb …)."""
    for d in (day, 30, 29, 28):
        try:
            return date(year, month, min(d, day))
        except ValueError:
            continue
    return date(year, month, 1)


def anniversary(plan: InsurancePlan | None) -> tuple[int, int]:
    """``(month, day)`` the plan's benefit year starts on (1 Jan when unset)."""
    if plan is None:
        return 1, 1
    month = getattr(plan, "anniversary_month", None)
    day = getattr(plan, "anniversary_day", None)
    anniv = getattr(plan, "anniversary_date", None)
    if not month and anniv is not None:
        month, day = anniv.month, anniv.day
    month = int(month) if month and 1 <= int(month) <= 12 else 1
    day = int(day) if day and 1 <= int(day) <= 31 else 1
    return month, day


def benefit_year_window(plan: InsurancePlan | None, on: date) -> tuple[date, date]:
    """``[start, next_start)`` of the benefit year containing ``on``."""
    month, day = anniversary(plan)
    start = _safe_date(on.year, month, day)
    if start > on:
        start = _safe_date(on.year - 1, month, day)
    return start, _safe_date(start.year + 1, month, day)


@dataclass
class SlotBenefits:
    slot_id: int
    year_start: date
    year_end: date
    annual_max: Decimal | None
    benefits_used_ytd: Decimal = _ZERO
    claim_count: int = 0
    claim_ids: list[str] = field(default_factory=list)
    max_remaining_effective: Decimal | None = None
    #: ``claims`` | ``claims_capped_by_slot`` | ``slot`` | ``plan`` | ``none``
    max_remaining_source: str = "none"
    deductible_remaining_effective: Decimal = _ZERO
    #: ``slot`` | ``plan`` | ``none``
    deductible_remaining_source: str = "none"
    ortho_remaining_effective: Decimal | None = None
    #: The slot's own columns were written before this benefit year began.
    slot_values_stale: bool = False


def _claim_dos(claim: InsuranceClaim) -> date | None:
    d = claim.date_of_service_from or claim.submitted_date
    if d is None and claim.created_at is not None:
        d = claim.created_at.date() if isinstance(claim.created_at, datetime) else claim.created_at
    return d


def _claim_used(claim: InsuranceClaim) -> Decimal:
    paid = _money(claim.total_paid)
    if (claim.status or "").lower() in SETTLED_CLAIM_STATUSES:
        return paid
    return max(paid, _money(claim.est_insurance))


def _claim_matches(claim: InsuranceClaim, slot: PatientInsurance, plan: InsurancePlan | None) -> bool:
    if claim.ins_plan_id is not None:
        return claim.ins_plan_id == slot.ins_plan_id
    if plan is None or claim.carrier_id is None or claim.carrier_id != plan.carrier_id:
        return False
    is_secondary_claim = (claim.claim_type or "").lower() == "secondary"
    is_secondary_slot = (slot.insurance_type or "primary").lower() != "primary"
    return is_secondary_claim == is_secondary_slot


def _slot_written_on(slot: PatientInsurance) -> date | None:
    stamp = slot.updated_at or slot.created_at
    if stamp is None:
        return None
    return stamp.date() if isinstance(stamp, datetime) else stamp


def slot_benefits(
    db: Session,
    slots: Iterable[PatientInsurance],
    *,
    on: date | None = None,
    plans: dict[int, InsurancePlan] | None = None,
) -> dict[int, SlotBenefits]:
    """Effective remaining max / deductible for each slot, keyed by slot id.

    One claims read for every patient involved, so an enriched page of slots
    or a coverage context costs one extra statement."""
    slots = [s for s in slots if s is not None and s.id is not None]
    if not slots:
        return {}
    on = on or office_today(None)
    plans = dict(plans or {})
    for s in slots:
        if s.ins_plan_id and s.ins_plan_id not in plans:
            p = db.get(InsurancePlan, s.ins_plan_id)
            if p is not None:
                plans[s.ins_plan_id] = p

    patient_ids = {s.patient_id for s in slots}
    claims = db.execute(
        select(InsuranceClaim).where(
            InsuranceClaim.patient_id.in_(patient_ids),
            InsuranceClaim.is_preauth.is_not(True),
        )
    ).scalars().all()
    claims = [c for c in claims if (c.status or "").lower() not in VOID_CLAIM_STATUSES]

    out: dict[int, SlotBenefits] = {}
    for slot in slots:
        plan = plans.get(slot.ins_plan_id) if slot.ins_plan_id else None
        start, end = benefit_year_window(plan, on)
        annual_max = _money(plan.individual_max) if plan is not None and plan.individual_max is not None else None
        res = SlotBenefits(slot_id=slot.id, year_start=start, year_end=end, annual_max=annual_max)

        written = _slot_written_on(slot)
        stale = written is not None and written < start
        res.slot_values_stale = stale

        for c in claims:
            if c.patient_id != slot.patient_id or not _claim_matches(c, slot, plan):
                continue
            dos = _claim_dos(c)
            if dos is None or not (start <= dos < end):
                continue
            res.benefits_used_ytd += _claim_used(c)
            res.claim_count += 1
            res.claim_ids.append(c.id)

        column_max = None if stale or slot.max_remaining is None else _money(slot.max_remaining)
        if res.claim_count and annual_max is not None:
            derived = max(annual_max - res.benefits_used_ytd, _ZERO)
            if column_max is not None and column_max < derived:
                res.max_remaining_effective, res.max_remaining_source = column_max, "claims_capped_by_slot"
            else:
                res.max_remaining_effective, res.max_remaining_source = derived, "claims"
        elif column_max is not None:
            res.max_remaining_effective, res.max_remaining_source = column_max, "slot"
        elif annual_max is not None:
            res.max_remaining_effective, res.max_remaining_source = annual_max, "plan"

        if not stale and slot.deductible_remaining is not None:
            res.deductible_remaining_effective = _money(slot.deductible_remaining)
            res.deductible_remaining_source = "slot"
        elif plan is not None and plan.individual_deductible is not None:
            res.deductible_remaining_effective = _money(plan.individual_deductible)
            res.deductible_remaining_source = "plan"

        if slot.ortho_remaining is not None:
            res.ortho_remaining_effective = _money(slot.ortho_remaining)
        elif plan is not None and plan.ortho_max is not None:
            res.ortho_remaining_effective = _money(plan.ortho_max)
        out[slot.id] = res
    return out
