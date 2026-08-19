"""Refresh the ADA/CDT catalog in ``procedure_codes`` from a categorized master CSV.

``procedure_codes`` is the single global (no ``tenant_id``) catalog — the ADA/CDT
code *is* the primary key, and every transactional table (``patient_procedures``,
``fee_schedule_entries``, ``chart_conditions``, …) FKs to it. So this loader
**never deletes**: a code that is missing from the CSV stays put (it may be a
legacy/local code with a million ledger rows behind it).

Why not ``seed_medical_codes.py``? That one is a first-time bulk load and stamps
``default_fee``/``requires_*``/``is_active`` from the CSV, resetting anything the
Denticon migration or the practice already set. This script is the *refresh* path:
it only touches the two columns the master list is authoritative for —
``description`` and ``category`` — and leaves fees, charting config (PROC-1),
tooth/surface rules (CHG-2) and the active flag alone.

Expected CSV (header names are matched case-insensitively)::

    Category,Code,Description
    Diagnostic,D0120,Periodic Oral Evaluation

    python -m scripts.seed_ada_codes --dry-run                 # report, write nothing
    python -m scripts.seed_ada_codes                           # data/ada_cdt_categorized_master.csv
    python -m scripts.seed_ada_codes path/to/other.csv
    python -m scripts.seed_ada_codes --medical-category medical  # relabel non-D codes (CHG-3)
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProcedureCode
from app.db.session import SessionLocal

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "ada_cdt_categorized_master.csv"

# Column widths from the model — truncate rather than let the driver raise.
_MAX_CODE = 20
_MAX_DESCRIPTION = 500
_MAX_CATEGORY = 100


def _read_csv(path: Path) -> list[tuple[str, str, str]]:
    """Return [(code, description, category)] with case-insensitive headers."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise SystemExit(f"{path}: empty file (no header row)")
        lookup = {(name or "").strip().lower(): name for name in reader.fieldnames}
        missing = {"code", "description"} - lookup.keys()
        if missing:
            raise SystemExit(
                f"{path}: missing column(s) {sorted(missing)}; found {reader.fieldnames}"
            )
        out: list[tuple[str, str, str]] = []
        for row in reader:
            code = (row.get(lookup["code"]) or "").strip()
            description = (row.get(lookup["description"]) or "").strip()
            category = (row.get(lookup.get("category", "")) or "").strip()
            if not code or not description:
                continue
            out.append((code[:_MAX_CODE], description[:_MAX_DESCRIPTION], category[:_MAX_CATEGORY]))
    return out


def load(
    db: Session,
    rows: list[tuple[str, str, str]],
    *,
    fallback_category: str = "Other",
    medical_category: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Upsert description/category only. Returns a counts dict."""
    existing = {c.code: c for c in db.execute(select(ProcedureCode)).scalars()}
    seen: set[str] = set()
    added = changed = unchanged = duplicate = 0

    for code, description, category in rows:
        if code in seen:
            duplicate += 1
            continue
        seen.add(code)

        # CHG-3: the "ALL MEDICAL" button wants the non-ADA (CPT/HCPCS) codes findable.
        # The master list files them under the same catch-all as everything else, so
        # relabel them on request instead of shipping a second CSV.
        if medical_category and not code[:1].isalpha():
            category = medical_category
        category = category or fallback_category

        current = existing.get(code)
        if current is None:
            added += 1
            if not dry_run:
                db.add(ProcedureCode(code=code, description=description, category=category))
        elif current.description != description or current.category != category:
            changed += 1
            if not dry_run:
                current.description = description
                current.category = category
        else:
            unchanged += 1

    if not dry_run:
        db.commit()

    return {
        "added": added,
        "changed": changed,
        "unchanged": unchanged,
        "duplicate_rows": duplicate,
        "kept_not_in_csv": len(existing.keys() - seen),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_path", nargs="?", type=Path, default=DEFAULT_CSV, help=f"default: {DEFAULT_CSV}"
    )
    parser.add_argument(
        "--fallback-category", default="Other", help="category for rows with a blank Category cell"
    )
    parser.add_argument(
        "--medical-category",
        default=None,
        metavar="NAME",
        help='relabel non-ADA codes (no leading letter) to NAME, e.g. "medical" (CHG-3)',
    )
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args()

    if not args.csv_path.exists():
        raise SystemExit(f"{args.csv_path}: not found")

    rows = _read_csv(args.csv_path)
    if not rows:
        raise SystemExit(f"{args.csv_path}: no usable rows")

    with SessionLocal() as db:
        counts = load(
            db,
            rows,
            fallback_category=args.fallback_category,
            medical_category=args.medical_category,
            dry_run=args.dry_run,
        )

    verb = "would apply" if args.dry_run else "applied"
    print(
        f"seed_ada_codes ({args.csv_path.name}, {len(rows)} rows): {verb} "
        f"{counts['added']} new + {counts['changed']} updated, "
        f"{counts['unchanged']} already current, {counts['duplicate_rows']} duplicate row(s); "
        f"{counts['kept_not_in_csv']} existing code(s) not in the CSV left untouched"
    )


if __name__ == "__main__":
    main()
