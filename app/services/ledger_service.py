"""Patient ledger feed (Phase 3 / C-3, optional aggregate).

Composes the patient's procedures (charges) and payments (credits) into a single
date-ordered feed with a server-computed ``running_balance`` in ``Decimal``. The
data already exists across resources — this endpoint exists for correctness
(precise running balance) and convenience; the FE could otherwise compose it from
the now-filterable ``patient-procedures`` + ``patient-payments`` lists.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import (
    InsuranceClaim,
    Office,
    Patient,
    PatientAdjustment,
    PatientPayment,
    PatientProcedure,
    ProcedureCode,
    Provider,
    User,
)
from app.services import account_scope
from app.services.ledger_sign import payment_credit, payment_debit

# Stable secondary sort within a date: charges post before credits.
_TYPE_ORDER = {"procedure": 0, "payment": 1}
# Account-ledger chronological tiebreak within a date.
_ACCT_TYPE_ORDER = {"charge": 0, "payment": 1, "adjustment": 2}


def _f(value) -> float:  # noqa: ANN001
    return float(value or 0)


# LED-1: display-sort key extractors (running balance stays chronological).
_LEDGER_SORT_KEYS = {
    "date": lambda e: (e["entry_date"], _TYPE_ORDER.get(e["entry_type"], 9), str(e["source_id"])),
    "amount": lambda e: e["charge"] - e["credit"],
    "code": lambda e: (e["procedure_code"] or e["payment_type"] or ""),
    "provider": lambda e: (e.get("provider_name") or ""),
    "status": lambda e: (e["status"] or ""),
}


def get_patient_ledger(
    db: Session,
    patient_id: int,
    tenant_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    transaction_type: str = "all",
    status: str | None = None,
    sort_by: str = "date",
    sort_order: str = "asc",
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
        # AL-9: charges already exclude archived rows; credits must match.
        PatientPayment.is_archived.is_(False),
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
            # AUD-2: creator/timestamps per ledger row.
            "provider_id": p.provider_id,
            "created_by": p.created_by,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    for pay in db.execute(pay_stmt).scalars():
        entries.append({
            "entry_date": pay.payment_date.isoformat() if pay.payment_date else "",
            "entry_type": "payment",
            "source_id": pay.id,
            "description": pay.notes or pay.payment_type,
            # AL-9: `amount` carries two sign conventions — ledger_sign settles it.
            "charge": _f(payment_debit(pay.amount, pay.payment_type)),
            "credit": _f(payment_credit(pay.amount, pay.payment_type)),
            "procedure_code": None,
            "tooth": None,
            "payment_type": pay.payment_type,
            "status": None,
            "provider_id": pay.provider_id,
            "created_by": pay.created_by,
            "created_at": pay.created_at.isoformat() if pay.created_at else None,
        })

    # Chronological sort first — the running balance must be date-ordered.
    entries.sort(key=lambda e: (e["entry_date"], _TYPE_ORDER.get(e["entry_type"], 9), str(e["source_id"])))

    # Running balance over the FULL window (Decimal), computed before slicing.
    running = Decimal(0)
    for e in entries:
        running += Decimal(str(e["charge"])) - Decimal(str(e["credit"]))
        e["running_balance"] = float(running)

    # AUD-2: resolve creator display names (batched).
    actor_ids = {e["created_by"] for e in entries if e.get("created_by") is not None}
    names = _user_names(db, actor_ids)
    provider_ids = {e["provider_id"] for e in entries if e.get("provider_id")}
    providers = {p.id: p.name for p in db.execute(
        select(Provider).where(Provider.id.in_(provider_ids))
    ).scalars()} if provider_ids else {}
    for e in entries:
        e["created_by_name"] = names.get(e["created_by"]) if e.get("created_by") is not None else None
        e["modified_by"] = None
        e["modified_at"] = None
        e["provider_name"] = providers.get(e.get("provider_id"))

    # LED-1: display filters (applied after the running balance is computed).
    tt = (transaction_type or "all").lower()
    if tt in ("procedure", "charge"):
        entries = [e for e in entries if e["entry_type"] == "procedure"]
    elif tt == "payment":
        entries = [e for e in entries if e["entry_type"] == "payment"]
    if status:
        entries = [e for e in entries if (e["status"] or "").lower() == status.lower()]

    # LED-1: display sort.
    reverse = (sort_order or "asc").lower() == "desc"
    entries.sort(key=_LEDGER_SORT_KEYS.get(sort_by, _LEDGER_SORT_KEYS["date"]), reverse=reverse)

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


def _user_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {u.id: _user_label(u) for u in db.execute(select(User).where(User.id.in_(ids))).scalars()}


# ── Account Ledger — denormalised, server-paged feed ─────────────────────────
# AL-1/2/4/5/7 delivered the per-patient feed. This pass adds:
#   AL-6  `duration_minutes` on charge rows, and a trustworthy `unbilled` now that
#         `claim_id` is backfillable from the source export.
#   AL-8  claim rows (`source_type='claim'`), one per dated status event.
#   AL-9  a genuinely signed `amount` (+charge / −credit) under one sign convention.
#   AL-10 `user_label` falls back to the legacy login when the poster has no
#         `users` row, so the User column is not blank on migrated history.
#   AL-11 `scope=account` — the merged, server-paged feed for every patient on
#         the account, with `patient_id`/`patient_name` per row.
_DEC0 = Decimal("0")

# Chronological tiebreak within a date. A claim row is informational and sorts
# last so it never lands between a charge and the payment that settles it.
_ACCT_TYPE_ORDER = {"charge": 0, "payment": 1, "adjustment": 2, "claim": 3}

# AL-8: the legacy Code cell for a claim row, by coverage tier.
_CLAIM_TIER_CODE = {
    "primary": ("CLM-P", "Pri"),
    "secondary": ("CLM-S", "Sec"),
    "tertiary": ("CLM-T", "Ter"),
    "quaternary": ("CLM-Q", "Qua"),
}
# AL-8: claim date column -> (event key, legacy event label), in ledger order.
_CLAIM_EVENTS = (
    ("submitted_date", "submitted", "Sent"),
    ("paid_date", "paid", "Paid"),
    ("close_date", "closed", "Closed"),
)


# AL-14: some migrated notes arrive already money-prefixed
# ("$-89 Payment - Insurance Check No: 78687655"), so the grid's own
# "$<amount> <text>" composition produced "$0 $-89 Payment - …". `description` is
# plain text on every row now; presentation belongs to the client.
_MONEY_PREFIX = re.compile(r"^\s*\$\s*-?[\d,]+(?:\.\d+)?\s*")


def _plain_description(text: str | None) -> str | None:
    if not text:
        return text
    stripped = _MONEY_PREFIX.sub("", text, count=1)
    # Never strip the whole cell away — a description that is only an amount is
    # better than an empty one.
    return stripped.strip() or text.strip()


def _user_label(u: User | None) -> str | None:
    if u is None:
        return None
    return u.short_id or u.username


def _claim_tier(claim: InsuranceClaim) -> tuple[str, str]:
    key = (claim.billing_order or claim.claim_type or "primary").strip().lower()
    return _CLAIM_TIER_CODE.get(key, ("CLM-P", "Pri"))


def _window(stmt, col, date_from, date_to):  # noqa: ANN001, ANN202
    if date_from is not None:
        stmt = stmt.where(col >= date_from)
    if date_to is not None:
        stmt = stmt.where(col <= date_to)
    return stmt


def _charge_rows(db, patient_ids, date_from, date_to, include_archived):  # noqa: ANN001, ANN201
    stmt = select(PatientProcedure).where(
        PatientProcedure.patient_id.in_(patient_ids),
        PatientProcedure.is_void.is_(False),
    )
    if not include_archived:
        stmt = stmt.where(PatientProcedure.is_archived.is_(False))
    stmt = _window(stmt, PatientProcedure.date_of_service, date_from, date_to)
    return [{
        "patient_id": p.patient_id,
        "entry_date": p.date_of_service, "source_type": "charge", "source_id": p.id,
        "code": p.procedure_code, "description": p.notes, "transaction_kind": "P",
        "apply_to": p.apply_to, "tooth": p.tooth, "surface": p.surface,
        "provider_id": p.provider_id, "office_id": p.office_id,
        "patient_estimate": p.patient_estimate, "insurance_estimate": p.insurance_estimate,
        "billing_status": p.billing_status, "unbilled": p.claim_id is None,
        "claim_id": p.claim_id,
        # AL-17: the legacy "H" indicator, and what keeps a held charge out of
        # Create Claim. It was already on the row; it just wasn't exposed, so the
        # grid had to walk /patient-procedures per account member to find it.
        "hold_claim": bool(p.hold_claim),
        # AL-6: chair time booked against the charge (LEDGER.DURATION).
        "duration_minutes": p.duration_minutes,
        # AL-15: patient money already applied to this charge.
        "pat_paid": p.pat_paid, "pat_adjust": p.pat_adjust,
        "user_id": p.created_by, "user_legacy": p.created_by_legacy,
        "created_at": p.created_at,
        "updated_at": p.updated_at, "updated_by": p.updated_by,
        "charge": p.fee or _DEC0, "credit": _DEC0,
    } for p in db.execute(stmt).scalars()]


def _payment_rows(db, patient_ids, date_from, date_to, include_archived):  # noqa: ANN001, ANN201
    stmt = select(PatientPayment).where(
        PatientPayment.patient_id.in_(patient_ids),
        PatientPayment.is_void.is_(False),
    )
    if not include_archived:
        stmt = stmt.where(PatientPayment.is_archived.is_(False))
    stmt = _window(stmt, PatientPayment.payment_date, date_from, date_to)
    rows = []
    for pay in db.execute(stmt).scalars():
        # AL-9: the stored sign means different things for migrated vs app-created
        # rows — ledger_sign is the single place that settles it.
        charge = payment_debit(pay.amount, pay.payment_type)
        credit = payment_credit(pay.amount, pay.payment_type)
        rows.append({
            "patient_id": pay.patient_id,
            "entry_date": pay.payment_date, "source_type": "payment", "source_id": pay.id,
            "code": "PMT", "description": pay.notes or pay.payment_type,
            "transaction_kind": "P" if charge else "C",
            "apply_to": None, "tooth": None, "surface": None,
            "provider_id": pay.provider_id, "office_id": pay.office_id,
            "patient_estimate": None, "insurance_estimate": None, "billing_status": None,
            "unbilled": None, "claim_id": None, "hold_claim": None,
            "duration_minutes": None, "pat_paid": None, "pat_adjust": None,
            "user_id": pay.created_by, "user_legacy": pay.created_by_legacy,
            "created_at": pay.created_at,
            "updated_at": pay.updated_at, "updated_by": pay.updated_by,
            "charge": charge, "credit": credit,
        })
    return rows


def _adjustment_rows(db, patient_ids, date_from, date_to):  # noqa: ANN001, ANN201
    stmt = _window(
        select(PatientAdjustment).where(
            PatientAdjustment.patient_id.in_(patient_ids),
            PatientAdjustment.is_void.is_(False),
        ), PatientAdjustment.adjustment_date, date_from, date_to)
    return [{
        "patient_id": adj.patient_id,
        "entry_date": adj.adjustment_date, "source_type": "adjustment", "source_id": str(adj.id),
        "code": "PATADJ", "description": adj.notes or adj.adjustment_type, "transaction_kind": "C",
        "apply_to": None, "tooth": None, "surface": None,
        "provider_id": adj.provider_id, "office_id": adj.office_id,
        "patient_estimate": None, "insurance_estimate": None, "billing_status": None,
        "unbilled": None, "claim_id": None, "hold_claim": None,
        "duration_minutes": None, "pat_paid": None, "pat_adjust": None,
        "user_id": adj.created_by, "user_legacy": None, "created_at": adj.created_at,
        "updated_at": None, "updated_by": None,
        # An adjustment on this table is a credit (the legacy −amount).
        "charge": _DEC0, "credit": adj.amount or _DEC0,
    } for adj in db.execute(stmt).scalars()]


def _claim_rows(db, patient_ids, date_from, date_to):  # noqa: ANN001, ANN201
    """AL-8: the claim *events* the legacy ledger interleaves with the money rows.

    One row per dated status transition (Sent / Paid / Closed), because the legacy
    row reflects the event and not the claim's current state — a claim sent in
    March and closed in May shows on both dates. A claim with no dates at all still
    yields one row (its creation date) rather than vanishing. These rows are
    informational: ``charge`` and ``credit`` are zero and the running balance does
    not move, because the money already arrived as an insurance ``payment`` row.
    """
    claims = db.execute(
        select(InsuranceClaim).where(InsuranceClaim.patient_id.in_(patient_ids))
    ).scalars().all()

    rows = []
    for claim in claims:
        code, tier = _claim_tier(claim)
        events = [(key, label, getattr(claim, col))
                  for col, key, label in _CLAIM_EVENTS if getattr(claim, col)]
        if not events:
            events = [(
                "created", (claim.status or "draft").title(),
                claim.created_at.date() if claim.created_at else claim.date_of_service_from,
            )]
        for event_key, label, when in events:
            if date_from is not None and (when is None or when < date_from):
                continue
            if date_to is not None and (when is None or when > date_to):
                continue
            rows.append({
                "patient_id": claim.patient_id,
                "entry_date": when, "source_type": "claim",
                "source_id": f"{claim.id}:{event_key}",
                "code": code,
                "description": f"{tier} Claim - {label}",
                # Informational: neither a debit nor a credit.
                "transaction_kind": "I",
                "apply_to": None, "tooth": None, "surface": None,
                "provider_id": claim.treating_provider_id or claim.billing_provider_id,
                "office_id": claim.office_id,
                "patient_estimate": None, "insurance_estimate": claim.est_insurance,
                "billing_status": claim.status, "unbilled": None,
                "claim_id": claim.id, "hold_claim": None,
                "duration_minutes": None, "pat_paid": None, "pat_adjust": None,
                "user_id": claim.created_by, "user_legacy": None,
                "created_at": claim.created_at,
                "updated_at": None, "updated_by": None,
                "charge": _DEC0, "credit": _DEC0,
                "claim_number": claim.claim_number, "claim_status": claim.status,
                "claim_event": event_key,
                "total_billed": claim.total_billed, "total_paid": claim.total_paid,
            })
    return rows


def _denormalise(db: Session, rows: list[dict], patients: dict) -> None:
    """Batched lookups by distinct id — one query per dimension, never per row."""
    office_ids = {r["office_id"] for r in rows if r["office_id"] is not None}
    provider_ids = {r["provider_id"] for r in rows if r["provider_id"]}
    user_ids = {r["user_id"] for r in rows if r["user_id"] is not None}
    user_ids |= {r["updated_by"] for r in rows if r.get("updated_by") is not None}
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
        # AL-10: prefer the live user, fall back to the legacy login string so the
        # User column is filled for staff who left before the migration.
        r["user_label"] = _user_label(users.get(r["user_id"])) or r.get("user_legacy")
        # AL-13: "Modified By" on the Edit Treatment / Edit Payment windows.
        r["updated_by_label"] = _user_label(users.get(r.get("updated_by")))
        patient = patients.get(r["patient_id"])
        r["patient_name"] = account_scope.patient_name(patient) if patient else None
        if r["source_type"] == "charge" and not r["description"]:
            r["description"] = code_desc.get(r["code"]) or r["code"]
        r["description"] = _plain_description(r["description"])


_ACCT_SORT_KEYS = {
    "date": lambda r: (
        r["entry_date"] or date.min, _ACCT_TYPE_ORDER.get(r["source_type"], 9), str(r["source_id"]),
    ),
    "code": lambda r: (r["code"] or ""),
    "provider": lambda r: (r["provider_name"] or ""),
    "amount": lambda r: r["amount"],
    "patient": lambda r: (r["patient_name"] or "", r["entry_date"] or date.min),
}


def get_account_ledger(
    db: Session,
    patient_id: int,
    tenant_id: int,
    *,
    scope: str = "patient",
    date_from: date | None = None,
    date_to: date | None = None,
    transaction_type: str = "all",
    include_claims: bool = False,
    include_archived: bool = False,
    sort_by: str = "date",
    order: str = "asc",
    page: int = 1,
    size: int = 50,
) -> dict:
    """One chronological feed of charges + payments + adjustments (+ claim events),
    fully denormalised, with a server-computed running balance over the FULL window.

    ``transaction_type``, ``sort_by``/``order`` and paging are applied for *display*
    **after** the running balance is computed, so a row keeps its account-level
    balance regardless of how the grid is filtered or sorted, and ``grand_total`` is
    the balance over the whole window rather than over the visible page.

    ``scope='account'`` (AL-11) widens the feed to every patient sharing the
    anchor's ``responsible_party_id``: the running balance and the grand total are
    computed across the merged multi-patient feed and the result is server-paged,
    replacing the browser-side merge of one request per member.
    """
    patient = account_scope.load_patient(db, patient_id, tenant_id)
    members = (
        account_scope.account_members(db, patient, tenant_id)
        if (scope or "patient").lower() == "account" else [patient]
    )
    patients = {m.id: m for m in members}
    patient_ids = list(patients)

    rows = (
        _charge_rows(db, patient_ids, date_from, date_to, include_archived)
        + _payment_rows(db, patient_ids, date_from, date_to, include_archived)
        + _adjustment_rows(db, patient_ids, date_from, date_to)
    )
    if include_claims:
        rows += _claim_rows(db, patient_ids, date_from, date_to)

    # Running balance over the full window, chronologically. A claim row carries the
    # balance as it stood at its position but contributes nothing to it.
    rows.sort(key=_ACCT_SORT_KEYS["date"])
    running = _DEC0
    for r in rows:
        # AL-9: `amount` is genuinely signed — +charge, −credit — as documented.
        r["amount"] = r["charge"] - r["credit"]
        running += r["amount"]
        r["running_balance"] = running
    grand_total = running

    # Display filter (the running balance is already account-level).
    tt = (transaction_type or "all").lower()
    if tt != "all":
        wanted = "charge" if tt == "procedure" else tt
        rows = [r for r in rows if r["source_type"] == wanted]
    total = len(rows)

    _denormalise(db, rows, patients)

    reverse = (order or "asc").lower() == "desc"
    rows.sort(key=_ACCT_SORT_KEYS.get(sort_by, _ACCT_SORT_KEYS["date"]), reverse=reverse)

    start = (page - 1) * size
    page_rows = rows[start:start + size]
    pages = (total + size - 1) // size if size else 0

    return {
        "patient_id": patient_id,
        "scope": (scope or "patient").lower(),
        "responsible_party_id": patient.responsible_party_id,
        "patient_ids": patient_ids,
        "rows": page_rows,
        "grand_total": grand_total,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
