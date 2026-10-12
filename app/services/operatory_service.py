"""Operatory writes (OFF-QA-11).

``operatories.id`` is a ``String(50)`` primary key (migrated chairs carry the
Denticon id, e.g. ``OPR-102``), and ``OperatoryCreate`` used to *require* it, so
the frontend invented ``op-{office_id}-{display_order}``: removing a chair and
adding another at the same position without a reload produced a duplicate id
and the second save 409'd. The server now mints the id when it is omitted; an
explicit id is still accepted (imports keep their legacy ids).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.db.models import Operatory


def next_operatory_id(db: Session, office_id: int | None) -> str:
    """``op-{office_id}-{n}`` with the first ``n`` not already taken (the format
    the frontend used, so existing ids and new ones read alike)."""
    prefix = f"op-{office_id if office_id is not None else 'x'}-"
    taken = set(db.execute(
        select(Operatory.id).where(Operatory.id.like(f"{prefix}%"))
    ).scalars().all())
    n = 1
    while f"{prefix}{n}" in taken:
        n += 1
    return f"{prefix}{n}"


class OperatoryCRUD(CRUDBase[Operatory]):
    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        payload = dict(data)
        if not (payload.get("id") or "").strip():
            payload["id"] = next_operatory_id(db, payload.get("office_id"))
        else:
            payload["id"] = payload["id"].strip()
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)
