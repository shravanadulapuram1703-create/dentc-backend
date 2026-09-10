"""Move legacy Topaz SigStrings out of the image column (SIG-1, legacy note).

Why
---
The legacy import wrote every migrated ``patient_signatures`` row with
``device_source = "0"`` and the raw Topaz **SigString** (``02008C00D5…`` — the
vector stroke record) in ``signature_data``, the column that is supposed to hold
a rendered image. Measured on the dev database on 2026-09-10 (3,862 rows):
3,760 legacy SigStrings (``device_source="0"``), 98 migrated data-URL images
(``device_source="2"``), 2 ``web-pad`` data URLs, and 2 rows holding the literal
string ``undefined`` (a legacy client bug; left alone and reported as
``unrecognised_kept``). The frontend cannot render a SigString as ``<img>`` and
shows "Topaz signature on file (legacy data — image not available)" for them.

**Applied on the dev database 2026-09-10**: 3,760 moved, 0 raw SigStrings left in
``signature_data``, every ``sig_string`` encrypted.

What this does
--------------
For every row whose ``signature_data`` *looks like* a SigString
(``signature_service.looks_like_sigstring``: hex text, not a ``data:`` URL) and
whose ``sig_string`` is still NULL:

* ``sig_string``      ← the SigString, **encrypted at rest** (SIG-4)
* ``sig_format``      ← ``topaz_sigstring_v1``
* ``device_vendor``   ← ``topaz``
* ``signature_data``  ← NULL (there is no image; the FE reads ``has_sig_string``)
* ``signature_len``   ← NULL (it was the SigString length, not an image length)

``device_source`` is left as the legacy ``"0"`` — it is part of the published
vocabulary and is the only marker that the row came from the import.

No image is rendered: turning a SigString back into a JPEG needs Topaz SigPlus
(a Windows COM component), which the API server does not have. A row migrated
here is exactly as renderable as it was before — just stored in the right
column, encrypted, and reported honestly.

``--users`` applies the same rule to ``users.signature_data`` (the Security →
Users signature store), writing the ``signature_``-prefixed columns.

Safe to re-run: a row already moved has ``sig_string`` set and is skipped.

Usage::

    python -m scripts.migrate_legacy_sigstrings                # dry run, report only
    python -m scripts.migrate_legacy_sigstrings --apply
    python -m scripts.migrate_legacy_sigstrings --apply --tenant-id 1 --users
"""

from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import select

from app.db.models import Patient, PatientSignature, User
from app.db.session import SessionLocal
from app.services import signature_service as svc

BATCH = 500


def _migrate_patient_signatures(db, *, tenant_id: int | None, apply: bool) -> Counter:  # noqa: ANN001
    stats: Counter = Counter()
    id_stmt = select(PatientSignature.id).where(
        PatientSignature.signature_data.is_not(None),
        PatientSignature.sig_string.is_(None),
    )
    if tenant_id is not None:
        id_stmt = id_stmt.where(
            PatientSignature.patient_id.in_(select(Patient.id).where(Patient.tenant_id == tenant_id))
        )
    # Ids first, then batches by id: a server-side cursor cannot survive the
    # per-batch commit, and the whole table is a few thousand rows.
    ids = list(db.execute(id_stmt.order_by(PatientSignature.id)).scalars())
    pending = 0
    for start in range(0, len(ids), BATCH):
        chunk = ids[start:start + BATCH]
        rows = db.execute(
            select(PatientSignature).where(PatientSignature.id.in_(chunk))
        ).scalars().all()
        for row in rows:
            _migrate_row(row, stats, apply)
            if apply:
                pending += 1
        if apply and pending >= BATCH:
            db.commit()
            pending = 0
    if apply:
        db.commit()
    return stats


def _migrate_row(row: PatientSignature, stats: Counter, apply: bool) -> None:
    stats["scanned"] += 1
    data = row.signature_data or ""
    if data.strip().startswith("data:"):
        stats["image_kept"] += 1
        return
    if not svc.looks_like_sigstring(data):
        stats["unrecognised_kept"] += 1
        return
    stats["sigstring_moved"] += 1
    if row.device_source == svc.DEVICE_SOURCE_LEGACY:
        stats["legacy_source"] += 1
    if not apply:
        return
    row.sig_string = svc.encrypt_sig_string(data.strip())
    row.sig_format = svc.SIG_FORMAT_TOPAZ_V1
    row.device_vendor = svc.DEVICE_VENDOR_TOPAZ
    row.signature_data = None
    row.signature_len = None


def _migrate_users(db, *, tenant_id: int | None, apply: bool) -> Counter:  # noqa: ANN001
    stats: Counter = Counter()
    stmt = select(User).where(User.signature_data.is_not(None), User.signature_sig_string.is_(None))
    if tenant_id is not None:
        stmt = stmt.where(User.tenant_id == tenant_id)
    for user in db.execute(stmt).scalars():
        stats["scanned"] += 1
        data = user.signature_data or ""
        if data.strip().startswith("data:"):
            stats["image_kept"] += 1
            continue
        if not svc.looks_like_sigstring(data):
            stats["unrecognised_kept"] += 1
            continue
        stats["sigstring_moved"] += 1
        if not apply:
            continue
        user.signature_sig_string = svc.encrypt_sig_string(data.strip())
        user.signature_sig_format = svc.SIG_FORMAT_TOPAZ_V1
        user.signature_device_vendor = svc.DEVICE_VENDOR_TOPAZ
        user.signature_data = None
        user.signature_len = None
    if apply:
        db.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--users", action="store_true", help="also migrate users.signature_data")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY RUN"
    with SessionLocal() as db:
        stats = _migrate_patient_signatures(db, tenant_id=args.tenant_id, apply=args.apply)
        print(f"[{mode}] patient_signatures: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
        if args.users:
            ustats = _migrate_users(db, tenant_id=args.tenant_id, apply=args.apply)
            print(f"[{mode}] users: " + ", ".join(f"{k}={v}" for k, v in sorted(ustats.items())))
    if not args.apply:
        print("Nothing written. Re-run with --apply to move the SigStrings.")


if __name__ == "__main__":
    main()
