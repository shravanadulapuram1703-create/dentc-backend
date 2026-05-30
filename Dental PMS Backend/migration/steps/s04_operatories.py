"""
STEP 4 — operatories
Source: Operatory.txt
Returns: { operatoryid_str: operatory_varchar_pk }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_int, parse_bool


def run(conn, maps: dict) -> dict:
    office_map = maps["office_map"]
    default_oid = next(iter(office_map.values()))

    src = cfg.src("Operatory.txt")
    cur = conn.cursor()
    operatory_map: dict[str, str] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        oid_src = (row.get("OPERATORYID") or "").strip()
        if not oid_src:
            skipped += 1
            continue

        db_id   = f"OPR-{oid_src}"
        oid     = (row.get("OID") or "").strip()
        off_id  = office_map.get(oid, default_oid)
        name    = clean(row.get("OPERATORYNAME") or row.get("NAME")) or f"Op {oid_src}"
        is_active = not parse_bool(row.get("ISDELETED", "False"))

        cur.execute(
            """
            INSERT INTO operatories (id, office_id, legacy_id, name, display_order, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name      = EXCLUDED.name,
                is_active = EXCLUDED.is_active
            """,
            (
                db_id, off_id, oid_src, name,
                parse_int(row.get("DISPLAYORDER"), 0),
                is_active,
            ),
        )
        operatory_map[oid_src] = db_id
        inserted += 1

    conn.commit()
    print(f"  [s04] operatories: {inserted} upserted, {skipped} skipped → map size {len(operatory_map)}")
    return operatory_map
