"""
STEP 1 — tenants
Source: PGroup.txt  (1 row — the Excel Dental practice group)
Also seeds one row from config if PGroup.txt is missing or empty.
Returns: { pgid_str: tenant_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    src = cfg.src("PGroup.txt")
    cur = conn.cursor()
    inserted = 0
    tenant_map: dict[str, int] = {}

    rows = list(read_denticon_file(src)) if src.exists() else []

    if not rows:
        # Fallback: seed a single tenant from config
        rows = [{"PGID": cfg.DENTICON_PGID, "PGNAME": cfg.DENTICON_TENANT_NAME}]

    for row in rows:
        pgid = (row.get("PGID") or cfg.DENTICON_PGID).strip()
        name = clean(row.get("PGNAME") or row.get("NAME") or cfg.DENTICON_TENANT_NAME) or "Unknown Practice"
        code = f"CLINIC-{pgid}"

        cur.execute(
            """
            INSERT INTO tenants (legacy_id, name, code)
            VALUES (%s, %s, %s)
            ON CONFLICT (legacy_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (pgid, name, code),
        )
        db_id = cur.fetchone()[0]
        tenant_map[pgid] = db_id
        inserted += 1

    conn.commit()
    print(f"  [s01] tenants: {inserted} upserted → map size {len(tenant_map)}")
    return tenant_map
