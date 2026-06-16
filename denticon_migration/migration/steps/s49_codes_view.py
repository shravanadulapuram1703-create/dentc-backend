"""
STEP 49 — codes_view
Source: CODESVIEW.txt  (HAS DATA)
Per-office procedure code visibility settings.
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import clean

COLS = ["tenant_id", "office_id", "code", "created_by"]


def run(conn, maps: dict) -> dict:
    tenant_map    = maps["tenant_map"]
    office_map    = maps["office_map"]
    proc_code_set = maps.get("proc_code_set", set())
    default_tid   = next(iter(tenant_map.values()))

    src = cfg.src("CODESVIEW.txt")
    if not src.exists():
        print("  [s49] codes_view: file not found, skipping")
        return {}

    skipped = 0
    buf = BulkBuffer(
        conn, "codes_view", COLS,
        conflict="ON CONFLICT (office_id, code) DO NOTHING",
        flush_every=20000, page_size=2000, label="codes_view",
    )

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
        buf.add((tid, office_id, code, clean(row.get("CREATEDBY"))))

    buf.flush()
    print(f"  [s49] codes_view: {buf.inserted} inserted, {skipped} skipped")
    return {}
