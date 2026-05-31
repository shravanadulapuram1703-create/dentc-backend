"""
STEP 35 — progress_notes
Source: ProgressNotes_Archive.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_date, parse_bool


def _trunc(val: str | None, max_len: int) -> str | None:
    text = clean(val)
    if not text:
        return None
    return text[:max_len]


def run(conn, maps: dict) -> dict:
    patient_map = maps["patient_map"]
    office_map  = maps["office_map"]

    src = cfg.src("ProgressNotes_Archive.txt")
    if not src.exists():
        print("  [s35] progress_notes: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        note_id = (row.get("PROGNOTESID") or "").strip()
        rpid    = (row.get("PATID") or row.get("RPID") or "").strip()
        pat_id  = patient_map.get(rpid)

        if not pat_id:
            skipped += 1
            continue

        oid = (row.get("OID") or "").strip()

        cur.execute(
            """
            INSERT INTO progress_notes (
                patient_id, office_id, legacy_id, note_date,
                notes, notes_html, tooth, is_deleted
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                pat_id,
                office_map.get(oid),
                note_id,
                parse_date(row.get("ACTDATE") or row.get("NOTEDATE") or ""),
                clean(row.get("NOTES") or row.get("NOTE")),
                clean(row.get("NOTESHTML") or row.get("HTMLNOTES")),
                _trunc(row.get("TH") or row.get("TOOTH"), 255),
                parse_bool(row.get("ISDELETED", "False")),
            ),
        )
        inserted += 1

        if inserted % 2000 == 0:
            conn.commit()

    conn.commit()
    print(f"  [s35] progress_notes: {inserted} inserted, {skipped} skipped")
    return {}
