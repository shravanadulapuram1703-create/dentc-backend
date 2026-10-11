"""Backfill ``providers.taxonomy_code`` from Denticon ``Providers.SPECIALTYID`` (FSW-5).

Denticon stores a provider's specialty as the **NUCC taxonomy code**
(``1223G0001X`` General Practice on 85 of 93 exported providers, ``122300000X``,
``124Q00000X``, ``1223P0700X``). The migration never carried it — ``specialty`` is
blank on 95 of 97 dev-DB providers and ``taxonomy_code`` on all of them — so the
New Fee Schedule Wizard's Specialties option listed almost nobody, and a
specialty-keyed fee-schedule assignment could never price.

The taxonomy code is the specialty id assignments match on
(``provider_taxonomy_service.provider_specialty_code``), so filling it is the
whole repair. Providers are matched on ``providers.legacy_id = PROVIDERID``
within ``--tenant-id``.

Dry-run by default. ``--apply`` writes; only NULL/blank ``taxonomy_code`` rows are
touched unless ``--overwrite``. Every change is written to a JSON backup first
(``--restore <file>`` puts the previous values back).

    python -m scripts.backfill_provider_specialties --tenant-id 1
    python -m scripts.backfill_provider_specialties --tenant-id 1 --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.db.models import Provider
from app.db.session import SessionLocal
from app.services.provider_taxonomy_service import is_taxonomy_shaped, label_for

DEFAULT_SOURCE = "F:/Recon Dental Data/Data Migration/Data Migration/Providers.txt"
BACKUP_DIR = Path(__file__).resolve().parent / "backups"


def _read_source(path: str) -> dict[str, str]:
    with open(path, encoding="latin-1", newline="") as fh:
        return {
            (row.get("PROVIDERID") or "").strip(): (row.get("SPECIALTYID") or "").strip().upper()
            for row in csv.DictReader(fh)
            if (row.get("PROVIDERID") or "").strip()
        }


def _restore(path: str) -> int:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        for row in rows:
            provider = db.get(Provider, row["id"])
            if provider is not None:
                provider.taxonomy_code = row["before"]
        db.commit()
    finally:
        db.close()
    print(f"restored {len(rows)} provider(s) from {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenant-id", type=int, help="Tenant whose providers carry these legacy ids")
    ap.add_argument("--source", default=DEFAULT_SOURCE, help="Path to Denticon Providers.txt")
    ap.add_argument("--apply", action="store_true", help="Write (default is a dry run)")
    ap.add_argument("--overwrite", action="store_true", help="Also replace a non-blank taxonomy_code")
    ap.add_argument("--restore", metavar="BACKUP_JSON", help="Undo a previous --apply")
    args = ap.parse_args(argv)

    if args.restore:
        return _restore(args.restore)
    if args.tenant_id is None:
        ap.error("--tenant-id is required")

    source = _read_source(args.source)
    db = SessionLocal()
    try:
        providers = db.execute(
            select(Provider).where(Provider.tenant_id == args.tenant_id, Provider.legacy_id.is_not(None))
        ).scalars().all()
        changes: list[dict] = []
        stats = {"providers": len(providers), "no_source_row": 0, "blank_in_source": 0,
                 "not_taxonomy_shaped": 0, "already_set": 0, "unchanged": 0, "to_write": 0}
        for p in providers:
            code = source.get((p.legacy_id or "").strip())
            if code is None:
                stats["no_source_row"] += 1
                continue
            if not code:
                stats["blank_in_source"] += 1
                continue
            if not is_taxonomy_shaped(code):
                stats["not_taxonomy_shaped"] += 1
                continue
            current = (p.taxonomy_code or "").strip().upper()
            if current == code:
                stats["unchanged"] += 1
                continue
            if current and not args.overwrite:
                stats["already_set"] += 1
                continue
            changes.append({"id": p.id, "legacy_id": p.legacy_id, "name": p.name,
                            "before": p.taxonomy_code, "after": code, "label": label_for(code)})
        stats["to_write"] = len(changes)

        by_code: dict[str, int] = {}
        for c in changes:
            by_code[c["after"]] = by_code.get(c["after"], 0) + 1
        print(json.dumps({"tenant_id": args.tenant_id, "apply": args.apply, **stats,
                          "by_code": {f"{k} ({label_for(k) or '?'})": v for k, v in sorted(by_code.items())}},
                         indent=2))
        if not args.apply or not changes:
            if not args.apply:
                print("dry run - nothing written (pass --apply)")
            return 0

        BACKUP_DIR.mkdir(exist_ok=True)
        backup = BACKUP_DIR / f"provider_taxonomy_{args.tenant_id}_{datetime.now():%Y%m%d%H%M%S}.json"
        backup.write_text(json.dumps(changes, indent=2), encoding="utf-8")
        for c in changes:
            db.get(Provider, c["id"]).taxonomy_code = c["after"]
        db.commit()
        print(f"wrote {len(changes)} provider(s); backup {backup}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
