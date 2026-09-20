"""Backfill ``user_offices`` (OFF-SCOPE data hygiene).

Office scoping treats a user with **zero** ``user_offices`` rows as *ungated*
(tenant-wide) so a migrated tenant is never locked out on deploy day — but that
means scoping does nothing for them until their assignments are seeded. The
report's data-hygiene note: *every real user must have ``user_offices`` rows,
with ``is_primary`` set for one of them* (even the seeded admin's ``offices[]``
is empty today).

This reconstructs each user's assignments from evidence already in the database,
in priority order, and marks a primary:

1. an existing ``user_offices`` row              — never disturbed
2. the linked provider's home office             — ``providers.user_id`` → ``providers.office_id``
3. offices the user posted/clocked into          — ``time_clock_entries``, ``audit_logs.office_id``
4. the tenant's single office, if it has one     — an unambiguous default

A user with none of the above (a corporate admin who never worked a chair) is
left unassigned on purpose — they are almost always the ``admin``/``owner`` who
holds ``offices:view_all`` and is meant to be tenant-wide.

    python -m scripts.backfill_user_offices                 # all tenants
    python -m scripts.backfill_user_offices --tenant 1      # one tenant
    python -m scripts.backfill_user_offices --dry-run       # report only
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Office, Provider, TimeClockEntry, User, UserOffice
from app.db.models.audit import AuditLog
from app.db.session import SessionLocal


def _existing(db: Session, user_id: int) -> set[int]:
    return set(db.execute(
        select(UserOffice.office_id).where(UserOffice.user_id == user_id)
    ).scalars().all())


def _evidence_offices(db: Session, user: User, tenant_office_ids: set[int]) -> list[int]:
    ordered: list[int] = []

    def _add(oid) -> None:  # noqa: ANN001
        if oid in tenant_office_ids and oid not in ordered:
            ordered.append(oid)

    # 2) linked provider's home office
    prov_office = db.execute(
        select(Provider.office_id).where(Provider.user_id == user.id)
    ).scalars().first()
    if prov_office is not None:
        _add(prov_office)
    # 3) where the user clocked in / made audited changes
    for oid in db.execute(
        select(TimeClockEntry.office_id).where(TimeClockEntry.user_id == user.id).distinct()
    ).scalars().all():
        _add(oid)
    for oid in db.execute(
        select(AuditLog.office_id).where(
            AuditLog.user_id == user.id, AuditLog.office_id.is_not(None)
        ).distinct()
    ).scalars().all():
        _add(oid)
    # 4) an only-office tenant
    if not ordered and len(tenant_office_ids) == 1:
        _add(next(iter(tenant_office_ids)))
    return ordered


def backfill(db: Session, tenant_id: int | None, dry_run: bool) -> dict:
    tenants = (
        [tenant_id]
        if tenant_id is not None
        else list(db.execute(select(Office.tenant_id).distinct()).scalars().all())
    )
    added = users_touched = 0
    for tid in tenants:
        tenant_office_ids = set(db.execute(
            select(Office.id).where(Office.tenant_id == tid, Office.is_active.is_(True))
        ).scalars().all())
        if not tenant_office_ids:
            continue
        users = db.execute(
            select(User).where(User.tenant_id == tid, User.is_active.is_(True))
        ).scalars().all()
        for user in users:
            if _existing(db, user.id):
                continue
            offices = _evidence_offices(db, user, tenant_office_ids)
            if not offices:
                continue
            users_touched += 1
            for i, oid in enumerate(offices):
                added += 1
                if not dry_run:
                    db.add(UserOffice(user_id=user.id, office_id=oid, is_primary=(i == 0)))
    if not dry_run:
        db.commit()
    return {"users_touched": users_touched, "assignments_added": added, "dry_run": dry_run}


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill user_offices from evidence")
    ap.add_argument("--tenant", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        result = backfill(db, args.tenant, args.dry_run)
    finally:
        db.close()
    print(result)


if __name__ == "__main__":
    main()
