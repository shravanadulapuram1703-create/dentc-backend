"""
STEP 9 — fee_schedules
Source: FeeScheH.txt
Returns: { feeid_str: fee_schedule_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    tenant_map   = maps["tenant_map"]
    ins_plan_map = maps["ins_plan_map"]
    office_map   = maps["office_map"]
    default_tid  = next(iter(tenant_map.values()))

    src = cfg.src("FeeScheH.txt")
    cur = conn.cursor()
    fee_sched_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        feeid = (row.get("FEEID") or "").strip()
        if not feeid:
            skipped += 1
            continue

        pgid  = (row.get("PGID") or "").strip()
        oid   = (row.get("OID") or "").strip()
        planid = (row.get("INSPLANID") or "").strip()
        tid   = tenant_map.get(pgid, default_tid)

        # fee_type: 1=UCR, 2=plan-assigned, 3=carrier-assigned
        fee_type_map = {"1": "ucr", "2": "plan", "3": "carrier"}
        fee_type = fee_type_map.get((row.get("FEETYPE") or "").strip(), "ucr")

        cur.execute(
            """
            INSERT INTO fee_schedules
                (tenant_id, legacy_id, name, fee_type, ins_plan_id, office_id)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (legacy_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (
                tid, feeid,
                clean(row.get("DESCR") or row.get("NAME")) or f"Fee Schedule {feeid}",
                fee_type,
                ins_plan_map.get(planid),
                office_map.get(oid),
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM fee_schedules WHERE legacy_id = %s", (feeid,))
            row_id = cur.fetchone()
        fee_sched_map[feeid] = row_id[0]
        inserted += 1

    conn.commit()
    print(f"  [s09] fee_schedules: {inserted} upserted, {skipped} skipped → map size {len(fee_sched_map)}")
    return fee_sched_map
