"""
STEP 49 — codes_view
Source: CODESVIEW.txt  (HAS DATA)
Per-office procedure code visibility settings.
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    tenant_map    = maps["tenant_map"]
    office_map    = maps["office_map"]
    proc_code_set = maps.get("proc_code_set", set())
    default_tid   = next(iter(tenant_map.values()))

    src = cfg.src("CODESVIEW.txt")
    if not src.exists():
        print("  [s49] codes_view: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        code = (row.get("CODE") or "").strip()
        oid  = (row.get("OID") or "").strip()
        pgid = (row.get("PGID") or "").strip()

        if not code or not oid:
            skipped += 1
            continue

        # Skip if code not in procedure_codes (FK would fail)
        if proc_code_set and code not in proc_code_set:
            skipped += 1
            continue

        office_id = office_map.get(oid)
        if not office_id:
            skipped += 1
            continue

        tid = tenant_map.get(pgid, default_tid)

        cur.execute(
            """
            INSERT INTO codes_view (tenant_id, office_id, code, created_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (office_id, code) DO NOTHING
            """,
            (tid, office_id, code, clean(row.get("CREATEDBY"))),
        )
        inserted += 1

        if inserted % 2000 == 0:
            conn.commit()

    conn.commit()
    print(f"  [s49] codes_view: {inserted} inserted, {skipped} skipped")
    return {}
