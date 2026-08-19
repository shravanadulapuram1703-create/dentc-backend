"""Load medical (CPT / HCPCS) procedure codes for medical cross-billing (CHG-3).

The Add-Procedures screen's **ALL MEDICAL** category button filters
``/procedure-codes`` to non-ADA codes (no leading ``D``); the catalog ships with
the ADA ``D####`` set only, so that button lands on an empty list. The API side
needs no change — ``GET /procedure-codes?category=medical`` already filters — this
is purely the data load.

No code list is bundled: CPT is AMA-licensed content, so the practice supplies
its own export (the same way ICD codes are handled in ``seed_aux_codes``). Point
this at a CSV with a header row; only ``code`` and ``description`` are required::

    code,description,category,default_fee,requires_tooth,requires_surface,requires_quadrant
    41899,Unlisted procedure - dentoalveolar structures,medical,0,false,false,false
    D0140,Limited oral evaluation,diagnostic,95,false,false,false

Unlisted columns fall back to the defaults (``category`` -> ``medical``, fee 0).
Idempotent: an existing ``code`` is updated in place, never duplicated.

    python -m scripts.seed_medical_codes path/to/medical_codes.csv
    python -m scripts.seed_medical_codes codes.csv --category cpt
    python -m scripts.seed_medical_codes codes.csv --dry-run
"""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProcedureCode
from app.db.session import SessionLocal

_BOOL_COLS = ("requires_tooth", "requires_surface", "requires_quadrant", "requires_lab")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "t")


def _decimal(value: str | None) -> Decimal:
    if value is None or value.strip() == "":
        return Decimal("0")
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return Decimal("0")


def load(
    db: Session, rows: list[dict], *, default_category: str = "medical", dry_run: bool = False
) -> tuple[int, int, int]:
    """Upsert ``rows`` into ``procedure_codes``. Returns (added, updated, skipped)."""
    added = updated = skipped = 0
    existing = {
        c.code: c for c in db.execute(select(ProcedureCode)).scalars()
    }
    for row in rows:
        code = (row.get("code") or "").strip()
        description = (row.get("description") or "").strip()
        if not code or not description:
            skipped += 1
            continue
        values = {
            "description": description[:500],
            "category": (row.get("category") or "").strip() or default_category,
            "default_fee": _decimal(row.get("default_fee")),
            "is_active": _bool(row.get("is_active"), True),
            **{col: _bool(row.get(col)) for col in _BOOL_COLS},
        }
        current = existing.get(code)
        if current is None:
            added += 1
            if not dry_run:
                db.add(ProcedureCode(code=code, **values))
        else:
            updated += 1
            if not dry_run:
                for key, value in values.items():
                    setattr(current, key, value)
    if not dry_run:
        db.commit()
    return added, updated, skipped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path, help="CSV export of the practice's medical codes")
    parser.add_argument(
        "--category", default="medical", help="Category for rows with no category column"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, write nothing")
    args = parser.parse_args()

    with args.csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"{args.csv_path}: no rows (is the header row present?)")

    with SessionLocal() as db:
        added, updated, skipped = load(
            db, rows, default_category=args.category, dry_run=args.dry_run
        )
    verb = "would load" if args.dry_run else "loaded"
    print(f"{verb} {added} new + {updated} updated procedure code(s); {skipped} row(s) skipped")


if __name__ == "__main__":
    main()
