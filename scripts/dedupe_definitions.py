"""Collapse duplicate ``definitions`` rows (PLAN-DTL-6).

``s43_definitions`` inserts with ``ON CONFLICT DO NOTHING`` on a table that had
no unique key, so every migration pass re-inserted the whole DEFINITIONS export.
On the migrated tenant each group is present 5x (DEFCOVERAGE 140 rows for 28
codes, FREQUENCYLIMITATIONS 65 for 13, INSLIMITATIONS 110 for 22, …) and every
dropdown consumer has had to de-duplicate client-side.

Keeps the lowest ``id`` in each ``(tenant_id, group_code, key1, description)``
group and deletes the rest. Verified before writing this: on the live data the
members of every duplicate group are identical on **every** other column
(``key2``, ``legacy_id``, flags, colour, sort order), and no table references
``definitions.id``, so nothing has to be repointed.

Alembic ``c8d9e0f1a2b3`` performs the same collapse and adds the unique
constraint; this script exists for a DB where the migration has not run yet,
or to preview the effect.

    python -m scripts.dedupe_definitions --dry-run
    python -m scripts.dedupe_definitions
    python -m scripts.dedupe_definitions --tenant 1
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Definition
from app.db.session import SessionLocal


def duplicate_groups(db: Session, tenant_id: int | None):
    """Yield ``(keep_id, [dupe_ids], differs)`` for each duplicated key."""
    stmt = select(
        Definition.tenant_id, Definition.group_code, Definition.key1, Definition.description,
        func.min(Definition.id),
    )
    if tenant_id is not None:
        stmt = stmt.where(Definition.tenant_id == tenant_id)
    stmt = stmt.group_by(
        Definition.tenant_id, Definition.group_code, Definition.key1, Definition.description
    ).having(func.count() > 1)

    for tid, group_code, key1, description, keep_id in db.execute(stmt).all():
        rows = list(db.execute(
            select(Definition).where(
                Definition.tenant_id == tid, Definition.group_code == group_code,
                Definition.key1 == key1, Definition.description == description,
            ).order_by(Definition.id)
        ).scalars())
        keep = rows[0]
        dupes = rows[1:]
        differs = [
            d.id for d in dupes
            if (d.key2, d.legacy_id, d.color, d.sort_order, d.section, d.input_type,
                d.is_active, d.is_flash_alert, d.blocks_charges)
            != (keep.key2, keep.legacy_id, keep.color, keep.sort_order, keep.section,
                keep.input_type, keep.is_active, keep.is_flash_alert, keep.blocks_charges)
        ]
        yield keep_id, [d.id for d in dupes], differs


def dedupe(db: Session, tenant_id: int | None = None, *, dry_run: bool = False) -> tuple[int, int]:
    removed = differing = 0
    for _keep, dupe_ids, differs in duplicate_groups(db, tenant_id):
        removed += len(dupe_ids)
        differing += len(differs)
        if dry_run:
            continue
        db.execute(Definition.__table__.delete().where(Definition.id.in_(dupe_ids)))
    if not dry_run:
        db.commit()
    return removed, differing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without deleting")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        removed, differing = dedupe(db, args.tenant, dry_run=args.dry_run)
        verb = "would remove" if args.dry_run else "removed"
        print(f"dedupe_definitions: {verb} {removed} duplicate row(s); "
              f"{differing} of them differed from their survivor on a non-key column")
    finally:
        db.close()


if __name__ == "__main__":
    main()
