"""
STEP 47 — questionnaire_options
Source: QALISTD.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_int, parse_bool


def run(conn, maps: dict) -> dict:
    q_map = maps.get("q_map", {})

    src = cfg.src("QALISTD.txt")
    if not src.exists():
        print("  [s47] questionnaire_options: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        opt_id = (row.get("QALISTDID") or "").strip()
        qid    = (row.get("QALISTID") or "").strip()
        q_db_id = q_map.get(qid)

        if not q_db_id:
            skipped += 1
            continue

        code = clean(row.get("CODE") or row.get("ANSWERCODE")) or opt_id

        cur.execute(
            """
            INSERT INTO questionnaire_options
                (questionnaire_id, legacy_id, answer_code, sort_order, is_active)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                q_db_id, opt_id, code,
                parse_int(row.get("SORTORDER"), 1),
                not parse_bool(row.get("ISDELETED", "False")),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s47] questionnaire_options: {inserted} inserted, {skipped} skipped")
    return {}
