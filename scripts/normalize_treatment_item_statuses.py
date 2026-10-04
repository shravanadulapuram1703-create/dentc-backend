"""Fold legacy ``treatment_plan_items.status`` codes to the canonical enum (SCHED-PT-4).

Why this exists
---------------
``TreatmentPlanItemRead.status`` is now the typed ``ItemStatus`` enum in OpenAPI
(the write schemas already were). Legacy Denticon rows can carry the old codes
(``D``/``A``/``U``/``H``/``Alt``/``RO``, ``planned`` …); the read model folds them
through ``treatment_service.LEGACY_ITEM_STATUS_MAP`` so they never 500, and this
script rewrites the stored values so filters (``?status=``) and the pending rule
see the canonical value too.

On the dev DB (2026-10-03) every one of the 775 rows was already canonical — the
PROC-INT migration lower-cased ``Completed``/``Scheduled`` — so this is for other
environments / re-imports.

An unrecognised value is **left as stored and reported** (not guessed): add it to
``LEGACY_ITEM_STATUS_MAP`` if it turns out to be a variant. Such a row would fail
read validation, so the report is the thing to act on.

Usage
-----
Dry-run by default::

    python -m scripts.normalize_treatment_item_statuses
    python -m scripts.normalize_treatment_item_statuses --apply
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import get_args

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import TreatmentPlanItem
from app.db.session import SessionLocal
from app.schemas.treatment import ItemStatus
from app.services.treatment_service import normalise_item_status

CANONICAL = set(get_args(ItemStatus))


def run(session: Session, *, apply: bool) -> None:
    rows = session.execute(
        select(TreatmentPlanItem.status, func.count()).group_by(TreatmentPlanItem.status)
    ).all()
    changes: Counter[tuple[str | None, str]] = Counter()
    unrecognised: Counter[str | None] = Counter()
    for stored, count in rows:
        canon = normalise_item_status(stored)
        if canon not in CANONICAL:
            unrecognised[stored] += count
            continue
        if canon != stored:
            changes[(stored, canon)] += count
            if apply:
                session.execute(
                    update(TreatmentPlanItem)
                    .where(TreatmentPlanItem.status == stored)
                    .values(status=canon)
                )

    print(f"{'APPLY' if apply else 'DRY RUN'}: {sum(changes.values())} row(s) to fold")
    for (old, new), n in sorted(changes.items(), key=lambda kv: -kv[1]):
        print(f"  {old!r:>20} -> {new:<18} {n}")
    if unrecognised:
        print("Unrecognised (left as stored — add to LEGACY_ITEM_STATUS_MAP):")
        for value, n in unrecognised.most_common():
            print(f"  {value!r:>20} {n}")
    if apply:
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()
    with SessionLocal() as session:
        run(session, apply=args.apply)


if __name__ == "__main__":
    main()
