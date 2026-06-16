"""
STEP 20 — patient_alerts
Source: PatFlashAlerts.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import clean, parse_bool, parse_datetime

COLS = ["patient_id", "legacy_id", "alert", "blocks_charges", "is_active", "deactivated_on"]


def run(conn, maps: dict) -> dict:
    patient_map = maps["patient_map"]

    src = cfg.src("PatFlashAlerts.txt")
    if not src.exists():
        print("  [s20] patient_alerts: file not found, skipping")
        return {}

    skipped = 0
    buf = BulkBuffer(
        conn, "patient_alerts", COLS,
        conflict="ON CONFLICT DO NOTHING",
        flush_every=20000, page_size=2000, label="patient_alerts",
    )

    for row in read_denticon_file(src):
        alert_id = (row.get("FLASHALERTID") or "").strip()
        rpid     = (row.get("PATID") or row.get("RPID") or "").strip()  # PATID-keyed: alerts are per-patient
        pat_id   = patient_map.get(rpid)

        if not pat_id:
            skipped += 1
            continue

        alert_text = clean(
            row.get("MESSAGE") or row.get("ALERT") or row.get("ALERTTEXT")
        ) or ""
        if not alert_text:
            skipped += 1
            continue

        is_active = parse_bool(row.get("ISACTIVE") or "True")
        deact_on  = parse_datetime(row.get("DEACTIVATEDON") or row.get("DELETEDDATE") or "")

        buf.add((
            pat_id, alert_id, alert_text,
            parse_bool(row.get("ISBLOCKCHARGES", "False")),
            is_active, deact_on,
        ))

    buf.flush()
    print(f"  [s20] patient_alerts: {buf.inserted} inserted, {skipped} skipped")
    return {}
