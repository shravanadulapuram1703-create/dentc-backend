"""Refunds & reversals (REF-1..4).

The module had no refund concept at all — the only workaround was an unvalidated
negative payment. This service makes a refund a first-class, auditable record:

* **REF-1** ``process_refund`` — validate the amount against the refundable
  credit and the refund policy, write a ``patient_refunds`` row, invalidate the
  cached balance and return the recomputed balance.
* **REF-2** ``reverse_payment`` / ``reverse_adjustment`` — void the source row
  posted in error and (optionally) issue a matching refund, so the balance
  recalculates and the action is captured with a reason + authoriser.
* **REF-3** ``refundable_balance`` — the unapplied-credit / refundable amount.
* **REF-4** ``refund_policy`` — the per-amount authorisation thresholds.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.db.models import (
    OfficeAdvancedSettings,
    Patient,
    PatientAdjustment,
    PatientPayment,
    PatientRefund,
    PaymentAllocation,
)
from app.integrations import redis_store
from app.services import balance_service
from app.services.user_admin_service import resolve_user_names

_ZERO = Decimal("0")
_APPROVER_ROLES = ["admin", "super_admin"]
_DEFAULT_APPROVAL_THRESHOLD = Decimal("500.00")


def _d(value) -> Decimal:  # noqa: ANN001
    return Decimal(value or 0)


def _get_patient(db: Session, patient_id: int, tenant_id: int) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


def _invalidate(tenant_id: int, patient_id: int) -> None:
    redis_store.cache_delete(f"balance:{tenant_id}:{patient_id}")


def _today() -> date:
    return datetime.now(timezone.utc).date()


# ── REF-4: policy ─────────────────────────────────────────────────────────────
def refund_policy(db: Session, tenant_id: int, office_id: int | None = None) -> dict:
    """Thresholds a refund POST is validated against. Configurable via the office
    advanced settings ``min_charge`` seat is not reused — a dedicated threshold is
    not modelled, so a sensible tenant default is returned (overridable later)."""
    threshold = _DEFAULT_APPROVAL_THRESHOLD
    if office_id is not None:
        settings = db.execute(
            select(OfficeAdvancedSettings).where(OfficeAdvancedSettings.office_id == office_id)
        ).scalar_one_or_none()
        # A practice can repurpose min_balance as a refund-approval ceiling; if unset
        # the tenant default stands.
        if settings and settings.min_balance is not None and settings.min_balance > _ZERO:
            threshold = _d(settings.min_balance)
    return {
        "manager_approval_threshold": threshold,
        "max_refund_without_source": threshold,
        "allow_over_credit": False,
        "approver_roles": list(_APPROVER_ROLES),
    }


# ── REF-3: refundable balance ─────────────────────────────────────────────────
def refundable_balance(db: Session, patient_id: int, tenant_id: int) -> dict:
    _get_patient(db, patient_id, tenant_id)
    balance = balance_service.get_patient_balance(db, patient_id, tenant_id)
    account_balance = _d(balance["account_balance"])
    credit = -account_balance if account_balance < _ZERO else _ZERO

    paid = db.execute(
        select(func.coalesce(func.sum(PatientPayment.amount), 0)).where(
            PatientPayment.patient_id == patient_id, PatientPayment.is_void.is_(False)
        )
    ).scalar_one()
    allocated = db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
            PaymentAllocation.patient_id == patient_id
        )
    ).scalar_one()
    unallocated = _d(paid) - _d(allocated)
    if unallocated < _ZERO:
        unallocated = _ZERO

    return {
        "patient_id": patient_id,
        "account_balance": account_balance,
        "credit_balance": credit,
        "unallocated_payments": unallocated,
        "refundable_amount": credit,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


# ── REF-1: process a refund ──────────────────────────────────────────────────
def process_refund(
    db: Session,
    patient_id: int,
    tenant_id: int,
    payload: dict,
    *,
    actor_id: int | None = None,
    actor_role: str | None = None,
) -> dict:
    patient = _get_patient(db, patient_id, tenant_id)
    amount = _d(payload.get("refund_amount"))
    if amount <= _ZERO:
        raise ValidationError("Refund amount must be greater than zero")

    source_payment_id = payload.get("source_payment_id")
    if source_payment_id is not None:
        source = db.get(PatientPayment, source_payment_id)
        if source is None or source.patient_id != patient_id:
            raise ValidationError("source_payment_id does not belong to this patient")

    # REF-4: enforce the authorisation policy.
    policy = refund_policy(db, tenant_id, payload.get("office_id"))
    _enforce_policy(policy, amount, actor_role, has_source=source_payment_id is not None)

    # REF-3 guard: don't refund more than the refundable credit unless a source
    # payment is cited (a same-day duplicate may not have hit the balance yet).
    if source_payment_id is None and not policy["allow_over_credit"]:
        refundable = _d(refundable_balance(db, patient_id, tenant_id)["refundable_amount"])
        if amount > refundable:
            raise ValidationError(
                "Refund exceeds the refundable credit balance",
                details={"refundable_amount": str(refundable), "requested": str(amount)},
            )

    refund = PatientRefund(
        tenant_id=tenant_id,
        patient_id=patient_id,
        office_id=payload.get("office_id") or patient.home_office_id,
        refund_date=payload.get("refund_date") or _today(),
        amount=amount,
        refund_method=payload.get("refund_method"),
        reason=payload.get("reason"),
        reason_code=payload.get("reason_code"),
        source_payment_id=source_payment_id,
        check_number=payload.get("check_number"),
        reference_number=payload.get("reference_number"),
        authorized_by=payload.get("authorized_by") or actor_id,
        notes=payload.get("notes"),
        created_by=actor_id,
    )
    db.add(refund)
    db.commit()
    db.refresh(refund)
    _invalidate(tenant_id, patient_id)

    return {
        "refund": _refund_out(db, refund),
        "balance": balance_service.get_patient_balance(db, patient_id, tenant_id),
    }


def _enforce_policy(policy: dict, amount: Decimal, actor_role: str | None, *, has_source: bool) -> None:
    if not has_source and amount > _d(policy["max_refund_without_source"]):
        if actor_role not in policy["approver_roles"]:
            raise ValidationError(
                "Refund exceeds the limit for a refund without a source payment; "
                "manager approval is required",
                details={"threshold": str(policy["max_refund_without_source"])},
            )
    if amount > _d(policy["manager_approval_threshold"]) and actor_role not in policy["approver_roles"]:
        raise ValidationError(
            "Refund exceeds the manager-approval threshold",
            details={"threshold": str(policy["manager_approval_threshold"])},
        )


# ── REF-2: reverse a payment / adjustment ────────────────────────────────────
def reverse_payment(
    db: Session, payment_id: str, tenant_id: int, payload: dict, *, actor_id: int | None = None,
) -> dict:
    payment = db.get(PatientPayment, payment_id)
    if payment is None:
        raise NotFoundError(f"PatientPayment '{payment_id}' was not found")
    _get_patient(db, payment.patient_id, tenant_id)
    if payment.is_void:
        raise ConflictError(f"Payment '{payment_id}' is already voided")

    reason = payload["reason"]
    payment.is_void = True
    payment.notes = f"{payment.notes or ''}\n[REVERSED] {reason}".strip()

    refund_out = None
    if payload.get("refund_method"):
        refund = PatientRefund(
            tenant_id=tenant_id, patient_id=payment.patient_id, office_id=payment.office_id,
            refund_date=_today(), amount=_d(payment.amount),
            refund_method=payload["refund_method"], reason=reason, reason_code="reversal",
            source_payment_id=payment_id, reversed_type="payment", reversed_id=payment_id,
            authorized_by=payload.get("authorized_by") or actor_id, created_by=actor_id,
        )
        db.add(refund)

    db.commit()
    _invalidate(tenant_id, payment.patient_id)
    if payload.get("refund_method"):
        db.refresh(refund)
        refund_out = _refund_out(db, refund)

    return {
        "reversed_type": "payment", "reversed_id": payment_id, "reason": reason,
        "refund": refund_out,
        "balance": balance_service.get_patient_balance(db, payment.patient_id, tenant_id),
    }


def reverse_adjustment(
    db: Session, adjustment_id: int, tenant_id: int, payload: dict, *, actor_id: int | None = None,
) -> dict:
    adj = db.execute(
        select(PatientAdjustment).where(
            PatientAdjustment.id == adjustment_id, PatientAdjustment.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if adj is None:
        raise NotFoundError(f"PatientAdjustment '{adjustment_id}' was not found")
    if adj.is_void:
        raise ConflictError(f"Adjustment '{adjustment_id}' is already voided")

    reason = payload["reason"]
    adj.is_void = True
    adj.notes = f"{adj.notes or ''}\n[REVERSED] {reason}".strip()
    db.commit()
    _invalidate(tenant_id, adj.patient_id)

    return {
        "reversed_type": "adjustment", "reversed_id": str(adjustment_id), "reason": reason,
        "refund": None,
        "balance": balance_service.get_patient_balance(db, adj.patient_id, tenant_id),
    }


# ── listing / serialisation ──────────────────────────────────────────────────
def list_refunds(
    db: Session, patient_id: int, tenant_id: int, *, page: int = 1, size: int = 50,
) -> tuple[list[dict], int]:
    _get_patient(db, patient_id, tenant_id)
    base = select(PatientRefund).where(
        PatientRefund.patient_id == patient_id, PatientRefund.tenant_id == tenant_id
    )
    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    rows = db.execute(
        base.order_by(PatientRefund.refund_date.desc(), PatientRefund.id.desc())
        .offset((page - 1) * size).limit(size)
    ).scalars().all()
    return [_refund_out(db, r) for r in rows], total


def _refund_out(db: Session, refund: PatientRefund) -> dict:
    names = resolve_user_names(
        db, {refund.authorized_by} if refund.authorized_by is not None else set()
    )
    return {
        "id": refund.id,
        "patient_id": refund.patient_id,
        "office_id": refund.office_id,
        "refund_date": refund.refund_date,
        "amount": refund.amount,
        "refund_method": refund.refund_method,
        "reason": refund.reason,
        "reason_code": refund.reason_code,
        "source_payment_id": refund.source_payment_id,
        "reversed_type": refund.reversed_type,
        "reversed_id": refund.reversed_id,
        "check_number": refund.check_number,
        "reference_number": refund.reference_number,
        "authorized_by": refund.authorized_by,
        "authorized_by_name": names.get(refund.authorized_by),
        "notes": refund.notes,
        "is_void": refund.is_void,
    }
