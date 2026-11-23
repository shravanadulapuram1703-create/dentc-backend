"""Family accounts & guarantors — the one home for RP-1 … RP-16.

Every rule about *who is responsible for a patient* lives here:

* **Guarantor payload** (RP-2/RP-11): ``guarantor_payload`` / ``guarantors_for``
  return the discriminated ``{kind: self|patient|responsible_party|unresolved}``
  shape from the typed columns — never by guessing which table a number in
  ``responsible_party_id`` belongs to.
* **Linking** (RP-5/RP-7): ``resolve_spec`` turns any of
  ``is_self > guarantor_patient_id > account_id > person > responsible_party_id``
  into a validated target, and ``apply_target`` writes it (no commit), keeping the
  legacy ``responsible_party_id`` alias in step (``sync_alias``).
* **Moves** (RP-6): ``change_guarantor`` (dependents, balance transfer, empty
  account retirement, audit event, cache invalidation) and ``merge_accounts``.
* **Parties** (RP-8): the primary lives on the account; ``account_parties`` holds
  at most two more.
* **Billing** (RP-9): ``post_account_payment`` splits one guarantor payment into
  per-member ``patient_payments`` rows sharing an ``account_payment_id``;
  ``generate_account_statement`` writes one statement per account addressed to
  the guarantor with member sections.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.db.models import (
    Account,
    AccountChangeEvent,
    AccountParty,
    InsuranceCarrier,
    InsurancePlan,
    InsuranceSubscriber,
    Patient,
    PatientInsurance,
    PatientPayment,
    PatientProcedure,
    PatientStatement,
    ResponsibleParty,
)
from app.db.models.accounts import (
    ADDITIONAL_PARTY_ROLES,
    MAX_ACCOUNT_PARTIES,
    SELF_RELATIONSHIP,
    billing_seed_from_party,
    create_account_row,
    party_account_id,
    resolve_legacy_key,
)
from app.integrations import redis_store
from app.services import patient_rules_service as rules

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
GUARANTOR_KINDS = ("self", "patient", "responsible_party", "unresolved")
SPEC_PRECEDENCE = ("is_self", "guarantor_patient_id", "account_id", "person", "responsible_party_id")
ACCOUNT_BILLING_FIELDS = (
    "account_no", "home_office_id", "send_statements", "no_email_statement", "send_collections",
    "collection_agency_id", "is_finance_charge", "statement_message", "financial_notes", "notes",
    "is_active",
)
DISTRIBUTE_MODES = ("oldest_first", "by_member")


def _d(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _name(obj: Any) -> str | None:
    if obj is None:
        return None
    return ", ".join(x for x in (obj.last_name, obj.first_name) if x) or None


def _invalidate_balance(tenant_id: int, patient_ids) -> None:  # noqa: ANN001
    keys = [f"balance:{tenant_id}:{pid}" for pid in patient_ids]
    if keys:
        redis_store.cache_delete(*keys)


# ── loading ───────────────────────────────────────────────────────────────────
def load_patient(db: Session, tenant_id: int, patient_id: int) -> Patient:
    row = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return row


def load_account(db: Session, tenant_id: int, account_id: int) -> Account:
    row = db.execute(
        select(Account).where(Account.id == account_id, Account.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Account '{account_id}' was not found")
    return row


def ensure_account(db: Session, patient: Patient) -> Account:
    """The patient's account; one is created (Self) for a row the importer wrote
    by raw SQL after the backfill ran."""
    if patient.account_id is not None:
        acc = db.get(Account, patient.account_id)
        if acc is not None:
            return acc
    conn = db.connection()
    guarantor_self = patient.guarantor_patient_id is None and patient.guarantor_party_id is None
    acc_id = create_account_row(
        conn, patient.tenant_id, home_office_id=patient.home_office_id,
        primary_guarantor_patient_id=patient.id if guarantor_self else patient.guarantor_patient_id,
        primary_guarantor_party_id=None if guarantor_self else patient.guarantor_party_id,
    )
    patient.account_id = acc_id
    if guarantor_self:
        patient.guarantor_patient_id = patient.id
    db.flush()
    return db.get(Account, acc_id)


def members_of(db: Session, account_id: int | None, tenant_id: int) -> list[Patient]:
    if account_id is None:
        return []
    return list(db.execute(
        select(Patient).where(Patient.tenant_id == tenant_id, Patient.account_id == account_id)
        .order_by(Patient.last_name, Patient.first_name, Patient.id)
    ).scalars())


# ── RP-2 / RP-11: guarantor payload ───────────────────────────────────────────
def guarantor_kind(patient: Patient) -> str:
    if patient.guarantor_patient_id is not None:
        return "self" if patient.guarantor_patient_id == patient.id else "patient"
    if patient.guarantor_party_id is not None:
        return "responsible_party"
    return "unresolved"


def _payload(patient: Patient, person: Any, kind: str) -> dict:
    return {
        "kind": kind,
        "id": (patient.guarantor_party_id if kind == "responsible_party"
               else patient.guarantor_patient_id),
        "patient_id": patient.guarantor_patient_id if kind in ("self", "patient") else None,
        "responsible_party_id": patient.guarantor_party_id if kind == "responsible_party" else None,
        "account_id": patient.account_id,
        "name": _name(person),
        "first_name": getattr(person, "first_name", None),
        "last_name": getattr(person, "last_name", None),
        "cell_phone": getattr(person, "cell_phone", None),
        "home_phone": (getattr(person, "home_phone", None) if kind == "responsible_party"
                       else getattr(person, "phone", None)),
        "email": getattr(person, "email", None),
        "home_office_id": getattr(person, "home_office_id", None),
        "relationship": patient.responsible_party_relationship,
        "resp_party_type": getattr(person, "resp_party_type", None) if kind == "responsible_party" else None,
        "legacy_id": getattr(person, "legacy_id", None) if person is not None else (
            (patient.responsible_party_id or None) if kind == "unresolved" else None),
    }


def guarantors_for(db: Session, patients) -> dict[int, dict]:  # noqa: ANN001
    """Batched guarantor payload per patient — two statements for any page."""
    rows = [p for p in patients if p is not None]
    pids = {p.guarantor_patient_id for p in rows if p.guarantor_patient_id is not None}
    pids -= {p.id for p in rows}
    by_pid = {p.id: p for p in rows}
    if pids:
        by_pid.update({p.id: p for p in db.execute(select(Patient).where(Patient.id.in_(pids))).scalars()})
    rpids = {p.guarantor_party_id for p in rows if p.guarantor_party_id is not None}
    by_rp = {r.id: r for r in db.execute(
        select(ResponsibleParty).where(ResponsibleParty.id.in_(rpids))).scalars()} if rpids else {}
    late = _late_imported_parties(db, [p for p in rows if guarantor_kind(p) == "unresolved"])
    out = {}
    for p in rows:
        kind = guarantor_kind(p)
        person = (by_pid.get(p.guarantor_patient_id) if kind in ("self", "patient")
                  else by_rp.get(p.guarantor_party_id) if kind == "responsible_party" else None)
        if kind == "unresolved" and p.id in late:
            person = late[p.id]
            payload = _payload(p, person, "responsible_party")
            payload.update(id=person.id, responsible_party_id=person.id)
            out[p.id] = payload
            continue
        out[p.id] = _payload(p, person, kind)
    return out


def _late_imported_parties(db: Session, unresolved) -> dict[int, ResponsibleParty]:  # noqa: ANN001
    """A migrated, unresolved RPID whose guarantor was imported *after* the
    backfill (RP-14) is resolved at read time by ``legacy_id`` — the pre-RP
    behaviour — until ``import_legacy_responsible_parties`` links it."""
    keys = {(p.tenant_id, (p.responsible_party_id or "").strip()) for p in unresolved}
    keys = {k for k in keys if k[1]}
    if not keys:
        return {}
    rows = db.execute(select(ResponsibleParty).where(
        ResponsibleParty.legacy_id.in_({k for _, k in keys}),
        ResponsibleParty.tenant_id.in_({t for t, _ in keys}),
    ).order_by(ResponsibleParty.id)).scalars().all()
    by_key: dict[tuple, ResponsibleParty] = {}
    for r in rows:
        by_key.setdefault((r.tenant_id, r.legacy_id), r)
    return {p.id: by_key[(p.tenant_id, (p.responsible_party_id or "").strip())]
            for p in unresolved
            if (p.tenant_id, (p.responsible_party_id or "").strip()) in by_key}


def guarantor_payload(db: Session, patient: Patient) -> dict:
    return guarantors_for(db, [patient])[patient.id]


def guarantor_person(db: Session, patient: Patient):  # noqa: ANN201
    """The guarantor as an object with the shared demographic attributes
    (``first_name``/``last_name``/``middle_initial``/``address_line1``/``city``/
    ``state``/``zip``/``email``/``legacy_id``) — a ``Patient`` for self/head of
    household, a ``ResponsibleParty`` for a non-patient, ``None`` if unresolved.
    Letters, prints and contracts use it instead of resolving the raw string."""
    if patient.guarantor_patient_id is not None:
        return patient if patient.guarantor_patient_id == patient.id else db.get(
            Patient, patient.guarantor_patient_id)
    if patient.guarantor_party_id is not None:
        return db.get(ResponsibleParty, patient.guarantor_party_id)
    return _late_imported_parties(db, [patient]).get(patient.id)


def sync_alias(patient: Patient) -> None:
    """RP-1: the deprecated ``responsible_party_id`` string = the guarantor's key."""
    if patient.guarantor_patient_id is not None:
        patient.responsible_party_id = str(patient.guarantor_patient_id)
    elif patient.guarantor_party_id is not None:
        patient.responsible_party_id = str(patient.guarantor_party_id)


def _primary_payload(db: Session, account: Account) -> dict:
    if account.primary_guarantor_patient_id is not None:
        person = db.get(Patient, account.primary_guarantor_patient_id)
        kind = "patient"
    elif account.primary_guarantor_party_id is not None:
        person = db.get(ResponsibleParty, account.primary_guarantor_party_id)
        kind = "responsible_party"
    else:
        person, kind = None, "unresolved"
    return {
        "kind": kind,
        "patient_id": account.primary_guarantor_patient_id,
        "responsible_party_id": account.primary_guarantor_party_id,
        "name": _name(person),
        "first_name": getattr(person, "first_name", None),
        "last_name": getattr(person, "last_name", None),
        "address_line1": getattr(person, "address_line1", None),
        "address_line2": getattr(person, "address_line2", None),
        "city": getattr(person, "city", None), "state": getattr(person, "state", None),
        "zip": getattr(person, "zip", None), "email": getattr(person, "email", None),
        "cell_phone": getattr(person, "cell_phone", None),
        "legacy_id": getattr(person, "legacy_id", None) if person else account.legacy_key,
    }


# ── RP-5 / RP-7: resolve a guarantor spec ─────────────────────────────────────
def _guarantor_patient(db: Session, tenant_id: int, pid: int) -> Patient:
    g = db.execute(
        select(Patient).where(Patient.id == pid, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if g is None:
        raise ValidationError(
            f"Guarantor patient '{pid}' was not found",
            details={"code": "guarantor_patient_not_found", "field": "guarantor_patient_id"},
        )
    if g.is_active is False:
        raise ValidationError(
            "An inactive patient cannot be a guarantor",
            details={"code": "guarantor_patient_inactive", "field": "guarantor_patient_id"},
        )
    return g


def _party(db: Session, tenant_id: int, party_id: int) -> ResponsibleParty:
    rp = db.execute(
        select(ResponsibleParty).where(
            ResponsibleParty.id == party_id, ResponsibleParty.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if rp is None:
        raise ValidationError(
            f"Responsible party '{party_id}' was not found",
            details={"code": "responsible_party_not_found", "field": "responsible_party_id"},
        )
    if rp.is_active is False:
        raise ValidationError(
            "An inactive responsible party cannot be a guarantor",
            details={"code": "responsible_party_inactive", "field": "responsible_party_id"},
        )
    return rp


def resolve_spec(
    db: Session, tenant_id: int, spec: dict, *, patient: Patient | None = None,
    user_id: int | None = None,
) -> dict:
    """Validate a guarantor spec and return ``{kind, account_id, guarantor_patient_id,
    guarantor_party_id}``. ``kind='self'`` with ``account_id=None`` means "a new
    account" (or the patient's current one when they already head it).

    A ``person`` is created here (flush only) so the caller's transaction owns it.
    """
    account_id = spec.get("account_id")
    if spec.get("is_self"):
        if account_id is not None:
            load_account(db, tenant_id, account_id)
        return {"kind": "self", "account_id": account_id,
                "guarantor_patient_id": patient.id if patient is not None else None,
                "guarantor_party_id": None}
    gpid = spec.get("guarantor_patient_id")
    if gpid is not None:
        if patient is not None and gpid == patient.id:
            return resolve_spec(db, tenant_id, {"is_self": True, "account_id": account_id},
                                patient=patient)
        g = _guarantor_patient(db, tenant_id, gpid)
        acc = ensure_account(db, g)
        if account_id is not None and account_id != acc.id:
            raise ValidationError(
                "The guarantor patient is on a different account",
                details={"code": "guarantor_not_on_account", "field": "account_id",
                         "guarantor_account_id": acc.id},
            )
        return {"kind": "patient", "account_id": acc.id, "guarantor_patient_id": g.id,
                "guarantor_party_id": None}
    if account_id is not None:
        acc = load_account(db, tenant_id, account_id)
        if not acc.is_active:
            raise ValidationError(
                "That account is closed",
                details={"code": "account_inactive", "field": "account_id",
                         "merged_into_account_id": acc.merged_into_account_id},
            )
        if acc.primary_guarantor_patient_id is not None:
            return {"kind": "patient", "account_id": acc.id,
                    "guarantor_patient_id": acc.primary_guarantor_patient_id,
                    "guarantor_party_id": None}
        if acc.primary_guarantor_party_id is not None:
            return {"kind": "responsible_party", "account_id": acc.id,
                    "guarantor_patient_id": None,
                    "guarantor_party_id": acc.primary_guarantor_party_id}
        raise ValidationError(
            "That account has no resolved guarantor to join under",
            details={"code": "account_has_no_guarantor", "field": "account_id"},
        )
    person = spec.get("person")
    if person:
        data = dict(person)
        rules.fold_middle_name(data)
        rp = ResponsibleParty(tenant_id=tenant_id, created_by=user_id, **data)
        db.add(rp)
        db.flush()
        return {"kind": "responsible_party", "account_id": None, "guarantor_patient_id": None,
                "guarantor_party_id": rp.id, "created_party": True}
    rpid = spec.get("responsible_party_id")
    if rpid is not None and str(rpid).strip():
        key = str(rpid).strip()
        # A key the patient already holds is an unchanged alias, not a new link.
        if patient is not None and key == (patient.responsible_party_id or "").strip():
            return {"kind": "unchanged"}
        if isinstance(rpid, int) or (key.isdigit() and not (patient is not None and patient.legacy_id)):
            row = db.execute(select(ResponsibleParty.id).where(
                ResponsibleParty.id == int(key), ResponsibleParty.tenant_id == tenant_id)).first()
            if row is not None:
                _party(db, tenant_id, row[0])
                return {"kind": "responsible_party",
                        "account_id": party_account_id(db.connection(), tenant_id, row[0]),
                        "guarantor_patient_id": None, "guarantor_party_id": row[0]}
        res = resolve_legacy_key(db.connection(), tenant_id, key,
                                 migrated=bool(patient is not None and patient.legacy_id))
        if res["kind"] == "patient":
            return resolve_spec(db, tenant_id, {"guarantor_patient_id": res["guarantor_patient_id"]},
                                patient=patient)
        if res["kind"] == "responsible_party":
            _party(db, tenant_id, res["guarantor_party_id"])
            return {"kind": "responsible_party", "account_id": res["account_id"],
                    "guarantor_patient_id": None, "guarantor_party_id": res["guarantor_party_id"]}
        if res["account_id"] is not None:  # a known, still-unresolved legacy account
            return {"kind": "unresolved", "account_id": res["account_id"],
                    "guarantor_patient_id": None, "guarantor_party_id": None}
        raise ValidationError(
            f"responsible_party_id '{key}' matches no responsible party, patient or legacy account",
            details={"code": "responsible_party_not_found", "field": "responsible_party_id"},
        )
    raise ValidationError(
        "A guarantor is required: send is_self, guarantor_patient_id, account_id, person "
        "or responsible_party_id",
        details={"code": "guarantor_required", "precedence": list(SPEC_PRECEDENCE)},
    )


def _new_account_for(db: Session, patient: Patient, target: dict, user_id: int | None) -> int:
    conn = db.connection()
    if target["kind"] == "responsible_party":
        seed = billing_seed_from_party(conn, target["guarantor_party_id"])
        seed["home_office_id"] = seed.get("home_office_id") or patient.home_office_id
        return create_account_row(conn, patient.tenant_id, created_by=user_id,
                                  primary_guarantor_party_id=target["guarantor_party_id"], **seed)
    return create_account_row(
        conn, patient.tenant_id, created_by=user_id, home_office_id=patient.home_office_id,
        primary_guarantor_patient_id=patient.id,
        send_statements=True if patient.send_statements is None else bool(patient.send_statements),
        send_collections=bool(patient.send_collections),
        is_finance_charge=bool(patient.is_finance_charge),
    )


def apply_target(
    db: Session, patient: Patient, target: dict, *, relationship: Any = None,
    user_id: int | None = None, keep_current_account_for_self: bool = True,
) -> None:
    """Write a resolved target onto an already-flushed patient (no commit)."""
    if target.get("kind") == "unchanged":
        if relationship is not None:
            patient.responsible_party_relationship = rules.normalize_resp_party_relationship(relationship)
        return
    kind = target["kind"]
    account_id = target.get("account_id")
    if kind == "self":
        patient.guarantor_patient_id = patient.id
        patient.guarantor_party_id = None
        if account_id is None:
            current = db.get(Account, patient.account_id) if patient.account_id else None
            heads_current = current is not None and (
                current.primary_guarantor_patient_id == patient.id
                or (current.primary_guarantor_patient_id is None
                    and current.primary_guarantor_party_id is None
                    and len(members_of(db, current.id, patient.tenant_id)) <= 1)
            )
            if keep_current_account_for_self and heads_current:
                account_id = current.id
                if current.primary_guarantor_patient_id is None:
                    current.primary_guarantor_patient_id = patient.id
            else:
                account_id = _new_account_for(db, patient, target, user_id)
        patient.account_id = account_id
        patient.responsible_party_relationship = SELF_RELATIONSHIP
    else:
        patient.guarantor_patient_id = target.get("guarantor_patient_id")
        patient.guarantor_party_id = target.get("guarantor_party_id")
        if account_id is None:
            account_id = _new_account_for(db, patient, target, user_id)
        patient.account_id = account_id
        if relationship is not None:
            patient.responsible_party_relationship = rules.normalize_resp_party_relationship(relationship)
    sync_alias(patient)
    db.flush()


# ── RP-3: account read / update ───────────────────────────────────────────────
def _member_rows(db: Session, account: Account, tenant_id: int) -> list[dict]:
    from app.services import balance_service, patient_intake_service

    members = members_of(db, account.id, tenant_id)
    today = date.today()
    out = []
    for p in members:
        row = patient_intake_service._member_row(db, tenant_id, p, today)
        row.update({
            "dob": p.dob, "relationship": p.responsible_party_relationship,
            "guarantor_kind": guarantor_kind(p),
            "is_guarantor": p.id == account.primary_guarantor_patient_id,
            "next_recall": p.next_recall,
        })
        out.append(row)
    _ = balance_service
    return out


def account_out(db: Session, account: Account, *, include_members: bool = True) -> dict:
    tenant_id = account.tenant_id
    parties = list_parties(db, tenant_id, account.id)
    out = {
        "id": account.id, "tenant_id": tenant_id, "account_no": account.account_no,
        "legacy_key": account.legacy_key,
        "primary_guarantor_patient_id": account.primary_guarantor_patient_id,
        "primary_guarantor_party_id": account.primary_guarantor_party_id,
        "primary_guarantor": _primary_payload(db, account),
        **{f: getattr(account, f) for f in ACCOUNT_BILLING_FIELDS if f != "account_no"},
        "merged_into_account_id": account.merged_into_account_id,
        "merged_at": account.merged_at,
        "created_at": account.created_at, "updated_at": account.updated_at,
        "created_by": account.created_by, "updated_by": account.updated_by,
        "parties": parties,
    }
    if include_members:
        members = _member_rows(db, account, tenant_id)
        out["members"] = members
        out["member_count"] = len(members)
        out["balance"] = round(sum(m.get("balance") or 0 for m in members), 2)
    else:
        out["member_count"] = db.execute(
            select(func.count(Patient.id)).where(Patient.account_id == account.id)).scalar_one()
    return out


def get_account(db: Session, tenant_id: int, account_id: int) -> dict:
    return account_out(db, load_account(db, tenant_id, account_id))


def get_patient_account(db: Session, tenant_id: int, patient_id: int) -> dict:
    patient = load_patient(db, tenant_id, patient_id)
    acc = ensure_account(db, patient)
    db.commit()
    out = account_out(db, acc)
    out["patient_id"] = patient.id
    out["guarantor"] = guarantor_payload(db, patient)
    return out


def list_accounts(
    db: Session, tenant_id: int, *, search: str | None = None, account_no: str | None = None,
    is_active: bool | None = True, page: int = 1, size: int = 50,
) -> dict:
    stmt = select(Account).where(Account.tenant_id == tenant_id)
    if is_active is not None:
        stmt = stmt.where(Account.is_active.is_(is_active))
    if account_no:
        stmt = stmt.where(Account.account_no == account_no.strip())
    term = (search or "").strip()
    if term:
        like = f"%{term.lower()}%"
        pmatch = select(Patient.account_id).where(
            Patient.tenant_id == tenant_id,
            or_(func.lower(Patient.last_name).like(like), func.lower(Patient.first_name).like(like)),
        )
        rpmatch = select(ResponsibleParty.id).where(
            ResponsibleParty.tenant_id == tenant_id,
            or_(func.lower(ResponsibleParty.last_name).like(like),
                func.lower(ResponsibleParty.first_name).like(like)),
        )
        stmt = stmt.where(or_(
            Account.account_no == term, Account.legacy_key == term,
            Account.id.in_(pmatch), Account.primary_guarantor_party_id.in_(rpmatch),
        ))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Account.id).offset((page - 1) * size).limit(size)).scalars().all()
    return {"items": [account_out(db, a, include_members=False) for a in rows],
            "total": total, "page": page, "size": size,
            "pages": (total + size - 1) // size if size else 0}


def update_account(db: Session, tenant_id: int, account_id: int, payload: dict,
                   *, user_id: int | None = None) -> dict:
    acc = load_account(db, tenant_id, account_id)
    changes = {}
    for field, value in payload.items():
        if field not in ACCOUNT_BILLING_FIELDS:
            continue
        if field == "account_no":
            value = (value or "").strip() or None
            if value is None:
                raise ValidationError("account_no cannot be blank",
                                      details={"code": "account_no_required", "field": "account_no"})
            taken = db.execute(select(Account.id).where(
                Account.tenant_id == tenant_id, Account.account_no == value,
                Account.id != acc.id)).first()
            if taken is not None:
                raise ConflictError("That account number is already in use",
                                    details={"code": "duplicate_account_no", "field": "account_no",
                                             "account_id": taken[0]})
        if getattr(acc, field) != value:
            changes[field] = {"before": getattr(acc, field), "after": value}
            setattr(acc, field, value)
    if changes:
        acc.updated_by = user_id
        acc.updated_at = datetime.utcnow()
        _event(db, tenant_id, "account_updated", user_id=user_id, old_account_id=acc.id,
               new_account_id=acc.id, details={"changes": _jsonable(changes)})
    db.commit()
    return get_account(db, tenant_id, account_id)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _event(db: Session, tenant_id: int, action: str, **kw: Any) -> AccountChangeEvent:
    ev = AccountChangeEvent(tenant_id=tenant_id, action=action, **{
        k: (_jsonable(v) if k in ("old_guarantor", "new_guarantor", "details") else v)
        for k, v in kw.items()})
    db.add(ev)
    return ev


# ── RP-6: change guarantor / move between accounts ───────────────────────────
def _patient_balance(db: Session, tenant_id: int, patient_id: int) -> Decimal:
    from app.services import balance_service

    return _d(balance_service.patient_balance_core(db, patient_id, tenant_id)["balance"])


def _transfer_balance(
    db: Session, tenant_id: int, patient: Patient, to_member: Patient, amount: Decimal,
    old_account_id: int, *, user_id: int | None, on: date,
) -> list[str]:
    """Leave ``amount`` with the old account: a credit adjustment on the moving
    patient and the matching debit on a remaining member (AL-9: an
    ``adjustment`` row's sign is its intent). Both carry one ``account_payment_id``."""
    group = f"XFER-{uuid7()}"
    note = (f"Balance transfer: {patient.id} moved off account {old_account_id}; "
            f"open balance left with {to_member.id}")
    rows = [
        PatientPayment(id=f"XF-{uuid7()}", patient_id=patient.id, account_id=old_account_id,
                       account_payment_id=group, payment_date=on, amount=-amount,
                       payment_type="adjustment", payment_method="balance_transfer",
                       office_id=patient.home_office_id, notes=note, created_by=user_id),
        PatientPayment(id=f"XF-{uuid7()}", patient_id=to_member.id, account_id=old_account_id,
                       account_payment_id=group, payment_date=on, amount=amount,
                       payment_type="adjustment", payment_method="balance_transfer",
                       office_id=to_member.home_office_id, notes=note, created_by=user_id),
    ]
    db.add_all(rows)
    db.flush()
    return [r.id for r in rows]


def _retire_if_empty(db: Session, tenant_id: int, account_id: int | None, *,
                     user_id: int | None) -> bool:
    if account_id is None:
        return False
    if members_of(db, account_id, tenant_id):
        return False
    acc = db.get(Account, account_id)
    if acc is None or not acc.is_active:
        return False
    acc.is_active = False
    acc.updated_by = user_id
    acc.updated_at = datetime.utcnow()
    for party in db.execute(select(AccountParty).where(
            AccountParty.account_id == account_id, AccountParty.is_active.is_(True))).scalars():
        party.is_active = False
    return True


def change_guarantor(db: Session, tenant_id: int, patient_id: int, payload: dict,
                     *, user_id: int | None = None) -> dict:
    """``POST /patients/{id}/change-guarantor`` (RP-6). One transaction."""
    try:
        return _change_guarantor(db, tenant_id, patient_id, payload, user_id=user_id)
    except Exception:
        db.rollback()
        raise


def _change_guarantor(db: Session, tenant_id: int, patient_id: int, payload: dict,
                      *, user_id: int | None) -> dict:
    patient = load_patient(db, tenant_id, patient_id)
    ensure_account(db, patient)
    old_account_id = patient.account_id
    old_guarantor = guarantor_payload(db, patient)
    move_balance = payload.get("move_open_balance", True)
    include_dependents = bool(payload.get("include_dependents"))
    effective = payload.get("effective_date") or date.today()

    dependents = [m for m in members_of(db, old_account_id, tenant_id)
                  if m.id != patient.id and m.guarantor_patient_id == patient.id]
    target = resolve_spec(db, tenant_id, payload, patient=patient, user_id=user_id)
    if target.get("kind") == "unchanged":
        target = {"kind": guarantor_kind(patient), "account_id": patient.account_id,
                  "guarantor_patient_id": patient.guarantor_patient_id,
                  "guarantor_party_id": patient.guarantor_party_id}
    if target["kind"] == "patient" and target["guarantor_patient_id"] in {d.id for d in dependents}:
        raise ValidationError(
            "A patient's own dependent cannot become their guarantor",
            details={"code": "guarantor_cycle", "field": "guarantor_patient_id"},
        )
    leaving = target.get("account_id") != old_account_id
    if dependents and leaving and not include_dependents and target["kind"] != "self":
        raise ConflictError(
            "This patient is the guarantor for other members of the account",
            details={"code": "guarantor_has_dependents",
                     "dependents": [{"patient_id": d.id, "name": _name(d)} for d in dependents],
                     "hint": "send include_dependents=true to move them too"},
        )

    apply_target(db, patient, target, relationship=payload.get("relationship"), user_id=user_id,
                 keep_current_account_for_self=not payload.get("new_account", False))
    new_account_id = patient.account_id
    moved_ids = [patient.id]
    if include_dependents and new_account_id != old_account_id:
        for dep in dependents:
            dep.account_id = new_account_id
            moved_ids.append(dep.id)
    elif dependents and new_account_id != old_account_id:
        # The guarantor left and the dependents stay: the account's primary must
        # still be a member, so it falls to the dependents' own resolution.
        pass
    db.flush()

    # The old account's primary moved away → promote someone who stayed.
    old_acc = db.get(Account, old_account_id) if old_account_id else None
    remaining = members_of(db, old_account_id, tenant_id) if old_account_id else []
    if old_acc is not None and old_acc.primary_guarantor_patient_id in moved_ids and remaining:
        heir = next((m for m in remaining if m.guarantor_patient_id == m.id), remaining[0])
        old_acc.primary_guarantor_patient_id = heir.id
        for m in remaining:
            if m.guarantor_patient_id in moved_ids:
                m.guarantor_patient_id = heir.id
                sync_alias(m)
        heir.guarantor_patient_id = heir.id
        heir.guarantor_party_id = None
        sync_alias(heir)

    transfer_ids: list[str] = []
    moved_balance = ZERO
    balance_left = False
    if new_account_id != old_account_id:
        for pid in moved_ids:
            moved_balance += _patient_balance(db, tenant_id, pid)
        if move_balance is False and remaining:
            to_member = next((m for m in remaining if m.id == (old_acc.primary_guarantor_patient_id
                                                              if old_acc else None)), remaining[0])
            for pid in moved_ids:
                amount = _patient_balance(db, tenant_id, pid)
                if amount != ZERO:
                    mover = db.get(Patient, pid)
                    transfer_ids += _transfer_balance(db, tenant_id, mover, to_member, amount,
                                                      old_account_id, user_id=user_id, on=effective)
            balance_left = True
    retired = _retire_if_empty(db, tenant_id, old_account_id, user_id=user_id) \
        if new_account_id != old_account_id else False

    new_guarantor = guarantor_payload(db, patient)
    ev = _event(
        db, tenant_id, "change_guarantor", patient_id=patient.id, user_id=user_id,
        old_account_id=old_account_id, new_account_id=new_account_id,
        old_guarantor=old_guarantor, new_guarantor=new_guarantor,
        move_open_balance=None if new_account_id == old_account_id else bool(move_balance is not False),
        moved_balance=None if new_account_id == old_account_id else moved_balance,
        effective_date=effective,
        details={"moved_patient_ids": moved_ids, "transfer_payment_ids": transfer_ids,
                 "balance_left_with_old_account": balance_left,
                 "old_account_retired": retired,
                 "created_party": bool(target.get("created_party"))},
    )
    db.commit()
    affected = set(moved_ids) | {m.id for m in remaining}
    _invalidate_balance(tenant_id, affected)
    return {
        "patient_id": patient.id,
        "event_id": ev.id,
        "old_account_id": old_account_id,
        "new_account_id": new_account_id,
        "old_guarantor": old_guarantor,
        "guarantor": new_guarantor,
        "moved_patient_ids": moved_ids,
        "moved_balance": float(moved_balance) if new_account_id != old_account_id else 0.0,
        "balance_left_with_old_account": balance_left,
        "transfer_payment_ids": transfer_ids,
        "old_account_retired": retired,
        "old_account": account_out(db, db.get(Account, old_account_id), include_members=False)
        if old_account_id else None,
        "new_account": account_out(db, db.get(Account, new_account_id), include_members=False),
    }


def apply_patch_guarantor(db: Session, tenant_id: int, existing: Patient, payload: dict,
                          *, user_id: int | None) -> dict | None:
    """RP-4/RP-7 on ``PATCH /patients/{id}``: pop the guarantor keys off the
    payload, validate them, apply in the same unit of work. Returns the old/new
    pair for the audit event, or None when the PATCH did not touch them."""
    keys = ("responsible_party_id", "guarantor_patient_id", "guarantor_party_id", "account_id")
    touched = {k: payload.pop(k) for k in keys if k in payload}
    if not touched:
        return None
    if all(v is None or (isinstance(v, str) and not v.strip()) for v in touched.values()):
        # PE-5: an all-blank guarantor block means "not set by this step", not
        # "clear the guarantor" — a patient can never be left without one, so
        # there is no clear to honour. Refusing here 422'd the whole PATCH
        # (fee schedule, demographics, …) for a payload shape the schema
        # advertises as valid. The keys are already popped, so nothing is
        # written; changing the guarantor needs a real value or
        # POST /patients/{id}/change-guarantor.
        return None
    spec: dict[str, Any] = {}
    if touched.get("guarantor_patient_id") is not None:
        spec["guarantor_patient_id"] = touched["guarantor_patient_id"]
    elif touched.get("guarantor_party_id") is not None:
        spec["responsible_party_id"] = int(touched["guarantor_party_id"])
    elif touched.get("account_id") is not None:
        spec["account_id"] = touched["account_id"]
    else:
        spec["responsible_party_id"] = touched.get("responsible_party_id")
    if spec.get("account_id") is not None and touched.get("guarantor_patient_id") is not None:
        spec["account_id"] = touched["account_id"]
    old = guarantor_payload(db, existing)
    old_account = existing.account_id
    target = resolve_spec(db, tenant_id, spec, patient=existing, user_id=user_id)
    if target.get("kind") == "unchanged":
        return None
    if target["kind"] != "self" and target.get("account_id") != old_account:
        dependents = [m for m in members_of(db, old_account, tenant_id)
                      if m.id != existing.id and m.guarantor_patient_id == existing.id]
        if dependents:
            raise ConflictError(
                "This patient is the guarantor for other members of the account",
                details={"code": "guarantor_has_dependents",
                         "dependents": [{"patient_id": d.id, "name": _name(d)} for d in dependents],
                         "hint": "use POST /patients/{id}/change-guarantor with include_dependents"},
            )
    apply_target(db, existing, target, relationship=payload.get("responsible_party_relationship"),
                 user_id=user_id)
    _retire_if_empty(db, tenant_id, old_account, user_id=user_id) \
        if existing.account_id != old_account else None
    _event(db, tenant_id, "change_guarantor", patient_id=existing.id, user_id=user_id,
           old_account_id=old_account, new_account_id=existing.account_id,
           old_guarantor=old, new_guarantor=guarantor_payload(db, existing),
           details={"via": "patch", "fields": sorted(touched)})
    _invalidate_balance(tenant_id, [existing.id])
    return {"old_account_id": old_account, "new_account_id": existing.account_id}


# ── RP-6: merge ───────────────────────────────────────────────────────────────
def merge_accounts(db: Session, tenant_id: int, target_id: int, source_id: int,
                   *, user_id: int | None = None) -> dict:
    if target_id == source_id:
        raise ValidationError("Cannot merge an account into itself",
                              details={"code": "merge_same_account"})
    target = load_account(db, tenant_id, target_id)
    source = load_account(db, tenant_id, source_id)
    if not target.is_active or not source.is_active:
        raise ValidationError("Both accounts must be active",
                              details={"code": "account_inactive"})
    target_parties = _additional_parties(db, target.id)
    source_parties = _additional_parties(db, source.id)
    incoming: list[tuple[int | None, int | None]] = []
    if source.primary_guarantor_party_id is not None:
        incoming.append((None, source.primary_guarantor_party_id))
    elif source.primary_guarantor_patient_id is not None:
        incoming.append((source.primary_guarantor_patient_id, None))
    incoming += [(p.patient_id, p.responsible_party_id) for p in source_parties]
    existing = {(p.patient_id, p.responsible_party_id) for p in target_parties}
    existing.add((target.primary_guarantor_patient_id, None) if target.primary_guarantor_patient_id
                 else (None, target.primary_guarantor_party_id))
    new_parties = [x for x in dict.fromkeys(incoming) if x not in existing]
    if 1 + len(target_parties) + len(new_parties) > MAX_ACCOUNT_PARTIES:
        raise ConflictError(
            f"Merging would give the account more than {MAX_ACCOUNT_PARTIES} responsible parties",
            details={"code": "account_parties_limit", "max": MAX_ACCOUNT_PARTIES,
                     "would_have": 1 + len(target_parties) + len(new_parties)},
        )
    moved = members_of(db, source.id, tenant_id)
    for m in moved:
        m.account_id = target.id
    for p in source_parties:
        p.is_active = False
    order = len(target_parties)
    for patient_id, party_id in new_parties:
        order += 1
        db.add(AccountParty(tenant_id=tenant_id, account_id=target.id, patient_id=patient_id,
                            responsible_party_id=party_id, role="secondary",
                            receives_statements=False, sort_order=order, created_by=user_id))
    source.is_active = False
    source.merged_into_account_id = target.id
    source.merged_at = datetime.utcnow()
    source.updated_by = user_id
    for m in moved:
        _event(db, tenant_id, "merge", patient_id=m.id, user_id=user_id,
               old_account_id=source.id, new_account_id=target.id,
               old_guarantor=guarantor_payload(db, m), new_guarantor=guarantor_payload(db, m))
    if not moved:
        _event(db, tenant_id, "merge", user_id=user_id, old_account_id=source.id,
               new_account_id=target.id)
    db.commit()
    _invalidate_balance(tenant_id, [m.id for m in members_of(db, target.id, tenant_id)])
    return {"account": get_account(db, tenant_id, target.id), "merged_account_id": source.id,
            "moved_patient_ids": [m.id for m in moved],
            "parties_added": len(new_parties)}


# ── RP-8: parties ─────────────────────────────────────────────────────────────
def _additional_parties(db: Session, account_id: int) -> list[AccountParty]:
    return list(db.execute(
        select(AccountParty).where(AccountParty.account_id == account_id,
                                   AccountParty.is_active.is_(True))
        .order_by(AccountParty.sort_order, AccountParty.id)
    ).scalars())


def _party_out(db: Session, row: AccountParty) -> dict:
    person = db.get(Patient, row.patient_id) if row.patient_id else db.get(
        ResponsibleParty, row.responsible_party_id)
    return {
        "id": row.id, "account_id": row.account_id, "role": row.role,
        "patient_id": row.patient_id, "responsible_party_id": row.responsible_party_id,
        "kind": "patient" if row.patient_id else "responsible_party",
        "name": _name(person), "responsibility_pct": row.responsibility_pct,
        "receives_statements": row.receives_statements, "sort_order": row.sort_order,
        "is_active": row.is_active, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def list_parties(db: Session, tenant_id: int, account_id: int) -> list[dict]:
    acc = load_account(db, tenant_id, account_id)
    primary = _primary_payload(db, acc)
    out = [{
        "id": None, "account_id": acc.id, "role": "primary", "kind": primary["kind"],
        "patient_id": acc.primary_guarantor_patient_id,
        "responsible_party_id": acc.primary_guarantor_party_id,
        "name": primary["name"], "responsibility_pct": None,
        "receives_statements": True, "sort_order": 0, "is_active": True,
        "created_at": None, "updated_at": None,
    }]
    out += [_party_out(db, r) for r in _additional_parties(db, acc.id)]
    return out


def _validate_party_person(db: Session, tenant_id: int, acc: Account, data: dict,
                           *, exclude_id: int | None = None) -> tuple[int | None, int | None]:
    pid, rpid = data.get("patient_id"), data.get("responsible_party_id")
    if (pid is None) == (rpid is None):
        raise ValidationError("Send exactly one of patient_id / responsible_party_id",
                              details={"code": "party_person_required"})
    if pid is not None:
        _guarantor_patient(db, tenant_id, pid)
        if pid == acc.primary_guarantor_patient_id:
            raise ConflictError("That patient is already the primary guarantor",
                                details={"code": "party_already_on_account"})
    else:
        _party(db, tenant_id, rpid)
        if rpid == acc.primary_guarantor_party_id:
            raise ConflictError("That party is already the primary guarantor",
                                details={"code": "party_already_on_account"})
    for p in _additional_parties(db, acc.id):
        if p.id != exclude_id and (p.patient_id, p.responsible_party_id) == (pid, rpid):
            raise ConflictError("That person is already a party on this account",
                                details={"code": "party_already_on_account", "party_id": p.id})
    return pid, rpid


def _validate_pct(parties: list[AccountParty], candidate: Decimal | None,
                  exclude_id: int | None = None) -> None:
    if candidate is not None and not (Decimal(0) <= Decimal(candidate) <= Decimal(100)):
        raise ValidationError("responsibility_pct must be between 0 and 100",
                              details={"code": "responsibility_pct_range",
                                       "field": "responsibility_pct"})
    total = sum((Decimal(p.responsibility_pct) for p in parties
                 if p.id != exclude_id and p.responsibility_pct is not None), Decimal(0))
    if candidate is not None and total + Decimal(candidate) > Decimal(100):
        raise ValidationError("Additional parties' responsibility exceeds 100%",
                              details={"code": "responsibility_pct_total",
                                       "field": "responsibility_pct",
                                       "allocated": str(total)})


def _validate_role(role: Any) -> str:
    role = (role or "secondary").strip().lower()
    if role not in ADDITIONAL_PARTY_ROLES:
        raise ValidationError(
            f"role must be one of {', '.join(ADDITIONAL_PARTY_ROLES)} "
            "(the primary is changed with /make-primary)",
            details={"code": "invalid_party_role", "field": "role",
                     "allowed": list(ADDITIONAL_PARTY_ROLES)})
    return role


def add_party(db: Session, tenant_id: int, account_id: int, data: dict,
              *, user_id: int | None = None) -> dict:
    acc = load_account(db, tenant_id, account_id)
    parties = _additional_parties(db, acc.id)
    if 1 + len(parties) + 1 > MAX_ACCOUNT_PARTIES:
        raise ConflictError(
            f"An account has at most {MAX_ACCOUNT_PARTIES} responsible parties",
            details={"code": "account_parties_limit", "max": MAX_ACCOUNT_PARTIES})
    if data.get("person") and data.get("responsible_party_id") is None and data.get("patient_id") is None:
        person = dict(data["person"])
        rules.fold_middle_name(person)
        rp = ResponsibleParty(tenant_id=tenant_id, created_by=user_id, **person)
        db.add(rp)
        db.flush()
        data = {**data, "responsible_party_id": rp.id}
    pid, rpid = _validate_party_person(db, tenant_id, acc, data)
    role = _validate_role(data.get("role"))
    _validate_pct(parties, data.get("responsibility_pct"))
    row = AccountParty(
        tenant_id=tenant_id, account_id=acc.id, patient_id=pid, responsible_party_id=rpid,
        role=role, responsibility_pct=data.get("responsibility_pct"),
        receives_statements=bool(data.get("receives_statements", False)),
        sort_order=data.get("sort_order") if data.get("sort_order") is not None else len(parties) + 1,
        created_by=user_id,
    )
    db.add(row)
    db.flush()
    _event(db, tenant_id, "party_added", user_id=user_id, old_account_id=acc.id,
           new_account_id=acc.id, details={"party": _party_out(db, row)})
    db.commit()
    return _party_out(db, row)


def _load_party(db: Session, tenant_id: int, account_id: int, party_id: int) -> AccountParty:
    row = db.execute(select(AccountParty).where(
        AccountParty.id == party_id, AccountParty.account_id == account_id,
        AccountParty.tenant_id == tenant_id)).scalar_one_or_none()
    if row is None or not row.is_active:
        raise NotFoundError(f"Account party '{party_id}' was not found")
    return row


def update_party(db: Session, tenant_id: int, account_id: int, party_id: int, data: dict,
                 *, user_id: int | None = None) -> dict:
    load_account(db, tenant_id, account_id)
    row = _load_party(db, tenant_id, account_id, party_id)
    before = _party_out(db, row)
    if "role" in data:
        row.role = _validate_role(data["role"])
    if "responsibility_pct" in data:
        _validate_pct(_additional_parties(db, account_id), data["responsibility_pct"],
                      exclude_id=row.id)
        row.responsibility_pct = data["responsibility_pct"]
    for f in ("receives_statements", "sort_order"):
        if f in data and data[f] is not None:
            setattr(row, f, data[f])
    row.updated_by = user_id
    row.updated_at = datetime.utcnow()
    db.flush()
    _event(db, tenant_id, "party_updated", user_id=user_id, old_account_id=account_id,
           new_account_id=account_id, details={"before": before, "after": _party_out(db, row)})
    db.commit()
    return _party_out(db, row)


def remove_party(db: Session, tenant_id: int, account_id: int, party_id: int,
                 *, user_id: int | None = None) -> None:
    load_account(db, tenant_id, account_id)
    row = _load_party(db, tenant_id, account_id, party_id)
    if row.responsible_party_id is not None and db.execute(select(Patient.id).where(
            Patient.account_id == account_id,
            Patient.guarantor_party_id == row.responsible_party_id)).first() is not None:
        raise ConflictError("That party is the guarantor of a member; change the member's "
                            "guarantor first", details={"code": "party_is_member_guarantor"})
    row.is_active = False
    row.updated_by = user_id
    row.updated_at = datetime.utcnow()
    _event(db, tenant_id, "party_removed", user_id=user_id, old_account_id=account_id,
           new_account_id=account_id, details={"party": _party_out(db, row)})
    db.commit()


def make_primary(db: Session, tenant_id: int, account_id: int, party_id: int,
                 *, user_id: int | None = None) -> dict:
    """Swap an additional party with the primary guarantor."""
    acc = load_account(db, tenant_id, account_id)
    row = _load_party(db, tenant_id, account_id, party_id)
    if row.patient_id is not None and db.get(Patient, row.patient_id).account_id != acc.id:
        raise ValidationError("A patient primary guarantor must be a member of the account",
                              details={"code": "guarantor_not_on_account"})
    old_primary = (acc.primary_guarantor_patient_id, acc.primary_guarantor_party_id)
    acc.primary_guarantor_patient_id = row.patient_id
    acc.primary_guarantor_party_id = row.responsible_party_id
    if old_primary != (None, None):
        row.patient_id, row.responsible_party_id = old_primary
        row.role = "secondary"
    else:
        row.is_active = False
    acc.updated_by = user_id
    acc.updated_at = datetime.utcnow()
    db.flush()
    _event(db, tenant_id, "primary_changed", user_id=user_id, old_account_id=acc.id,
           new_account_id=acc.id,
           details={"old_primary": {"patient_id": old_primary[0], "responsible_party_id": old_primary[1]},
                    "new_primary": {"patient_id": acc.primary_guarantor_patient_id,
                                    "responsible_party_id": acc.primary_guarantor_party_id}})
    db.commit()
    return get_account(db, tenant_id, acc.id)


# ── RP-9: account payments ────────────────────────────────────────────────────
def _oldest_open_charge(db: Session, patient_id: int) -> date | None:
    return db.execute(select(func.min(PatientProcedure.date_of_service)).where(
        PatientProcedure.patient_id == patient_id,
        PatientProcedure.is_archived.is_(False))).scalar_one_or_none()


def post_account_payment(db: Session, tenant_id: int, account_id: int, payload: dict,
                         *, user_id: int | None = None) -> dict:
    """One guarantor payment, split across members server-side.

    * ``by_member``: ``allocations[]`` must name members and sum to ``amount``
      to the cent (422 ``allocations_not_reconciled``).
    * ``oldest_first``: members with a positive balance, oldest open charge
      first, each paid up to their balance; any remainder lands on the
      guarantor member (else the first member) as a credit.
    Each slice is a normal ``patient_payments`` row (positive magnitude, AL-9)
    stamped with the account and one shared ``account_payment_id``."""
    acc = load_account(db, tenant_id, account_id)
    members = members_of(db, acc.id, tenant_id)
    if not members:
        raise ValidationError("The account has no members", details={"code": "account_empty"})
    amount = _d(payload.get("amount"))
    if amount <= ZERO:
        raise ValidationError("amount must be positive",
                              details={"code": "amount_must_be_positive", "field": "amount"})
    mode = (payload.get("distribute") or "oldest_first").strip().lower()
    if mode not in DISTRIBUTE_MODES:
        raise ValidationError(f"distribute must be one of {', '.join(DISTRIBUTE_MODES)}",
                              details={"code": "invalid_distribute", "field": "distribute"})
    member_ids = {m.id for m in members}
    split: list[tuple[int, Decimal]] = []
    if mode == "by_member":
        allocations = payload.get("allocations") or []
        if not allocations:
            raise ValidationError("by_member needs allocations[]",
                                  details={"code": "allocations_required", "field": "allocations"})
        seen = set()
        for i, a in enumerate(allocations):
            pid = a.get("patient_id")
            if pid not in member_ids:
                raise ValidationError("Allocation names a patient who is not on the account",
                                      details={"code": "patient_not_on_account", "index": i,
                                               "patient_id": pid})
            if pid in seen:
                raise ValidationError("A member appears twice in allocations",
                                      details={"code": "duplicate_allocation", "index": i})
            seen.add(pid)
            amt = _d(a.get("amount"))
            if amt <= ZERO:
                raise ValidationError("Each allocation must be positive",
                                      details={"code": "amount_must_be_positive", "index": i})
            split.append((pid, amt))
        total = sum((s for _, s in split), ZERO)
        if total != amount:
            raise ValidationError(
                "allocations do not add up to the payment amount",
                details={"code": "allocations_not_reconciled", "amount": str(amount),
                         "allocated": str(total)})
    else:
        remaining = amount
        owing = []
        for m in members:
            bal = _patient_balance(db, tenant_id, m.id)
            if bal > ZERO:
                owing.append((_oldest_open_charge(db, m.id) or date.max, m.id, bal))
        for _, pid, bal in sorted(owing):
            if remaining <= ZERO:
                break
            take = min(bal, remaining)
            split.append((pid, take))
            remaining -= take
        if remaining > ZERO:
            sink = acc.primary_guarantor_patient_id if acc.primary_guarantor_patient_id in member_ids \
                else members[0].id
            for i, (pid, amt) in enumerate(split):
                if pid == sink:
                    split[i] = (pid, amt + remaining)
                    break
            else:
                split.append((sink, remaining))
    group = f"ACCT-{uuid7()}"
    pay_date = payload.get("payment_date") or date.today()
    rows = []
    for pid, amt in split:
        rows.append(PatientPayment(
            id=f"AP-{uuid7()}", patient_id=pid, account_id=acc.id, account_payment_id=group,
            payment_date=pay_date, amount=amt,
            payment_type=payload.get("payment_type") or "patient",
            payment_method=payload.get("tender") or payload.get("payment_method"),
            check_number=payload.get("check_number"), bank_number=payload.get("bank_number"),
            office_id=payload.get("office_id") or acc.home_office_id,
            created_office_id=payload.get("created_office_id"),
            provider_id=payload.get("provider_id"),
            notes=payload.get("notes") or f"Account {acc.account_no} payment ({mode})",
            created_by=user_id,
        ))
    db.add_all(rows)
    db.flush()
    _event(db, tenant_id, "account_payment", user_id=user_id, old_account_id=acc.id,
           new_account_id=acc.id,
           details={"account_payment_id": group, "amount": str(amount), "distribute": mode,
                    "split": [{"patient_id": pid, "amount": str(a)} for pid, a in split]})
    db.commit()
    _invalidate_balance(tenant_id, member_ids)
    return {
        "account_id": acc.id, "account_payment_id": group, "amount": float(amount),
        "distribute": mode, "payment_date": pay_date,
        "payments": [{"id": r.id, "patient_id": r.patient_id, "amount": float(r.amount)} for r in rows],
    }


# ── RP-9: account statements ──────────────────────────────────────────────────
def _addressees(db: Session, acc: Account) -> list[dict]:
    primary = _primary_payload(db, acc)
    out = [{"role": "primary", **{k: primary[k] for k in (
        "kind", "patient_id", "responsible_party_id", "name", "address_line1", "address_line2",
        "city", "state", "zip", "email")}}]
    for p in _additional_parties(db, acc.id):
        if not p.receives_statements:
            continue
        person = db.get(Patient, p.patient_id) if p.patient_id else db.get(
            ResponsibleParty, p.responsible_party_id)
        out.append({
            "role": p.role, "kind": "patient" if p.patient_id else "responsible_party",
            "patient_id": p.patient_id, "responsible_party_id": p.responsible_party_id,
            "name": _name(person),
            **{k: getattr(person, k, None) for k in (
                "address_line1", "address_line2", "city", "state", "zip", "email")},
        })
    return out


def generate_account_statement(db: Session, tenant_id: int, account_id: int, payload: dict,
                               *, actor_id: int | None = None, batch_id: str | None = None,
                               commit: bool = True) -> PatientStatement:
    from app.services import balance_service, statement_service

    acc = load_account(db, tenant_id, account_id)
    members = members_of(db, acc.id, tenant_id)
    if not members:
        raise ValidationError("The account has no members", details={"code": "account_empty"})
    addressee = next((m for m in members if m.id == acc.primary_guarantor_patient_id), members[0])
    office_id = payload.get("office_id") or acc.home_office_id or addressee.home_office_id
    date_from, date_to = payload.get("date_from"), payload.get("date_to")
    sections = []
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    aging_tot: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for m in members:
        lines = statement_service._period_lines(db, m.id, date_from, date_to)
        bal = balance_service.patient_balance_core(db, m.id, tenant_id)
        closing = (_d(lines["opening"]) + _d(lines["charges"]) - _d(lines["payments"])
                   - _d(lines["adjustments"]))
        for k in ("opening", "charges", "payments", "adjustments"):
            totals[k] += _d(lines[k])
        totals["closing"] += closing
        for b in ("current", "b30", "b60", "b90", "b120"):
            aging_tot[b] += _d((bal.get("aging") or {}).get(b))
        sections.append({
            "patient_id": m.id, "patient_name": _name(m), "chart_no": m.chart_no,
            "opening_balance": str(_d(lines["opening"])), "total_charges": str(_d(lines["charges"])),
            "total_payments": str(_d(lines["payments"])),
            "total_adjustments": str(_d(lines["adjustments"])), "closing_balance": str(closing),
            "balance": bal.get("balance"), "aging": bal.get("aging"),
            "lines": _jsonable(lines.get("lines") or []),
        })
    aging_api = {"current": aging_tot["current"], "b30": aging_tot["b30"], "b60": aging_tot["b60"],
                 "b90": aging_tot["b90"], "b120": aging_tot["b120"]}
    message = payload.get("message") or acc.statement_message or statement_service._aging_message(
        db, office_id, {k: float(v) for k, v in aging_api.items()})
    stmt = PatientStatement(
        tenant_id=tenant_id, patient_id=addressee.id, account_id=acc.id, statement_scope="account",
        office_id=office_id, statement_date=payload.get("statement_date") or date.today(),
        period_start=date_from, period_end=date_to,
        opening_balance=totals["opening"], total_charges=totals["charges"],
        total_payments=totals["payments"], total_adjustments=totals["adjustments"],
        closing_balance=totals["closing"],
        aging_current=aging_tot["current"], aging_30=aging_tot["b30"], aging_60=aging_tot["b60"],
        aging_90=aging_tot["b90"], aging_120=aging_tot["b120"],
        message=(message or None) and str(message)[:500], batch_id=batch_id,
        snapshot={
            "scope": "account", "account_id": acc.id, "account_no": acc.account_no,
            "patient_name": _name(addressee), "chart_no": addressee.chart_no,
            "addressed_to": _addressees(db, acc),
            "members": sections,
            "account_balance": float(sum((_d(s["balance"]) for s in sections), ZERO)),
        },
        created_by=actor_id,
    )
    db.add(stmt)
    if commit:
        db.commit()
        db.refresh(stmt)
    else:
        db.flush()
    return stmt


def generate_account_batch(db: Session, tenant_id: int, office_id: int, payload: dict,
                           *, actor_id: int | None = None) -> dict:
    """STMT-2 at account scope: one statement per active account homed at the
    office whose total balance clears ``min_balance`` and that sends statements."""
    from app.services import statement_service

    min_balance = _d(payload.get("min_balance") or "0.01")
    only_aged = bool(payload.get("only_aged"))
    batch_id = f"STMT-{uuid7()}"
    accounts = db.execute(select(Account).where(
        Account.tenant_id == tenant_id, Account.is_active.is_(True),
        Account.home_office_id == office_id, Account.send_statements.is_(True))).scalars().all()
    generated = []
    for acc in accounts:
        members = members_of(db, acc.id, tenant_id)
        if not members or all(m.is_active is False for m in members):
            continue
        from app.services import balance_service

        bals = [balance_service.patient_balance_core(db, m.id, tenant_id) for m in members]
        if sum((_d(b["balance"]) for b in bals), ZERO) < min_balance:
            continue
        if only_aged and sum((_d((b.get("aging") or {}).get(k)) for b in bals
                              for k in ("b30", "b60", "b90", "b120")), ZERO) <= ZERO:
            continue
        stmt = generate_account_statement(
            db, tenant_id, acc.id,
            {"office_id": office_id, "statement_date": payload.get("statement_date"),
             "date_from": payload.get("date_from"), "date_to": payload.get("date_to")},
            actor_id=actor_id, batch_id=batch_id, commit=False)
        generated.append(statement_service._statement_out(stmt))
    db.commit()
    return {"office_id": office_id, "batch_id": batch_id, "scope": "account",
            "generated": len(generated), "statements": generated}


# ── RP-13: account insurance ──────────────────────────────────────────────────
def account_insurance(db: Session, tenant_id: int, account_id: int) -> list[dict]:
    acc = load_account(db, tenant_id, account_id)
    members = {m.id: m for m in members_of(db, acc.id, tenant_id)}
    if not members:
        return []
    rows = db.execute(
        select(PatientInsurance, InsurancePlan, InsuranceCarrier, InsuranceSubscriber)
        .outerjoin(InsurancePlan, InsurancePlan.id == PatientInsurance.ins_plan_id)
        .outerjoin(InsuranceCarrier, InsuranceCarrier.id == InsurancePlan.carrier_id)
        .outerjoin(InsuranceSubscriber, InsuranceSubscriber.id == PatientInsurance.subscriber_id)
        .where(PatientInsurance.patient_id.in_(list(members)))
    ).all()
    grouped: dict[tuple, dict] = {}
    for pi, plan, carrier, sub in rows:
        key = (pi.ins_plan_id, pi.subscriber_id)
        entry = grouped.get(key)
        if entry is None:
            sub_pid = getattr(sub, "subscriber_patient_id", None) if sub else None
            entry = grouped[key] = {
                "ins_plan_id": pi.ins_plan_id, "subscriber_id": pi.subscriber_id,
                "carrier_id": getattr(plan, "carrier_id", None),
                "carrier_name": getattr(carrier, "name", None),
                "group_number": getattr(plan, "group_number", None),
                "plan_type": getattr(plan, "plan_type", None),
                "legacy_plan_type": pi.legacy_plan_type,
                "subscriber_name": ", ".join(x for x in (
                    getattr(sub, "sub_last_name", None), getattr(sub, "sub_first_name", None)) if x) or None,
                "subscriber_patient_id": sub_pid,
                "subscriber_is_account_member": sub_pid in members if sub_pid else False,
                "members": [],
            }
        entry["members"].append({
            "patient_id": pi.patient_id, "patient_name": _name(members.get(pi.patient_id)),
            "insurance_type": pi.insurance_type, "relationship": pi.relationship,
            "is_active": pi.is_active,
        })
    return list(grouped.values())


# ── RP-16: change log ─────────────────────────────────────────────────────────
def _event_out(ev: AccountChangeEvent, names: dict) -> dict:
    return {
        "id": ev.id, "patient_id": ev.patient_id, "action": ev.action,
        "old_account_id": ev.old_account_id, "new_account_id": ev.new_account_id,
        "old_guarantor": ev.old_guarantor, "new_guarantor": ev.new_guarantor,
        "move_open_balance": ev.move_open_balance,
        "moved_balance": float(ev.moved_balance) if ev.moved_balance is not None else None,
        "effective_date": ev.effective_date, "details": ev.details,
        "user_id": ev.user_id, "user_name": names.get(ev.user_id), "at": ev.created_at,
    }


def change_log(db: Session, tenant_id: int, *, patient_id: int | None = None,
               account_id: int | None = None) -> list[dict]:
    from app.services.user_admin_service import resolve_user_names

    stmt = select(AccountChangeEvent).where(AccountChangeEvent.tenant_id == tenant_id)
    if patient_id is not None:
        load_patient(db, tenant_id, patient_id)
        stmt = stmt.where(AccountChangeEvent.patient_id == patient_id)
    if account_id is not None:
        load_account(db, tenant_id, account_id)
        stmt = stmt.where(or_(AccountChangeEvent.old_account_id == account_id,
                              AccountChangeEvent.new_account_id == account_id))
    rows = db.execute(stmt.order_by(AccountChangeEvent.id.desc())).scalars().all()
    names = resolve_user_names(db, {r.user_id for r in rows if r.user_id is not None})
    return [_event_out(r, names) for r in rows]


# ── metadata (RP-15) ──────────────────────────────────────────────────────────
def rules_metadata() -> dict:
    return {
        "guarantor_kinds": list(GUARANTOR_KINDS),
        "spec_precedence": list(SPEC_PRECEDENCE),
        "relationships": [{"code": c, "label": lbl} for c, lbl in rules.RESP_PARTY_RELATIONSHIPS],
        "relationship_definition_group": "resp_party_rel",
        "self_relationship": SELF_RELATIONSHIP,
        "max_account_parties": MAX_ACCOUNT_PARTIES,
        "additional_party_roles": list(ADDITIONAL_PARTY_ROLES),
        "distribute_modes": list(DISTRIBUTE_MODES),
        "responsible_party_id_alias": (
            "deprecated: equals the guarantor's key (patient id for self/patient, "
            "responsible_parties.id for a party, the legacy RPID when unresolved). "
            "Read guarantor.kind / account_id instead."),
    }
