"""MA-3 backfill: stamp ``section`` / ``alert_label`` on existing answers.

New writes fill both from the MEDALERT catalog (built-in list overlaid with the
tenant's definitions); reads fall back to the catalog for rows written before
that, so nothing renders wrong without this. Running it just makes the stored
rows self-describing, which is what a client reading ``/patient-medical-alerts``
directly sees. Only NULL columns are written — a stored value is always an
override and is never touched.

    python -m scripts.backfill_medical_alert_sections            # dry run
    python -m scripts.backfill_medical_alert_sections --apply
"""

from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import select

from app.db.models import PatientMedicalAlert
from app.db.session import SessionLocal
from app.services.medical_history_service import LEGACY_COMMENTS_CODE, alert_flags


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args()

    db = SessionLocal()
    stats: Counter = Counter()
    unmapped: Counter = Counter()
    try:
        rows = list(
            db.execute(
                select(PatientMedicalAlert).where(
                    (PatientMedicalAlert.section.is_(None))
                    | (PatientMedicalAlert.alert_label.is_(None))
                )
            ).scalars()
        )
        flags_by_tenant: dict[int, dict] = {}
        for row in rows:
            if row.alert_code == LEGACY_COMMENTS_CODE:
                stats["skipped_comments_row"] += 1
                continue
            flags = flags_by_tenant.setdefault(row.tenant_id, alert_flags(db, row.tenant_id))
            meta = flags.get(row.alert_code)
            if meta is None:
                unmapped[row.alert_code] += 1
                continue
            if row.section is None and meta.get("section"):
                row.section = meta["section"]
                stats["section"] += 1
            if row.alert_label is None and meta.get("label"):
                row.alert_label = meta["label"]
                stats["alert_label"] += 1
        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"[{mode}] rows examined: {len(rows)}")
    for key, value in sorted(stats.items()):
        print(f"  {key}: {value}")
    if unmapped:
        print("  codes not in any catalog (left as-is; read falls back to a humanised label):")
        for code, n in unmapped.most_common():
            print(f"    {code}: {n}")


if __name__ == "__main__":
    main()
