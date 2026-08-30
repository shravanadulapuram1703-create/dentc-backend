"""Insurance business logic that supplements generated CRUD.

INS-PT-5 — eligibility "Update Status": stamp a subscriber's verification
(``elig_status`` / ``elig_verified_on`` / ``elig_verified_by``) server-side. There
is no clearinghouse integration yet, so this records a *manual* verification; the
response reports whether the carrier advertises real-time eligibility
(``insurance_carriers.supports_realtime_eligibility``) for when that lands.

INS-PT-12 — the Dental/Medical vocabulary. ``insurance_carriers.carrier_type`` is
stringly typed (``"True"`` = dental, ``"False"`` = medical) and every screen
branches on it, so a typo yields a carrier that matches neither filter. The token
sets below are the **single** definition: the ``is_dental`` read field, the
``?is_dental=`` list filter and the write-side canonicalisation all use them, so
a value that reads as dental can no longer fail to filter as dental.

INS-PT-19/20/13 — duplicate prevention. The frontend checks for a colliding group
number twice (advisory while typing, blocking on save), but both are client-side:
an import, a script or a second concurrent user still creates the duplicate. The
matchers here are what makes the server the authority; the write paths turn a
match into a **409 with an explicit override**, because two offices can
legitimately hold separate plans on one group number and legacy allows it — which
is also why this is deliberately not a DB uniqueness constraint.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.crud.base import CRUDBase
from app.db.models import (
    Employer,
    InsuranceCarrier,
    InsurancePlan,
    InsuranceSubscriber,
    User,
)


def _display_name(user: User | None) -> str | None:
    if user is None:
        return None
    full = " ".join(p for p in (user.first_name, user.last_name) if p).strip()
    return full or user.username


def verify_eligibility(
    db: Session, subscriber_id: int, tenant_id: int, actor: User,
    *, elig_status: str | None = None, notes: str | None = None,
) -> dict:
    sub = db.get(InsuranceSubscriber, subscriber_id)
    if sub is None or sub.tenant_id != tenant_id:
        raise NotFoundError(f"InsuranceSubscriber '{subscriber_id}' was not found")

    realtime_supported: bool | None = None
    if sub.ins_plan_id is not None:
        plan = db.get(InsurancePlan, sub.ins_plan_id)
        if plan is not None:
            carrier = db.get(InsuranceCarrier, plan.carrier_id)
            if carrier is not None:
                realtime_supported = carrier.supports_realtime_eligibility

    sub.elig_status = elig_status or "verified"
    sub.elig_verified_on = datetime.now(timezone.utc)
    sub.elig_verified_by = _display_name(actor)
    if notes is not None:
        sub.elig_notes = notes
    db.commit()
    db.refresh(sub)

    return {
        "subscriber_id": sub.id,
        "elig_status": sub.elig_status,
        "elig_verified_on": sub.elig_verified_on,
        "elig_verified_by": sub.elig_verified_by,
        "realtime_supported": realtime_supported,
        # No clearinghouse wired yet → always a manual stamp.
        "method": "manual",
    }


# ── INS-PT-12: the Dental / Medical vocabulary ───────────────────────────────
#: ``carrier_type`` values that denote a *medical* carrier. Anything else — a
#: typo included — reads as dental, which is what the legacy data does: 1,335 of
#: the 1,340 migrated carriers are ``"True"``.
MEDICAL_TOKENS = frozenset({"false", "medical", "m", "0", "f", "no"})
DENTAL_TOKENS = frozenset({"true", "dental", "d", "1", "t", "yes"})

#: What a canonical write stores.
CARRIER_TYPE_DENTAL = "True"
CARRIER_TYPE_MEDICAL = "False"


def carrier_is_dental(carrier_type: str | None) -> bool | None:
    """``None`` when unknown (the column is NULL), else the derived flag."""
    if carrier_type is None:
        return None
    return carrier_type.strip().lower() not in MEDICAL_TOKENS


def canonical_carrier_type(value: str | None) -> str | None:
    """Normalise a written ``carrier_type`` to ``"True"`` / ``"False"``.

    A value outside both vocabularies is stored **as written** rather than
    coerced or rejected — the same call PROV-3 made for ``providers.role``. It
    still reads as dental via :func:`carrier_is_dental`, so the read model and
    the ``?is_dental=`` filter agree about it; rejecting the save instead would
    turn an unfamiliar string into a form the user cannot submit.
    """
    if value is None:
        return None
    token = value.strip().lower()
    if token in MEDICAL_TOKENS:
        return CARRIER_TYPE_MEDICAL
    if token in DENTAL_TOKENS:
        return CARRIER_TYPE_DENTAL
    return value


def _apply_carrier_type(data: dict[str, Any]) -> dict[str, Any]:
    """Fold the writable ``is_dental`` (INS-PT-12) into ``carrier_type`` and
    canonicalise whatever ends up there. ``is_dental`` wins when both are sent —
    it is the typed field, so it is the one that cannot have been mistyped."""
    payload = dict(data)
    is_dental = payload.pop("is_dental", None)
    if is_dental is not None:
        payload["carrier_type"] = (
            CARRIER_TYPE_DENTAL if is_dental else CARRIER_TYPE_MEDICAL
        )
    elif "carrier_type" in payload:
        payload["carrier_type"] = canonical_carrier_type(payload["carrier_type"])
    return payload


def _is_dental_clause(is_dental: bool):
    """SQL mirror of :func:`carrier_is_dental` — same vocabulary, so the filter
    and the read field can never disagree about a given row."""
    token = func.lower(func.trim(InsuranceCarrier.carrier_type))
    if is_dental:
        return InsuranceCarrier.carrier_type.is_not(None) & token.notin_(MEDICAL_TOKENS)
    return token.in_(MEDICAL_TOKENS)


# ── INS-PT-19/20/21: plan group-number collisions ────────────────────────────
def _norm(value: str | None) -> str | None:
    value = (value or "").strip()
    return value.lower() or None


def find_plan_group_matches(
    db: Session,
    tenant_id: int | None,
    group_number: str | None,
    *,
    carrier_id: int | None = None,
    exclude_id: int | None = None,
) -> dict[str, list[InsurancePlan]]:
    """Plans sharing ``group_number``, split three ways.

    * ``active`` — same carrier, live. This is the real duplicate, and the only
      bucket the write guard blocks on.
    * ``inactive`` — same carrier, deactivated (INS-PT-21). Reported, never
      blocking: re-using a retired plan's group number is allowed, but the
      frontend was making that call on its own and the backend never expressed it.
    * ``other_carrier`` — same group number under a different carrier. Also only
      reported: a group number is a *carrier's* identifier for an employer group,
      so two carriers reusing the digits is not a collision.

    Matching is case-insensitive and trimmed; a blank group number matches
    nothing (most migrated plans are NULL — see INS-PT-15 — and "no group number"
    is not a duplicate of "no group number").
    """
    needle = _norm(group_number)
    out: dict[str, list[InsurancePlan]] = {"active": [], "inactive": [], "other_carrier": []}
    if needle is None:
        return out

    stmt = select(InsurancePlan).where(
        func.lower(func.trim(InsurancePlan.group_number)) == needle
    )
    if tenant_id is not None:
        stmt = stmt.where(InsurancePlan.tenant_id == tenant_id)
    if exclude_id is not None:
        stmt = stmt.where(InsurancePlan.id != exclude_id)

    for plan in db.execute(stmt).scalars():
        if carrier_id is not None and plan.carrier_id != carrier_id:
            out["other_carrier"].append(plan)
        elif plan.is_active:
            out["active"].append(plan)
        else:
            out["inactive"].append(plan)
    return out


def plan_match_payload(db: Session, plans: list[InsurancePlan]) -> list[dict]:
    """Denormalise a match list for the dialog: it names the plan the user would
    be adopting, so it has to carry the carrier/employer names, not ids."""
    if not plans:
        return []
    carrier_ids = {p.carrier_id for p in plans if p.carrier_id}
    employer_ids = {p.employer_id for p in plans if p.employer_id}
    carriers = {
        c.id: c
        for c in db.execute(
            select(InsuranceCarrier).where(InsuranceCarrier.id.in_(carrier_ids))
        ).scalars()
    } if carrier_ids else {}
    employers = {
        e.id: e.name
        for e in db.execute(
            select(Employer).where(Employer.id.in_(employer_ids))
        ).scalars()
    } if employer_ids else {}

    out = []
    for p in plans:
        carrier = carriers.get(p.carrier_id)
        out.append({
            "id": p.id,
            "group_number": p.group_number,
            "carrier_id": p.carrier_id,
            "carrier_name": carrier.name if carrier else None,
            "payer_id": carrier.payer_id if carrier else None,
            "employer_id": p.employer_id,
            "employer_name": employers.get(p.employer_id),
            "plan_type": p.plan_type,
            "coverage_type": p.coverage_type,
            "is_active": p.is_active,
        })
    return out


def group_availability(
    db: Session,
    tenant_id: int | None,
    group_number: str,
    *,
    carrier_id: int | None = None,
    exclude_plan_id: int | None = None,
) -> dict:
    """INS-PT-20: "is this group taken?" in one indexed lookup.

    The frontend was answering this by paging the full list endpoint on every
    save. Without ``carrier_id`` the question is tenant-wide and every match
    lands in ``matches``; with it, the answer is split the way the write guard
    splits it, so the dialog can say *which* kind of collision it found.
    """
    found = find_plan_group_matches(
        db, tenant_id, group_number,
        carrier_id=carrier_id, exclude_id=exclude_plan_id,
    )
    return {
        "group_number": group_number,
        "carrier_id": carrier_id,
        "taken": bool(found["active"]),
        "matches": plan_match_payload(db, found["active"]),
        # INS-PT-21: surfaced separately — a deactivated plan does not block a
        # save, but the user should be told the number was used before.
        "inactive_matches": plan_match_payload(db, found["inactive"]),
        "other_carrier_matches": plan_match_payload(db, found["other_carrier"]),
    }


# ── INS-PT-13: carrier / employer quick-add name collisions ──────────────────
def find_name_matches(
    db: Session,
    model: type,
    tenant_id: int | None,
    name: str | None,
    *,
    exclude_id: int | None = None,
) -> dict[str, list]:
    """Rows whose ``name`` matches case-insensitively after trimming.

    ``employers`` has no ``is_active`` column, so everything it returns is
    ``active`` — the split exists for carriers.
    """
    needle = _norm(name)
    out: dict[str, list] = {"active": [], "inactive": []}
    if needle is None:
        return out

    stmt = select(model).where(func.lower(func.trim(model.name)) == needle)
    if tenant_id is not None and hasattr(model, "tenant_id"):
        stmt = stmt.where(model.tenant_id == tenant_id)
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)

    for row in db.execute(stmt).scalars():
        bucket = "active" if getattr(row, "is_active", True) else "inactive"
        out[bucket].append(row)
    return out


def name_availability(
    db: Session,
    model: type,
    tenant_id: int | None,
    name: str,
    *,
    exclude_id: int | None = None,
) -> dict:
    found = find_name_matches(db, model, tenant_id, name, exclude_id=exclude_id)

    def _rows(rows: list) -> list[dict]:
        return [
            {"id": r.id, "name": r.name, "is_active": bool(getattr(r, "is_active", True))}
            for r in rows
        ]

    return {
        "name": name,
        "taken": bool(found["active"]),
        "matches": _rows(found["active"]),
        "inactive_matches": _rows(found["inactive"]),
    }


def _like(value: str) -> str:
    """Escape the LIKE wildcards so a group number containing ``%`` or ``_``
    searches for itself instead of matching everything."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ── CRUD subclasses ──────────────────────────────────────────────────────────
class InsurancePlanCRUD(CRUDBase[InsurancePlan]):
    """Server-side duplicate guard (INS-PT-19) plus the per-field plan searches
    the legacy "Search For" dialog offers (INS-PT-7/14)."""

    custom_filter_fields = (
        "group_number_contains",
        "group_number_startswith",
        "carrier_name",
        "payer_id",
    )

    def _extra_list_clauses(self, filters: dict[str, Any]) -> list:
        clauses = []
        contains = (filters.get("group_number_contains") or "").strip()
        if contains:
            clauses.append(
                InsurancePlan.group_number.ilike(f"%{_like(contains)}%", escape="\\")
            )
        starts = (filters.get("group_number_startswith") or "").strip()
        if starts:
            clauses.append(
                InsurancePlan.group_number.ilike(f"{_like(starts)}%", escape="\\")
            )
        # INS-PT-7: "Carrier Name" and "Payer ID" issued the identical free-text
        # query, so a numeric carrier-name search also matched group and payer
        # values. Each now reaches exactly one column on the carrier.
        carrier_clauses = []
        carrier_name = (filters.get("carrier_name") or "").strip()
        if carrier_name:
            carrier_clauses.append(
                InsuranceCarrier.name.ilike(f"%{_like(carrier_name)}%", escape="\\")
            )
        payer_id = (filters.get("payer_id") or "").strip()
        if payer_id:
            carrier_clauses.append(
                InsuranceCarrier.payer_id.ilike(f"%{_like(payer_id)}%", escape="\\")
            )
        for clause in carrier_clauses:
            clauses.append(
                InsurancePlan.carrier_id.in_(select(InsuranceCarrier.id).where(clause))
            )
        return clauses

    def _guard(
        self,
        db: Session,
        *,
        tenant_id: int | None,
        carrier_id: int | None,
        group_number: str | None,
        allow_duplicate: bool,
        exclude_id: int | None = None,
    ) -> None:
        if allow_duplicate:
            return
        found = find_plan_group_matches(
            db, tenant_id, group_number, carrier_id=carrier_id, exclude_id=exclude_id
        )
        if not found["active"]:
            return
        raise ConflictError(
            "An active plan already exists for this carrier and group number",
            code="duplicate_plan_group",
            details={
                "group_number": group_number,
                "carrier_id": carrier_id,
                "matches": plan_match_payload(db, found["active"]),
                "inactive_matches": plan_match_payload(db, found["inactive"]),
                "other_carrier_matches": plan_match_payload(db, found["other_carrier"]),
                # The dialog's third option. Legacy allows the duplicate, so the
                # API has to as well — it just refuses to make one by accident.
                "override_field": "allow_duplicate_group",
            },
        )

    def create(
        self, db: Session, data: dict[str, Any], *,
        tenant_id: int | None = None, created_by: int | None = None,
    ) -> InsurancePlan:
        payload = dict(data)
        allow = bool(payload.pop("allow_duplicate_group", False))
        self._guard(
            db, tenant_id=tenant_id,
            carrier_id=payload.get("carrier_id"),
            group_number=payload.get("group_number"),
            allow_duplicate=allow,
        )
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    def update(
        self, db: Session, obj_id: Any, data: dict[str, Any], *,
        tenant_id: int | None = None, updated_by: int | None = None,
    ) -> InsurancePlan:
        payload = dict(data)
        allow = bool(payload.pop("allow_duplicate_group", False))
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        # Evaluate against the merge of payload + stored row, so a PATCH carrying
        # only the group number is still checked against the plan's own carrier
        # (and a PATCH that only moves the carrier against its stored group).
        carrier_id = payload.get("carrier_id", existing.carrier_id)
        group_number = payload.get("group_number", existing.group_number)
        # A plan that is *already* a duplicate stays editable. Backfilling the
        # migrated group numbers (INS-PT-15) put 3,609 groups into a legitimate
        # pre-existing collision, and blocking every later edit of those plans
        # would punish the repair. The guard fires on a **move** — the identity
        # (carrier, group) actually changing — not on the stored state.
        moved = (
            carrier_id != existing.carrier_id
            or _norm(group_number) != _norm(existing.group_number)
        )
        self._guard(
            db, tenant_id=tenant_id, carrier_id=carrier_id, group_number=group_number,
            allow_duplicate=allow or not moved, exclude_id=existing.id,
        )
        return super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)


class _NameGuardCRUD(CRUDBase):
    """Shared quick-add guard (INS-PT-13): creating a second carrier/employer
    under an existing name is a 409 the caller can override, not a silent
    duplicate.

    Only ``create`` is guarded. Renaming an existing row onto a taken name is far
    more likely to be a deliberate merge or correction than a slip, and blocking
    it would strand rows whose name a practice has decided to reuse.
    """

    override_field = "allow_duplicate_name"
    conflict_code = "duplicate_name"

    def create(
        self, db: Session, data: dict[str, Any], *,
        tenant_id: int | None = None, created_by: int | None = None,
    ) -> Any:
        payload = dict(data)
        allow = bool(payload.pop(self.override_field, False))
        if not allow:
            found = find_name_matches(db, self.model, tenant_id, payload.get("name"))
            if found["active"]:
                raise ConflictError(
                    f"A {self.resource_name} named '{payload.get('name')}' already exists",
                    code=self.conflict_code,
                    details={
                        "name": payload.get("name"),
                        "matches": [{"id": r.id, "name": r.name} for r in found["active"]],
                        "override_field": self.override_field,
                    },
                )
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    def update(
        self, db: Session, obj_id: Any, data: dict[str, Any], *,
        tenant_id: int | None = None, updated_by: int | None = None,
    ) -> Any:
        payload = dict(data)
        payload.pop(self.override_field, None)
        return super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)


class InsuranceCarrierCRUD(_NameGuardCRUD):
    """INS-PT-12 (canonical ``carrier_type`` + a writable ``is_dental``, and an
    ``?is_dental=`` filter sharing the read field's vocabulary) and INS-PT-13
    (quick-add name collision)."""

    custom_filter_fields = ("is_dental",)
    conflict_code = "duplicate_carrier_name"

    def _extra_list_clauses(self, filters: dict[str, Any]) -> list:
        is_dental = filters.get("is_dental")
        if is_dental is None:
            return []
        return [_is_dental_clause(bool(is_dental))]

    def create(self, db: Session, data: dict[str, Any], **kwargs: Any) -> Any:
        return super().create(db, _apply_carrier_type(data), **kwargs)

    def update(self, db: Session, obj_id: Any, data: dict[str, Any], **kwargs: Any) -> Any:
        return super().update(db, obj_id, _apply_carrier_type(data), **kwargs)


class EmployerCRUD(_NameGuardCRUD):
    conflict_code = "duplicate_employer_name"
