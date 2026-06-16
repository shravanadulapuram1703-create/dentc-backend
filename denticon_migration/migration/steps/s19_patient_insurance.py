"""
STEP 19 — patient_insurance
Source: PatInsPlans.txt
Links patient ↔ insurance plan ↔ subscriber
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import clean, parse_decimal

# Map Denticon BILLINGORDER to insurance_type
BILLING_TYPE_MAP = {
    "D": "primary",
    "S": "secondary",
    "T": "tertiary",
}

COLS = [
    "patient_id", "ins_plan_id", "subscriber_id", "legacy_plan_type",
    "insurance_type", "relationship",
    "deductible_remaining", "max_remaining", "ortho_remaining",
]


def run(conn, maps: dict) -> dict:
    patient_map  = maps["patient_map"]
    ins_plan_map = maps["ins_plan_map"]
    sub_map      = maps.get("sub_map", {})

    if not ins_plan_map:
        print("  [s19] WARNING: ins_plan_map is empty — run steps 7-9 first (e.g. --from 7 --steps 7-11)")

    src = cfg.src("PatInsPlans.txt")
    skipped = 0
    buf = BulkBuffer(
        conn, "patient_insurance", COLS,
        conflict=(
            "ON CONFLICT (patient_id, insurance_type) DO UPDATE SET "
            "ins_plan_id = EXCLUDED.ins_plan_id, "
            "subscriber_id = EXCLUDED.subscriber_id, "
            "updated_at = NOW()"
        ),
        dedup_index=(COLS.index("patient_id"), COLS.index("insurance_type")),
        flush_every=20000, page_size=2000, label="patient_insurance",
    )

    for row in read_denticon_file(src):
        rpid   = (row.get("PATID") or row.get("RPID") or "").strip()  # PATID-keyed: insurance is per-patient
        planid = (row.get("INSPLANID") or "").strip()
        pat_id = patient_map.get(rpid)
        plan_id = ins_plan_map.get(planid)

        if not pat_id or not plan_id:
            skipped += 1
            continue

        billing = (row.get("BILLINGORDER") or "D").strip()[:1].upper()
        ins_type = BILLING_TYPE_MAP.get(billing, "primary")

        respplanid = (row.get("RESPPLANID") or "").strip()
        sub_id = sub_map.get(respplanid)

        buf.add((
            pat_id, plan_id, sub_id,
            clean(row.get("PLANTYPE")),
            ins_type,
            clean(row.get("RELTOPAT")),
            parse_decimal(row.get("INDDEDUCTREM") or row.get("DEDUCTREM") or "0"),
            parse_decimal(row.get("INDMAXREM") or row.get("MAXREM") or "0"),
            parse_decimal(row.get("ORTHOREMAINING") or row.get("ORTHOREM") or "0"),
        ))

    buf.flush()
    print(f"  [s19] patient_insurance: {buf.inserted} upserted, {skipped} skipped")
    return {}
