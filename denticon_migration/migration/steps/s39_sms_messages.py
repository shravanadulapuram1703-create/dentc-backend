"""
STEP 39 — sms_messages
Source: SMS.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_datetime, parse_bool


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    office_map  = maps["office_map"]
    patient_map = maps["patient_map"]
    appt_map    = maps.get("appt_map", {})
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("SMS.txt")
    if not src.exists():
        print("  [s39] sms_messages: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        sms_id = (row.get("SMSMSGID") or "").strip()
        if not sms_id:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        oid  = (row.get("OID") or "").strip()
        rpid = (row.get("PATID") or row.get("RPID") or "").strip()
        aid  = (row.get("APPTID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)

        cur.execute(
            """
            INSERT INTO sms_messages (
                tenant_id, office_id, patient_id, appointment_id, legacy_id,
                sent_text, sent_phone, send_status, delivered_on,
                reply_text, reply_phone, reply_received_on,
                message_type, is_read
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                tid,
                office_map.get(oid),
                patient_map.get(rpid),
                appt_map.get(aid) if aid and aid != "0" else None,
                sms_id,
                clean(row.get("SENTTEXT")),
                clean(row.get("SENTPHONE")),
                clean(row.get("SENTSTATUS")),
                parse_datetime(row.get("SENDELIVERYON") or ""),
                clean(row.get("REPLYTEXT")),
                clean(row.get("REPLYPHONE")),
                parse_datetime(row.get("REPLYRECEIVEDON") or ""),
                clean(row.get("MESSAGETYPE")),
                parse_bool(row.get("ISREAD", "False")),
            ),
        )
        inserted += 1

        if inserted % 2000 == 0:
            conn.commit()

    conn.commit()
    print(f"  [s39] sms_messages: {inserted} inserted, {skipped} skipped")
    return {}
