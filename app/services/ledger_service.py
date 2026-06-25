"""Patient ledger feed (Phase 3 / C-3, optional aggregate).

Composes the patient's procedures (charges) and payments (credits) into a single
date-ordered feed with a server-computed ``running_balance`` in ``Decimal``. The
data already exists across resources — this endpoint exists for correctness
(precise running balance) and convenience; the FE could otherwise compose it from
the now-filterable ``patient-procedures`` + ``patient-payments`` lists.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import (
    Office,
    Patient,
    PatientAdjustment,
    PatientPayment,
    PatientProcedure,
    ProcedureCode,
    Provider,
    User,
)

# Stable secondary sort within a date: charges post before credits.
_TYPE_ORDER = {"procedure": 0, "payment": 1}
# Account-ledger chronological tiebreak within a date.
_ACCT_TYPE_ORDER = {"charge": 0, "payment": 1, "adjustment": 2}


def _f(value) -> float:  # noqa: ANN001
    return float(value or 0)


def get_patient_ledger(
    db: Session,
    patient_id: int,
    tenant_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    patient = db.execute(
        select(Patient.id).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")

    proc_stmt = select(PatientProcedure).where(
        PatientProcedure.patient_id == patient_id,
        PatientProcedure.is_void.is_(False),
        PatientProcedure.is_archived.is_(False),
    )
    if date_from is not None:
        proc_stmt = proc_stmt.where(PatientProcedure.date_of_service >= date_from)
    if date_to is not None:
        proc_stmt = proc_stmt.where(PatientProcedure.date_of_service <= date_to)

    pay_stmt = select(PatientPayment).where(
        PatientPayment.patient_id == patient_id,
        PatientPayment.is_void.is_(False),
    )
    if date_from is not None:
        pay_stmt = pay_stmt.where(PatientPayment.payment_date >= date_from)
    if date_to is not None:
        pay_stmt = pay_stmt.where(PatientPayment.payment_date <= date_to)

    entries: list[dict] = []
    for p in db.execute(proc_stmt).scalars():
        entries.append({
            "entry_date": p.date_of_service.isoformat() if p.date_of_service else "",
            "entry_type": "procedure",
            "source_id": p.id,
            "description": p.notes or p.procedure_code,
            "charge": _f(p.fee),
            "credit": 0.0,
            "procedure_code": p.procedure_code,
            "tooth": p.tooth,
            "payment_type": None,
            "status": p.billing_status,
        })
    for pay in db.execute(pay_stmt).scalars():
        entries.append({
            "entry_date": pay.payment_date.isoformat() if pay.payment_date else "",
            "entry_type": "payment",
            "source_id": pay.id,
            "description": pay.notes or pay.payment_type,
            "charge": 0.0,
            "credit": _f(pay.amount),
            "procedure_code": None,
            "tooth": None,
            "payment_type": pay.payment_type,
            "status": None,
        })

    entries.sort(key=lambda e: (e["entry_date"], _TYPE_ORDER.get(e["entry_type"], 9), str(e["source_id"])))

    # Running balance over the FULL window (Decimal), computed before slicing.
    running = Decimal(0)
    for e in entries:
        running += Decimal(str(e["charge"])) - Decimal(str(e["credit"]))
        e["running_balance"] = float(running)

    total = len(entries)
    start = (page - 1) * size
    end = start + size
    page_entries = entries[start:end]

    opening = entries[start - 1]["running_balance"] if start > 0 and start <= total else 0.0
    closing = page_entries[-1]["running_balance"] if page_entries else opening

    return {
        "patient_id": patient_id,
        "entries": page_entries,
        "opening_balance": float(opening),
        "closing_balance": float(closing),
        "total": total,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


# ── Account Ledger — denormalised, server-paged feed (AL-1/2/4/5/7) ───────────
_DEC0 = Decimal("0")


def _user_label(u: User | None) -> str | None:
    if u is None:
        return None
    return u.short_id or u.username


def get_account_ledger(
    db: Session,
    patient_id: int,
    tenant_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    transaction_type: str = "all",
    sort_by: str = "date",
    order: str = "asc",
    page: int = 1,
    size: int = 50,
) -> dict:
    """Single chronological feed of charges (procedures) + payments + adjustments,
    fully denormalised, with a server-computed running balance over the FULL account
    window. The ``transaction_type`` filter and ``sort_by``/``order`` are applied for
    display *after* the running balance is computed, so each row keeps its
    account-level balance regardless of filter/sort. ``grand_total`` is the final
    account balance over the whole window."""
    if db.execute(
        select(Patient.id).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none() is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")

    def _date_window(stmt, col):  # noqa: ANN001
        if date_from is not None:
            stmt = stmt.where(col >= date_from)
        if date_to is not None:
            stmt = stmt.where(col <= date_to)
        return stmt

    procs = db.execute(_date_window(
        select(PatientProcedure).where(
            PatientProcedure.patient_id == patient_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
        ), PatientProcedure.date_of_service)).scalars().all()
    pays = db.execute(_date_window(
        select(PatientPayment).where(
            PatientPayment.patient_id == patient_id,
            PatientPayment.is_void.is_(False),
        ), PatientPayment.payment_date)).scalars().all()
    adjs = db.execute(_date_window(
        select(PatientAdjustment).where(
            PatientAdjustment.patient_id == patient_id,
            PatientAdjustment.is_void.is_(False),
        ), PatientAdjustment.adjustment_date)).scalars().all()

    rows: list[dict] = []
    for p in procs:
        rows.append({
            "entry_date": p.date_of_service, "source_type": "charge", "source_id": p.id,
            "code": p.procedure_code, "description": p.notes, "transaction_kind": "P",
            "apply_to": p.apply_to, "tooth": p.tooth, "surface": p.surface,
            "provider_id": p.provider_id, "office_id": p.office_id,
            "patient_estimate": p.patient_estimate, "insurance_estimate": p.insurance_estimate,
            "billing_status": p.billing_status, "unbilled": p.claim_id is None,
            "user_id": p.created_by, "charge": p.fee or _DEC0, "credit": _DEC0,
        })
    for pay in pays:
        rows.append({
            "entry_date": pay.payment_date, "source_type": "payment", "source_id": pay.id,
            "code": "PMT", "description": pay.notes or pay.payment_type, "transaction_kind": "C",
            "apply_to": None, "tooth": None, "surface": None,
            "provider_id": pay.provider_id, "office_id": pay.office_id,
            "patient_estimate": None, "insurance_estimate": None, "billing_status": None,
            "unbilled": None, "user_id": pay.created_by,
            "charge": _DEC0, "credit": pay.amount or _DEC0,
        })
    for adj in adjs:
        rows.append({
            "entry_date": adj.adjustment_date, "source_type": "adjustment", "source_id": str(adj.id),
            "code": "PATADJ", "description": adj.notes or adj.adjustment_type, "transaction_kind": "P",
            "apply_to": None, "tooth": None, "surface": None,
            "provider_id": adj.provider_id, "office_id": adj.office_id,
            "patient_estimate": None, "insurance_estimate": None, "billing_status": None,
            "unbilled": None, "user_id": adj.created_by,
            "charge": _DEC0, "credit": adj.amount or _DEC0,  # adjustments reduce balance (legacy −amount)
        })

    # Running balance over the full account window, chronologically.
    rows.sort(key=lambda r: (
        r["entry_date"] or date.min,
        _ACCT_TYPE_ORDER.get(r["source_type"], 9),
        str(r["source_id"]),
    ))
    running = _DEC0
    for r in rows:
        r["amount"] = r["charge"] - r["credit"]
        running += r["amount"]
        r["running_balance"] = running
    grand_total = running

    # Display filter (running balance already account-level).
    tt = (transaction_type or "all").lower()
    if tt in ("procedure", "charge"):
        rows = [r for r in rows if r["source_type"] == "charge"]
    elif tt == "payment":
        rows = [r for r in rows if r["source_type"] == "payment"]
    elif tt == "adjustment":
        rows = [r for r in rows if r["source_type"] == "adjustment"]
    total = len(rows)

    # Denormalise lookups (batched by distinct id — cheap regardless of row count).
    office_ids = {r["office_id"] for r in rows if r["office_id"] is not None}
    provider_ids = {r["provider_id"] for r in rows if r["provider_id"]}
    user_ids = {r["user_id"] for r in rows if r["user_id"] is not None}
    codes = {r["code"] for r in rows if r["source_type"] == "charge" and r["code"]}
    offices = {o.id: o for o in db.execute(
        select(Office).where(Office.id.in_(office_ids))).scalars()} if office_ids else {}
    providers = {p.id: p for p in db.execute(
        select(Provider).where(Provider.id.in_(provider_ids))).scalars()} if provider_ids else {}
    users = {u.id: u for u in db.execute(
        select(User).where(User.id.in_(user_ids))).scalars()} if user_ids else {}
    code_desc = {c.code: c.description for c in db.execute(
        select(ProcedureCode).where(ProcedureCode.code.in_(codes))).scalars()} if codes else {}

    for r in rows:
        office = offices.get(r["office_id"])
        r["office_short_id"] = (office.short_id or office.office_code) if office else None
        provider = providers.get(r["provider_id"])
        r["provider_name"] = provider.name if provider else None
        r["user_label"] = _user_label(users.get(r["user_id"]))
        if r["source_type"] == "charge" and not r["description"]:
            r["description"] = code_desc.get(r["code"]) or r["code"]

    # Display sort.
    reverse = (order or "asc").lower() == "desc"
    _keys = {
        "date": lambda r: (r["entry_date"] or date.min, _ACCT_TYPE_ORDER.get(r["source_type"], 9), str(r["source_id"])),
        "code": lambda r: (r["code"] or ""),
        "provider": lambda r: (r["provider_name"] or ""),
        "amount": lambda r: r["amount"],
    }
    rows.sort(key=_keys.get(sort_by, _keys["date"]), reverse=reverse)

    start = (page - 1) * size
    page_rows = rows[start:start + size]
    pages = (total + size - 1) // size if size else 0

    return {
        "patient_id": patient_id,
        "rows": page_rows,
        "grand_total": grand_total,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
