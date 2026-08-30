"""Server-side fee resolution (FEE-3).

Until now the *only* implementation of "what does this code cost for this
patient" lived in the frontend (``src/services/feeScheduleResolver.ts``). That
worked, but it meant two clients could disagree, and nothing stopped a charge
being posted with an arbitrary fee. This module is the same algorithm on the
server, used by:

* ``GET /api/v1/patients/{patient_id}/fee`` — the quote endpoint, which returns
  the resolved fee **and how it was resolved** (which schedule, at what
  specificity, and any equally-specific rival that disagrees);
* ``estimate_service`` — so the estimate and the quote can never diverge;
* ``PatientProcedureCRUD`` — a charge posted with no ``fee`` is priced here
  instead of landing as ``0.00``.

The algorithm (settled from the migrated data, see the dev report)
-----------------------------------------------------------------
``fee_schedule_assignments`` binds a schedule to any mix of plan / carrier /
provider / office / office group / specialty. A row is a **candidate** when
every key it sets matches the charge; **specificity** is the number of keys it
sets, so the most specific matching row wins (ties → the newest row). Below the
assignments sit the plan's directly-linked schedule, then the office's
``default_fee_schedule_id``, then the code's ``default_fee``. Inactive schedules
are excluded.

The split is read as ``fee = entry.patient_fee``,
``insurance_fee = entry.insurance_fee`` — ``insurance_fee`` is ``0.00`` in every
migrated schedule (only staff-entered rows set it), which is why a coverage
percentage (FEE-1) and not the schedule is what actually produces an insurance
estimate.

Conflicts are **reported, not hidden**: when two equally-specific assignments
price the code differently, ``conflicts`` lists them so the UI can say so rather
than silently picking one.
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
    Office,
    Patient,
    PatientInsurance,
    ProcedureCode,
    Provider,
)

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")


def _money(value: Any) -> Decimal:  # noqa: ANN401
    if value is None:
        return _ZERO
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


# ── context resolution ──────────────────────────────────────────────────────


class PricingContext:
    """The keys an assignment row can be matched against."""

    __slots__ = ("office_id", "provider_id", "ins_plan_id", "carrier_id",
                 "office_group_id", "specialty_id", "_candidates")

    def __init__(
        self,
        *,
        office_id: int | None = None,
        provider_id: str | None = None,
        ins_plan_id: int | None = None,
        carrier_id: int | None = None,
        office_group_id: int | None = None,
        specialty_id: str | None = None,
    ) -> None:
        self.office_id = office_id
        self.provider_id = provider_id
        self.ins_plan_id = ins_plan_id
        self.carrier_id = carrier_id
        self.office_group_id = office_group_id
        self.specialty_id = specialty_id
        # Matching assignments, resolved once. A multi-line estimate prices
        # every line against the same context, so recomputing this per line
        # would re-read the assignment table N times for one answer.
        self._candidates: list[tuple[int, FeeScheduleAssignment]] | None = None

    def as_dict(self) -> dict:
        return {
            "office_id": self.office_id,
            "provider_id": self.provider_id,
            "ins_plan_id": self.ins_plan_id,
            "carrier_id": self.carrier_id,
            "office_group_id": self.office_group_id,
            "specialty_id": self.specialty_id,
        }


def primary_plan_id(db: Session, patient_id: int) -> int | None:
    """The patient's active primary dental plan (else the first active slot)."""
    rows = db.execute(
        select(PatientInsurance).where(
            PatientInsurance.patient_id == patient_id,
            PatientInsurance.is_active.is_(True),
        )
    ).scalars().all()
    if not rows:
        return None
    slot = next((r for r in rows if (r.insurance_type or "").lower() == "primary"), rows[0])
    return slot.ins_plan_id


def build_context(
    db: Session,
    *,
    patient_id: int | None = None,
    office_id: int | None = None,
    provider_id: str | None = None,
    ins_plan_id: int | None = None,
) -> PricingContext:
    """Fill in everything derivable: patient → plan → carrier, office → group,
    provider → specialty."""
    if patient_id is not None and office_id is None:
        patient = db.get(Patient, patient_id)
        if patient is not None:
            office_id = patient.home_office_id
    if patient_id is not None and ins_plan_id is None:
        ins_plan_id = primary_plan_id(db, patient_id)

    carrier_id = None
    if ins_plan_id:
        plan = db.get(InsurancePlan, ins_plan_id)
        carrier_id = plan.carrier_id if plan is not None else None

    office_group_id = None
    if office_id:
        office = db.get(Office, office_id)
        office_group_id = office.office_group_id if office is not None else None

    specialty_id = None
    if provider_id:
        provider = db.get(Provider, provider_id)
        specialty_id = (provider.specialty or None) if provider is not None else None

    return PricingContext(
        office_id=office_id,
        provider_id=provider_id,
        ins_plan_id=ins_plan_id,
        carrier_id=carrier_id,
        office_group_id=office_group_id,
        specialty_id=specialty_id,
    )


# ── assignment matching ─────────────────────────────────────────────────────

_KEYS = (
    ("ins_plan_id", "ins_plan_id"),
    ("carrier_id", "carrier_id"),
    ("provider_id", "provider_id"),
    ("office_id", "office_id"),
    ("office_group_id", "office_group_id"),
    ("specialty_id", "specialty_id"),
)


def _same(a: Any, b: Any) -> bool:  # noqa: ANN401
    """Key equality — string keys compare case-insensitively and trimmed."""
    if a is None or b is None:
        return False
    if isinstance(a, str) or isinstance(b, str):
        return str(a).strip().lower() == str(b).strip().lower()
    return a == b


def _candidates(
    db: Session, tenant_id: int, ctx: PricingContext
) -> list[tuple[int, FeeScheduleAssignment]]:
    """``(specificity, assignment)`` for every assignment whose *set* keys all
    match the context, best first. An assignment with no keys at all is the
    practice-wide default (specificity 0). Memoised on the context."""
    if ctx._candidates is not None:
        return ctx._candidates
    rows = db.execute(
        select(FeeScheduleAssignment).where(FeeScheduleAssignment.tenant_id == tenant_id)
    ).scalars().all()

    out: list[tuple[int, FeeScheduleAssignment]] = []
    for row in rows:
        specificity = 0
        ok = True
        for attr, ctx_attr in _KEYS:
            value = getattr(row, attr, None)
            if value is None or value == "":
                continue
            specificity += 1
            if not _same(value, getattr(ctx, ctx_attr)):
                ok = False
                break
        if ok:
            out.append((specificity, row))
    out.sort(key=lambda pair: (pair[0], pair[1].id), reverse=True)
    ctx._candidates = out
    return out


def _active_schedule(db: Session, schedule_id: int | None, tenant_id: int) -> FeeSchedule | None:
    if not schedule_id:
        return None
    sched = db.get(FeeSchedule, schedule_id)
    if sched is None or sched.tenant_id != tenant_id or sched.is_active is False:
        return None
    return sched


def _entry(db: Session, schedule_id: int, code: str) -> FeeScheduleEntry | None:
    return db.execute(
        select(FeeScheduleEntry).where(
            FeeScheduleEntry.fee_schedule_id == schedule_id,
            FeeScheduleEntry.procedure_code == code,
        ).order_by(FeeScheduleEntry.id.desc())
    ).scalars().first()


def _priced(entry: FeeScheduleEntry | None) -> bool:
    return entry is not None and (
        entry.patient_fee is not None or entry.insurance_fee is not None
    )


# ── the public resolver ─────────────────────────────────────────────────────


def resolve_procedure_fee(
    db: Session,
    tenant_id: int,
    procedure_code: str,
    *,
    patient_id: int | None = None,
    office_id: int | None = None,
    provider_id: str | None = None,
    ins_plan_id: int | None = None,
    ctx: PricingContext | None = None,
) -> dict:
    """Resolve ``procedure_code``'s fee for this patient/office/provider.

    Pass a prebuilt ``ctx`` (from :func:`build_context`) when pricing several
    codes for the same patient — it carries the resolved plan/carrier/office
    group and memoises the matching assignments.

    Never raises for an unpriced code — it falls through to the code's
    ``default_fee`` (and ultimately ``0.00``) and says so in ``fee_source``.
    """
    code = (procedure_code or "").strip()
    proc = db.get(ProcedureCode, code) if code else None
    if code and proc is None:
        raise NotFoundError(f"Procedure code '{code}' was not found")

    if ctx is None:
        ctx = build_context(
            db,
            patient_id=patient_id,
            office_id=office_id,
            provider_id=provider_id,
            ins_plan_id=ins_plan_id,
        )

    chosen: FeeScheduleEntry | None = None
    chosen_schedule: FeeSchedule | None = None
    source = "code_default"
    specificity = 0
    conflicts: list[dict] = []

    # 1. fee_schedule_assignments — most specific match wins, ties → newest row.
    for spec, assign in _candidates(db, tenant_id, ctx):
        sched = _active_schedule(db, assign.fee_schedule_id, tenant_id)
        if sched is None:
            continue
        entry = _entry(db, sched.id, code)
        if not _priced(entry):
            continue
        if chosen is None:
            chosen, chosen_schedule, source, specificity = entry, sched, "assignment", spec
            continue
        # An equally-specific rival that prices the code differently is a real
        # configuration conflict — report it instead of silently picking one.
        if spec == specificity and _money(entry.patient_fee) != _money(chosen.patient_fee):
            conflicts.append({
                "fee_schedule_id": sched.id,
                "fee_schedule_name": sched.name,
                "fee": _money(entry.patient_fee),
                "specificity": spec,
            })

    # 2. a schedule linked directly to the plan.
    if chosen is None and ctx.ins_plan_id:
        linked_id = db.execute(
            select(FeeSchedule.id).where(
                FeeSchedule.ins_plan_id == ctx.ins_plan_id,
                FeeSchedule.is_active.is_(True),
                FeeSchedule.tenant_id == tenant_id,
            ).order_by(FeeSchedule.id.desc())
        ).scalars().first()
        sched = _active_schedule(db, linked_id, tenant_id)
        if sched is not None:
            entry = _entry(db, sched.id, code)
            if _priced(entry):
                chosen, chosen_schedule, source = entry, sched, "plan_schedule"

    # 3. the office default.
    office = db.get(Office, ctx.office_id) if ctx.office_id else None
    if chosen is None and office is not None:
        sched = _active_schedule(db, office.default_fee_schedule_id, tenant_id)
        if sched is not None:
            entry = _entry(db, sched.id, code)
            if _priced(entry):
                chosen, chosen_schedule, source = entry, sched, "office_default"

    # The office UCR schedule is a separate lookup — it is the "what we normally
    # charge" figure the ledger prints next to the contracted fee.
    ucr_fee: Decimal | None = None
    if office is not None:
        ucr = _active_schedule(db, office.default_ucr_fee_schedule_id, tenant_id)
        if ucr is not None:
            ucr_entry = _entry(db, ucr.id, code)
            if _priced(ucr_entry):
                ucr_fee = _money(ucr_entry.patient_fee)

    if chosen is not None:
        fee = _money(chosen.patient_fee)
        insurance_fee = _money(chosen.insurance_fee)
    else:
        fee = _money(proc.default_fee) if proc is not None else _ZERO
        insurance_fee = _ZERO

    return {
        "procedure_code": code,
        "fee": fee,
        "insurance_fee": insurance_fee,
        "ucr_fee": ucr_fee,
        "fee_schedule_id": chosen_schedule.id if chosen_schedule else None,
        "fee_schedule_name": chosen_schedule.name if chosen_schedule else None,
        "fee_source": source,
        "specificity": specificity,
        "conflicts": conflicts,
        "context": ctx.as_dict(),
    }
