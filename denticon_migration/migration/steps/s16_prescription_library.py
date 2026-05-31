"""
STEP 16 — prescription_library
Source: PGRX.txt
Returns: { rxrefid_str: library_rx_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_int, parse_bool


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("PGRX.txt")
    if not src.exists():
        print("  [s16] prescription_library: file not found, skipping")
        return {}

    cur = conn.cursor()
    rx_lib_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        rxid = (row.get("RXRefID") or row.get("RXREFID") or "").strip()
        if not rxid:
            skipped += 1
            continue

        drug = clean(row.get("DrugName") or row.get("DRUGNAME")) or f"Drug {rxid}"
        pgid = (row.get("PGID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)

        cur.execute(
            """
            INSERT INTO prescription_library
                (tenant_id, legacy_id, drug_name, dispense, sig, refills, is_as_written)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                tid, rxid, drug,
                clean(row.get("Dispense") or row.get("DISPENSE")),
                clean(row.get("Sig") or row.get("SIG")),
                parse_int(row.get("Refill") or row.get("REFILL"), 0),
                parse_bool(row.get("IsAsWritten") or row.get("ISASWRITTEN") or "False"),
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM prescription_library WHERE legacy_id = %s", (rxid,))
            row_id = cur.fetchone()
        if row_id:
            rx_lib_map[rxid] = row_id[0]
        inserted += 1

    conn.commit()
    print(f"  [s16] prescription_library: {inserted} inserted, {skipped} skipped → map size {len(rx_lib_map)}")
    return rx_lib_map
