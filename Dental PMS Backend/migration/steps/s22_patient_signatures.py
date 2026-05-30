"""
STEP 22 — patient_signatures
Source: PATSIGNATURE.txt
NOTE: SIGNATURE field contains large encoded binary stroke data — stored as-is.
Returns: { signatureid_str: signature_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_int, parse_bool


def run(conn, maps: dict) -> dict:
    patient_map = maps["patient_map"]

    src = cfg.src("PATSIGNATURE.txt")
    if not src.exists():
        print("  [s22] patient_signatures: file not found, skipping")
        return {}

    cur = conn.cursor()
    sig_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        sig_id  = (row.get("SIGNATUREID") or "").strip()
        pat_key = (row.get("PATID") or row.get("RPID") or "").strip()
        pat_id  = patient_map.get(pat_key)

        if not pat_id or not sig_id:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO patient_signatures
                (patient_id, legacy_id, signature_data, signature_len, device_source, is_user_sig)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                pat_id, sig_id,
                clean(row.get("SIGNATURE")),          # store encoded as-is
                parse_int(row.get("SIGNATURELEN")),
                clean(row.get("DEVICESOURCE")),
                parse_bool(row.get("ISUSER", "False")),
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM patient_signatures WHERE legacy_id = %s", (sig_id,))
            row_id = cur.fetchone()
        if row_id:
            sig_map[sig_id] = row_id[0]
        inserted += 1

    conn.commit()
    print(f"  [s22] patient_signatures: {inserted} inserted, {skipped} skipped → map size {len(sig_map)}")
    return sig_map
