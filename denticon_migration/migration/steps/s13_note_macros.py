"""
STEP 13 — note_macros
Source: ChartNotesMacros.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("ChartNotesMacros.txt")
    if not src.exists():
        print("  [s13] note_macros: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        mid = (row.get("MACROID") or "").strip()
        if not mid:
            skipped += 1
            continue

        name    = clean(row.get("MACRONAME")) or f"Macro {mid}"
        content = clean(row.get("MACROVALUE") or row.get("CONTENT")) or ""
        pgid    = (row.get("PGID") or "").strip()
        tid     = tenant_map.get(pgid, default_tid)

        cur.execute(
            """
            INSERT INTO note_macros (tenant_id, legacy_id, name, content, category)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (tid, mid, name, content, clean(row.get("Macrocat") or row.get("MACROCAT"))),
        )
        inserted += 1

    conn.commit()
    print(f"  [s13] note_macros: {inserted} inserted, {skipped} skipped")
    return {}
