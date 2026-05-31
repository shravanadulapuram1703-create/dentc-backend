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

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import Patient, PatientPayment, PatientProcedure
from app.integrations import redis_store

_CACHE_TTL = 30


def _cache_key(tenant_id: int, patient_id: int) -> str:
    return f"balance:{tenant_id}:{patient_id}"


def _f(value) -> float:  # noqa: ANN001
    return float(value or 0)


def _aging(db: Session, patient_id: int, today: date) -> dict[str, float]:
    """Bucket gross procedure charges by age of date_of_service (Option A)."""
    d30, d60, d90, d120 = (today - timedelta(days=n) for n in (30, 60, 90, 120))
    bucket = case(
        (PatientProcedure.date_of_service >= d30, "current"),
        (PatientProcedure.date_of_service >= d60, "b30"),
        (PatientProcedure.date_of_service >= d90, "b60"),
        (PatientProcedure.date_of_service >= d120, "b90"),
        else_="b120",
    ).label("bucket")
    rows = db.execute(
        select(bucket, func.coalesce(func.sum(PatientProcedure.fee), 0))
        .where(
            PatientProcedure.patient_id == patient_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
        )
        .group_by(bucket)
    ).all()
    out = {"current": 0.0, "b30": 0.0, "b60": 0.0, "b90": 0.0, "b120": 0.0}
    for name, total in rows:
        out[name] = _f(total)
    return out


def _recent_activity(db: Session, patient_id: int, today: date) -> dict:
    base = (PatientPayment.patient_id == patient_id, PatientPayment.is_void.is_(False))
    today_total = db.execute(
        select(func.coalesce(func.sum(PatientPayment.amount), 0)).where(
            *base, PatientPayment.payment_date == today
        )
    ).scalar_one()
    is_ins = or_(
        PatientPayment.payment_type.ilike("ins%"),
        PatientPayment.payment_type.ilike("%insurance%"),
    )
    last_ins = db.execute(
        select(func.max(PatientPayment.payment_date)).where(*base, is_ins)
    ).scalar_one()
    last_pat = db.execute(
        select(func.max(PatientPayment.payment_date)).where(*base, ~is_ins)
    ).scalar_one()
    return {
        "today": _f(today_total),
        "last_ins": last_ins.isoformat() if last_ins else None,
        "last_pat": last_pat.isoformat() if last_pat else None,
    }


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

    charged, est_ins, est_pat = db.execute(
        select(
            func.coalesce(func.sum(PatientProcedure.fee), 0),
            func.coalesce(func.sum(PatientProcedure.insurance_estimate), 0),
            func.coalesce(func.sum(PatientProcedure.patient_estimate), 0),
        ).where(
            PatientProcedure.patient_id == patient_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
        )
    ).one()

    paid = db.execute(
        select(func.coalesce(func.sum(PatientPayment.amount), 0)).where(
            PatientPayment.patient_id == patient_id,
            PatientPayment.is_void.is_(False),
        )
    ).scalar_one()

    balance = Decimal(charged) - Decimal(paid)
    patient_responsible = Decimal(charged) - Decimal(paid) - Decimal(est_ins)

    result = {
        "patient_id": patient_id,
        # existing fields (unchanged contract)
        "total_charged": _f(charged),
        "total_paid": _f(paid),
        "balance": _f(balance),
        # C-3 additive fields
        "account_balance": _f(balance),
        "estimated_insurance": _f(est_ins),
        "estimated_patient": _f(est_pat),
        "patient_balance": _f(patient_responsible),
        "aging": _aging(db, patient_id, today),
        "recent_activity": _recent_activity(db, patient_id, today),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    redis_store.cache_set(_cache_key(tenant_id, patient_id), json.dumps(result), _CACHE_TTL)
    return result
