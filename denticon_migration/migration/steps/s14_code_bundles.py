"""
STEP 14 — code_bundles
Source: CODESEXPLOSIONH.txt
Returns: { codesexplosionid_str: bundle_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_bool


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("CODESEXPLOSIONH.txt")
    if not src.exists():
        print("  [s14] code_bundles: file not found, skipping")
        return {}

    cur = conn.cursor()
    bundle_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        bid = (row.get("CODESEXPLOSIONID") or "").strip()
        if not bid:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)
        desc = clean(row.get("DESCR") or row.get("NAME")) or f"Bundle {bid}"

        cur.execute(
            """
            INSERT INTO code_bundles
                (tenant_id, legacy_id, name, display_code, description, same_tooth)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (tid, bid, desc, clean(row.get("CODE")), desc,
             parse_bool(row.get("SAMETOOTHNO", "False"))),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM code_bundles WHERE legacy_id = %s", (bid,))
            row_id = cur.fetchone()
        if row_id:
            bundle_map[bid] = row_id[0]
        inserted += 1

    conn.commit()
    print(f"  [s14] code_bundles: {inserted} inserted, {skipped} skipped → map size {len(bundle_map)}")
    return bundle_map
