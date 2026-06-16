"""
STEP 23 — medical_history_records
Source: PatMedicalHistoryH.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import parse_bool, parse_datetime, clean

COLS = ["patient_id", "legacy_id", "signature_id", "is_archived", "created_at"]


def run(conn, maps: dict) -> dict:
    patient_map = maps["patient_map"]
    sig_map     = maps.get("sig_map", {})

    src = cfg.src("PatMedicalHistoryH.txt")
    if not src.exists():
        print("  [s23] medical_history_records: file not found, skipping")
        return {}

    skipped = 0
    buf = BulkBuffer(
        conn, "medical_history_records", COLS,
        conflict="ON CONFLICT DO NOTHING",
        template="(%s,%s,%s,%s,COALESCE(%s, NOW()))",
        flush_every=20000, page_size=2000, label="medical_history_records",
    )

    for row in read_denticon_file(src):
        hist_id = (row.get("PATMEDICALHISTORYID") or "").strip()
        rpid    = (row.get("PATID") or row.get("RPID") or "").strip()  # PatMedicalHistoryH is PATID-keyed
        pat_id  = patient_map.get(rpid)

        if not pat_id:
            skipped += 1
            continue

        sig_legacy = (row.get("SIGNATUREID") or "").strip()
        sig_db_id  = sig_map.get(sig_legacy)
        created_at = parse_datetime(row.get("CREATEDON") or row.get("ACTDATE") or "")

        buf.add((
            pat_id, hist_id, sig_db_id,
            parse_bool(row.get("MOVETOARCHIVE", "False")),
            created_at,
        ))

    buf.flush()
    print(f"  [s23] medical_history_records: {buf.inserted} inserted, {skipped} skipped")
    return {}
