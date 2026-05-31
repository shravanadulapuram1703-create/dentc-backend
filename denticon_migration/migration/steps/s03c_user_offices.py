"""
STEP 3c — user_offices
Source: Providers.txt (providers already in DB; users seeded by s03b)
Links each user to their primary office.

The provider's OID in Providers.txt becomes their primary office assignment.
Providers who appear in multiple offices (same SHORTID, different OID) get
multiple user_office rows — only the first is marked is_primary=True.

Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    office_map = maps["office_map"]
    user_map   = maps.get("user_map", {})
    default_oid = next(iter(office_map.values()), None)

    if not user_map:
        print("  [s03c] user_offices: no user_map (run s03b first) — skipping")
        return {}

    if not default_oid:
        print("  [s03c] user_offices: no office_map (run s02 first) — skipping")
        return {}

    src = cfg.src("Providers.txt")
    cur = conn.cursor()
    inserted = skipped = 0

    # Track which users already have a primary office assigned
    primary_assigned: set[int] = set()

    for row in read_denticon_file(src):
        prov_id  = (row.get("PROVIDERID") or "").strip()
        short_id = (row.get("SHORTID") or "").strip()
        oid      = (row.get("OID") or "").strip()

        # Find the user: prefer SHORTID match, fall back to PROVIDERID
        user_id  = user_map.get(short_id) or user_map.get(prov_id)
        office_id = office_map.get(oid) if oid else default_oid

        if not user_id or not office_id:
            skipped += 1
            continue

        is_primary = user_id not in primary_assigned

        cur.execute(
            """
            INSERT INTO user_offices (user_id, office_id, is_primary)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, office_id) DO UPDATE SET
                is_primary = EXCLUDED.is_primary
            """,
            (user_id, office_id, is_primary),
        )
        if is_primary:
            primary_assigned.add(user_id)
        inserted += 1

    conn.commit()
    print(f"  [s03c] user_offices: {inserted} links created, {skipped} skipped")
    return {}
