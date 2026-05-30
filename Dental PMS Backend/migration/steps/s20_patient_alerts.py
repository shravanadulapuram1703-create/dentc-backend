"""
STEP 20 — patient_alerts
Source: PatFlashAlerts.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_bool, parse_datetime


def run(conn, maps: dict) -> dict:
    patient_map = maps["patient_map"]

    src = cfg.src("PatFlashAlerts.txt")
    if not src.exists():
        print("  [s20] patient_alerts: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        alert_id = (row.get("FLASHALERTID") or "").strip()
        rpid     = (row.get("RPID") or row.get("PATID") or "").strip()
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

        cur.execute(
            """
            INSERT INTO patient_alerts
                (patient_id, legacy_id, alert, blocks_charges, is_active, deactivated_on)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                pat_id, alert_id, alert_text,
                parse_bool(row.get("ISBLOCKCHARGES", "False")),
                is_active, deact_on,
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s20] patient_alerts: {inserted} inserted, {skipped} skipped")
    return {}
