"""
STEP 45 — perio_chart_settings
Source: CHARTPERIOSETUP.txt
NOTE: USERID is a username string — map to users.id via legacy_id.
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import parse_bool, parse_int
from migration.utils.user_lookup import build_user_lookup, resolve_user_id


def run(conn, maps: dict) -> dict:
    src = cfg.src("CHARTPERIOSETUP.txt")
    if not src.exists():
        print("  [s45] perio_chart_settings: file not found, skipping")
        return {}

    cur = conn.cursor()
    user_lookup = build_user_lookup(conn)

    inserted = skipped = 0

    for row in read_denticon_file(src):
        username = (row.get("USERID") or "").strip()
        user_id  = resolve_user_id(user_lookup, username)
        if not user_id:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO perio_chart_settings
                (user_id, is_forward, is_indicator, is_mgj, pd_level, bp_level, ip_level)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (user_id) DO UPDATE SET
                is_forward   = EXCLUDED.is_forward,
                pd_level     = EXCLUDED.pd_level
            """,
            (
                user_id,
                parse_bool(row.get("ISFORWARD", "True")),
                parse_bool(row.get("ISINDICATOR", "True")),
                parse_bool(row.get("ISMGJ", "True")),
                parse_int(row.get("PDLEVEL"), 4),
                parse_int(row.get("BPLEVEL"), 2),
                parse_int(row.get("IPLEVEL"), 3),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s45] perio_chart_settings: {inserted} upserted, {skipped} skipped")
    return {}
