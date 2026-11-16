"""RP-1/RP-3/RP-4: give every patient without an account one (re-runnable).

Alembic ``9435491c1d19`` runs the same ``account_backfill.backfill`` inside the
migration. Re-run it after anything writes patients by raw SQL (the Denticon
importer ``s17``), then ``scripts.import_legacy_responsible_parties`` (RP-14).

    python -m scripts.backfill_patient_accounts            # dry run (rolled back)
    python -m scripts.backfill_patient_accounts --apply
"""

from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.services.account_backfill import backfill


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        summary = backfill(db.connection())
        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    for k, v in summary.items():
        print(f"{k:36} {v}")
    print(f"{'applied':36} {args.apply}")


if __name__ == "__main__":
    main()
