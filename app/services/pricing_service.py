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

Two engines, one entry point (``settings.PRICING_ENGINE_V2``)
------------------------------------------------------------
:func:`resolve_procedure_fee` dispatches on the flag. With it **off** (the default
through R1/R2) it runs :func:`_resolve_v1`, byte-for-byte the original algorithm,
so nothing about live pricing changes while the new columns and pointers are
backfilled. With it **on** it runs :func:`_resolve_v2`.

**v1** (``_resolve_v1``) — ``fee_schedule_assignments`` binds a schedule to any mix
of plan / carrier / provider / office / office group / specialty; a row is a
candidate when every key it sets matches, *specificity* is the count of set keys,
the most specific wins (ties → newest row), then the plan-linked schedule, the
office default, and the code's ``default_fee``. No date-of-service dimension
(newest entry by id wins).

**v2** (``_resolve_v2``) — the precedence card in :mod:`app.services.fee_vocab`:
payer assignments (plan then carrier, by the lexicographic rank vector, *not* a
key count) → the patient's own list → provider/specialty assignments → the office
default list → the office UCR list → unpriced. The fee in force is the latest
entry whose ``effective_date`` is on or before the date of service (never a
future-dated one); a ``0.00`` fee on a percentage list is "not priced" unless the
entry is explicitly ``is_no_charge``; a payer list that lacks the code is a flagged
gap, not a silent fall-through. ``fee_source`` is stamped on the charge, so a
later Setup edit never re-prices posted history. The UCR figure is always a
parallel lookup on the office's own list, whichever tier priced the fee, and the
contractual write-off is ``ucr_fee − fee``.

Conflicts are **reported, not hidden**: v1 lists an equally-specific rival in
``conflicts``; v2 refuses a duplicate binding at authoring time instead.
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
from app.services import fee_vocab

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
                 "office_group_id", "specialty_id", "_candidates",
                 # ── v2 (PRICING_ENGINE_V2) fields ────────────────────────────
                 # Filled by build_context always; ignored by the v1 resolver.
                 "patient_fee_schedule_id", "office_default_fee_schedule_id",
                 "office_ucr_fee_schedule_id", "office_timezone", "date_of_service",
                 "_v2_candidates")

    def __init__(
        self,
        *,
        office_id: int | None = None,
        provider_id: str | None = None,
        ins_plan_id: int | None = None,
        carrier_id: int | None = None,
        office_group_id: int | None = None,
        specialty_id: str | None = None,
        patient_fee_schedule_id: int | None = None,
        office_default_fee_schedule_id: int | None = None,
        office_ucr_fee_schedule_id: int | None = None,
        office_timezone: str | None = None,
        date_of_service: date | None = None,
    ) -> None:
        self.office_id = office_id
        self.provider_id = provider_id
        self.ins_plan_id = ins_plan_id
        self.carrier_id = carrier_id
        self.office_group_id = office_group_id
        self.specialty_id = specialty_id
        # v2: the patient's own list and the office's two pointers are real
        # resolution tiers, not decoration.
        self.patient_fee_schedule_id = patient_fee_schedule_id
        self.office_default_fee_schedule_id = office_default_fee_schedule_id
        self.office_ucr_fee_schedule_id = office_ucr_fee_schedule_id
        self.office_timezone = office_timezone
        self.date_of_service = date_of_service
        # Matching assignments, resolved once. A multi-line estimate prices
        # every line against the same context, so recomputing this per line
        # would re-read the assignment table N times for one answer.
        self._candidates: list[tuple[int, FeeScheduleAssignment]] | None = None
        self._v2_candidates: list[FeeScheduleAssignment] | None = None

    def as_dict(self) -> dict:
        return {
            "office_id": self.office_id,
            "provider_id": self.provider_id,
            "ins_plan_id": self.ins_plan_id,
            "carrier_id": self.carrier_id,
            "office_group_id": self.office_group_id,
            "specialty_id": self.specialty_id,
            "patient_fee_schedule_id": self.patient_fee_schedule_id,
            "office_default_fee_schedule_id": self.office_default_fee_schedule_id,
            "office_ucr_fee_schedule_id": self.office_ucr_fee_schedule_id,
            "date_of_service": self.date_of_service.isoformat() if self.date_of_service else None,
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
    date_of_service: date | None = None,
) -> PricingContext:
    """Fill in everything derivable: patient → plan → carrier, office → group,
    provider → specialty, plus the v2 tiers (patient list, office pointers) and
    the office timezone the date-of-service default is computed in.

    The v2 fields are always populated; the v1 resolver ignores them, so one
    context serves both engines and a multi-line estimate builds it once.
    """
    patient = db.get(Patient, patient_id) if patient_id is not None else None
    if patient is not None and office_id is None:
        office_id = patient.home_office_id
    if patient_id is not None and ins_plan_id is None:
        ins_plan_id = primary_plan_id(db, patient_id)

    carrier_id = None
    if ins_plan_id:
        plan = db.get(InsurancePlan, ins_plan_id)
        carrier_id = plan.carrier_id if plan is not None else None

    office = db.get(Office, office_id) if office_id else None
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
        patient_fee_schedule_id=(patient.fee_schedule_id if patient is not None else None),
        office_default_fee_schedule_id=(office.default_fee_schedule_id if office is not None else None),
        office_ucr_fee_schedule_id=(office.default_ucr_fee_schedule_id if office is not None else None),
        office_timezone=(office.timezone if office is not None else None),
        date_of_service=date_of_service,
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
    date_of_service: date | None = None,
    ctx: PricingContext | None = None,
) -> dict:
    """Resolve ``procedure_code``'s fee for this patient/office/provider.

    Dispatches on ``settings.PRICING_ENGINE_V2``. With the flag **off** (the
    default through R1/R2) this is byte-for-byte the previous resolver, so every
    live caller — the estimate engine, the charge write path, ``GET
    /patients/{id}/fee`` — behaves exactly as before while the new columns are
    populated but not yet consulted. With the flag **on** it walks the precedence
    card in :mod:`app.services.fee_vocab` (payer assignments → the patient's list →
    provider/office assignments → office default → office UCR), honours the entry
    in force on the date of service, and never prices from a $0 or future-dated
    entry. Both return the same dict shape (v2 adds keys; it never drops one).

    Pass a prebuilt ``ctx`` (from :func:`build_context`) when pricing several
    codes for the same patient.
    """
    if settings.PRICING_ENGINE_V2:
        return _resolve_v2(
            db, tenant_id, procedure_code,
            patient_id=patient_id, office_id=office_id, provider_id=provider_id,
            ins_plan_id=ins_plan_id, date_of_service=date_of_service, ctx=ctx,
        )
    return _resolve_v1(
        db, tenant_id, procedure_code,
        patient_id=patient_id, office_id=office_id, provider_id=provider_id,
        ins_plan_id=ins_plan_id, ctx=ctx,
    )


def _resolve_v1(
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
    """The pre-R1 resolver, unchanged. Assignments by key-count specificity, then
    the plan-linked schedule, then the office default, then ``default_fee`` — with
    no date-of-service dimension (newest entry by id wins)."""
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


# ── v2 resolver (PRICING_ENGINE_V2) ──────────────────────────────────────────


def _entry_in_force(
    db: Session, schedule_id: int, code: str, on: date | None, today: date, pricing_model: str
) -> tuple[FeeScheduleEntry | None, str | None]:
    """The priced entry in force for ``code`` on ``on``, and a warning if any.

    * the latest entry with ``effective_date <= on`` wins (normal case);
    * if none qualifies, the *earliest* entry is used with
      ``entry_predates_service_date`` — the migrated data stamps one load date
      (2020-01-01) on lists that price charges going back years, so a back-dated
      charge must still resolve to the historical fee rather than nothing;
    * unless that earliest entry is itself *future* (``> today``): then the list
      only holds prices staged for later, and pricing today at next month's fee is
      the specific error the date logic exists to prevent — return
      ``entry_not_yet_effective`` and let the caller keep walking tiers.

    A ``patient_fee <= 0`` entry on a percentage list is treated as *not priced*
    (blank source fees became ``0.00`` in the import), unless it is explicitly
    ``is_no_charge``.
    """
    rows = db.execute(
        select(FeeScheduleEntry).where(
            FeeScheduleEntry.fee_schedule_id == schedule_id,
            FeeScheduleEntry.procedure_code == code,
        )
    ).scalars().all()
    usable = [e for e in rows if _priced_v2(e, pricing_model)]
    if not usable:
        return None, None

    dated = sorted(usable, key=lambda e: (e.effective_date or date.min))
    in_force = [e for e in dated if (e.effective_date or date.min) <= on] if on else dated
    if in_force:
        return in_force[-1], None  # latest on/before the service date

    earliest = dated[0]
    if earliest.effective_date and earliest.effective_date > today:
        # Every price on this list starts after today — do not use it now.
        return None, "entry_not_yet_effective"
    return earliest, "entry_predates_service_date"


def _priced_v2(entry: FeeScheduleEntry, pricing_model: str) -> bool:
    if getattr(entry, "is_no_charge", False):
        return True
    if pricing_model == "copay":
        return (entry.patient_fee is not None and entry.patient_fee > 0) or (
            entry.insurance_fee is not None and entry.insurance_fee > 0
        )
    # percentage / unknown: a real, positive patient fee. 0.00 is "not priced".
    return entry.patient_fee is not None and entry.patient_fee > 0


def _entry_fee(entry: FeeScheduleEntry, pricing_model: str) -> Decimal:
    """The charge amount an entry states. On a copay list the amount can live in
    ``insurance_fee`` (``patient_fee`` blank); the two are **never summed**."""
    if getattr(entry, "is_no_charge", False):
        return _ZERO
    if pricing_model == "copay":
        if entry.patient_fee is not None and entry.patient_fee > 0:
            return _money(entry.patient_fee)
        return _money(entry.insurance_fee)
    return _money(entry.patient_fee)


def _v2_candidate_rows(db: Session, tenant_id: int, ctx: PricingContext) -> list[FeeScheduleAssignment]:
    """Assignments whose every set key matches the context, memoised on the ctx.

    Unlike v1 this computes no key-count specificity — ordering is the lexicographic
    rank vector in :func:`fee_vocab.assignment_sort_key`, applied by the caller
    after partitioning payer rows from provider/office rows.
    """
    if ctx._v2_candidates is not None:
        return ctx._v2_candidates
    rows = db.execute(
        select(FeeScheduleAssignment).where(FeeScheduleAssignment.tenant_id == tenant_id)
    ).scalars().all()
    out: list[FeeScheduleAssignment] = []
    for row in rows:
        ok = True
        for attr in fee_vocab.ASSIGNMENT_KEYS:
            value = getattr(row, attr, None)
            if value is None or value == "":
                continue
            if not _same(value, getattr(ctx, attr, None)):
                ok = False
                break
        # A row that sets no payer/provider key is a legacy practice-wide row;
        # v2 ignores it (offices own the practice-wide default now).
        if ok and fee_vocab.has_assignment_target(row):
            out.append(row)
    ctx._v2_candidates = out
    return out


def _resolve_v2(
    db: Session,
    tenant_id: int,
    procedure_code: str,
    *,
    patient_id: int | None = None,
    office_id: int | None = None,
    provider_id: str | None = None,
    ins_plan_id: int | None = None,
    date_of_service: date | None = None,
    ctx: PricingContext | None = None,
) -> dict:
    code = (procedure_code or "").strip()
    proc = db.get(ProcedureCode, code) if code else None
    if code and proc is None:
        raise NotFoundError(f"Procedure code '{code}' was not found")

    if ctx is None:
        ctx = build_context(
            db, patient_id=patient_id, office_id=office_id, provider_id=provider_id,
            ins_plan_id=ins_plan_id, date_of_service=date_of_service,
        )
    on = date_of_service or ctx.date_of_service
    today = office_today(ctx.office_timezone)
    if on is None:
        on = today
    warnings: list[str] = []
    skipped: list[dict] = []

    # ── build the ordered candidate list: (schedule_id, fee_source, is_payer) ─
    matches = _v2_candidate_rows(db, tenant_id, ctx)
    payer = sorted(
        (a for a in matches if a.ins_plan_id or a.carrier_id),
        key=fee_vocab.assignment_sort_key, reverse=True,
    )
    non_payer = sorted(
        (a for a in matches if not (a.ins_plan_id or a.carrier_id)),
        key=fee_vocab.assignment_sort_key, reverse=True,
    )

    candidates: list[tuple[int, str, bool]] = []
    for a in payer:
        candidates.append((a.fee_schedule_id, fee_vocab.fee_source_for_assignment(a), True))
    if ctx.patient_fee_schedule_id:
        candidates.append((ctx.patient_fee_schedule_id, "patient_schedule", False))
    for a in non_payer:
        candidates.append((a.fee_schedule_id, "assignment_provider", False))
    if ctx.office_default_fee_schedule_id:
        candidates.append((ctx.office_default_fee_schedule_id, "office_default", False))
    if ctx.office_ucr_fee_schedule_id:
        candidates.append((ctx.office_ucr_fee_schedule_id, "office_ucr", False))

    # ── walk the tiers, first priced entry wins ──────────────────────────────
    chosen_entry: FeeScheduleEntry | None = None
    chosen_schedule: FeeSchedule | None = None
    source = "unpriced"
    fee = _ZERO
    seen_schedules: set[int] = set()
    for schedule_id, fee_source, is_payer in candidates:
        if schedule_id in seen_schedules:
            continue
        seen_schedules.add(schedule_id)
        sched = _active_schedule(db, schedule_id, tenant_id)
        if sched is None:
            if is_payer:
                skipped.append({"fee_schedule_id": schedule_id, "reason": "inactive_or_foreign"})
            continue
        entry, entry_warning = _entry_in_force(db, sched.id, code, on, today, sched.pricing_model)
        if entry is None:
            # A future-only list (its prices start after the service date) is worth
            # saying so on any tier, not just a payer one.
            if entry_warning:
                warnings.append(entry_warning)
            # A payer list that applies but does not price this code is a real gap
            # the fee-schedule owner must close — never a silent fall-through to the
            # practice list.
            if is_payer:
                warnings.append("code_missing_on_bound_schedule")
                skipped.append({
                    "fee_schedule_id": sched.id, "fee_schedule_name": sched.name,
                    "reason": entry_warning or "code_missing",
                })
            continue
        if entry_warning:
            warnings.append(entry_warning)
        chosen_entry, chosen_schedule, source = entry, sched, fee_source
        fee = _entry_fee(entry, sched.pricing_model)
        break

    # ── UCR is a separate, parallel lookup — the office's own list, always ────
    ucr_fee: Decimal | None = None
    ucr_schedule_id: int | None = None
    if ctx.office_ucr_fee_schedule_id:
        ucr_sched = _active_schedule(db, ctx.office_ucr_fee_schedule_id, tenant_id)
        if ucr_sched is not None:
            ucr_entry, _ = _entry_in_force(db, ucr_sched.id, code, on, today, ucr_sched.pricing_model)
            if ucr_entry is not None:
                ucr_fee = _entry_fee(ucr_entry, ucr_sched.pricing_model)
                ucr_schedule_id = ucr_sched.id
            else:
                warnings.append("ucr_unpriced")
    else:
        warnings.append("office_without_ucr")

    is_unpriced = chosen_entry is None
    if is_unpriced:
        warnings.append("unpriced")

    # The contractual write-off is UCR minus the contracted fee; only meaningful
    # when a non-UCR list priced the line, and unknown (not zero) with no UCR.
    expected_write_off: Decimal | None = None
    if ucr_fee is not None and not is_unpriced and source != "office_ucr":
        expected_write_off = _money(ucr_fee - fee) if ucr_fee > fee else _ZERO

    payer_amount = None
    if chosen_entry is not None and chosen_schedule is not None and chosen_schedule.pricing_model == "copay":
        payer_amount = _money(chosen_entry.insurance_fee)

    return {
        "procedure_code": code,
        "fee": fee,
        # v1 parity keys so every existing caller/reader keeps working ──────────
        "insurance_fee": payer_amount or _ZERO,
        "ucr_fee": ucr_fee,
        "fee_schedule_id": chosen_schedule.id if chosen_schedule else None,
        "fee_schedule_name": chosen_schedule.name if chosen_schedule else None,
        "fee_source": source,
        "specificity": 0,
        "conflicts": [],
        "context": ctx.as_dict(),
        # ── v2 additions ────────────────────────────────────────────────────
        "pricing_model": chosen_schedule.pricing_model if chosen_schedule else "percentage",
        "fee_type": chosen_schedule.fee_type if chosen_schedule else None,
        "fee_effective_date": (
            chosen_entry.effective_date.isoformat()
            if chosen_entry is not None and chosen_entry.effective_date else None
        ),
        "ucr_fee_schedule_id": ucr_schedule_id,
        "payer_amount": payer_amount,
        "expected_write_off": expected_write_off,
        "is_unpriced": is_unpriced,
        "date_of_service": on.isoformat() if on else None,
        "warnings": warnings,
        "skipped": skipped,
    }


def quote(
    db: Session,
    tenant_id: int,
    *,
    office_id: int | None = None,
    provider_id: str | None = None,
    ins_plan_id: int | None = None,
    date_of_service: date | None = None,
    lines: list[dict],
) -> dict:
    """Fee-only quote for one or more lines with **no patient** — the scheduler,
    a treatment-plan template, or the add-patient screen quoting before a patient
    or a date of service exists. Each line is priced through the same resolver a
    patient quote uses (so they cannot disagree); a per-line ``provider_id``
    overrides the shared context. There is no coverage split here — that needs a
    patient, and ``POST /patients/{id}/estimate`` is the patient path."""
    base = build_context(db, office_id=office_id, provider_id=provider_id,
                         ins_plan_id=ins_plan_id, date_of_service=date_of_service)
    out: list[dict] = []
    for line in lines:
        ctx = base
        line_provider = line.get("provider_id")
        if line_provider and line_provider != base.provider_id:
            ctx = build_context(db, office_id=office_id, provider_id=line_provider,
                                ins_plan_id=ins_plan_id, date_of_service=date_of_service)
        out.append(resolve_procedure_fee(
            db, tenant_id, line["procedure_code"], ctx=ctx, date_of_service=date_of_service,
        ))
    return {"office_id": office_id, "ins_plan_id": ins_plan_id, "lines": out}


def fee_binding(db: Session, tenant_id: int, ins_plan_id: int) -> dict:
    """Which fee schedule a plan binds — the read-only "Fee schedule in effect"
    panel on the Insurance Plan wizard (§3.5). Looks only at the payer tiers of
    the precedence card (a plan-keyed assignment, else a carrier-keyed one with no
    plan key), ranked the same way the resolver ranks them. ``bound`` is false when
    no payer assignment names this plan — pricing then falls through to the
    patient/office tiers, which is not the plan's own binding."""
    plan = db.get(InsurancePlan, ins_plan_id)
    if plan is None or plan.tenant_id != tenant_id:
        raise NotFoundError(f"InsurancePlan '{ins_plan_id}' was not found")
    carrier_id = plan.carrier_id

    rows = db.execute(
        select(FeeScheduleAssignment).where(FeeScheduleAssignment.tenant_id == tenant_id)
    ).scalars().all()
    matches: list[tuple[str, FeeScheduleAssignment]] = []
    for row in rows:
        if row.ins_plan_id == ins_plan_id:
            matches.append(("plan", row))
        elif row.ins_plan_id is None and carrier_id is not None and row.carrier_id == carrier_id:
            matches.append(("carrier", row))

    result = {
        "ins_plan_id": ins_plan_id,
        "carrier_id": carrier_id,
        "bound": False,
        "via": None,
        "fee_schedule_id": None,
        "fee_schedule_name": None,
        "fee_schedule_active": None,
        "fee_source": None,
        "assignment_id": None,
    }
    if not matches:
        return result
    via, best = max(matches, key=lambda m: fee_vocab.assignment_sort_key(m[1]))
    sched = db.get(FeeSchedule, best.fee_schedule_id) if best.fee_schedule_id else None
    result.update(
        bound=sched is not None,
        via=via,
        fee_schedule_id=best.fee_schedule_id,
        fee_schedule_name=sched.name if sched is not None else None,
        fee_schedule_active=bool(sched.is_active) if sched is not None else None,
        fee_source=fee_vocab.fee_source_for_assignment(best),
        assignment_id=best.id,
    )
    return result
