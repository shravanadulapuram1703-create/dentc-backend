"""
STEP 6 — insurance_carriers
Source: Carrier.txt
Returns: { carrierid_str: carrier_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    tenant_map = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("Carrier.txt")
    cur = conn.cursor()
    carrier_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        cid = (row.get("CARRIERID") or "").strip()
        if not cid:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)
        name = clean(row.get("CARRIERNAME") or row.get("NAME")) or f"Carrier {cid}"

        cur.execute(
            """
            INSERT INTO insurance_carriers
                (tenant_id, legacy_id, name, payer_id, phone, phone2,
                 address, city, state, zip, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (legacy_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (
                tid, cid, name,
                clean(row.get("PAYERID") or row.get("ELECTRONICPAYERID")),
                clean(row.get("PHONE")),
                clean(row.get("PHONE2")),
                clean(row.get("ADDRESS1") or row.get("ADDRESS")),
                clean(row.get("CITY")),
                clean(row.get("STATE")),
                clean(row.get("ZIP")),
                clean(row.get("NOTES")),
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM insurance_carriers WHERE legacy_id = %s", (cid,))
            row_id = cur.fetchone()
        carrier_map[cid] = row_id[0]
        inserted += 1

    conn.commit()
    print(f"  [s06] insurance_carriers: {inserted} upserted, {skipped} skipped → map size {len(carrier_map)}")
    return carrier_map
