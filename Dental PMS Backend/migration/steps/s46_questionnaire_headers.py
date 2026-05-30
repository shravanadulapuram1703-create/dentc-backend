"""
STEP 46 — questionnaire_headers
Source: QALISTH.txt
Returns: { qalistid_str: questionnaire_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_bool


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("QALISTH.txt")
    if not src.exists():
        print("  [s46] questionnaire_headers: file not found, skipping")
        return {}

    cur = conn.cursor()
    q_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        qid  = (row.get("QALISTID") or "").strip()
        if not qid:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)
        desc = clean(row.get("DESCR") or row.get("DESCRIPTION")) or f"Questionnaire {qid}"

        cur.execute(
            """
            INSERT INTO questionnaire_headers
                (tenant_id, legacy_id, description, is_multi_select, is_active)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                tid, qid, desc,
                parse_bool(row.get("ISMULTISELECT", "False")),
                not parse_bool(row.get("ISDELETED", "False")),
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM questionnaire_headers WHERE legacy_id = %s", (qid,))
            row_id = cur.fetchone()
        if row_id:
            q_map[qid] = row_id[0]
        inserted += 1

    conn.commit()
    print(f"  [s46] questionnaire_headers: {inserted} inserted, {skipped} skipped → map size {len(q_map)}")
    return q_map
