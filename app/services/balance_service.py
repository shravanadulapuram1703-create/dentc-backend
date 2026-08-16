"""Patient account-balance computation with a short-lived Redis cache.

Balance = (non-void charges) − (non-void payments), aggregated on read (the
migrated schema has no materialised balance column) and cached briefly. Phase 3
(C-3) enriches the response with insurance/patient estimate splits, aging
buckets, and recent-activity — all additive, computed from existing columns, no
schema change. Tenancy is verified via the patient row.

Caveats honoured per the implementation plan:
- Excludes ``is_void`` AND ``is_archived`` rows (the original code ignored archive).
- ``payment_type`` insurance/patient classification is best-effort (values vary by
  source); insurance = payment_type matching 'ins%'/'%insurance%', else patient.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import (
    Patient,
    PatientOpeningBalance,
    PatientPayment,
    PatientProcedure,
    PatientRefund,
)
from app.integrations import redis_store

_CACHE_TTL = 30

# Opening-balance aging column -> balance aging bucket (GAP-AP-12).
_OPENING_BUCKETS = {
    "current": "current", "over_30": "b30", "over_60": "b60",
    "over_90": "b90", "over_120": "b120",
}


def _cache_key(tenant_id: int, patient_id: int) -> str:
    return f"balance:{tenant_id}:{patient_id}"


def _f(value) -> float:  # noqa: ANN001
    return float(value or 0)


def _charges(
    db: Session, patient_id: int, today: date
) -> tuple[Decimal, Decimal, Decimal, Decimal, dict[str, float]]:
    """One pass over ``patient_procedures``: totals, today's charges and aging.

    PP-5: this used to be three separate full scans of the patient's procedure
    history (totals, today, aging). Conditional aggregation collapses them into a
    single scan, which — with ``ix_patient_procedures_patient_dos`` — is what
    takes the cold aggregate off the tens-of-seconds path.
    """
    d30, d60, d90, d120 = (today - timedelta(days=n) for n in (30, 60, 90, 120))

    def _sum_where(clause):  # noqa: ANN001, ANN202
        return func.coalesce(func.sum(case((clause, PatientProcedure.fee), else_=0)), 0)

    def _bucket_sum(lo: date | None, hi: date | None):  # noqa: ANN202
        cond = []
        if lo is not None:
            cond.append(PatientProcedure.date_of_service >= lo)
        if hi is not None:
            cond.append(PatientProcedure.date_of_service < hi)
        return _sum_where(and_(*cond) if len(cond) > 1 else cond[0])

    charged, est_ins, est_pat, today_charges, current, b30, b60, b90, b120 = db.execute(
        select(
            func.coalesce(func.sum(PatientProcedure.fee), 0),
            func.coalesce(func.sum(PatientProcedure.insurance_estimate), 0),
            func.coalesce(func.sum(PatientProcedure.patient_estimate), 0),
            _sum_where(PatientProcedure.date_of_service == today),
            _bucket_sum(d30, None),
            _bucket_sum(d60, d30),
            _bucket_sum(d90, d60),
            _bucket_sum(d120, d90),
            _bucket_sum(None, d120),
        ).where(
            PatientProcedure.patient_id == patient_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
        )
    ).one()

    aging = {
        "current": _f(current), "b30": _f(b30), "b60": _f(b60),
        "b90": _f(b90), "b120": _f(b120),
    }
    return (
        Decimal(charged), Decimal(est_ins), Decimal(est_pat), Decimal(today_charges), aging,
    )


def _opening(db: Session, patient_id: int) -> dict[str, float]:
    """GAP-AP-12: this patient's opening A/R aging buckets (0.0 if none seeded)."""
    row = db.execute(
        select(PatientOpeningBalance).where(PatientOpeningBalance.patient_id == patient_id)
    ).scalar_one_or_none()
    if row is None:
        return {col: 0.0 for col in _OPENING_BUCKETS}
    return {col: _f(getattr(row, col)) for col in _OPENING_BUCKETS}


def _payments(db: Session, patient_id: int, today: date) -> tuple[Decimal, dict]:
    """One pass over ``patient_payments``: total paid + the recent-activity block.

    PP-5: the total, today's total and the two "most recent payment" probes were
    four separate statements; the rows are few enough per patient that reading
    them once and reducing in Python beats four round trips (and the two ORDER
    BY … LIMIT 1 probes could not use an index before this change).
    """
    rows = db.execute(
        select(
            PatientPayment.payment_date,
            PatientPayment.amount,
            PatientPayment.payment_type,
            PatientPayment.id,
        ).where(
            PatientPayment.patient_id == patient_id,
            PatientPayment.is_void.is_(False),
        )
    ).all()

    total = Decimal(0)
    today_total = Decimal(0)
    last: dict[str, tuple] = {}
    for pay_date, amount, pay_type, pay_id in rows:
        value = Decimal(amount or 0)
        total += value
        if pay_date == today:
            today_total += value
        kind = "ins" if (pay_type or "").lower().startswith("ins") or "insurance" in (
            pay_type or ""
        ).lower() else "pat"
        key = (pay_date or date.min, str(pay_id))
        if kind not in last or key > last[kind][0]:
            last[kind] = (key, pay_date, value)

    def _out(kind: str) -> tuple:
        entry = last.get(kind)
        return (entry[1], entry[2]) if entry else (None, None)

    last_ins_date, last_ins_amt = _out("ins")
    last_pat_date, last_pat_amt = _out("pat")
    return total, {
        "today": _f(today_total),
        "last_ins": last_ins_date.isoformat() if last_ins_date else None,
        "last_pat": last_pat_date.isoformat() if last_pat_date else None,
        # Patients gap: amounts alongside dates.
        "last_ins_amount": _f(last_ins_amt),
        "last_pat_amount": _f(last_pat_amt),
    }


def _refunds_total(db: Session, patient_id: int) -> Decimal:
    """REF-1: sum of non-void refunds. A refund returns a credit to the patient, so
    it *increases* the account balance (``balance += refund``)."""
    total = db.execute(
        select(func.coalesce(func.sum(PatientRefund.amount), 0)).where(
            PatientRefund.patient_id == patient_id,
            PatientRefund.is_void.is_(False),
        )
    ).scalar_one()
    return Decimal(total or 0)


def get_patient_balance(db: Session, patient_id: int, tenant_id: int) -> dict:
    cached = redis_store.cache_get(_cache_key(tenant_id, patient_id))
    if cached:
        return json.loads(cached)

    patient = db.execute(
        select(Patient.id).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")

    today = datetime.now(timezone.utc).date()

    # PP-5: two scans total (procedures + payments) instead of six statements.
    charged, est_ins, est_pat, today_charges, aging = _charges(db, patient_id, today)
    paid, recent = _payments(db, patient_id, today)
    refunded = _refunds_total(db, patient_id)

    # GAP-AP-12: fold seeded opening A/R into charges, balance and aging.
    opening = _opening(db, patient_id)
    opening_total = Decimal(str(sum(opening.values())))
    charged_total = charged + opening_total

    # REF-1: a refund undoes a credit — net payments are payments − refunds.
    net_paid = paid - refunded
    balance = charged_total - net_paid
    patient_responsible = charged_total - net_paid - est_ins

    for src_col, bucket in _OPENING_BUCKETS.items():
        aging[bucket] = round(aging[bucket] + opening[src_col], 2)

    result = {
        "patient_id": patient_id,
        # existing fields (unchanged contract)
        "total_charged": _f(charged_total),
        "total_paid": _f(paid),
        "balance": _f(balance),
        # C-3 additive fields
        "account_balance": _f(balance),
        "estimated_insurance": _f(est_ins),
        "estimated_patient": _f(est_pat),
        "patient_balance": _f(patient_responsible),
        # Patients gap: outstanding expected-insurance portion + today's charges.
        "insurance_balance": _f(est_ins),
        "today_charges": _f(today_charges),
        # GAP-AP-12: seeded opening A/R total (already included in balance/aging above).
        "opening_balance": _f(opening_total),
        # REF-1/3: refunds issued + the refundable credit (a negative balance).
        "total_refunded": _f(refunded),
        "credit_balance": _f(-balance if balance < 0 else Decimal(0)),
        "aging": aging,
        "recent_activity": recent,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    redis_store.cache_set(_cache_key(tenant_id, patient_id), json.dumps(result), _CACHE_TTL)
    return result
