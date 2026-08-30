"""Provider ↔ office scoping (PROV-1) and role normalisation (PROV-3).

A provider is multi-office: the many-to-many truth lives in ``provider_offices``,
while ``providers.office_id`` is only the provider's *home* office (the legacy
scalar the migration carried over). Filtering on the scalar alone made
``GET /providers?office_id=`` return an empty list for most offices, which is what
emptied the toolbar provider dropdown and left the grid rendering raw ids.

Both readers here resolve the same **union**: assigned (``provider_offices``) ∪
home office (``providers.office_id``). ``GET /offices/{id}/providers`` stays the
pure assignment grid (its PUT replaces exactly what its GET returns) — the
effective set is exposed next to it as ``…/providers/effective``.

**PROV-3 — ``providers.role`` is free text.** Live tenant 1 holds ``dentist``
(78), ``hygienist`` (16), ``Dentist`` (2), ``Hygenist`` (1 — misspelled) and
``staff`` (2), while ``specialty`` is blank on 96 of 97 rows. Any screen that
needs "doctors here, hygienists there" therefore had to normalise client-side,
and the frontend grew a ``providerKind()`` heuristic to do it — one misspelling
away from putting a hygienist in the treating-provider list. The vocabulary is
now seeded as the ``provider_role`` definition group and canonicalised on every
write by :class:`ProviderCRUD`, so the split is data rather than a guess.

Two deliberate limits:

* Canonicalisation is a **spelling fix, not an enum**. An unrecognised role is
  stored as written (lower-cased and trimmed) rather than rejected — a practice
  may legitimately use a title this list has never heard of, and a 422 on save
  would be a worse failure than an unfamiliar string.
* Migrated rows are not rewritten on read. ``scripts/normalize_provider_roles.py``
  repairs them in one pass, dry-run by default.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.db.models import Provider, ProviderOffice

#: Canonical ``providers.role`` values (mirrors the ``provider_role`` definition
#: group seeded by ``scripts/seed_account_definitions.py``).
PROVIDER_ROLES: tuple[str, ...] = (
    "dentist", "hygienist", "assistant", "specialist", "staff",
)

#: Spelling / casing variants seen in the migrated data and in the wild, mapped
#: onto the canonical value. Keys are compared lower-cased and stripped.
_ROLE_ALIASES: dict[str, str] = {
    "dentist": "dentist", "dds": "dentist", "dmd": "dentist", "doctor": "dentist",
    "dr": "dentist", "provider": "dentist", "denist": "dentist", "dentis": "dentist",
    "hygienist": "hygienist", "hygenist": "hygienist", "hygienest": "hygienist",
    "hygeinist": "hygienist", "rdh": "hygienist", "hygiene": "hygienist",
    "assistant": "assistant", "asst": "assistant", "rda": "assistant",
    "dental assistant": "assistant", "da": "assistant",
    "specialist": "specialist", "spec": "specialist",
    "staff": "staff", "admin": "staff", "front desk": "staff", "office": "staff",
}

#: Licence titles that identify a kind when ``role`` says nothing useful — the
#: backend half of the frontend's ``providerKind()`` fallback.
_TITLE_KIND: dict[str, str] = {
    "dds": "dentist", "dmd": "dentist", "ddh": "dentist", "md": "dentist",
    "rdh": "hygienist", "rdhap": "hygienist",
    "rda": "assistant", "cda": "assistant",
}


def canonical_role(role: str | None) -> str | None:
    """Map a free-text role onto the canonical vocabulary.

    Returns the canonical value when the input is recognised, the trimmed
    lower-cased input when it is not, and ``None`` for an empty value. Never
    raises — an unfamiliar role is data to preserve, not an error.
    """
    if role is None:
        return None
    cleaned = " ".join(role.strip().lower().split())
    if not cleaned:
        return None
    return _ROLE_ALIASES.get(cleaned, cleaned)


#: Roles that name a clinical kind outright. ``staff`` is deliberately absent:
#: it is the generic bucket, so a licence title outranks it (someone filed as
#: ``staff`` who holds an ``RDH`` is a hygienist, and leaving them out of the
#: hygiene dropdown is the bug this whole gap is about).
_CLINICAL_ROLES = ("dentist", "hygienist", "assistant", "specialist")


def provider_kind(role: str | None, title: str | None = None) -> str | None:
    """The provider's *kind* for the "doctors here, hygienists there" split.

    A clinical role wins outright. Otherwise the licence title decides, and only
    then does a non-clinical or unrecognised role stand on its own.
    """
    canon = canonical_role(role)
    if canon in _CLINICAL_ROLES:
        return canon
    by_title = _TITLE_KIND.get((title or "").strip().lower())
    return by_title or canon


def office_scope_clause(office_id: int):  # noqa: ANN201
    """``Provider`` rows serving ``office_id``: assigned ∪ home-office scalar."""
    return or_(
        Provider.office_id == office_id,
        Provider.id.in_(
            select(ProviderOffice.provider_id).where(ProviderOffice.office_id == office_id)
        ),
    )


class ProviderCRUD(CRUDBase[Provider]):
    """``?office_id=`` spans the M:N join instead of only the home-office scalar,
    and ``role`` is canonicalised on write (PROV-3)."""

    custom_filter_fields = ("office_id",)

    def _extra_list_clauses(self, filters: dict[str, Any]) -> list:
        office_id = filters.get("office_id")
        return [] if office_id is None else [office_scope_clause(office_id)]

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        return super().create(db, _canonicalise(data), tenant_id=tenant_id, created_by=created_by)

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        return super().update(db, obj_id, _canonicalise(data), tenant_id=tenant_id, updated_by=updated_by)


def _canonicalise(data: dict) -> dict:
    """Normalise ``role`` in a write payload, leaving a PATCH that omits it alone."""
    if "role" not in data:
        return data
    payload = dict(data)
    payload["role"] = canonical_role(payload["role"])
    return payload


def effective_office_providers(
    db: Session, office_id: int, tenant_id: int, *, include_inactive: bool = False
) -> list[Provider]:
    """Every provider who serves ``office_id`` (assignment ∪ home office)."""
    stmt = select(Provider).where(
        Provider.tenant_id == tenant_id, office_scope_clause(office_id)
    )
    if not include_inactive:
        stmt = stmt.where(Provider.is_active.is_(True))
    return list(db.execute(stmt.order_by(Provider.name.asc(), Provider.id.asc())).scalars().all())
