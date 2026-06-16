"""Collapse duplicate code_bundles (Explosion Codes) per (tenant_id, legacy_id).

Background: the Denticon importer used ``ON CONFLICT DO NOTHING`` but
``code_bundles`` had no unique constraint, so the clause was a no-op — re-runs and
repeated source rows produced duplicate bundles (e.g. 4 rows per legacy_id). This
keeps the lowest ``id`` in each group and removes the duplicates (and their items,
which are redundant copies hanging off the duplicate bundle).

Idempotent. Run after deploying the uniqueness migration is not required — the
migration runs the same dedupe before adding the constraint — but this script lets
you dedupe on demand or per tenant.

    python -m scripts.dedupe_code_bundles            # all tenants
    python -m scripts.dedupe_code_bundles --tenant 1 # one tenant
    python -m scripts.dedupe_code_bundles --dry-run  # report only
"""

from __future__ import annotations

import argparse

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import CodeBundle, CodeBundleItem
from app.db.session import SessionLocal


def dedupe(db: Session, tenant_id: int | None = None, *, dry_run: bool = False) -> int:
    """Remove duplicate bundles; return the number of bundles removed."""
    survivors = select(
        CodeBundle.tenant_id, CodeBundle.legacy_id, func.min(CodeBundle.id)
    ).where(CodeBundle.legacy_id.is_not(None))
    if tenant_id is not None:
        survivors = survivors.where(CodeBundle.tenant_id == tenant_id)
    survivors = survivors.group_by(CodeBundle.tenant_id, CodeBundle.legacy_id).having(
        func.count() > 1
    )

    removed = 0
    for tid, legacy_id, keep_id in db.execute(survivors).all():
        dupe_ids = db.execute(
            select(CodeBundle.id).where(
                CodeBundle.tenant_id == tid,
                CodeBundle.legacy_id == legacy_id,
                CodeBundle.id != keep_id,
            )
        ).scalars().all()
        if not dupe_ids:
            continue
        removed += len(dupe_ids)
        if dry_run:
            continue
        db.execute(delete(CodeBundleItem).where(CodeBundleItem.bundle_id.in_(dupe_ids)))
        db.execute(delete(CodeBundle).where(CodeBundle.id.in_(dupe_ids)))
    if not dry_run:
        db.commit()
    return removed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without deleting")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        n = dedupe(db, args.tenant, dry_run=args.dry_run)
        verb = "would remove" if args.dry_run else "removed"
        print(f"dedupe_code_bundles: {verb} {n} duplicate bundle(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
