"""
STEP 7 — insurance_plans
Source: InsPlans.txt
Returns: { insplanid_str: plan_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import clean, parse_decimal, parse_date, map_plan_type, parse_bool

COLS = [
    "tenant_id", "carrier_id", "employer_id", "legacy_id", "group_number",
    "plan_type", "is_prepaid", "individual_max", "individual_deductible",
    "ortho_max", "family_max", "family_deductible", "anniversary_date", "coverage_type",
]


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    carrier_map = maps["carrier_map"]
    employer_map = maps.get("employer_map", {})
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("InsPlans.txt")
    skipped = 0
    buf = BulkBuffer(
        conn, "insurance_plans", COLS,
        conflict=(
            "ON CONFLICT (legacy_id) DO UPDATE SET "
            "group_number = EXCLUDED.group_number"
        ),
        returning="id, legacy_id",
        dedup_index=COLS.index("legacy_id"),
        flush_every=10000, page_size=2000, label="insurance_plans",
    )

    for row in read_denticon_file(src):
        planid = (row.get("INSPLANID") or "").strip()
        if not planid:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        cid  = (row.get("CARRIERID") or "").strip()
        empid = (row.get("EMPID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)
        carrier_id = carrier_map.get(cid)
        if not carrier_id:
            skipped += 1
            continue

        buf.add((
            tid,
            carrier_id,
            employer_map.get(empid),
            planid,
            clean(row.get("GROUPNO")),
            map_plan_type(row.get("PLANTYPE", "")),
            parse_bool(row.get("ISPREPAID", "False")),
            parse_decimal(row.get("INDMAX") or row.get("INDIVMAX") or "0"),
            parse_decimal(row.get("INDDED") or row.get("INDIVDED") or "0"),
            parse_decimal(row.get("ORTHOMAX") or "0"),
            parse_decimal(row.get("FAMMAX") or row.get("FAMILYMAX") or "0"),
            parse_decimal(row.get("FAMDED") or row.get("FAMILYDED") or "0"),
            parse_date(row.get("ANNIVDATE") or ""),
            clean(row.get("COVERAGETYPE")),
        ))

    buf.flush()
    ins_plan_map = {str(legacy): pk for pk, legacy in buf.returned}
    print(f"  [s07] insurance_plans: {buf.inserted} upserted, {skipped} skipped → map size {len(ins_plan_map)}")
    return ins_plan_map
