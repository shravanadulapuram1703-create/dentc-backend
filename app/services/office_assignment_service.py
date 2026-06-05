"""Office Assignment service (gaps #24–#32).

A single generic M:N reconcile (``get_assigned`` / ``set_assigned``) drives every
catalog→office assignment (procedures, exp-codes, production-types, providers,
note-macros, RX, letters), mirroring the ``user_offices`` pattern. Users get
dedicated bulk-set / copy-from helpers over the existing ``user_offices`` table.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Office, User, UserOffice

# ── Generic catalog↔office assignment ────────────────────────────────────────
def get_assigned(db: Session, link_model: type, fk_attr: str, target_model: type, target_pk: str, office_id: int) -> list:
    sub = select(getattr(link_model, fk_attr)).where(link_model.office_id == office_id)
    return list(db.execute(
        select(target_model).where(getattr(target_model, target_pk).in_(sub))
    ).scalars().all())


def set_assigned(
    db: Session, link_model: type, fk_attr: str, target_model: type, target_pk: str,
    office_id: int, tenant_id: int, ids: list[Any],
) -> list:
    existing = {
        getattr(row, fk_attr): row
        for row in db.execute(select(link_model).where(link_model.office_id == office_id)).scalars()
    }
    desired = set(ids)
    for key, row in existing.items():
        if key not in desired:
            db.delete(row)
    for key in desired:
        if key not in existing:
            db.add(link_model(tenant_id=tenant_id, office_id=office_id, **{fk_attr: key}))
    db.commit()
    return get_assigned(db, link_model, fk_attr, target_model, target_pk, office_id)


# ── Users (#27) — bulk set, copy-from, denormalized read over user_offices ───
def get_office_users(db: Session, office_id: int) -> list[User]:
    sub = select(UserOffice.user_id).where(UserOffice.office_id == office_id)
    return list(db.execute(
        select(User).where(User.id.in_(sub)).order_by(User.last_name.asc(), User.first_name.asc())
    ).scalars().all())


def set_office_users(db: Session, office_id: int, user_ids: list[int]) -> list[User]:
    existing = {
        link.user_id: link
        for link in db.execute(select(UserOffice).where(UserOffice.office_id == office_id)).scalars()
    }
    desired = set(user_ids)
    for uid, link in existing.items():
        if uid not in desired:
            db.delete(link)
    for uid in desired:
        if uid not in existing:
            db.add(UserOffice(user_id=uid, office_id=office_id, is_primary=False))
    db.commit()
    return get_office_users(db, office_id)


def copy_users_from(db: Session, target_office_id: int, source_office_id: int) -> list[User]:
    source_ids = set(db.execute(
        select(UserOffice.user_id).where(UserOffice.office_id == source_office_id)
    ).scalars().all())
    existing = set(db.execute(
        select(UserOffice.user_id).where(UserOffice.office_id == target_office_id)
    ).scalars().all())
    for uid in source_ids - existing:
        db.add(UserOffice(user_id=uid, office_id=target_office_id, is_primary=False))
    db.commit()
    return get_office_users(db, target_office_id)
