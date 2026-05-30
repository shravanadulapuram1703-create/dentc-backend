"""
STEP 19 — patient_insurance
Source: PatInsPlans.txt
Links patient ↔ insurance plan ↔ subscriber
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_decimal

# Map Denticon BILLINGORDER to insurance_type
BILLING_TYPE_MAP = {
    "D": "primary",
    "S": "secondary",
    "T": "tertiary",
}


def run(conn, maps: dict) -> dict:
    patient_map  = maps["patient_map"]
    ins_plan_map = maps["ins_plan_map"]
    sub_map      = maps.get("sub_map", {})

    if not ins_plan_map:
        print("  [s19] WARNING: ins_plan_map is empty — run steps 7-9 first (e.g. --from 7 --steps 7-11)")

    src = cfg.src("PatInsPlans.txt")
    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        rpid   = (row.get("RPID") or row.get("PATID") or "").strip()
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

        cur.execute(
            """
            INSERT INTO patient_insurance (
                patient_id, ins_plan_id, subscriber_id, legacy_plan_type,
                insurance_type, relationship,
                deductible_remaining, max_remaining, ortho_remaining
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (patient_id, insurance_type) DO UPDATE SET
                ins_plan_id  = EXCLUDED.ins_plan_id,
                subscriber_id = EXCLUDED.subscriber_id,
                updated_at   = NOW()
            """,
            (
                pat_id, plan_id, sub_id,
                clean(row.get("PLANTYPE")),
                ins_type,
                clean(row.get("RELTOPAT")),
                parse_decimal(row.get("INDDEDUCTREM") or row.get("DEDUCTREM") or "0"),
                parse_decimal(row.get("INDMAXREM") or row.get("MAXREM") or "0"),
                parse_decimal(row.get("ORTHOREMAINING") or row.get("ORTHOREM") or "0"),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s19] patient_insurance: {inserted} upserted, {skipped} skipped")
    return {}
