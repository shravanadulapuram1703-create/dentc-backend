"""Normalize chart_materials.pattern from legacy GIF filenames to bare keys.

Background: the Denticon importer (``migration/steps/s12_chart_materials.py``)
stored the source ``MATPATTERN`` value verbatim — a GIF filename such as
``hash.gif`` / ``round.gif`` / ``arestin.gif``. The charting renderer (and the
Restorative Materials Setup screen's Sample column) keys its fill-pattern catalog
by the *bare* key (``hash``, ``round``, ``arestin``), so a stored ``hash.gif``
never matches and the cell renders a ``?`` placeholder.

This strips the file extension and lowercases, so ``hash.gif`` -> ``hash``.
NULL patterns (e.g. the "Unknown" material) are left untouched.

Idempotent — running twice is a no-op (already-bare keys have no extension).

    python -m scripts.backfill_chart_material_patterns            # all tenants
    python -m scripts.backfill_chart_material_patterns --tenant 1 # one tenant
    python -m scripts.backfill_chart_material_patterns --dry-run  # report only
"""

from __future__ import annotations

import argparse
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChartMaterial
from app.db.session import SessionLocal


def normalize_pattern(value: str | None) -> str | None:
    """``hash.gif`` -> ``hash``; bare/empty/None pass through unchanged."""
    if not value:
        return value
    base = os.path.splitext(value.strip())[0]
    return base.lower() or None


def backfill(db: Session, tenant_id: int | None = None, *, dry_run: bool = False) -> int:
    """Rewrite legacy ``*.gif`` patterns to bare keys; return rows changed."""
    stmt = select(ChartMaterial).where(ChartMaterial.pattern.is_not(None))
    if tenant_id is not None:
        stmt = stmt.where(ChartMaterial.tenant_id == tenant_id)

    changed = 0
    for mat in db.execute(stmt).scalars():
        new_val = normalize_pattern(mat.pattern)
        if new_val != mat.pattern:
            changed += 1
            if not dry_run:
                mat.pattern = new_val
    if not dry_run:
        db.commit()
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        n = backfill(db, args.tenant, dry_run=args.dry_run)
        verb = "would normalize" if args.dry_run else "normalized"
        print(f"backfill_chart_material_patterns: {verb} {n} pattern(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
