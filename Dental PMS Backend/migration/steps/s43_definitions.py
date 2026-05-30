"""
STEP 43 — definitions
Source: DEFINITIONS.txt + STATUSTRACK.txt
        (both loaded into the same table with different group_code values)
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_bool


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    cur = conn.cursor()
    inserted = skipped = 0

    # ── DEFINITIONS.txt ──────────────────────────────────────────────────────
    src = cfg.src("DEFINITIONS.txt")
    if src.exists():
        for row in read_denticon_file(src):
            def_id = (row.get("DEFINITIONSID") or "").strip()
            if not def_id:
                skipped += 1
                continue

            pgid  = (row.get("PGID") or "").strip()
            tid   = tenant_map.get(pgid, default_tid)
            group = clean(row.get("DEFGROUP")) or "UNKNOWN"
            key1  = clean(row.get("DEFKEY1")) or ""
            desc  = clean(row.get("DESCR") or row.get("DESCRIPTION")) or key1

            cur.execute(
                """
                INSERT INTO definitions
                    (tenant_id, legacy_id, group_code, key1, key2,
                     description, is_flash_alert, blocks_charges)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (
                    tid, def_id, group, key1,
                    clean(row.get("DEFKEY2")),
                    desc,
                    parse_bool(row.get("ISFLASHALERT", "False")),
                    parse_bool(row.get("ISBLOCKCHARGES", "False")),
                ),
            )
            inserted += 1

    # ── STATUSTRACK.txt ───────────────────────────────────────────────────────
    src2 = cfg.src("STATUSTRACK.txt")
    if src2.exists():
        for row in read_denticon_file(src2):
            code = (row.get("CODE") or "").strip()
            if not code:
                skipped += 1
                continue
            pgid = (row.get("PGID") or "").strip()
            tid  = tenant_map.get(pgid, default_tid)
            desc = clean(row.get("DESCR") or row.get("DESCRIPTION")) or code

            cur.execute(
                """
                INSERT INTO definitions
                    (tenant_id, group_code, key1, description)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (tid, "STATUSTRACK", code, desc),
            )
            inserted += 1

    conn.commit()
    print(f"  [s43] definitions: {inserted} inserted, {skipped} skipped")
    return {}
