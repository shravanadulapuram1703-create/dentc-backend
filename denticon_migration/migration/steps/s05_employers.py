"""
STEP 5 — employers
Source: Employers.txt
Returns: { empid_str: employer_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    tenant_map = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("Employers.txt")
    if not src.exists():
        print("  [s05] employers: file not found, skipping")
        return {}

    cur = conn.cursor()
    employer_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        empid = (row.get("EMPID") or "").strip()
        if not empid:
            skipped += 1
            continue

        name = clean(row.get("NAME")) or f"Employer {empid}"
        pgid = (row.get("PGID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)

        cur.execute(
            """
            INSERT INTO employers
                (tenant_id, legacy_id, name, address, address2, city, state, zip, phone)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (legacy_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (
                tid, empid, name,
                clean(row.get("ADDRESS1") or row.get("ADDRESS")),
                clean(row.get("ADDRESS2")),  # INS-PT-11
                clean(row.get("CITY")),
                clean(row.get("STATE")),
                clean(row.get("ZIP")),
                clean(row.get("PHONE")),
            ),
        )
        # employers has no UNIQUE constraint on legacy_id by default; use SELECT on conflict
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM employers WHERE legacy_id = %s", (empid,))
            row_id = cur.fetchone()
        employer_map[empid] = row_id[0]
        inserted += 1

    conn.commit()
    print(f"  [s05] employers: {inserted} upserted, {skipped} skipped → map size {len(employer_map)}")
    return employer_map
