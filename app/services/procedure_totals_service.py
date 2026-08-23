"""Per-procedure applied-money rollup (CHG-5).

The "Procedures To Post" grid shows **Pat Paid**, **Pat Adj** and a true **Rem
Amt** per charge; ``PatientProcedureRead`` carried no running totals, so the grid
rendered 0.00 / Rem Amt = patient_estimate. This computes them from what is
already posted:

===================== =====================================================
``paid_to_date``      patient payments allocated to the procedure
                      (``payment_allocations`` rows with no carrier link)
``insurance_paid``    carrier money: insurance-linked allocations +
                      ``ledger_insurance_details`` prim/sec/ter ins paid
``adjusted_to_date``  non-void ``patient_adjustments`` on the procedure —
                      either the whole adjustment (scalar ``procedure_id``) or
                      its per-procedure split (ADJ-1 allocations). Never both:
                      an allocated adjustment is counted only through its
                      allocations.
``remaining_amount``  what the patient still owes on the charge — see below
``outstanding_amount`` ``fee`` minus everything applied (AL-15)
===================== =====================================================

**AL-15.** These roll-ups came back ``0`` on every migrated procedure, and
``remaining_amount`` was ``0`` even on a $75 charge with nothing paid. Two causes,
both upstream of the arithmetic:

* ``payment_allocations`` cannot supply ``paid_to_date``. The Denticon allocation
  export holds 6,951 rows for 1.33M payments and **every ``AMOUNT`` in it is
  ``0.0000``** (AL-16), so there was never anything to sum. What *does* survive is
  ``LEDGER.PATPAID`` / ``PATADJUST`` — per-procedure patient money — now stored on
  ``patient_procedures.pat_paid`` / ``pat_adjust`` and used as the floor for the
  two roll-ups (an allocation beats it, so app-created splits still win).
* ``remaining_amount`` was ``patient_estimate − …``, and
  ``patient_estimate`` is ``0.00`` on 1,372,558 of 1,372,574 migrated procedures
  (the migration never mapped a patient-estimate column; Denticon has none — the
  patient's share is ``fee − insurance_estimate``). It now falls back to that
  derivation when no estimate was recorded, so the number means something.

Every query is batched by the id set, so enriching a page costs 4 statements
regardless of page size.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    LedgerInsuranceDetail,
    PatientAdjustment,
    PatientPayment,
    PatientProcedure,
    PaymentAllocation,
)

ZERO = Decimal("0")


def _d(value) -> Decimal:  # noqa: ANN001
    return Decimal(value or 0)


def _allocated(db: Session, ids: list[str]) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """(patient-paid, insurance-paid) per procedure from ``payment_allocations``."""
    patient: dict[str, Decimal] = {}
    insurance: dict[str, Decimal] = {}
    rows = db.execute(
        select(
            PaymentAllocation.procedure_id,
            PaymentAllocation.claim_id,
            PaymentAllocation.ins_plan_id,
            func.coalesce(func.sum(PaymentAllocation.amount), 0),
        )
        .join(PatientPayment, PatientPayment.id == PaymentAllocation.payment_id)
        .where(
            PaymentAllocation.procedure_id.in_(ids),
            PaymentAllocation.payment_id.is_not(None),
            PatientPayment.is_void.is_(False),
        )
        .group_by(
            PaymentAllocation.procedure_id,
            PaymentAllocation.claim_id,
            PaymentAllocation.ins_plan_id,
        )
    ).all()
    for procedure_id, claim_id, ins_plan_id, amount in rows:
        bucket = insurance if (claim_id or ins_plan_id) else patient
        bucket[procedure_id] = bucket.get(procedure_id, ZERO) + _d(amount)
    return patient, insurance


def _insurance_details(db: Session, ids: list[str]) -> dict[str, Decimal]:
    """Carrier money posted through ``ledger_insurance_details`` (the INS-1 path)."""
    rows = db.execute(
        select(
            LedgerInsuranceDetail.procedure_id,
            func.coalesce(func.sum(LedgerInsuranceDetail.prim_ins_paid), 0),
            func.coalesce(func.sum(LedgerInsuranceDetail.sec_ins_paid), 0),
            func.coalesce(func.sum(LedgerInsuranceDetail.ter_ins_paid), 0),
        )
        .where(LedgerInsuranceDetail.procedure_id.in_(ids))
        .group_by(LedgerInsuranceDetail.procedure_id)
    ).all()
    return {row[0]: _d(row[1]) + _d(row[2]) + _d(row[3]) for row in rows}


def _adjusted(db: Session, ids: list[str]) -> dict[str, Decimal]:
    """Non-void adjustments applied to each procedure (scalar ∪ ADJ-1 split)."""
    out: dict[str, Decimal] = {}

    # Adjustments split across procedures (ADJ-1) — counted through their split.
    split_rows = db.execute(
        select(
            PaymentAllocation.procedure_id,
            func.coalesce(func.sum(PaymentAllocation.amount), 0),
        )
        .join(PatientAdjustment, PatientAdjustment.id == PaymentAllocation.adjustment_id)
        .where(
            PaymentAllocation.procedure_id.in_(ids),
            PaymentAllocation.adjustment_id.is_not(None),
            PatientAdjustment.is_void.is_(False),
        )
        .group_by(PaymentAllocation.procedure_id)
    ).all()
    for procedure_id, amount in split_rows:
        out[procedure_id] = out.get(procedure_id, ZERO) + _d(amount)

    # Whole adjustments attached to one procedure. An adjustment that has been
    # split is excluded so it is never counted twice.
    split_ids = select(PaymentAllocation.adjustment_id).where(
        PaymentAllocation.adjustment_id.is_not(None)
    )
    scalar_rows = db.execute(
        select(
            PatientAdjustment.procedure_id,
            func.coalesce(func.sum(PatientAdjustment.amount), 0),
        )
        .where(
            PatientAdjustment.procedure_id.in_(ids),
            PatientAdjustment.is_void.is_(False),
            PatientAdjustment.id.not_in(split_ids),
        )
        .group_by(PatientAdjustment.procedure_id)
    ).all()
    for procedure_id, amount in scalar_rows:
        out[procedure_id] = out.get(procedure_id, ZERO) + _d(amount)
    return out


def _legacy_applied(db: Session, ids: list[str]) -> dict[str, tuple[Decimal, Decimal]]:
    """AL-15: ``(pat_paid, pat_adjust)`` per procedure — the migrated ledger's own
    record of what was applied, and the only one that survived (see AL-16)."""
    rows = db.execute(
        select(PatientProcedure.id, PatientProcedure.pat_paid, PatientProcedure.pat_adjust)
        .where(PatientProcedure.id.in_(ids))
    ).all()
    return {pid: (_d(paid), _d(adjust)) for pid, paid, adjust in rows}


def applied_totals(db: Session, procedure_ids: list[str]) -> dict[str, dict[str, Decimal]]:
    """``{procedure_id: {paid_to_date, insurance_paid_to_date, adjusted_to_date}}``."""
    ids = [pid for pid in procedure_ids if pid]
    if not ids:
        return {}
    patient_paid, insurance_alloc = _allocated(db, ids)
    insurance_detail = _insurance_details(db, ids)
    adjusted = _adjusted(db, ids)
    legacy = _legacy_applied(db, ids)

    def _pick(allocated: Decimal, legacy_value: Decimal) -> Decimal:
        """An allocation is the more precise record, so it wins; the legacy scalar
        fills in where there are no allocations at all — which, on migrated data,
        is everywhere."""
        return allocated if allocated else legacy_value

    return {
        pid: {
            "paid_to_date": _pick(patient_paid.get(pid, ZERO), legacy.get(pid, (ZERO, ZERO))[0]),
            "insurance_paid_to_date": insurance_alloc.get(pid, ZERO)
            + insurance_detail.get(pid, ZERO),
            "adjusted_to_date": _pick(
                adjusted.get(pid, ZERO), legacy.get(pid, (ZERO, ZERO))[1]
            ),
        }
        for pid in ids
    }


def patient_share(procedure) -> Decimal:  # noqa: ANN001
    """What the patient is expected to owe on a charge.

    ``patient_estimate`` when one was recorded; otherwise ``fee − insurance_estimate``.
    Denticon's LEDGER has no patient-estimate column, so the stored value is ``0.00``
    on 1,372,558 of 1,372,574 migrated procedures and the subtraction produced ``0``
    for every historical charge."""
    estimate = _d(procedure.patient_estimate)
    if estimate:
        return estimate
    share = _d(procedure.fee) - _d(procedure.insurance_estimate)
    return share if share > ZERO else ZERO


def allocations_summary(db: Session, procedure) -> dict:  # noqa: ANN001
    """Per-procedure drill-down behind the grid's Pat Paid / Pat Adj / Rem Amt."""
    totals = applied_totals(db, [procedure.id]).get(procedure.id, {})
    paid = totals.get("paid_to_date", ZERO)
    adjusted = totals.get("adjusted_to_date", ZERO)
    insurance_paid = totals.get("insurance_paid_to_date", ZERO)
    allocations = db.execute(
        select(PaymentAllocation)
        .where(PaymentAllocation.procedure_id == procedure.id)
        .order_by(PaymentAllocation.alloc_date.asc(), PaymentAllocation.id.asc())
    ).scalars().all()
    adjustments = db.execute(
        select(PatientAdjustment)
        .where(
            or_(
                PatientAdjustment.procedure_id == procedure.id,
                PatientAdjustment.id.in_(
                    select(PaymentAllocation.adjustment_id).where(
                        PaymentAllocation.procedure_id == procedure.id,
                        PaymentAllocation.adjustment_id.is_not(None),
                    )
                ),
            ),
            PatientAdjustment.is_void.is_(False),
        )
        .order_by(PatientAdjustment.adjustment_date.asc(), PatientAdjustment.id.asc())
    ).scalars().all()
    return {
        "procedure_id": procedure.id,
        "patient_id": procedure.patient_id,
        "fee": _d(procedure.fee),
        "patient_estimate": _d(procedure.patient_estimate),
        "insurance_estimate": _d(procedure.insurance_estimate),
        "paid_to_date": paid,
        "insurance_paid_to_date": insurance_paid,
        "adjusted_to_date": adjusted,
        # AL-15: the patient's share, falling back to fee − insurance estimate
        # when no patient estimate was recorded (true of all migrated rows).
        "remaining_amount": patient_share(procedure) - paid - adjusted,
        # AL-15: the legacy "Outstanding Amount" line — the whole charge minus
        # everything applied to it, from any source.
        "outstanding_amount": _d(procedure.fee) - paid - insurance_paid - adjusted,
        "allocations": list(allocations),
        "adjustments": list(adjustments),
    }
