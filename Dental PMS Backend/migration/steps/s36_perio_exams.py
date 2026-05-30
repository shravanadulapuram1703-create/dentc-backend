"""
STEP 36 — perio_exams
Source: PERIOCHARTHEADER.txt
Returns: { perioexamid_str: perio_exam_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_date, parse_bool


def run(conn, maps: dict) -> dict:
    patient_map = maps["patient_map"]
    office_map  = maps["office_map"]

    src = cfg.src("PERIOCHARTHEADER.txt")
    if not src.exists():
        print("  [s36] perio_exams: file not found, skipping")
        return {}

    cur = conn.cursor()
    perio_exam_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        exam_id = (row.get("PerioExamID") or row.get("PERIOEXAMID") or "").strip()
        rpid    = (row.get("PATID") or "").strip()
        pat_id  = patient_map.get(rpid)

        if not pat_id or not exam_id:
            skipped += 1
            continue

        oid      = (row.get("OID") or "").strip()
        exam_dt  = parse_date(row.get("ACTDATE") or "")
        if not exam_dt:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO perio_exams
                (patient_id, office_id, legacy_id, exam_date, notes, is_voided)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                pat_id,
                office_map.get(oid),
                exam_id, exam_dt,
                clean(row.get("NOTES")),
                parse_bool(row.get("ISVOIDED", "False")),
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM perio_exams WHERE legacy_id = %s", (exam_id,))
            row_id = cur.fetchone()
        if row_id:
            perio_exam_map[exam_id] = row_id[0]
        inserted += 1

    conn.commit()
    print(f"  [s36] perio_exams: {inserted} inserted, {skipped} skipped → map size {len(perio_exam_map)}")
    return perio_exam_map
