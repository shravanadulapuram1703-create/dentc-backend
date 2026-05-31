"""
STEP 23 — medical_history_records
Source: PatMedicalHistoryH.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import parse_bool, parse_datetime, clean


def run(conn, maps: dict) -> dict:
    patient_map = maps["patient_map"]
    sig_map     = maps.get("sig_map", {})

    src = cfg.src("PatMedicalHistoryH.txt")
    if not src.exists():
        print("  [s23] medical_history_records: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        hist_id = (row.get("PATMEDICALHISTORYID") or "").strip()
        rpid    = (row.get("RPID") or row.get("PATID") or "").strip()
        pat_id  = patient_map.get(rpid)

        if not pat_id:
            skipped += 1
            continue

        sig_legacy = (row.get("SIGNATUREID") or "").strip()
        sig_db_id  = sig_map.get(sig_legacy)
        created_at = parse_datetime(row.get("ACTDATE") or row.get("CREATEDDATE") or "")

        cur.execute(
            """
            INSERT INTO medical_history_records
                (patient_id, legacy_id, signature_id, is_archived, created_at)
            VALUES (%s,%s,%s,%s,COALESCE(%s, NOW()))
            ON CONFLICT DO NOTHING
            """,
            (
                pat_id, hist_id, sig_db_id,
                parse_bool(row.get("ISARCHIVED", "False")),
                created_at,
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s23] medical_history_records: {inserted} inserted, {skipped} skipped")
    return {}
