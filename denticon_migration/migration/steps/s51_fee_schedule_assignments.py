"""
STEP 51 — fee_schedule_assignments
Source: FeeScheA.txt  (HAS DATA)
Assigns which fee schedule applies per plan / carrier / provider / office.
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    tenant_map    = maps["tenant_map"]
    ins_plan_map  = maps.get("ins_plan_map", {})
    carrier_map   = maps.get("carrier_map", {})
    provider_map  = maps.get("provider_map", {})
    office_map    = maps.get("office_map", {})
    fee_sched_map = maps.get("fee_sched_map", {})
    default_tid   = next(iter(tenant_map.values()))

    if not fee_sched_map:
        print("  [s51] WARNING: fee_sched_map is empty — run steps 9-11 first (e.g. --from 9 --steps 9-11)")

    src = cfg.src("FeeScheA.txt")
    if not src.exists():
        print("  [s51] fee_schedule_assignments: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        assign_id = (row.get("FEESCHEDAID") or "").strip()
        feeid     = (row.get("FEEID") or "").strip()
        fs_id     = fee_sched_map.get(feeid)

        if not assign_id or not fs_id:
            skipped += 1
            continue

        pgid   = (row.get("PGID") or "").strip()
        planid = (row.get("INSPLANID") or "0").strip()
        cid    = (row.get("CARRIERID") or "0").strip()
        prid   = (row.get("PROVIDERID") or "0").strip()
        oid    = (row.get("OID") or "0").strip()
        tid    = tenant_map.get(pgid, default_tid)

        cur.execute(
            """
            INSERT INTO fee_schedule_assignments
                (tenant_id, legacy_id, ins_plan_id, carrier_id,
                 provider_id, office_id, fee_schedule_id,
                 specialty_id, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                tid, assign_id,
                ins_plan_map.get(planid) if planid != "0" else None,
                carrier_map.get(cid) if cid != "0" else None,
                provider_map.get(prid) if prid != "0" else None,
                office_map.get(oid) if oid != "0" else None,
                fs_id,
                clean(row.get("SPECIALTYID")),
                clean(row.get("CREATEDBY")),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s51] fee_schedule_assignments: {inserted} inserted, {skipped} skipped")
    return {}
