"""
Phase R1 — Reconcile the three sources of truth.

Cross-checks:
  A. manifest        (what the source claims exists)  — from state.db
  B. upload state    (what the uploader believes it wrote) — from state.db
  C. the GCS bucket  (what GCS actually holds) — a live listing

Produces state/reconcile_report.json and, if anything is off, a CSV of the
discrepancies. Ends by printing GO / NO-GO against the hard gates:

    objects_missing_from_gcs  MUST be 0
    objects_in_gcs_not_expected (orphans)  MUST be 0
    files still pending/error MUST be 0

Never mutates anything. Read-only.

Run:
    python 04_reconcile.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import common as c


def main() -> int:
    cfg = c.load_config()
    state_dir = cfg.state_path
    log = c.get_logger("reconcile", state_dir)

    if not cfg.gcs_bucket_originals:
        print("ERROR: GCS_BUCKET_ORIGINALS is not set in .env")
        return 2

    store = c.StateStore(state_dir)

    # ── A/B: from the resume store ──────────────────────────────────────
    expected_keys: dict[str, int] = {}   # object_key -> size
    counts = store.counts()
    total = store.total()
    for row in store.iter_all():
        if row["status"] in ("uploaded", "exists") and row["object_key"]:
            expected_keys[row["object_key"]] = row["size"] or 0
    store.close()

    log.info("Resume store: %d files total; %d distinct objects expected in GCS.",
             total, len(expected_keys))
    pending = counts.get("pending", 0) + counts.get("error", 0)

    # ── C: live bucket listing ──────────────────────────────────────────
    log.info("Listing gs://%s/%s/ … (this can take a few minutes)",
             cfg.gcs_bucket_originals, cfg.gcs_prefix)
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(cfg.gcs_bucket_originals)
    except Exception as exc:
        log.error("Could not create GCS client: %r", exc)
        return 2

    gcs_keys: dict[str, int] = {}
    n = 0
    bar = c.make_progress(max(len(expected_keys), 1), unit="obj", desc="list-gcs")
    for blob in client.list_blobs(bucket, prefix=f"{cfg.gcs_prefix}/"):
        gcs_keys[blob.name] = blob.size or 0
        n += 1
        if n % 500 == 0:
            bar.update(500)
    bar.close()
    log.info("GCS holds %d object(s) under the prefix.", len(gcs_keys))

    # ── compare ─────────────────────────────────────────────────────────
    exp = set(expected_keys)
    got = set(gcs_keys)
    missing = exp - got                      # expected but not in GCS
    orphans = got - exp                       # in GCS but not expected
    size_mismatch = [
        k for k in (exp & got) if expected_keys[k] and expected_keys[k] != gcs_keys[k]
    ]

    bytes_expected = sum(expected_keys.values())
    bytes_gcs = sum(gcs_keys.values())

    report = {
        "generated_at": c.utcnow_iso(),
        "bucket": cfg.gcs_bucket_originals,
        "prefix": cfg.gcs_prefix,
        "files_total": total,
        "files_uploaded": counts.get("uploaded", 0),
        "files_exists": counts.get("exists", 0),
        "files_pending_or_error": pending,
        "files_skipped": counts.get("skipped", 0),
        "objects_expected": len(exp),
        "objects_in_gcs": len(got),
        "objects_missing_from_gcs": len(missing),
        "objects_orphan_in_gcs": len(orphans),
        "objects_size_mismatch": len(size_mismatch),
        "bytes_expected": bytes_expected,
        "bytes_in_gcs": bytes_gcs,
    }
    (state_dir / "reconcile_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    if missing or orphans or size_mismatch:
        disc = state_dir / "reconcile_discrepancies.csv"
        with open(disc, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["kind", "object_key", "expected_size", "gcs_size"])
            for k in sorted(missing):
                w.writerow(["missing_from_gcs", k, expected_keys[k], ""])
            for k in sorted(orphans):
                w.writerow(["orphan_in_gcs", k, "", gcs_keys[k]])
            for k in sorted(size_mismatch):
                w.writerow(["size_mismatch", k, expected_keys[k], gcs_keys[k]])
        log.info("Discrepancies written to %s", disc)

    # ── verdict ─────────────────────────────────────────────────────────
    log.info("──────── RECONCILIATION ────────")
    for k, v in report.items():
        log.info("  %-26s : %s", k, v)
    gates_ok = (len(missing) == 0 and len(orphans) == 0
                and len(size_mismatch) == 0 and pending == 0)
    log.info("────────────────────────────────")
    if gates_ok:
        log.info("✅ GO — all gates pass. Bytes are safely in GCS.")
    else:
        log.warning("⛔ NO-GO — resolve the items above, then re-run upload + reconcile.")
        if missing:
            log.warning("   %d object(s) expected but MISSING from GCS.", len(missing))
        if orphans:
            log.warning("   %d ORPHAN object(s) in GCS not in the manifest.", len(orphans))
        if pending:
            log.warning("   %d file(s) still pending/error — run 02_upload.py again.", pending)
    return 0 if gates_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
