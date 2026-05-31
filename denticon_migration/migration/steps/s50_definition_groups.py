"""
STEP 50 — definition_groups
Source: DEFINITIONSH.txt  (HAS DATA)
Metadata about each DEFINITIONS group (what KEY1/KEY2 mean, editability, type).
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_bool


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("DEFINITIONSH.txt")
    if not src.exists():
        print("  [s50] definition_groups: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        group_code = (row.get("DEFGROUP") or "").strip()
        if not group_code:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)
        desc = clean(row.get("DESCR") or row.get("DESCRIPTION")) or group_code

        cur.execute(
            """
            INSERT INTO definition_groups
                (tenant_id, legacy_id, group_code, description,
                 key1_label, key2_label, is_editable, can_add, group_type)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, group_code) DO UPDATE SET
                description = EXCLUDED.description,
                is_editable = EXCLUDED.is_editable
            """,
            (
                tid, group_code, group_code, desc,
                clean(row.get("KEY1DESCR")),
                clean(row.get("KEY2DESCR")),
                clean(row.get("ISEDITABLE") or "Y").upper() == "Y",
                clean(row.get("CANADD") or "Y").upper() == "Y",
                clean(row.get("TYPE")),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s50] definition_groups: {inserted} upserted, {skipped} skipped")
    return {}
