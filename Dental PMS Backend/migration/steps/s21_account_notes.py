"""
STEP 21 — account_notes
Source: RESPNOTES.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_bool


def run(conn, maps: dict) -> dict:
    patient_map = maps["patient_map"]

    src = cfg.src("RESPNOTES.txt")
    if not src.exists():
        print("  [s21] account_notes: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        note_id = (row.get("RESPNOTESID") or "").strip()
        rpid    = (row.get("RPID") or "").strip()
        pat_id  = patient_map.get(rpid)

        if not pat_id:
            skipped += 1
            continue

        notes = clean(row.get("NOTES"))
        if not notes:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO account_notes
                (patient_id, legacy_id, note_type, notes, is_struck_off)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                pat_id, note_id,
                clean(row.get("NTYPE")),
                notes,
                parse_bool(row.get("STRIKEOFF", "False")),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s21] account_notes: {inserted} inserted, {skipped} skipped")
    return {}
