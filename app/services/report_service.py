"""Practice-wide reporting aggregation (Reports module, FE dev-report gaps 1/2/3).

Server-side roll-ups over a tenant (optionally scoped to one office) so the
Reports frontend stops fanning out CRUD list endpoints (which truncate for large
practices). Results are briefly Redis-cached, mirroring ``balance_service``.

Tenancy: the financial child tables (``patient_procedures``, ``patient_payments``,
``insurance_claims``, ``appointments``) carry no ``tenant_id`` — every query joins
``patients`` and filters ``patients.tenant_id``. Appointments are scoped the same
way (real appointments always have a ``patient_id``; blocked slots are excluded).

Portability: aggregation groups by the raw ``DATE`` columns (and ``CAST(... AS
DATE)`` for ``created_at``) and buckets weeks/months in Python — no Postgres-only
``date_trunc`` — so the SQLite-backed test suite exercises the same code path.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.services.ledger_sign import sum_payment_credit

from app.db.models import (
    Appointment,
    InsuranceClaim,
    InsuranceSubscriber,
    Patient,
    PatientAdjustment,
    PatientPayment,
    PatientProcedure,
)
from app.integrations import redis_store

_CACHE_TTL = 60

# Claim statuses considered SETTLED (no longer an open insurance receivable).
# Free-form in the schema (FE gap 5) — matched case-insensitively here; this is
# the canonical vocabulary documented back to the FE team. Anything not in this
# set with a positive (billed − paid) remainder counts as outstanding.
_CLAIM_SETTLED = {"paid", "closed", "denied", "rejected", "void", "voided", "cancelled", "canceled"}

# Subscriber elig_status values considered VERIFIED (INS-11). Everything else
# (incl. NULL/blank/"unknown"/"pending") counts as a pending verification.
_ELIG_VERIFIED = {"verified", "active", "confirmed", "eligible"}


def _f(value) -> float:  # noqa: ANN001
    return float(value or 0)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _cache_key(prefix: str, tenant_id: int, office_id: int | None, *parts: object) -> str:
    tail = ":".join(str(p) for p in parts)
    return f"report:{prefix}:{tenant_id}:{office_id or 'all'}:{tail}"


# ── production / collections ────────────────────────────────────────────────
def _production(db: Session, tenant_id: int, office_id: int | None,
                date_from: date, date_to: date) -> float:
    stmt = (
        select(func.coalesce(func.sum(PatientProcedure.fee), 0))
        .join(Patient, Patient.id == PatientProcedure.patient_id)
        .where(
            Patient.tenant_id == tenant_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
            PatientProcedure.date_of_service >= date_from,
            PatientProcedure.date_of_service <= date_to,
        )
    )
    if office_id is not None:
        stmt = stmt.where(PatientProcedure.office_id == office_id)
    return _f(db.execute(stmt).scalar_one())


def _collections(db: Session, tenant_id: int, office_id: int | None,
                 date_from: date, date_to: date) -> float:
    stmt = (
        # AL-9: collections are the rows' credits, not their raw signed amounts.
        select(sum_payment_credit())
        .join(Patient, Patient.id == PatientPayment.patient_id)
        .where(
            Patient.tenant_id == tenant_id,
            PatientPayment.is_void.is_(False),
            PatientPayment.payment_date >= date_from,
            PatientPayment.payment_date <= date_to,
        )
    )
    if office_id is not None:
        stmt = stmt.where(PatientPayment.office_id == office_id)
    return _f(db.execute(stmt).scalar_one())


def _new_patients(db: Session, tenant_id: int, office_id: int | None,
                  date_from: date, date_to: date) -> int:
    # ``created_at`` is a DateTime; compare against the half-open day range
    # [date_from 00:00, date_to+1 00:00) rather than CAST(... AS DATE) — the cast
    # is Postgres-correct but mis-parses under SQLite's NUMERIC date affinity.
    upper = date_to + timedelta(days=1)
    stmt = select(func.count(Patient.id)).where(
        Patient.tenant_id == tenant_id,
        Patient.created_at >= date_from,
        Patient.created_at < upper,
    )
    if office_id is not None:
        stmt = stmt.where(Patient.home_office_id == office_id)
    return int(db.execute(stmt).scalar_one() or 0)


def _active_patients(db: Session, tenant_id: int, office_id: int | None) -> int:
    stmt = select(func.count(Patient.id)).where(
        Patient.tenant_id == tenant_id,
        Patient.is_active.is_(True),
    )
    if office_id is not None:
        stmt = stmt.where(Patient.home_office_id == office_id)
    return int(db.execute(stmt).scalar_one() or 0)


def _scheduled_appointments(db: Session, tenant_id: int, office_id: int | None,
                            date_from: date, date_to: date) -> int:
    stmt = (
        select(func.count(Appointment.id))
        .join(Patient, Patient.id == Appointment.patient_id)
        .where(
            Patient.tenant_id == tenant_id,
            Appointment.date >= date_from,
            Appointment.date <= date_to,
            Appointment.is_cancelled.is_(False),
            Appointment.is_blocked.is_(False),
            Appointment.is_archived.is_(False),
        )
    )
    if office_id is not None:
        stmt = stmt.where(Appointment.office_id == office_id)
    return int(db.execute(stmt).scalar_one() or 0)


def _insurance_receivables(db: Session, tenant_id: int, office_id: int | None) -> float:
    """Σ max(total_billed − total_paid, 0) over active, non-settled claims."""
    remainder = func.coalesce(InsuranceClaim.total_billed, 0) - func.coalesce(
        InsuranceClaim.total_paid, 0
    )
    stmt = (
        select(InsuranceClaim.status, func.coalesce(func.sum(remainder), 0))
        .join(Patient, Patient.id == InsuranceClaim.patient_id)
        .where(
            Patient.tenant_id == tenant_id,
            InsuranceClaim.is_active.is_(True),
        )
        .group_by(InsuranceClaim.status)
    )
    if office_id is not None:
        stmt = stmt.where(InsuranceClaim.office_id == office_id)
    total = 0.0
    for status, amount in db.execute(stmt).all():
        if (status or "").strip().lower() in _CLAIM_SETTLED:
            continue
        total += max(_f(amount), 0.0)
    return total


# ── accounts receivable (cumulative, point-in-time) ─────────────────────────
def _ar_components(db: Session, tenant_id: int, office_id: int | None,
                   as_of: date) -> tuple[float, float, float]:
    """Return (charged, est_insurance, paid_plus_adjustments) ≤ as_of."""
    proc_stmt = (
        select(
            func.coalesce(func.sum(PatientProcedure.fee), 0),
            func.coalesce(func.sum(PatientProcedure.insurance_estimate), 0),
        )
        .join(Patient, Patient.id == PatientProcedure.patient_id)
        .where(
            Patient.tenant_id == tenant_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
            PatientProcedure.date_of_service <= as_of,
        )
    )
    pay_stmt = (
        select(sum_payment_credit())  # AL-9
        .join(Patient, Patient.id == PatientPayment.patient_id)
        .where(
            Patient.tenant_id == tenant_id,
            PatientPayment.is_void.is_(False),
            PatientPayment.payment_date <= as_of,
        )
    )
    adj_stmt = (
        select(func.coalesce(func.sum(PatientAdjustment.amount), 0))
        .where(
            PatientAdjustment.tenant_id == tenant_id,
            PatientAdjustment.is_void.is_(False),
            PatientAdjustment.adjustment_date <= as_of,
        )
    )
    if office_id is not None:
        proc_stmt = proc_stmt.where(PatientProcedure.office_id == office_id)
        pay_stmt = pay_stmt.where(PatientPayment.office_id == office_id)
        adj_stmt = adj_stmt.where(PatientAdjustment.office_id == office_id)

    charged, est_ins = db.execute(proc_stmt).one()
    paid = db.execute(pay_stmt).scalar_one()
    adjusted = db.execute(adj_stmt).scalar_one()
    return _f(charged), _f(est_ins), _f(paid) + _f(adjusted)


def get_accounts_receivable(db: Session, tenant_id: int, office_id: int | None,
                            as_of: date | None = None) -> dict:
    as_of = as_of or _today()
    cached = redis_store.cache_get(_cache_key("ar", tenant_id, office_id, as_of.isoformat()))
    if cached:
        return json.loads(cached)

    charged, est_ins, credits = _ar_components(db, tenant_id, office_id, as_of)
    total_ar = round(charged - credits, 2)
    # insurance_ar is best-effort (gross outstanding estimate, clamped to total).
    insurance_ar = max(0.0, min(est_ins, total_ar)) if total_ar > 0 else 0.0
    patient_ar = round(total_ar - insurance_ar, 2)

    result = {
        "total_ar": total_ar,
        "patient_ar": patient_ar,
        "insurance_ar": round(insurance_ar, 2),
        "office_id": office_id,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    redis_store.cache_set(
        _cache_key("ar", tenant_id, office_id, as_of.isoformat()), json.dumps(result), _CACHE_TTL
    )
    return result


# ── aging (gross-charge dating, parity with per-patient balance) ────────────
def get_aging(db: Session, tenant_id: int, office_id: int | None,
              as_of: date | None = None) -> dict:
    as_of = as_of or _today()
    cached = redis_store.cache_get(_cache_key("aging", tenant_id, office_id, as_of.isoformat()))
    if cached:
        return json.loads(cached)

    d30, d60, d90, d120 = (as_of - timedelta(days=n) for n in (30, 60, 90, 120))
    bucket = case(
        (PatientProcedure.date_of_service >= d30, "current"),
        (PatientProcedure.date_of_service >= d60, "d30"),
        (PatientProcedure.date_of_service >= d90, "d60"),
        (PatientProcedure.date_of_service >= d120, "d90"),
        else_="d120_plus",
    ).label("bucket")
    stmt = (
        select(bucket, func.coalesce(func.sum(PatientProcedure.fee), 0))
        .join(Patient, Patient.id == PatientProcedure.patient_id)
        .where(
            Patient.tenant_id == tenant_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
            PatientProcedure.date_of_service <= as_of,
        )
        .group_by(bucket)
    )
    if office_id is not None:
        stmt = stmt.where(PatientProcedure.office_id == office_id)

    out = {"current": 0.0, "d30": 0.0, "d60": 0.0, "d90": 0.0, "d120_plus": 0.0}
    for name, total in db.execute(stmt).all():
        out[name] = _f(total)
    result = {
        **out,
        "total": round(sum(out.values()), 2),
        "office_id": office_id,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    redis_store.cache_set(
        _cache_key("aging", tenant_id, office_id, as_of.isoformat()), json.dumps(result), _CACHE_TTL
    )
    return result


# ── executive summary ───────────────────────────────────────────────────────
def get_summary(db: Session, tenant_id: int, office_id: int | None,
                date_from: date, date_to: date) -> dict:
    key = _cache_key("summary", tenant_id, office_id, date_from.isoformat(), date_to.isoformat())
    cached = redis_store.cache_get(key)
    if cached:
        return json.loads(cached)

    ar = get_accounts_receivable(db, tenant_id, office_id, date_to)
    result = {
        "production": _production(db, tenant_id, office_id, date_from, date_to),
        "collections": _collections(db, tenant_id, office_id, date_from, date_to),
        "new_patients": _new_patients(db, tenant_id, office_id, date_from, date_to),
        "active_patients": _active_patients(db, tenant_id, office_id),
        "scheduled_appointments": _scheduled_appointments(
            db, tenant_id, office_id, date_from, date_to
        ),
        "insurance_receivables": round(_insurance_receivables(db, tenant_id, office_id), 2),
        "outstanding_ar": ar["total_ar"],
        "office_id": office_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    redis_store.cache_set(key, json.dumps(result), _CACHE_TTL)
    return result


# ── trends (daily aggregation, rolled up to the requested interval) ─────────
def _as_date(value) -> date | None:  # noqa: ANN001
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])  # SQLite may hand back ISO strings


def _bucket_start(d: date, interval: str) -> date:
    if interval == "month":
        return d.replace(day=1)
    if interval == "week":
        return d - timedelta(days=d.weekday())  # ISO Monday
    return d


def get_trends(db: Session, tenant_id: int, office_id: int | None,
               date_from: date, date_to: date, interval: str = "day") -> dict:
    interval = interval if interval in ("day", "week", "month") else "day"
    key = _cache_key(
        "trends", tenant_id, office_id, interval, date_from.isoformat(), date_to.isoformat()
    )
    cached = redis_store.cache_get(key)
    if cached:
        return json.loads(cached)

    prod_stmt = (
        select(PatientProcedure.date_of_service, func.coalesce(func.sum(PatientProcedure.fee), 0))
        .join(Patient, Patient.id == PatientProcedure.patient_id)
        .where(
            Patient.tenant_id == tenant_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
            PatientProcedure.date_of_service >= date_from,
            PatientProcedure.date_of_service <= date_to,
        )
        .group_by(PatientProcedure.date_of_service)
    )
    coll_stmt = (
        select(PatientPayment.payment_date, sum_payment_credit())  # AL-9
        .join(Patient, Patient.id == PatientPayment.patient_id)
        .where(
            Patient.tenant_id == tenant_id,
            PatientPayment.is_void.is_(False),
            PatientPayment.payment_date >= date_from,
            PatientPayment.payment_date <= date_to,
        )
        .group_by(PatientPayment.payment_date)
    )
    # New patients: select created_at and bucket by day in Python (no CAST-to-DATE
    # group-by, which is not portable to SQLite — see _new_patients).
    upper = date_to + timedelta(days=1)
    newp_stmt = select(Patient.created_at).where(
        Patient.tenant_id == tenant_id,
        Patient.created_at >= date_from,
        Patient.created_at < upper,
    )
    if office_id is not None:
        prod_stmt = prod_stmt.where(PatientProcedure.office_id == office_id)
        coll_stmt = coll_stmt.where(PatientPayment.office_id == office_id)
        newp_stmt = newp_stmt.where(Patient.home_office_id == office_id)

    prod = {r[0]: _f(r[1]) for r in db.execute(prod_stmt).all() if r[0] is not None}
    coll = {r[0]: _f(r[1]) for r in db.execute(coll_stmt).all() if r[0] is not None}
    newp: dict[date, int] = {}
    for (created,) in db.execute(newp_stmt).all():
        d = _as_date(created)
        if d is not None:
            newp[d] = newp.get(d, 0) + 1

    buckets: dict[date, dict] = {}

    def _slot(raw) -> dict:  # noqa: ANN001
        d = _as_date(raw)
        start = _bucket_start(d, interval)
        return buckets.setdefault(
            start, {"period": start.isoformat(), "production": 0.0, "collections": 0.0, "new_patients": 0}
        )

    for raw, amount in prod.items():
        _slot(raw)["production"] += amount
    for raw, amount in coll.items():
        _slot(raw)["collections"] += amount
    for raw, count in newp.items():
        _slot(raw)["new_patients"] += count

    ordered = [
        {**b, "production": round(b["production"], 2), "collections": round(b["collections"], 2)}
        for _, b in sorted(buckets.items())
    ]
    result = {
        "interval": interval,
        "buckets": ordered,
        "office_id": office_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    redis_store.cache_set(key, json.dumps(result), _CACHE_TTL)
    return result


# ── insurance eligibility-verification summary (INS-11) ───────────
def get_insurance_verification_summary(
    db: Session, tenant_id: int, office_id: int | None
) -> dict:
    """Count active subscribers grouped by ``elig_status`` (single GROUP BY)."""
    cached = redis_store.cache_get(_cache_key("elig", tenant_id, office_id))
    if cached:
        return json.loads(cached)

    label = func.coalesce(func.nullif(InsuranceSubscriber.elig_status, ""), "unknown")
    stmt = (
        select(label, func.count())
        .where(
            InsuranceSubscriber.tenant_id == tenant_id,
            InsuranceSubscriber.is_active.is_(True),
        )
        .group_by(label)
    )
    if office_id is not None:
        stmt = stmt.where(InsuranceSubscriber.office_id == office_id)

    by_status: dict[str, int] = {}
    for status, count in db.execute(stmt).all():
        by_status[str(status)] = by_status.get(str(status), 0) + int(count)

    total = sum(by_status.values())
    verified = sum(c for s, c in by_status.items() if s.strip().lower() in _ELIG_VERIFIED)
    result = {
        "by_status": by_status,
        "total": total,
        "verified": verified,
        "pending": total - verified,
        "office_id": office_id,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    redis_store.cache_set(_cache_key("elig", tenant_id, office_id), json.dumps(result), _CACHE_TTL)
    return result
