"""
STEP 42 — postcard_templates
Source: POSTCARDS.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    tenant_map = maps["tenant_map"]
    office_map = maps["office_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("POSTCARDS.txt")
    if not src.exists():
        print("  [s42] postcard_templates: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        pc_id = (row.get("PCID") or row.get("POSTCARDID") or "").strip()
        if not pc_id:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        oid  = (row.get("OID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)
        name = clean(row.get("NAME") or row.get("PCNAME")) or f"Postcard {pc_id}"

        cur.execute(
            """
            INSERT INTO postcard_templates
                (tenant_id, office_id, legacy_id, name, card_type, body)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                tid, office_map.get(oid),
                pc_id, name,
                clean(row.get("TYPE")),
                clean(row.get("BODY") or row.get("CONTENT")),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s42] postcard_templates: {inserted} inserted, {skipped} skipped")
    return {}
