"""Provider ↔ office scoping (PROV-1).

A provider is multi-office: the many-to-many truth lives in ``provider_offices``,
while ``providers.office_id`` is only the provider's *home* office (the legacy
scalar the migration carried over). Filtering on the scalar alone made
``GET /providers?office_id=`` return an empty list for most offices, which is what
emptied the toolbar provider dropdown and left the grid rendering raw ids.

Both readers here resolve the same **union**: assigned (``provider_offices``) ∪
home office (``providers.office_id``). ``GET /offices/{id}/providers`` stays the
pure assignment grid (its PUT replaces exactly what its GET returns) — the
effective set is exposed next to it as ``…/providers/effective``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.db.models import Provider, ProviderOffice


def office_scope_clause(office_id: int):  # noqa: ANN201
    """``Provider`` rows serving ``office_id``: assigned ∪ home-office scalar."""
    return or_(
        Provider.office_id == office_id,
        Provider.id.in_(
            select(ProviderOffice.provider_id).where(ProviderOffice.office_id == office_id)
        ),
    )


class ProviderCRUD(CRUDBase[Provider]):
    """``?office_id=`` spans the M:N join instead of only the home-office scalar."""

    custom_filter_fields = ("office_id",)

    def _extra_list_clauses(self, filters: dict[str, Any]) -> list:
        office_id = filters.get("office_id")
        return [] if office_id is None else [office_scope_clause(office_id)]


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
