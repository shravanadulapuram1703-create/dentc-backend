"""
STEP 7 — insurance_plans
Source: InsPlans.txt
Returns: { insplanid_str: plan_db_id }

INS-PT-15: the column names below were wrong, so several fields read as NULL on
every one of the 31,331 migrated plans. ``InsPlans.txt`` writes ``GROUPNUMBER``
(not ``GROUPNO``), ``INDIVIDUALMAX`` / ``INDIVIDUALDEDUCTIBLE`` /
``INDIVIDUALORTHOMAX`` / ``FAMILYDEDUCTIBLE`` (not the abbreviated forms) — only
``FAMILYMAX`` happened to match, which is why family_max was the one benefit
column with data. The group number is the field both duplicate-prevention layers
and the legacy smart search key off, so the whole feature was inert against
production data; the maxima and deductibles feed the read-only BENEFIT INFO
panel and the estimate engine.

Existing rows are repaired by ``scripts/backfill_insurance_source_fields.py``
without re-running the migration.
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import (
    clean, parse_decimal, parse_date, parse_datetime, map_plan_type, parse_bool,
)

COLS = [
    "tenant_id", "carrier_id", "employer_id", "legacy_id", "group_number",
    "plan_type", "is_prepaid", "individual_max", "individual_deductible",
    "ortho_max", "family_max", "family_deductible", "anniversary_date", "coverage_type",
    # INS-PT-8: the Setup grid renders Created/Modified as date + user. These are
    # Denticon login strings, and most have no users row to point a FK at.
    "created_on", "created_by", "modified_on", "modified_by",
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
            "group_number = EXCLUDED.group_number, "
            "individual_max = EXCLUDED.individual_max, "
            "individual_deductible = EXCLUDED.individual_deductible, "
            "ortho_max = EXCLUDED.ortho_max, "
            "family_max = EXCLUDED.family_max, "
            "family_deductible = EXCLUDED.family_deductible, "
            "created_on = EXCLUDED.created_on, "
            "created_by = EXCLUDED.created_by, "
            "modified_on = EXCLUDED.modified_on, "
            "modified_by = EXCLUDED.modified_by"
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
            # INS-PT-15: GROUPNUMBER, not GROUPNO.
            clean(row.get("GROUPNUMBER") or row.get("GROUPNO")),
            map_plan_type(row.get("PLANTYPE", "")),
            parse_bool(row.get("ISPREPAID", "False")),
            parse_decimal(row.get("INDIVIDUALMAX") or row.get("INDMAX") or "0"),
            parse_decimal(row.get("INDIVIDUALDEDUCTIBLE") or row.get("INDDED") or "0"),
            # The plan-level ortho maximum is the individual one; FAMILYORTHOMAX
            # is the family cap and has no column of its own here.
            parse_decimal(row.get("INDIVIDUALORTHOMAX") or row.get("ORTHOMAX") or "0"),
            parse_decimal(row.get("FAMILYMAX") or row.get("FAMMAX") or "0"),
            parse_decimal(row.get("FAMILYDEDUCTIBLE") or row.get("FAMDED") or "0"),
            parse_date(row.get("ANNIVDATE") or ""),
            clean(row.get("COVERAGETYPE")),
            parse_datetime(row.get("CREATEDON") or ""),
            clean(row.get("CREATEDBY")),
            parse_datetime(row.get("MODIFIEDON") or ""),
            clean(row.get("MODIFIEDBY")),
        ))

    buf.flush()
    ins_plan_map = {str(legacy): pk for pk, legacy in buf.returned}
    print(f"  [s07] insurance_plans: {buf.inserted} upserted, {skipped} skipped → map size {len(ins_plan_map)}")
    return ins_plan_map
