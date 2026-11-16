"""Family accounts (RP-1 … RP-16).

accounts · account_parties · account_change_events

Denticon's model: every patient belongs to exactly one **account**, and the
account has one primary guarantor (a patient on it, or a non-patient
``responsible_parties`` row) plus up to two additional financially responsible
parties. Statements, aging and guarantor payments are account-level.

Before this module the only link was ``patients.responsible_party_id`` — one
string that held a ``responsible_parties.id``, the patient's own id (self) or a
migrated RPID, with membership defined as "everyone holding the same string".
The id spaces collide (RP-1/RP-2), so the typed columns here are canonical and
the string is a computed alias.

**Every ORM-inserted patient gets an account** (RP-4) through the
``before_insert``/``after_insert`` hooks at the bottom of this file: an explicit
``account_id`` / guarantor is honoured, a legacy ``responsible_party_id`` key is
resolved with the same rules as the migration backfill, and anything else is a
new account with the patient as **Self**. The hooks run on the flush connection,
so they cover ``POST /patients``, ``/patients/register``, AppointNow's
``resolve_patient`` and every test fixture alike.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.attributes import set_committed_value

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin

#: RP-8: the primary guarantor plus at most two additional parties.
MAX_ACCOUNT_PARTIES = 3
#: Roles an ``account_parties`` row may hold. The **primary** lives on the
#: account itself (``primary_guarantor_*``) so "exactly one primary" is
#: structural rather than a rule two writers could disagree on.
ADDITIONAL_PARTY_ROLES = ("secondary", "billing_contact")
SELF_RELATIONSHIP = "S"


class Account(Base, IntPKMixin, TimestampMixin):
    """RP-3: one row per guarantor account. Account-level billing facts live
    here and are canonical for account statements; they are *seeded* from the
    guarantor (the self patient's flags or the RP row's) when the account is
    created, never mirrored back."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_no", name="uq_accounts_tenant_account_no"),
        CheckConstraint(
            "primary_guarantor_patient_id IS NULL OR primary_guarantor_party_id IS NULL",
            name="ck_accounts_single_primary",
        ),
        Index("ix_accounts_tenant_legacy_key", "tenant_id", "legacy_key"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    #: Display account number: the Denticon RPID for migrated accounts, else the id.
    account_no: Mapped[str | None] = mapped_column(String(30))
    #: The pre-RP-1 ``responsible_party_id`` string this account was grouped by
    #: (migrated RPID / unresolved key). NULL for app-created accounts.
    legacy_key: Mapped[str | None] = mapped_column(String(50))
    primary_guarantor_patient_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("patients.id", name="fk_accounts_primary_guarantor_patient_id", use_alter=True),
        index=True,
    )
    primary_guarantor_party_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("responsible_parties.id"), index=True
    )
    home_office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    send_statements: Mapped[bool] = mapped_column(Boolean, default=True)
    no_email_statement: Mapped[bool] = mapped_column(Boolean, default=False)
    send_collections: Mapped[bool] = mapped_column(Boolean, default=False)
    collection_agency_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("collection_agencies.id")
    )
    is_finance_charge: Mapped[bool] = mapped_column(Boolean, default=False)
    statement_message: Mapped[str | None] = mapped_column(Text)
    financial_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: RP-6 merge: the surviving account, set on the deactivated source.
    merged_into_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", name="fk_accounts_merged_into", use_alter=True)
    )
    merged_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class AccountParty(Base, IntPKMixin, TimestampMixin):
    """RP-8: an *additional* financially responsible party on an account
    (divorced parents splitting a child's balance, a separate bill-to)."""

    __tablename__ = "account_parties"
    __table_args__ = (
        CheckConstraint(
            "(patient_id IS NULL) <> (responsible_party_id IS NULL)",
            name="ck_account_parties_one_person",
        ),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), index=True)
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    responsible_party_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("responsible_parties.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), default="secondary")
    responsibility_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    receives_statements: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class AccountChangeEvent(Base, IntPKMixin, CreatedAtMixin):
    """RP-16: append-only log of guarantor / account changes."""

    __tablename__ = "account_change_events"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    #: change_guarantor | merge | party_added | party_updated | party_removed |
    #: primary_changed | account_updated | account_payment
    action: Mapped[str] = mapped_column(String(30))
    old_account_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("accounts.id"), index=True)
    new_account_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("accounts.id"), index=True)
    old_guarantor: Mapped[dict | None] = mapped_column(JSON)
    new_guarantor: Mapped[dict | None] = mapped_column(JSON)
    move_open_balance: Mapped[bool | None] = mapped_column(Boolean)
    moved_balance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    effective_date: Mapped[date | None]
    details: Mapped[dict | None] = mapped_column(JSON)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


# ── Connection-level resolution (shared by the hooks and family_account_service) ─────
def _patients():  # noqa: ANN202
    from app.db.models.patients import Patient

    return Patient.__table__


def _parties():  # noqa: ANN202
    from app.db.models.patients import ResponsibleParty

    return ResponsibleParty.__table__


def next_account_no(conn, tenant_id: int, account_id: int) -> str:  # noqa: ANN001
    """``{id}``, or ``A{id}`` / ``A{id}-n`` when a migrated RPID already holds it."""
    acc = Account.__table__
    candidates = [str(account_id), f"A{account_id}"]
    n = 1
    while True:
        for cand in candidates:
            taken = conn.execute(
                select(acc.c.id).where(
                    acc.c.tenant_id == tenant_id, acc.c.account_no == cand, acc.c.id != account_id
                )
            ).first()
            if taken is None:
                return cand
        candidates = [f"A{account_id}-{n}"]
        n += 1


def _free_account_no(conn, tenant_id: int, key: str) -> str | None:  # noqa: ANN001
    """A migrated RPID is the Denticon account number — used when free."""
    acc = Account.__table__
    cand = key[:30]
    taken = conn.execute(select(acc.c.id).where(
        acc.c.tenant_id == tenant_id, acc.c.account_no == cand)).first()
    return None if taken is not None else cand


def create_account_row(conn, tenant_id: int, **values: Any) -> int:  # noqa: ANN001
    acc = Account.__table__
    values.setdefault("is_active", True)
    values.setdefault("send_statements", True)
    values.setdefault("no_email_statement", False)
    values.setdefault("send_collections", False)
    values.setdefault("is_finance_charge", False)
    explicit_no = values.pop("account_no", None)
    res = conn.execute(insert(acc).values(tenant_id=tenant_id, created_at=datetime.utcnow(), **values))
    new_id = res.inserted_primary_key[0]
    no = explicit_no or next_account_no(conn, tenant_id, new_id)
    conn.execute(update(acc).where(acc.c.id == new_id).values(account_no=no))
    return new_id


def party_account_id(conn, tenant_id: int, party_id: int) -> int | None:  # noqa: ANN001
    """The active account a non-patient party is primary on, else one it is an
    additional party on."""
    acc = Account.__table__
    ap = AccountParty.__table__
    row = conn.execute(
        select(acc.c.id).where(
            acc.c.tenant_id == tenant_id, acc.c.primary_guarantor_party_id == party_id,
            acc.c.is_active.is_(True),
        ).order_by(acc.c.id)
    ).first()
    if row is not None:
        return row[0]
    row = conn.execute(
        select(ap.c.account_id).where(
            ap.c.tenant_id == tenant_id, ap.c.responsible_party_id == party_id,
            ap.c.is_active.is_(True),
        ).order_by(ap.c.id)
    ).first()
    return row[0] if row is not None else None


def resolve_legacy_key(
    conn, tenant_id: int, key: str, *, migrated: bool  # noqa: ANN001
) -> dict[str, Any]:
    """Resolve a pre-RP-1 ``responsible_party_id`` string to
    ``{account_id, guarantor_patient_id, guarantor_party_id, kind}``.

    Same precedence as the migration backfill: for an **app-created** patient a
    numeric key is a ``responsible_parties.id`` first (what ``/patients/register``
    wrote), then another patient's id (head of household); a **migrated** patient's
    key is always a Denticon RPID. Then an account already grouped by that key,
    then an imported RP row with that ``legacy_id``. ``kind='unresolved'`` = none
    of those (the account is created grouped by the key, guarantor unknown)."""
    pt = _patients()
    rp = _parties()
    acc = Account.__table__
    out: dict[str, Any] = {
        "account_id": None, "guarantor_patient_id": None, "guarantor_party_id": None,
        "kind": "unresolved",
    }
    if not migrated and key.isdigit() and len(key) <= 9:
        num = int(key)
        party = conn.execute(
            select(rp.c.id).where(rp.c.id == num, rp.c.tenant_id == tenant_id)
        ).first()
        if party is not None:
            out.update(guarantor_party_id=num, kind="responsible_party",
                       account_id=party_account_id(conn, tenant_id, num))
            return out
        head = conn.execute(
            select(pt.c.id, pt.c.account_id).where(pt.c.id == num, pt.c.tenant_id == tenant_id)
        ).first()
        if head is not None:
            out.update(guarantor_patient_id=num, kind="patient", account_id=head[1])
            return out
    grouped = conn.execute(
        select(acc.c.id, acc.c.primary_guarantor_patient_id, acc.c.primary_guarantor_party_id)
        .where(acc.c.tenant_id == tenant_id, acc.c.legacy_key == key, acc.c.is_active.is_(True))
        .order_by(acc.c.id)
    ).first()
    if grouped is not None:
        out["account_id"] = grouped[0]
        if grouped[1] is not None:
            out.update(guarantor_patient_id=grouped[1], kind="patient")
        elif grouped[2] is not None:
            out.update(guarantor_party_id=grouped[2], kind="responsible_party")
        return out
    party = conn.execute(
        select(rp.c.id).where(rp.c.tenant_id == tenant_id, rp.c.legacy_id == key).order_by(rp.c.id)
    ).first()
    if party is not None:
        out.update(guarantor_party_id=party[0], kind="responsible_party",
                   account_id=party_account_id(conn, tenant_id, party[0]))
    return out


def _billing_seed_from_patient(target) -> dict:  # noqa: ANN001
    return {
        "home_office_id": target.home_office_id,
        "send_statements": True if target.send_statements is None else bool(target.send_statements),
        "send_collections": bool(target.send_collections),
        "is_finance_charge": bool(target.is_finance_charge),
    }


def billing_seed_from_party(conn, party_id: int) -> dict:  # noqa: ANN001
    rp = _parties()
    row = conn.execute(select(rp).where(rp.c.id == party_id)).mappings().first()
    if row is None:
        return {}
    return {
        "home_office_id": row["home_office_id"],
        "send_statements": True if row["send_statements"] is None else bool(row["send_statements"]),
        "no_email_statement": bool(row["no_email_statement"]),
        "send_collections": bool(row["send_collections"]),
        "is_finance_charge": bool(row["is_finance_charge"]),
        "collection_agency_id": row["collection_agency_id"],
        "statement_message": row["statement_message"],
        "financial_notes": row["financial_notes"],
    }


# ── ORM hooks: every inserted patient has an account (RP-4) ───────────────────
def _patient_before_insert(mapper, connection, target) -> None:  # noqa: ANN001, ARG001
    target._rp_self = False
    target._rp_unresolved = False
    tenant_id = target.tenant_id
    if target.account_id is not None:
        if target.guarantor_patient_id is None and target.guarantor_party_id is None:
            target._rp_self = True
        return
    pt = _patients()
    if target.guarantor_patient_id is not None:
        row = connection.execute(
            select(pt.c.account_id).where(pt.c.id == target.guarantor_patient_id)
        ).first()
        target.account_id = row[0] if row is not None else None
    elif target.guarantor_party_id is not None:
        target.account_id = party_account_id(connection, tenant_id, target.guarantor_party_id)
        if target.account_id is None:
            seed = billing_seed_from_party(connection, target.guarantor_party_id)
            seed["home_office_id"] = seed.get("home_office_id") or target.home_office_id
            target.account_id = create_account_row(
                connection, tenant_id, primary_guarantor_party_id=target.guarantor_party_id,
                created_by=target.created_by, **seed,
            )
    else:
        key = (target.responsible_party_id or "").strip()
        if key:
            res = resolve_legacy_key(connection, tenant_id, key, migrated=target.legacy_id is not None)
            target.guarantor_patient_id = res["guarantor_patient_id"]
            target.guarantor_party_id = res["guarantor_party_id"]
            target.account_id = res["account_id"]
            if res["kind"] == "unresolved":
                target._rp_unresolved = True
                if target.account_id is None:
                    target.account_id = create_account_row(
                        connection, tenant_id, legacy_key=key, account_no=_free_account_no(connection, tenant_id, key),
                        created_by=target.created_by, **_billing_seed_from_patient(target),
                    )
                return
            if target.account_id is None and target.guarantor_party_id is not None:
                seed = billing_seed_from_party(connection, target.guarantor_party_id)
                seed["home_office_id"] = seed.get("home_office_id") or target.home_office_id
                target.account_id = create_account_row(
                    connection, tenant_id, primary_guarantor_party_id=target.guarantor_party_id,
                    created_by=target.created_by, **seed,
                )
        else:
            target._rp_self = True
    if target.account_id is None:
        # Self, or a guarantor patient that predates accounts: a new account.
        target._rp_self = target.guarantor_patient_id is None and target.guarantor_party_id is None
        target.account_id = create_account_row(
            connection, tenant_id, created_by=target.created_by,
            primary_guarantor_patient_id=target.guarantor_patient_id,
            **_billing_seed_from_patient(target),
        )


def _patient_after_insert(mapper, connection, target) -> None:  # noqa: ANN001, ARG001
    pt = _patients()
    acc = Account.__table__
    values: dict[str, Any] = {}
    if getattr(target, "_rp_self", False):
        values["guarantor_patient_id"] = target.id
        values["responsible_party_id"] = str(target.id)
        if not target.responsible_party_relationship:
            values["responsible_party_relationship"] = SELF_RELATIONSHIP
        connection.execute(
            update(acc).where(
                acc.c.id == target.account_id,
                acc.c.primary_guarantor_patient_id.is_(None),
                acc.c.primary_guarantor_party_id.is_(None),
                acc.c.legacy_key.is_(None),
            ).values(primary_guarantor_patient_id=target.id)
        )
    elif not getattr(target, "_rp_unresolved", False):
        alias = (
            str(target.guarantor_patient_id) if target.guarantor_patient_id is not None
            else str(target.guarantor_party_id) if target.guarantor_party_id is not None
            else None
        )
        if alias and not (target.responsible_party_id or "").strip():
            values["responsible_party_id"] = alias
    if values:
        connection.execute(update(pt).where(pt.c.id == target.id).values(**values))
        for k, v in values.items():
            set_committed_value(target, k, v)


def _stamp_account_from_patient(mapper, connection, target) -> None:  # noqa: ANN001, ARG001
    if getattr(target, "account_id", None) is not None or target.patient_id is None:
        return
    pt = _patients()
    row = connection.execute(select(pt.c.account_id).where(pt.c.id == target.patient_id)).first()
    if row is not None:
        target.account_id = row[0]


def _install() -> None:
    from app.db.models.billing import PatientPayment, PatientStatement
    from app.db.models.patients import Patient

    if not event.contains(Patient, "before_insert", _patient_before_insert):
        event.listen(Patient, "before_insert", _patient_before_insert)
        event.listen(Patient, "after_insert", _patient_after_insert)
        event.listen(PatientPayment, "before_insert", _stamp_account_from_patient)
        event.listen(PatientStatement, "before_insert", _stamp_account_from_patient)
