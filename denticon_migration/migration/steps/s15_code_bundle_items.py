"""
STEP 15 — code_bundle_items
Source: CODESEXPLOSIOND.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_int


def run(conn, maps: dict) -> dict:
    bundle_map    = maps.get("bundle_map", {})
    proc_code_set = maps.get("proc_code_set", set())

    src = cfg.src("CODESEXPLOSIOND.txt")
    if not src.exists():
        print("  [s15] code_bundle_items: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        item_id = (row.get("CODESEXPLOSIONDID") or "").strip()
        bid     = (row.get("CODESEXPLOSIONID") or "").strip()
        code    = (row.get("CODE") or row.get("ADACODE") or "").strip()
        bundle_db_id = bundle_map.get(bid)

        if not bundle_db_id or not code:
            skipped += 1
            continue

        # If code not in procedure_codes, skip (FK would fail)
        if proc_code_set and code not in proc_code_set:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO code_bundle_items
                (bundle_id, legacy_id, procedure_code, tooth, sort_order)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                bundle_db_id, item_id, code,
                clean(row.get("TH")),
                parse_int(row.get("SORTORDER"), 1),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s15] code_bundle_items: {inserted} inserted, {skipped} skipped")
    return {}
