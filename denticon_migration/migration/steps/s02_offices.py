"""
STEP 2 — offices
Source: Office.txt
Returns: { oid_str: office_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_int


def run(conn, maps: dict) -> dict:
    tenant_map = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("Office.txt")
    cur = conn.cursor()
    office_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        oid = (row.get("OID") or "").strip()
        if not oid:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        tenant_id = tenant_map.get(pgid, default_tid)
        name = clean(row.get("OFFICENAME") or row.get("NAME")) or f"Office {oid}"
        code = f"O-{oid}"

        cur.execute(
            """
            INSERT INTO offices (
                tenant_id, legacy_id, office_code, name, short_id,
                address_line1, city, state, zip, phone, fax, email,
                slot_interval_minutes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (legacy_id) DO UPDATE SET
                name          = EXCLUDED.name,
                phone         = EXCLUDED.phone,
                updated_at    = NOW()
            RETURNING id
            """,
            (
                tenant_id, oid, code, name,
                clean(row.get("SHORTID")),
                clean(row.get("ADDRESS1") or row.get("ADDRESS")),
                clean(row.get("CITY")),
                clean(row.get("STATE")),
                clean(row.get("ZIP")),
                clean(row.get("PHONE")),
                clean(row.get("FAX")),
                clean(row.get("EMAIL")),
                parse_int(row.get("APPINTERVAL"), 10),
            ),
        )
        db_id = cur.fetchone()[0]
        office_map[oid] = db_id
        inserted += 1

    conn.commit()
    print(f"  [s02] offices: {inserted} upserted, {skipped} skipped → map size {len(office_map)}")
    return office_map
