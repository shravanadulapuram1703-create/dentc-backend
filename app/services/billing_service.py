"""Billing business logic that exceeds plain CRUD.

- Allocating a payment across procedures/claims with an over-allocation guard.
- Splitting an adjustment the same way (ADJ-1) and reporting what has already
  been applied to a procedure (CHG-5).
- Recalculating a claim's billed/estimate totals from its linked procedures.

Tables ``patient_payments`` / ``insurance_claims`` carry no ``tenant_id`` column;
tenancy is verified through the owning patient.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.crud.base import CRUDBase
from app.db.models import (
    Appointment,
    AuditLog,
    ClaimSubmission,
    ExplosionCode,
    ExplosionCodeItem,
    InsuranceCarrier,
    InsuranceClaim,
    InsurancePlan,
    LedgerInsuranceDetail,
    Patient,
    PatientAdjustment,
    PatientInsurance,
    PatientPayment,
    PatientProcedure,
    PaymentAllocation,
    ProcedureCode,
)
from app.integrations import redis_store
from app.schemas.billing import AdjustmentAllocationLine, AllocationLine
from app.services import procedure_totals_service
from app.services.user_admin_service import resolve_user_names


def _assert_patient_in_tenant(db: Session, patient_id: int, tenant_id: int) -> None:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError("Related patient not found in this tenant")


def allocate_payment(
    db: Session, payment_id: str, lines: list[AllocationLine], tenant_id: int
) -> list[PaymentAllocation]:
    payment = db.get(PatientPayment, payment_id)
    if payment is None:
        raise NotFoundError(f"PatientPayment '{payment_id}' was not found")
    _assert_patient_in_tenant(db, payment.patient_id, tenant_id)

    already = db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
            PaymentAllocation.payment_id == payment_id
        )
    ).scalar_one()
    requested = sum((line.amount for line in lines), Decimal("0"))
    if Decimal(already) + requested > payment.amount:
        raise ValidationError(
            "Allocations exceed the payment amount",
            details={
                "payment_amount": str(payment.amount),
                "already_allocated": str(already),
                "requested": str(requested),
            },
        )

    created: list[PaymentAllocation] = []
    for line in lines:
        alloc = PaymentAllocation(
            patient_id=payment.patient_id,
            payment_id=payment_id,
            procedure_id=line.procedure_id,
            claim_id=line.claim_id,
            ins_plan_id=line.ins_plan_id,
            provider_id=line.provider_id,
            amount=line.amount,
            alloc_type=line.alloc_type,
            alloc_date=line.alloc_date,
        )
        db.add(alloc)
        created.append(alloc)
    db.commit()
    for alloc in created:
        db.refresh(alloc)
    return created


# ── ADJ-1: split one adjustment across specific outstanding procedures ────────
def allocate_adjustment(
    db: Session,
    adjustment_id: int,
    lines: list[AdjustmentAllocationLine],
    tenant_id: int,
    *,
    replace: bool = False,
) -> list[PaymentAllocation]:
    """Write one adjustment down against named procedures.

    Mirrors :func:`allocate_payment` — same table, same over-allocation guard —
    because an adjustment splits exactly the way a payment does. ``replace``
    re-issues the split (the grid edits the whole set at once); otherwise the
    lines are added to whatever is already allocated.
    """
    adjustment = db.get(PatientAdjustment, adjustment_id)
    if adjustment is None:
        raise NotFoundError(f"PatientAdjustment '{adjustment_id}' was not found")
    if adjustment.tenant_id != tenant_id:
        raise NotFoundError(f"PatientAdjustment '{adjustment_id}' was not found")
    if adjustment.is_void:
        raise ValidationError("A voided adjustment cannot be allocated", code="adjustment_void")

    if replace:
        db.execute(
            sa_delete(PaymentAllocation).where(PaymentAllocation.adjustment_id == adjustment_id)
        )
        db.flush()

    already = Decimal(db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
            PaymentAllocation.adjustment_id == adjustment_id
        )
    ).scalar_one())
    requested = sum((line.amount for line in lines), Decimal("0"))
    if already + requested > Decimal(adjustment.amount):
        raise ValidationError(
            "Allocations exceed the adjustment amount",
            details={
                "adjustment_amount": str(adjustment.amount),
                "already_allocated": str(already),
                "requested": str(requested),
            },
        )

    procedure_ids = [line.procedure_id for line in lines]
    owned = {
        pid for (pid,) in db.execute(
            select(PatientProcedure.id).where(
                PatientProcedure.id.in_(procedure_ids),
                PatientProcedure.patient_id == adjustment.patient_id,
            )
        ).all()
    }
    missing = [pid for pid in procedure_ids if pid not in owned]
    if missing:
        raise ValidationError(
            "Allocation targets a procedure that does not belong to this patient",
            details={"procedure_ids": missing},
        )

    created: list[PaymentAllocation] = []
    for line in lines:
        alloc = PaymentAllocation(
            patient_id=adjustment.patient_id,
            adjustment_id=adjustment_id,
            procedure_id=line.procedure_id,
            provider_id=line.provider_id or adjustment.provider_id,
            amount=line.amount,
            alloc_type="ADJ",
            alloc_date=line.alloc_date or adjustment.adjustment_date,
        )
        db.add(alloc)
        created.append(alloc)
    db.commit()
    for alloc in created:
        db.refresh(alloc)
    redis_store.cache_delete(f"balance:{tenant_id}:{adjustment.patient_id}")
    return created


def list_adjustment_allocations(
    db: Session, adjustment_id: int, tenant_id: int
) -> list[PaymentAllocation]:
    adjustment = db.get(PatientAdjustment, adjustment_id)
    if adjustment is None or adjustment.tenant_id != tenant_id:
        raise NotFoundError(f"PatientAdjustment '{adjustment_id}' was not found")
    return list(db.execute(
        select(PaymentAllocation)
        .where(PaymentAllocation.adjustment_id == adjustment_id)
        .order_by(PaymentAllocation.id.asc())
    ).scalars().all())


# ── CHG-5: what has already been applied to one procedure ─────────────────────
def procedure_allocations_summary(db: Session, procedure_id: str, tenant_id: int) -> dict:
    procedure = db.get(PatientProcedure, procedure_id)
    if procedure is None:
        raise NotFoundError(f"PatientProcedure '{procedure_id}' was not found")
    _assert_patient_in_tenant(db, procedure.patient_id, tenant_id)
    return procedure_totals_service.allocations_summary(db, procedure)


# ── INS-PAY-2: a claim's money is *derived*, never accumulated ────────────────
#: The per-tier paid / adjusted columns a coverage row can carry. Kept here so
#: the recompute, the batch post and the reversal all agree about what "paid"
#: means — three tiers, not just the primary (INS-PAY-5).
_PAID_COLUMNS = (
    LedgerInsuranceDetail.prim_ins_paid,
    LedgerInsuranceDetail.sec_ins_paid,
    LedgerInsuranceDetail.ter_ins_paid,
)
_ADJUST_COLUMNS = (
    LedgerInsuranceDetail.prim_ins_adjust,
    LedgerInsuranceDetail.sec_ins_adjust,
    LedgerInsuranceDetail.ter_ins_adjust,
)


def _sum_coverage(db: Session, claim_id: str) -> tuple[Decimal, Decimal, int]:
    """``(paid, adjusted, live_row_count)`` over a claim's **live** coverage rows.

    This is the whole of the INS-PAY-2 fix. ``record_insurance_payment`` used to
    do ``claim.total_paid += paid`` and nothing ever subtracted, so deleting the
    coverage rows left the claim claiming money that no row backed. Deriving the
    total means a delete, a reversal and a re-post all converge on the truth.
    """
    row = db.execute(
        select(
            *[func.coalesce(func.sum(col), 0) for col in _PAID_COLUMNS],
            *[func.coalesce(func.sum(col), 0) for col in _ADJUST_COLUMNS],
            func.count(),
        ).where(
            LedgerInsuranceDetail.claim_id == claim_id,
            LedgerInsuranceDetail.is_void.is_(False),
        )
    ).one()
    paid = sum((Decimal(v) for v in row[:3]), Decimal("0"))
    adjusted = sum((Decimal(v) for v in row[3:6]), Decimal("0"))
    return paid, adjusted, int(row[6])


def _recompute_claim_totals(db: Session, claim: InsuranceClaim) -> dict:
    """Derive every money column on a claim from the rows that back it.

    Charges/estimate come from the linked procedures, paid/adjusted from the live
    coverage rows. Does **not** commit — the caller owns the transaction, which is
    what makes the batch post (INS-PAY-3) atomic.
    """
    billed, estimated, procedure_count = db.execute(
        select(
            func.coalesce(func.sum(PatientProcedure.fee), 0),
            func.coalesce(func.sum(PatientProcedure.insurance_estimate), 0),
            func.count(),
        ).where(
            PatientProcedure.claim_id == claim.id,
            PatientProcedure.is_void.is_(False),
        )
    ).one()
    posted, adjusted, coverage_count = _sum_coverage(db, claim.id)
    # The baseline is *added*, never replaced: a migrated claim's paid total has
    # no coverage rows behind it, so deriving from rows alone would erase it.
    opening = Decimal(claim.opening_paid or 0)

    claim.total_billed = Decimal(billed)
    claim.est_insurance = Decimal(estimated)
    claim.total_paid = opening + posted
    return {
        "procedure_count": int(procedure_count),
        "coverage_row_count": coverage_count,
        "total_adjusted": adjusted,
        "opening_paid": opening,
        "posted_paid": posted,
    }


def recalculate_claim(db: Session, claim_id: str, tenant_id: int) -> dict:
    """Recompute a claim's billed / estimate / **paid** totals from its rows.

    INS-PAY-2: ``total_paid`` used to be echoed back untouched, so a claim whose
    coverage rows had been deleted still reported the carrier's money. It is now
    derived, which means this endpoint also *repairs* a claim that was left
    inconsistent by the old delete path — no hand-PATCH needed.
    """
    claim = db.get(InsuranceClaim, claim_id)
    if claim is None:
        raise NotFoundError(f"InsuranceClaim '{claim_id}' was not found")
    _assert_patient_in_tenant(db, claim.patient_id, tenant_id)

    counts = _recompute_claim_totals(db, claim)
    db.commit()
    db.refresh(claim)
    redis_store.cache_delete(f"balance:{tenant_id}:{claim.patient_id}")
    return {
        "id": claim.id,
        "claim_number": claim.claim_number,
        "status": claim.status,
        "total_billed": claim.total_billed,
        "total_paid": claim.total_paid,
        "est_insurance": claim.est_insurance,
        "procedure_count": counts["procedure_count"],
        "coverage_row_count": counts["coverage_row_count"],
        "total_adjusted": counts["total_adjusted"],
        # Published so the figure is explicable: "paid" is what this system
        # posted plus what came across from the legacy claim.
        "opening_paid": counts["opening_paid"],
        "posted_paid": counts["posted_paid"],
    }


def _get_claim(db: Session, claim_id: str, tenant_id: int) -> InsuranceClaim:
    claim = db.get(InsuranceClaim, claim_id)
    if claim is None:
        raise NotFoundError(f"InsuranceClaim '{claim_id}' was not found")
    _assert_patient_in_tenant(db, claim.patient_id, tenant_id)
    return claim


# ── INS-1: record an insurance payment with remittance identifiers ───────────
#: Every per-tier money field a coverage row accepts on a write. Listed once so
#: the single post and the batch post (INS-PAY-3) cannot drift, and so adding a
#: tier column does not mean editing two builders.
_COVERAGE_MONEY_FIELDS = (
    "prim_estimated", "prim_deductible", "prim_ins_paid", "prim_ins_adjust",
    "sec_estimated", "sec_deductible", "sec_ins_paid", "sec_ins_adjust",
    "ter_estimated", "ter_deductible", "ter_ins_paid", "ter_ins_adjust",
)
_COVERAGE_PLAN_FIELDS = ("prim_ins_plan_id", "sec_ins_plan_id", "ter_ins_plan_id")
#: Identifiers that describe the *cheque*, not the procedure — so on a batch post
#: they come from the header and a line only overrides them deliberately.
_REMITTANCE_FIELDS = (
    "payment_method", "check_number", "bank_number", "eob_number",
    "eft_trace_number", "notes",
)
_PAID_FIELDS = ("prim_ins_paid", "sec_ins_paid", "ter_ins_paid")
_ADJUST_FIELDS = ("prim_ins_adjust", "sec_ins_adjust", "ter_ins_adjust")


def _build_coverage_row(
    payload: dict, *, patient_id: int, claim_id: str | None, actor_id: int | None,
    payment_date: date,
) -> LedgerInsuranceDetail:
    """One coverage row from a line payload. INS-PAY-5: all three tiers are built
    identically — the primary is no longer a special case."""
    row = LedgerInsuranceDetail(
        patient_id=patient_id,
        claim_id=claim_id,
        procedure_id=payload.get("procedure_id"),
        office_id=payload.get("office_id"),
        payment_date=payment_date,
        created_by=actor_id,
        # ``*_posted`` records which tier this row actually carries money for, so
        # a tertiary remittance is distinguishable from an empty one.
        prim_posted=payload.get("prim_ins_paid") is not None,
        sec_posted=payload.get("sec_ins_paid") is not None,
        ter_posted=payload.get("ter_ins_paid") is not None,
    )
    for field in _COVERAGE_MONEY_FIELDS + _COVERAGE_PLAN_FIELDS + _REMITTANCE_FIELDS:
        if payload.get(field) is not None:
            setattr(row, field, payload[field])
    return row


def _reject_negative(payload: dict, *, line_index: int | None = None) -> None:
    """A remittance line is never negative. Backing a payment out is
    :func:`reverse_insurance_payment`, which keeps an audit trail — a negative
    amount smuggled through the normal post would not."""
    for field in _COVERAGE_MONEY_FIELDS:
        value = payload.get(field)
        if value is not None and Decimal(value) < 0:
            where = "" if line_index is None else f" (line {line_index + 1})"
            raise ValidationError(
                f"{field} may not be negative{where} — reverse the payment instead",
                code="negative_remittance_amount",
                details={"field": field, "line": line_index},
            )


def _money(value) -> Decimal:  # noqa: ANN001
    """Two decimal places — the reconciliation error is quoted back to the user
    as a cheque amount, and ``50.0`` does not read as money."""
    return Decimal(value).quantize(Decimal("0.01"))


def _sum_fields(payload: dict, fields: tuple[str, ...]) -> Decimal:
    return sum((Decimal(payload.get(f) or 0) for f in fields), Decimal("0"))


def _mark_claim_paid(claim: InsuranceClaim, paid: Decimal, payment_date: date) -> None:
    if paid > 0 and claim.status in ("sent", "submitted", "pending"):
        claim.status = "paid"
        claim.paid_date = payment_date


def _claim_totals_out(claim: InsuranceClaim) -> dict:
    return {
        "id": claim.id,
        "claim_number": claim.claim_number,
        "status": claim.status,
        "total_billed": claim.total_billed,
        "total_paid": claim.total_paid,
        "est_insurance": claim.est_insurance,
        "opening_paid": claim.opening_paid,
        "write_off_amount": claim.write_off_amount,
        "write_off_mode": claim.write_off_mode,
        "write_off_value": claim.write_off_value,
    }


def record_insurance_payment(
    db: Session, tenant_id: int, payload: dict, *, actor_id: int | None = None
) -> LedgerInsuranceDetail:
    """Post a carrier insurance payment carrying the reconciliation identifiers
    (check / bank / EOB / EFT-trace) that a posted payment must keep so it can be
    matched back to the carrier's remittance.

    INS-PAY-1 the remittance ``notes`` land on the row itself; INS-PAY-5 all
    three tiers post through the same builder; INS-PAY-2 the claim's totals are
    **recomputed** from its live rows rather than incremented, so this post and a
    later reversal cannot disagree about what the carrier has paid.
    """
    _assert_patient_in_tenant(db, payload["patient_id"], tenant_id)
    _reject_negative(payload)
    claim = _get_claim(db, payload["claim_id"], tenant_id) if payload.get("claim_id") else None

    payment_date = payload.get("payment_date") or datetime.now(timezone.utc).date()
    detail = _build_coverage_row(
        payload, patient_id=payload["patient_id"],
        claim_id=payload.get("claim_id"), actor_id=actor_id, payment_date=payment_date,
    )
    db.add(detail)

    if claim is not None:
        db.flush()
        _recompute_claim_totals(db, claim)
        _mark_claim_paid(claim, _sum_fields(payload, _PAID_FIELDS), payment_date)

    db.commit()
    db.refresh(detail)
    redis_store.cache_delete(f"balance:{tenant_id}:{payload['patient_id']}")
    return detail


# ── INS-PAY-3: one cheque covering several procedures is one transaction ──────
def record_insurance_payment_batch(
    db: Session, tenant_id: int, payload: dict, *, actor_id: int | None = None
) -> dict:
    """Post a whole remittance — one header + N lines — atomically.

    A four-procedure cheque used to be four POSTs, and a failure on the third
    left the claim half-paid with nothing able to roll it back; the window could
    only report "posted N of M". Everything here happens in one transaction:
    either every line lands or none does.

    ``payment_amount``, when supplied, is reconciled against the sum of the lines
    **to the cent** before anything is written. That moves the window's
    reconciliation rule server-side, so an import or a second client cannot post
    a remittance whose parts do not add up to the cheque.
    """
    patient_id = payload["patient_id"]
    _assert_patient_in_tenant(db, patient_id, tenant_id)
    lines = payload.get("lines") or []
    if not lines:
        raise ValidationError("A remittance needs at least one line", code="empty_remittance")

    claim = _get_claim(db, payload["claim_id"], tenant_id) if payload.get("claim_id") else None
    payment_date = payload.get("payment_date") or datetime.now(timezone.utc).date()

    header = {f: payload.get(f) for f in _REMITTANCE_FIELDS if payload.get(f) is not None}
    header["office_id"] = payload.get("office_id")

    allocated = Decimal("0")
    adjusted = Decimal("0")
    rows: list[LedgerInsuranceDetail] = []
    for index, raw in enumerate(lines):
        line = {**header, **{k: v for k, v in raw.items() if v is not None}}
        _reject_negative(line, line_index=index)
        # A line may only reference a procedure on this claim: a mis-typed id
        # would otherwise post the carrier's money against someone else's claim.
        procedure_id = line.get("procedure_id")
        if procedure_id and claim is not None:
            procedure = db.get(PatientProcedure, procedure_id)
            if procedure is None or procedure.claim_id != claim.id:
                raise ValidationError(
                    f"Procedure '{procedure_id}' is not on claim '{claim.id}'",
                    code="procedure_not_on_claim",
                    details={"line": index, "procedure_id": procedure_id},
                )
        allocated += _sum_fields(line, _PAID_FIELDS)
        adjusted += _sum_fields(line, _ADJUST_FIELDS)
        rows.append(_build_coverage_row(
            line, patient_id=patient_id, claim_id=payload.get("claim_id"),
            actor_id=actor_id, payment_date=payment_date,
        ))

    expected = payload.get("payment_amount")
    if expected is not None and Decimal(expected) != allocated:
        raise ValidationError(
            f"Allocated {allocated} does not reconcile with the payment amount {expected}",
            code="remittance_not_reconciled",
            details={
                "payment_amount": str(_money(expected)),
                "allocated": str(_money(allocated)),
                "unallocated": str(_money(Decimal(expected) - allocated)),
            },
        )

    for row in rows:
        db.add(row)

    result: dict = {"lines": rows, "allocated": allocated, "adjusted": adjusted, "claim": None}
    if claim is not None:
        db.flush()
        _apply_claim_write_off(claim, payload, adjusted)
        _recompute_claim_totals(db, claim)
        _mark_claim_paid(claim, allocated, payment_date)
        if payload.get("close_claim"):
            claim.status = "closed"
            claim.close_date = payment_date
            claim.is_active = False

    db.commit()
    for row in rows:
        db.refresh(row)
    if claim is not None:
        db.refresh(claim)
        result["claim"] = _claim_totals_out(claim)
    redis_store.cache_delete(f"balance:{tenant_id}:{patient_id}")
    return result


def _apply_claim_write_off(claim: InsuranceClaim, payload: dict, adjusted: Decimal) -> None:
    """INS-PAY-4: record what the user actually entered in "Enter Adjustment".

    The money itself stays on the lines — that is what the ledger reconciles
    against, and what the per-procedure ``*_ins_adjust`` columns already model.
    What was missing is the *intent*: once "10%" has been distributed as
    7.70 / 7.00 / 7.70 there is nothing left saying it was ever a 10% claim
    write-off. ``write_off_amount`` is the distributed total so a claim-level
    report does not have to re-sum the lines.
    """
    mode = payload.get("write_off_mode")
    value = payload.get("write_off_value")
    if mode is None and value is None:
        return
    if mode not in (None, "amount", "percent"):
        raise ValidationError(
            "write_off_mode must be 'amount' or 'percent'",
            code="invalid_write_off_mode", details={"write_off_mode": mode},
        )
    claim.write_off_mode = mode
    claim.write_off_value = Decimal(value) if value is not None else None
    claim.write_off_amount = adjusted


# ── INS-PAY-2: back a posted remittance out, with a trail ────────────────────
def reverse_insurance_payment(
    db: Session, detail_id: int, tenant_id: int, payload: dict, *, actor_id: int | None = None
) -> dict:
    """Void a posted coverage row and re-derive the claim.

    The only way to undo a mis-keyed remittance used to be ``DELETE``, which
    destroyed the evidence *and* left ``insurance_claims.total_paid`` holding
    money no row backed. This mirrors ``/patient-payments/{id}/reverse``: the row
    stays, marked void with a reason and an actor, and the claim's totals are
    recomputed from what is left.
    """
    detail = db.get(LedgerInsuranceDetail, detail_id)
    if detail is None:
        raise NotFoundError(f"LedgerInsuranceDetail '{detail_id}' was not found")
    _assert_patient_in_tenant(db, detail.patient_id, tenant_id)
    if detail.is_void:
        raise ConflictError(
            f"Insurance payment '{detail_id}' is already reversed", code="already_reversed"
        )

    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise ValidationError("A reversal reason is required", code="reason_required")

    reversed_amount = sum(
        (Decimal(getattr(detail, f) or 0) for f in _PAID_FIELDS), Decimal("0")
    )
    detail.is_void = True
    detail.void_reason = reason
    detail.voided_at = datetime.now(timezone.utc)
    detail.voided_by = actor_id
    # The recompute below is a SQL aggregate, so the void has to reach the
    # database before it runs — otherwise the claim is re-derived from a row set
    # that still counts this payment.
    db.flush()

    claim = db.get(InsuranceClaim, detail.claim_id) if detail.claim_id else None
    if claim is not None:
        _recompute_claim_totals(db, claim)
        # A claim nobody has paid should not still say "paid". Judged on the
        # recomputed total, so a migrated claim keeps its status on the strength
        # of its opening baseline.
        if claim.status == "paid" and Decimal(claim.total_paid or 0) <= 0:
            claim.status = "sent" if claim.submitted_date else "draft"
            claim.paid_date = None

    db.commit()
    db.refresh(detail)
    if claim is not None:
        db.refresh(claim)
    redis_store.cache_delete(f"balance:{tenant_id}:{detail.patient_id}")
    return {
        "id": detail.id,
        "claim_id": detail.claim_id,
        "reversed_amount": reversed_amount,
        "reason": reason,
        "voided_at": detail.voided_at,
        "claim": _claim_totals_out(claim) if claim is not None else None,
    }


# ── INS-PAY-2: every write to a coverage row re-derives its claim ────────────
class LedgerInsuranceDetailCRUD(CRUDBase[LedgerInsuranceDetail]):
    """Keep ``insurance_claims`` honest no matter which path wrote the row.

    The reported bug was that ``DELETE /ledger-insurance-details/{id}`` removed a
    posted remittance while the claim kept the money. Routing the reversal
    through ``/reverse`` fixes the *intended* path, but the generic CRUD routes
    are still there and are what an import or an older client uses — so they
    re-derive the claim too. Belt and braces on purpose: a claim asserting money
    no row backs is a number the practice chases the carrier with.

    DELETE is a **void**, not a removal (``soft_delete_field="is_void"``), so the
    evidence of a mis-keyed remittance survives its own correction.
    """

    def _sync_claim(self, db: Session, claim_id: str | None) -> None:
        if not claim_id:
            return
        claim = db.get(InsuranceClaim, claim_id)
        if claim is not None:
            _recompute_claim_totals(db, claim)

    def create(self, db: Session, data: dict, **kwargs) -> LedgerInsuranceDetail:  # noqa: ANN003
        obj = super().create(db, data, **kwargs)
        self._sync_claim(db, obj.claim_id)
        db.commit()
        db.refresh(obj)
        return obj

    def update(self, db: Session, obj_id, data: dict, **kwargs) -> LedgerInsuranceDetail:  # noqa: ANN001, ANN003
        existing = self.get(db, obj_id, tenant_id=kwargs.get("tenant_id"))
        # A row moved between claims leaves the old claim overstated unless that
        # one is recomputed as well.
        previous_claim_id = existing.claim_id
        obj = super().update(db, obj_id, data, **kwargs)
        self._sync_claim(db, previous_claim_id)
        if obj.claim_id != previous_claim_id:
            self._sync_claim(db, obj.claim_id)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj_id, *, tenant_id: int | None = None) -> None:  # noqa: ANN001
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        claim_id = existing.claim_id
        super().delete(db, obj_id, tenant_id=tenant_id)
        self._sync_claim(db, claim_id)
        db.commit()


# ── INS-PAY-7: every outstanding claim for a patient, with its roll-ups ───────
def _tier_sum(*columns):
    """``coalesce(a,0) + coalesce(b,0) + …`` — the per-tier columns summed into
    one figure, since a remittance may land on any tier."""
    total = func.coalesce(columns[0], 0)
    for column in columns[1:]:
        total = total + func.coalesce(column, 0)
    return total


def outstanding_claims(
    db: Session, patient_id: int, tenant_id: int, *,
    include_closed: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """The claim picker the Insurance Payment window needs.

    The window is opened *from* a claim, so it only ever showed that one. The
    legacy screen lists every outstanding claim with charges / est ins / ded used
    / ins paid / ins adj / remaining so the user can pick the claim the cheque
    actually pays. Those roll-ups live on two other tables, so building the
    picker client-side meant one ``/detail`` call per claim; this aggregates all
    of them in three statements regardless of claim count.
    """
    _assert_patient_in_tenant(db, patient_id, tenant_id)

    stmt = select(InsuranceClaim).where(InsuranceClaim.patient_id == patient_id)
    if not include_closed:
        # "Outstanding" = still chasing the carrier; a closed or denied claim is
        # not a candidate for a cheque.
        stmt = stmt.where(InsuranceClaim.status.notin_(("closed", "void", "denied")))
    if date_from is not None:
        stmt = stmt.where(InsuranceClaim.date_of_service_from >= date_from)
    if date_to is not None:
        stmt = stmt.where(InsuranceClaim.date_of_service_from <= date_to)
    claims = list(db.execute(
        stmt.order_by(InsuranceClaim.date_of_service_from.desc(), InsuranceClaim.id.desc())
    ).scalars().all())
    if not claims:
        return []

    claim_ids = [c.id for c in claims]
    charges = {
        row[0]: (Decimal(row[1]), Decimal(row[2]), int(row[3]))
        for row in db.execute(
            select(
                PatientProcedure.claim_id,
                func.coalesce(func.sum(PatientProcedure.fee), 0),
                func.coalesce(func.sum(PatientProcedure.insurance_estimate), 0),
                func.count(),
            )
            .where(
                PatientProcedure.claim_id.in_(claim_ids),
                PatientProcedure.is_void.is_(False),
            )
            .group_by(PatientProcedure.claim_id)
        ).all()
    }
    coverage = {
        row[0]: (Decimal(row[1]), Decimal(row[2]), Decimal(row[3]))
        for row in db.execute(
            select(
                LedgerInsuranceDetail.claim_id,
                func.coalesce(func.sum(_tier_sum(
                    LedgerInsuranceDetail.prim_ins_paid,
                    LedgerInsuranceDetail.sec_ins_paid,
                    LedgerInsuranceDetail.ter_ins_paid,
                )), 0),
                func.coalesce(func.sum(_tier_sum(
                    LedgerInsuranceDetail.prim_ins_adjust,
                    LedgerInsuranceDetail.sec_ins_adjust,
                    LedgerInsuranceDetail.ter_ins_adjust,
                )), 0),
                func.coalesce(func.sum(_tier_sum(
                    LedgerInsuranceDetail.prim_deductible,
                    LedgerInsuranceDetail.sec_deductible,
                    LedgerInsuranceDetail.ter_deductible,
                )), 0),
            )
            .where(
                LedgerInsuranceDetail.claim_id.in_(claim_ids),
                LedgerInsuranceDetail.is_void.is_(False),
            )
            .group_by(LedgerInsuranceDetail.claim_id)
        ).all()
    }
    carriers = {
        c.id: c.name
        for c in db.execute(
            select(InsuranceCarrier).where(
                InsuranceCarrier.id.in_({c.carrier_id for c in claims if c.carrier_id})
            )
        ).scalars()
    } if any(c.carrier_id for c in claims) else {}

    zero3 = (Decimal("0"), Decimal("0"), Decimal("0"))
    out = []
    for claim in claims:
        billed, estimated, line_count = charges.get(claim.id, (Decimal("0"), Decimal("0"), 0))
        paid, adjusted, deductible = coverage.get(claim.id, zero3)
        out.append({
            "claim_id": claim.id,
            "claim_number": claim.claim_number,
            "status": claim.status,
            "claim_type": claim.claim_type,
            "billing_order": claim.billing_order,
            "office_id": claim.office_id,
            "carrier_id": claim.carrier_id,
            "carrier_name": carriers.get(claim.carrier_id),
            "ins_plan_id": claim.ins_plan_id,
            "billing_provider_id": claim.billing_provider_id,
            "treating_provider_id": claim.treating_provider_id,
            "date_of_service_from": claim.date_of_service_from,
            "date_of_service_to": claim.date_of_service_to,
            "submitted_date": claim.submitted_date,
            "procedure_count": line_count,
            "total_charges": billed,
            "est_insurance": estimated,
            "deductible_used": deductible,
            "ins_paid": paid,
            "ins_adjusted": adjusted,
            # What the carrier is still expected to pay. Floored at zero: an
            # over-payment is a credit on the account, not a negative receivable.
            "remaining": max(estimated - paid - adjusted, Decimal("0")),
        })
    return out


# ── SVC-1: submit a claim ─────────────────────────────────────────────────────
def submit_claim(
    db: Session, claim_id: str, tenant_id: int, payload: dict, *, actor_id: int | None = None
) -> dict:
    """Submit (send) a claim: stamp sent_date + status, and create the
    ``claim_submissions`` record that returns the ``batch_id`` / send method."""
    claim = _get_claim(db, claim_id, tenant_id)
    sent_date = payload.get("sent_date") or datetime.now(timezone.utc).date()
    batch_id = payload.get("batch_id") or f"BATCH-{uuid7()}"
    is_preauth = bool(payload.get("is_preauth"))

    submission = ClaimSubmission(
        claim_id=claim_id,
        batch_id=batch_id,
        is_preauth=is_preauth,
        total_charges=claim.total_billed,
        submission_status="sent",
        created_by=actor_id,
    )
    db.add(submission)

    claim.status = "preauth_sent" if is_preauth else "sent"
    claim.submitted_date = sent_date
    # Mark this claim's procedures billed so they stop showing as unbilled.
    for proc in db.execute(
        select(PatientProcedure).where(
            PatientProcedure.claim_id == claim_id, PatientProcedure.is_void.is_(False)
        )
    ).scalars():
        proc.billing_status = "billed"

    db.commit()
    db.refresh(submission)
    return {
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "status": claim.status,
        "batch_id": batch_id,
        "sent_date": sent_date,
        "send_method": payload.get("send_method", "electronic"),
        "submission_id": submission.id,
    }


# ── AUD-3: claim status-change history ───────────────────────────────────────
def claim_status_history(db: Session, claim_id: str, tenant_id: int) -> dict:
    """Auditable timeline of a claim's status transitions, composed from the audit
    log (the middleware records every status/submit POST) plus the claim's own
    lifecycle dates as synthesised events."""
    claim = _get_claim(db, claim_id, tenant_id)

    logs = db.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "insurance-claims",
            AuditLog.resource_id == str(claim_id),
        ).order_by(AuditLog.created_at.asc())
    ).scalars().all()

    actor_ids = {log.user_id for log in logs if log.user_id is not None}
    names = resolve_user_names(db, actor_ids)

    events: list[dict] = []
    for log in logs:
        path = log.path or ""
        if path.endswith("/status") or path.endswith("/submit") or path.endswith("/recalculate"):
            method = "submit" if path.endswith("/submit") else "status_change"
            events.append({
                "status": None,
                "changed_at": log.created_at.isoformat() if log.created_at else None,
                "changed_by": log.user_id,
                "changed_by_name": names.get(log.user_id),
                "method": method,
                "source": "audit_log",
            })

    # Synthesised lifecycle events from the claim's own date columns.
    for label, when in (
        ("submitted", claim.submitted_date), ("paid", claim.paid_date), ("closed", claim.close_date)
    ):
        if when is not None:
            events.append({
                "status": label, "changed_at": when.isoformat() if hasattr(when, "isoformat") else str(when),
                "changed_by": None, "changed_by_name": None, "method": None, "source": "claim_field",
            })

    events.sort(key=lambda e: e["changed_at"] or "")
    return {
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "current_status": claim.status,
        "events": events,
    }


# ── CHG-8: patient insurance summary (carrier names by rank) ─────────────────
_RANK_ORDER = ["primary", "secondary", "tertiary", "quaternary"]


def patient_insurance_summary(db: Session, patient_id: int, tenant_id: int) -> dict:
    _assert_patient_in_tenant(db, patient_id, tenant_id)
    slots = db.execute(
        select(PatientInsurance).where(
            PatientInsurance.patient_id == patient_id, PatientInsurance.is_active.is_(True)
        )
    ).scalars().all()

    plan_ids = {s.ins_plan_id for s in slots if s.ins_plan_id}
    plans = {p.id: p for p in db.execute(
        select(InsurancePlan).where(InsurancePlan.id.in_(plan_ids))
    ).scalars()} if plan_ids else {}
    carrier_ids = {p.carrier_id for p in plans.values() if p.carrier_id}
    carriers = {c.id: c.name for c in db.execute(
        select(InsuranceCarrier).where(InsuranceCarrier.id.in_(carrier_ids))
    ).scalars()} if carrier_ids else {}

    def _rank_of(slot: PatientInsurance) -> str:
        return (slot.insurance_type or "").lower() or "primary"

    ranked: list[dict] = []
    for slot in slots:
        plan = plans.get(slot.ins_plan_id)
        ranked.append({
            "rank": _rank_of(slot),
            "ins_plan_id": slot.ins_plan_id,
            "carrier_id": plan.carrier_id if plan else None,
            "carrier_name": carriers.get(plan.carrier_id) if plan else None,
            "group_number": plan.group_number if plan else None,
            "is_active": slot.is_active,
        })
    ranked.sort(key=lambda r: _RANK_ORDER.index(r["rank"]) if r["rank"] in _RANK_ORDER else 99)

    by_rank = {r["rank"]: r for r in ranked}
    return {
        "patient_id": patient_id,
        "primary": by_rank.get("primary"),
        "secondary": by_rank.get("secondary"),
        "plans": ranked,
    }


# ── CHG-9: today's appointment for the check-out flow ────────────────────────
def todays_appointment(db: Session, patient_id: int, tenant_id: int) -> dict:
    _assert_patient_in_tenant(db, patient_id, tenant_id)
    today = datetime.now(timezone.utc).date()
    appt = db.execute(
        select(Appointment).where(
            Appointment.patient_id == patient_id,
            Appointment.date == today,
            Appointment.is_archived.is_(False),
        ).order_by(Appointment.start_time.asc())
    ).scalars().first()
    if appt is None:
        return {"patient_id": patient_id, "has_appointment": False}
    return {
        "patient_id": patient_id,
        "appointment_id": appt.id,
        "appt_date": appt.date,
        "start_time": appt.start_time.isoformat() if appt.start_time else None,
        "status": appt.status,
        "provider_id": appt.provider_id,
        "operatory_id": appt.operatory_id,
        "has_appointment": True,
    }


# ── CHG-4: expand an explosion code into its procedures ──────────────────────
def expand_explosion_code(
    db: Session, code: str, tenant_id: int, *, office_id: int | None = None
) -> dict:
    stmt = select(ExplosionCode).where(
        ExplosionCode.tenant_id == tenant_id,
        ExplosionCode.code == code,
        ExplosionCode.is_active.is_(True),
    )
    rows = db.execute(stmt).scalars().all()
    # Prefer an office-specific definition, else a tenant-wide (office_id NULL) one.
    header = next((r for r in rows if r.office_id == office_id), None) or next(
        (r for r in rows if r.office_id is None), None
    ) or (rows[0] if rows else None)
    if header is None:
        raise NotFoundError(f"Explosion code '{code}' was not found")

    items = db.execute(
        select(ExplosionCodeItem).where(
            ExplosionCodeItem.explosion_code_id == header.id
        ).order_by(ExplosionCodeItem.display_order.asc(), ExplosionCodeItem.id.asc())
    ).scalars().all()

    proc_codes = {i.procedure_code for i in items}
    descs = {p.code: (p.description, p.default_fee) for p in db.execute(
        select(ProcedureCode).where(ProcedureCode.code.in_(proc_codes))
    ).scalars()} if proc_codes else {}

    procedures = []
    for item in items:
        desc, default_fee = descs.get(item.procedure_code, (None, None))
        procedures.append({
            "procedure_code": item.procedure_code,
            "description": desc,
            "default_fee": item.default_fee if item.default_fee is not None else default_fee,
            "tooth": item.tooth,
            "surface": item.surface,
            "display_order": item.display_order,
        })
    return {
        "explosion_code": header.code,
        "description": header.description,
        "procedures": procedures,
    }
