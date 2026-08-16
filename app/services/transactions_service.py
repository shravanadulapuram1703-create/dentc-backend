"""Office financial dashboards + the unified cross-patient transaction feed.

Backs the Transactions **Dashboard** and global **Transactions** page, which had
no office-level aggregation or cross-patient feed at all:

* **DASH-1** office financial summary (outstanding / patient / insurance A/R).
* **DASH-2** collections summary for a period (today / month / …).
* **DASH-3** insurance receivables, total + by carrier.
* **DASH-4** adjustment / write-off / refund totals for a period.
* **DASH-5 · SRCH-1/3** the unified, paginated, searchable cross-patient feed
  (charges + payments + adjustments + refunds + claims), tenant- or office-scoped,
  with amount-range and transaction-number filters.

Amounts are ``Decimal``. ``patient_payments`` / ``insurance_claims`` /
``patient_procedures`` carry no ``tenant_id``; tenancy is enforced through the
owning patient (a per-tenant patient-id set) — the same pattern the balance and
billing services use.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import (
    InsuranceCarrier,
    InsuranceClaim,
    Office,
    Patient,
    PatientAdjustment,
    PatientPayment,
    PatientProcedure,
    PatientRefund,
    Provider,
)

_ZERO = Decimal("0")

# Open (unpaid/unresolved) claim statuses for insurance A/R.
_OPEN_CLAIM_STATUSES = {"draft", "ready", "sent", "submitted", "pending", "resubmitted", "hold"}


def _d(value: Any) -> Decimal:  # noqa: ANN401
    return Decimal(value or 0)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _assert_office(db: Session, office_id: int, tenant_id: int) -> Office:
    office = db.get(Office, office_id)
    if office is None or office.tenant_id != tenant_id:
        raise NotFoundError(f"Office '{office_id}' was not found")
    return office


def _period_window(period: str, date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = _now().date()
    if period == "custom" and (date_from or date_to):
        return (date_from or date(today.year, 1, 1)), (date_to or today)
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=today.weekday()), today
    if period == "year":
        return date(today.year, 1, 1), today
    # default: month
    return date(today.year, today.month, 1), today


# ── DASH-1: office financial summary ─────────────────────────────────────────
def office_financial_summary(db: Session, office_id: int, tenant_id: int) -> dict:
    _assert_office(db, office_id, tenant_id)

    charged, est_ins = db.execute(
        select(
            func.coalesce(func.sum(PatientProcedure.fee), 0),
            func.coalesce(func.sum(PatientProcedure.insurance_estimate), 0),
        ).where(
            PatientProcedure.office_id == office_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
        )
    ).one()
    paid = db.execute(
        select(func.coalesce(func.sum(PatientPayment.amount), 0)).where(
            PatientPayment.office_id == office_id, PatientPayment.is_void.is_(False)
        )
    ).scalar_one()
    adjusted = db.execute(
        select(func.coalesce(func.sum(PatientAdjustment.amount), 0)).where(
            PatientAdjustment.office_id == office_id, PatientAdjustment.is_void.is_(False)
        )
    ).scalar_one()
    refunded = db.execute(
        select(func.coalesce(func.sum(PatientRefund.amount), 0)).where(
            PatientRefund.office_id == office_id, PatientRefund.is_void.is_(False)
        )
    ).scalar_one()

    # Per-patient net split → aggregate outstanding vs credit.
    outstanding, credit, count = _office_balance_split(db, office_id)

    return {
        "office_id": office_id,
        "outstanding_balance": outstanding,
        "patient_balance": _d(outstanding) - _d(est_ins) if outstanding > _d(est_ins) else _ZERO,
        "insurance_receivable": _d(est_ins),
        "credit_balance": credit,
        "patient_count": count,
        "as_of": _now().isoformat(),
        # (charged/paid/adjusted/refunded retained internally for parity, not exposed)
        "_charged": _d(charged), "_paid": _d(paid),
        "_adjusted": _d(adjusted), "_refunded": _d(refunded),
    }


def _office_balance_split(db: Session, office_id: int) -> tuple[Decimal, Decimal, int]:
    """Net balance per patient (charges − payments − adjustments + refunds), split
    into total outstanding (debit) and total credit; count of non-zero patients."""
    charge_rows = dict(db.execute(
        select(PatientProcedure.patient_id, func.coalesce(func.sum(PatientProcedure.fee), 0)).where(
            PatientProcedure.office_id == office_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
        ).group_by(PatientProcedure.patient_id)
    ).all())
    pay_rows = dict(db.execute(
        select(PatientPayment.patient_id, func.coalesce(func.sum(PatientPayment.amount), 0)).where(
            PatientPayment.office_id == office_id, PatientPayment.is_void.is_(False)
        ).group_by(PatientPayment.patient_id)
    ).all())
    adj_rows = dict(db.execute(
        select(PatientAdjustment.patient_id, func.coalesce(func.sum(PatientAdjustment.amount), 0)).where(
            PatientAdjustment.office_id == office_id, PatientAdjustment.is_void.is_(False)
        ).group_by(PatientAdjustment.patient_id)
    ).all())
    ref_rows = dict(db.execute(
        select(PatientRefund.patient_id, func.coalesce(func.sum(PatientRefund.amount), 0)).where(
            PatientRefund.office_id == office_id, PatientRefund.is_void.is_(False)
        ).group_by(PatientRefund.patient_id)
    ).all())

    patients = set(charge_rows) | set(pay_rows) | set(adj_rows) | set(ref_rows)
    outstanding = credit = _ZERO
    count = 0
    for pid in patients:
        net = (_d(charge_rows.get(pid)) - _d(pay_rows.get(pid))
               - _d(adj_rows.get(pid)) + _d(ref_rows.get(pid)))
        if net > _ZERO:
            outstanding += net
            count += 1
        elif net < _ZERO:
            credit += -net
            count += 1
    return outstanding, credit, count


# ── DASH-2: collections summary ──────────────────────────────────────────────
def collections_summary(
    db: Session, office_id: int, tenant_id: int, *,
    period: str = "today", date_from: date | None = None, date_to: date | None = None,
) -> dict:
    _assert_office(db, office_id, tenant_id)
    start, end = _period_window(period, date_from, date_to)

    rows = db.execute(
        select(PatientPayment.payment_type, PatientPayment.amount).where(
            PatientPayment.office_id == office_id,
            PatientPayment.is_void.is_(False),
            PatientPayment.payment_date >= start,
            PatientPayment.payment_date <= end,
        )
    ).all()
    ins = pat = _ZERO
    for ptype, amount in rows:
        value = _d(amount)
        if (ptype or "").lower().startswith("ins") or "insurance" in (ptype or "").lower():
            ins += value
        else:
            pat += value

    return {
        "office_id": office_id,
        "period": period,
        "date_from": start,
        "date_to": end,
        "patient_payments": pat,
        "insurance_payments": ins,
        "total_collections": pat + ins,
        "payment_count": len(rows),
        "as_of": _now().isoformat(),
    }


# ── DASH-3: insurance receivables ────────────────────────────────────────────
def insurance_receivables(db: Session, office_id: int, tenant_id: int) -> dict:
    _assert_office(db, office_id, tenant_id)

    claims = db.execute(
        select(InsuranceClaim).where(
            InsuranceClaim.office_id == office_id,
            InsuranceClaim.is_active.is_(True),
        )
    ).scalars().all()

    total = _ZERO
    open_count = 0
    by_carrier: dict[int | None, dict] = {}
    for claim in claims:
        if (claim.status or "").lower() not in _OPEN_CLAIM_STATUSES:
            continue
        outstanding = _d(claim.est_insurance) - _d(claim.total_paid)
        if outstanding <= _ZERO:
            continue
        total += outstanding
        open_count += 1
        bucket = by_carrier.setdefault(
            claim.carrier_id, {"carrier_id": claim.carrier_id, "outstanding": _ZERO, "claim_count": 0}
        )
        bucket["outstanding"] += outstanding
        bucket["claim_count"] += 1

    carrier_ids = {cid for cid in by_carrier if cid is not None}
    names = {
        c.id: c.name for c in db.execute(
            select(InsuranceCarrier).where(InsuranceCarrier.id.in_(carrier_ids))
        ).scalars()
    } if carrier_ids else {}
    for cid, bucket in by_carrier.items():
        bucket["carrier_name"] = names.get(cid)

    return {
        "office_id": office_id,
        "total_outstanding": total,
        "open_claim_count": open_count,
        "by_carrier": sorted(
            by_carrier.values(), key=lambda b: b["outstanding"], reverse=True
        ),
        "as_of": _now().isoformat(),
    }


# ── DASH-4: adjustment / write-off / refund totals ───────────────────────────
def adjustment_summary(
    db: Session, office_id: int, tenant_id: int, *,
    period: str = "month", date_from: date | None = None, date_to: date | None = None,
) -> dict:
    _assert_office(db, office_id, tenant_id)
    start, end = _period_window(period, date_from, date_to)

    adj_rows = db.execute(
        select(PatientAdjustment.write_off_type, PatientAdjustment.amount).where(
            PatientAdjustment.office_id == office_id,
            PatientAdjustment.is_void.is_(False),
            PatientAdjustment.adjustment_date >= start,
            PatientAdjustment.adjustment_date <= end,
        )
    ).all()
    adjustment_total = write_off_total = _ZERO
    by_type: dict[str, Decimal] = {}
    for wtype, amount in adj_rows:
        value = _d(amount)
        adjustment_total += value
        if wtype:
            write_off_total += value
            by_type[wtype] = by_type.get(wtype, _ZERO) + value

    refund_total = db.execute(
        select(func.coalesce(func.sum(PatientRefund.amount), 0)).where(
            PatientRefund.office_id == office_id,
            PatientRefund.is_void.is_(False),
            PatientRefund.refund_date >= start,
            PatientRefund.refund_date <= end,
        )
    ).scalar_one()

    return {
        "office_id": office_id,
        "period": period,
        "date_from": start,
        "date_to": end,
        "adjustment_total": adjustment_total,
        "write_off_total": write_off_total,
        "refund_total": _d(refund_total),
        "write_off_by_type": by_type,
        "as_of": _now().isoformat(),
    }


# ── DASH-5 · SRCH-1/3: unified cross-patient transaction feed ────────────────
def transaction_feed(
    db: Session,
    tenant_id: int,
    *,
    office_id: int | None = None,
    search: str | None = None,
    transaction_type: str = "all",
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    transaction_number: str | None = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    if office_id is not None:
        _assert_office(db, office_id, tenant_id)

    # Tenant patient-id scope (payments/procedures/claims lack tenant_id).
    patient_ids = {
        pid for (pid,) in db.execute(
            select(Patient.id).where(Patient.tenant_id == tenant_id)
        ).all()
    }
    if not patient_ids:
        return _empty_feed(page, size)

    tt = (transaction_type or "all").lower()
    rows: list[dict] = []

    def _in_window(d: date | None) -> bool:
        if d is None:
            return date_from is None and date_to is None
        if date_from and d < date_from:
            return False
        if date_to and d > date_to:
            return False
        return True

    def _office_ok(oid: int | None) -> bool:
        return office_id is None or oid == office_id

    if tt in ("all", "charge", "procedure"):
        for p in db.execute(
            select(PatientProcedure).where(
                PatientProcedure.patient_id.in_(patient_ids),
                PatientProcedure.is_void.is_(False),
                PatientProcedure.is_archived.is_(False),
            )
        ).scalars():
            if not _office_ok(p.office_id) or not _in_window(p.date_of_service):
                continue
            rows.append({
                "transaction_number": f"PROC:{p.id}", "transaction_type": "charge",
                "source_id": p.id, "entry_date": p.date_of_service, "patient_id": p.patient_id,
                "office_id": p.office_id, "provider_id": p.provider_id,
                "code": p.procedure_code, "description": p.notes, "amount": _d(p.fee),
                "status": p.billing_status,
            })

    if tt in ("all", "payment"):
        for pay in db.execute(
            select(PatientPayment).where(
                PatientPayment.patient_id.in_(patient_ids), PatientPayment.is_void.is_(False)
            )
        ).scalars():
            if not _office_ok(pay.office_id) or not _in_window(pay.payment_date):
                continue
            rows.append({
                "transaction_number": f"PMT:{pay.id}", "transaction_type": "payment",
                "source_id": pay.id, "entry_date": pay.payment_date, "patient_id": pay.patient_id,
                "office_id": pay.office_id, "provider_id": pay.provider_id,
                "code": pay.payment_type, "description": pay.notes or pay.payment_type,
                "amount": -_d(pay.amount), "status": pay.payment_type,
            })

    if tt in ("all", "adjustment"):
        for adj in db.execute(
            select(PatientAdjustment).where(
                PatientAdjustment.patient_id.in_(patient_ids), PatientAdjustment.is_void.is_(False)
            )
        ).scalars():
            if not _office_ok(adj.office_id) or not _in_window(adj.adjustment_date):
                continue
            rows.append({
                "transaction_number": f"ADJ:{adj.id}", "transaction_type": "adjustment",
                "source_id": str(adj.id), "entry_date": adj.adjustment_date,
                "patient_id": adj.patient_id, "office_id": adj.office_id,
                "provider_id": adj.provider_id, "code": adj.adjustment_type,
                "description": adj.notes or adj.adjustment_type, "amount": -_d(adj.amount),
                "status": adj.write_off_type,
            })

    if tt in ("all", "refund"):
        for ref in db.execute(
            select(PatientRefund).where(
                PatientRefund.tenant_id == tenant_id, PatientRefund.is_void.is_(False)
            )
        ).scalars():
            if not _office_ok(ref.office_id) or not _in_window(ref.refund_date):
                continue
            rows.append({
                "transaction_number": f"REF:{ref.id}", "transaction_type": "refund",
                "source_id": str(ref.id), "entry_date": ref.refund_date,
                "patient_id": ref.patient_id, "office_id": ref.office_id, "provider_id": None,
                "code": ref.refund_method, "description": ref.reason or "Refund",
                "amount": _d(ref.amount), "status": ref.reason_code,
            })

    if tt in ("all", "claim"):
        for claim in db.execute(
            select(InsuranceClaim).where(
                InsuranceClaim.patient_id.in_(patient_ids), InsuranceClaim.is_active.is_(True)
            )
        ).scalars():
            claim_date = claim.submitted_date or claim.date_of_service_from
            if not _office_ok(claim.office_id) or not _in_window(claim_date):
                continue
            rows.append({
                "transaction_number": claim.claim_number, "transaction_type": "claim",
                "source_id": claim.id, "entry_date": claim_date, "patient_id": claim.patient_id,
                "office_id": claim.office_id, "provider_id": claim.billing_provider_id,
                "code": claim.claim_type, "description": f"Claim {claim.claim_number}",
                "amount": _d(claim.total_billed), "status": claim.status,
            })

    # ── filters (SRCH-1/3) ────────────────────────────────────────────────────
    if status:
        rows = [r for r in rows if (r.get("status") or "").lower() == status.lower()]
    if transaction_number:
        needle = transaction_number.lower()
        rows = [r for r in rows if needle in (r["transaction_number"] or "").lower()
                or needle in (r["source_id"] or "").lower()]
    if amount_min is not None:
        rows = [r for r in rows if abs(r["amount"]) >= amount_min]
    if amount_max is not None:
        rows = [r for r in rows if abs(r["amount"]) <= amount_max]

    # Denormalise patient/provider names (batched).
    _attach_names(db, rows)

    if search:
        needle = search.lower()
        rows = [r for r in rows if needle in " ".join(str(x or "") for x in (
            r.get("patient_name"), r.get("provider_name"), r.get("code"),
            r.get("description"), r["transaction_number"],
        )).lower()]

    rows.sort(key=lambda r: (r["entry_date"] or date.min, r["transaction_number"]), reverse=True)

    total = len(rows)
    start = (page - 1) * size
    page_rows = rows[start:start + size]
    pages = (total + size - 1) // size if size else 0
    return {
        "rows": page_rows,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "as_of": _now().isoformat(),
    }


def _attach_names(db: Session, rows: list[dict]) -> None:
    patient_ids = {r["patient_id"] for r in rows if r.get("patient_id") is not None}
    provider_ids = {r["provider_id"] for r in rows if r.get("provider_id")}
    patients = {p.id: p for p in db.execute(
        select(Patient).where(Patient.id.in_(patient_ids))
    ).scalars()} if patient_ids else {}
    providers = {p.id: p.name for p in db.execute(
        select(Provider).where(Provider.id.in_(provider_ids))
    ).scalars()} if provider_ids else {}
    for r in rows:
        p = patients.get(r.get("patient_id"))
        if p is not None:
            r["patient_name"] = ", ".join(x for x in (p.last_name, p.first_name) if x) or p.chart_no
        else:
            r["patient_name"] = None
        r["provider_name"] = providers.get(r.get("provider_id"))


def _empty_feed(page: int, size: int) -> dict:
    return {"rows": [], "total": 0, "page": page, "size": size, "pages": 0,
            "as_of": _now().isoformat()}
