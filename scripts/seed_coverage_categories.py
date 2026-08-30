"""Seed ``procedure_codes.coverage_category`` — the ADA → coverage-category
mapping the insurance-estimate engine matches on (FEE-1).

Why this exists
---------------
Every coverage percentage in the system lives in ``insurance_coverage_rules``
banded on **Denticon coverage-category codes**::

    start_code  end_code  description                     coverage_pct
    01          01        Diagnostic                            100.00
    01A         01A       Diagnostic:  X-Rays                   100.00
    03          03        Restorative                            80.00
    03A         03A       Restorative: Crowns                    50.00

A charge, meanwhile, carries an ADA code (``D2740``). Nothing joined the two, so
``estimate_service`` compared ``"D2740"`` against the band ``"03A"``–``"03A"``,
matched nothing, and returned **0 % insurance on every migrated plan** — the
FEE-1 blocker. (A minority of plans band on real ADA ranges, ``D0100``–``D0999``;
those always worked, which is why the bug looked intermittent.)

The source column is gone: Denticon's ``Codes.INSCATEGORYID`` was read by
migration step ``s10`` only to derive the display label (``category =
"Restorative"``) and then discarded, so it cannot be re-read without a fresh
export. What *is* reconstructable is the structure itself — the categories are
organised along the published **CDT family ranges** (``D2xxx`` = restorative,
``D3xxx`` = endodontics, …), the same public taxonomy
``scripts/seed_procedure_code_rules.py`` derives the ``requires_*`` flags from.
No licensed CDT data file is used and no ADA descriptor text is reproduced.

The range table lives in ``app/services/coverage_category_service.py`` so the
seeder, the estimate engine and ``GET /api/v1/metadata/coverage-categories`` all
read the same rows — the mapping cannot drift between what is stored, what is
matched, and what is published.

What it will *not* do
---------------------
* A code that matches no range is left **NULL**, never filed under
  ``12`` ("Non-covered Services"). The 167 medical/CPT codes in the catalog are
  *unclassified*, not *denied*, and a seeder is not the place to decide that.
* Without ``--overwrite`` a code that already carries a category is left alone,
  so a practice that corrected ``D2950`` keeps its correction. That is also why
  ``coverage_category_service.category_for`` prefers the stored value over the
  derived one.

Usage
-----
Dry-run by default — it prints what would change and writes nothing::

    python -m scripts.seed_coverage_categories                 # report only
    python -m scripts.seed_coverage_categories --apply         # write
    python -m scripts.seed_coverage_categories --apply --overwrite
    python -m scripts.seed_coverage_categories --csv map.csv --apply

``--csv`` takes precedence over the derived ranges for the codes it names::

    code,coverage_category
    D2950,03B
    D9944,11B
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProcedureCode
from app.db.session import SessionLocal
from app.services import coverage_category_service as covcat


def _load_csv(path: Path) -> dict[str, str]:
    overrides: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("code") or "").strip()
            cat = (row.get("coverage_category") or "").strip()
            if code and cat:
                overrides[code] = cat
    return overrides


def run(session: Session, *, apply: bool, overwrite: bool, overrides: dict[str, str]) -> int:
    codes = session.execute(select(ProcedureCode)).scalars().all()

    changed = 0
    skipped_existing = 0
    unmapped: list[str] = []
    per_category: Counter[str] = Counter()

    for proc in codes:
        target = overrides.get(proc.code) or covcat.derive_category(proc.code)
        if target is None:
            unmapped.append(proc.code)
            continue
        per_category[target] += 1
        if proc.coverage_category == target:
            continue
        if proc.coverage_category and not overwrite:
            skipped_existing += 1
            continue
        if apply:
            proc.coverage_category = target
        changed += 1

    if apply:
        session.commit()

    verb = "set" if apply else "would set"
    print(f"procedure_codes scanned: {len(codes)}")
    print(f"  coverage_category {verb}: {changed}")
    if skipped_existing:
        print(f"  left alone (already classified, no --overwrite): {skipped_existing}")
    print(f"  unmapped (left NULL): {len(unmapped)}")
    if unmapped:
        preview = ", ".join(sorted(unmapped)[:12])
        print(f"    e.g. {preview}{' …' if len(unmapped) > 12 else ''}")
    print("  by category:")
    for cat, count in sorted(per_category.items()):
        print(f"    {cat:<4} {covcat.describe(cat) or '':<42} {count}")
    if not apply:
        print("\nDry run — nothing written. Re-run with --apply.")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument("--overwrite", action="store_true",
                        help="also replace a category a code already carries")
    parser.add_argument("--csv", type=Path, help="per-code overrides (code,coverage_category)")
    args = parser.parse_args()

    overrides = _load_csv(args.csv) if args.csv else {}
    if overrides:
        print(f"csv overrides: {len(overrides)} codes")

    with SessionLocal() as session:
        run(session, apply=args.apply, overwrite=args.overwrite, overrides=overrides)


if __name__ == "__main__":
    main()
