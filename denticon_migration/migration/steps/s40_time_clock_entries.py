"""
STEP 40 — time_clock_entries
Source: TCLOCK.txt
NOTE: USERID is a username string — map to users.id via legacy_id.
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_datetime, parse_decimal
from migration.utils.user_lookup import build_user_lookup, resolve_user_id


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    office_map  = maps["office_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("TCLOCK.txt")
    if not src.exists():
        print("  [s40] time_clock_entries: file not found, skipping")
        return {}

    # Build username → user_id map from DB (since USERID is a string, not a numeric ID)
    cur = conn.cursor()
    user_lookup = build_user_lookup(conn)

    inserted = skipped = 0

    for row in read_denticon_file(src):
        tc_id    = (row.get("TCLOCKID") or "").strip()
        username = (row.get("USERID") or "").strip()
        oid      = (row.get("OID") or "").strip()
        pgid     = (row.get("PGID") or "").strip()
        user_id  = resolve_user_id(user_lookup, username)
        tid      = tenant_map.get(pgid, default_tid)

        if not user_id:
            skipped += 1
            continue

        clock_in = parse_datetime(row.get("LIN") or "")
        if not clock_in:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO time_clock_entries
                (tenant_id, office_id, user_id, legacy_id, clock_in, clock_out, total_hours)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                tid,
                office_map.get(oid),
                user_id, tc_id,
                clock_in,
                parse_datetime(row.get("LOUT") or ""),
                parse_decimal(row.get("LTOTAL") or "0"),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s40] time_clock_entries: {inserted} inserted, {skipped} skipped")
    return {}
