"""Patient account-balance computation with a short-lived Redis cache.

Balance = (non-void charges) − (non-void payments). The migrated schema has no
materialised balance column, so we aggregate on read and cache the result for a
few seconds to absorb dashboard bursts. Tenancy is verified via the patient row.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import Patient, PatientPayment, PatientProcedure
from app.integrations import redis_store

_CACHE_TTL = 30


def _cache_key(tenant_id: int, patient_id: int) -> str:
    return f"balance:{tenant_id}:{patient_id}"


def get_patient_balance(db: Session, patient_id: int, tenant_id: int) -> dict:
    cached = redis_store.cache_get(_cache_key(tenant_id, patient_id))
    if cached:
        return json.loads(cached)

    patient = db.execute(
        select(Patient.id).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")

    charged = db.execute(
        select(func.coalesce(func.sum(PatientProcedure.fee), 0)).where(
            PatientProcedure.patient_id == patient_id,
            PatientProcedure.is_void.is_(False),
        )
    ).scalar_one() or Decimal(0)

    paid = db.execute(
        select(func.coalesce(func.sum(PatientPayment.amount), 0)).where(
            PatientPayment.patient_id == patient_id,
            PatientPayment.is_void.is_(False),
        )
    ).scalar_one() or Decimal(0)

    result = {
        "patient_id": patient_id,
        "total_charged": float(charged),
        "total_paid": float(paid),
        "balance": float(Decimal(charged) - Decimal(paid)),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    redis_store.cache_set(_cache_key(tenant_id, patient_id), json.dumps(result), _CACHE_TTL)
    return result
