"""
STEP 33 — payment_allocations
Source: LedgerPymtAllocation_Archive.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_date, parse_decimal


def run(conn, maps: dict) -> dict:
    patient_map   = maps["patient_map"]
    provider_map  = maps.get("provider_map", {})
    procedure_map = maps.get("procedure_map", {})
    payment_map   = maps.get("payment_map", {})
    claim_map     = maps.get("claim_map", {})
    ins_plan_map  = maps.get("ins_plan_map", {})

    src = cfg.src("LedgerPymtAllocation_Archive.txt")
    if not src.exists():
        print("  [s33] payment_allocations: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        alloc_id   = (row.get("PAYALLOCID") or "").strip()
        rpid       = (row.get("PATID") or "").strip()
        pat_id     = patient_map.get(rpid)

        if not pat_id:
            skipped += 1
            continue

        proc_leg  = (row.get("PROCLEDGERID") or "").strip()
        pay_leg   = (row.get("PAYLEDGERID") or "").strip()
        claim_leg = (row.get("CLAIMID") or "").strip()
        planid    = (row.get("INSPLANID") or "").strip()
        prid      = (row.get("PROVIDERID") or "").strip()

        cur.execute(
            """
            INSERT INTO payment_allocations (
                patient_id, legacy_id, procedure_id, payment_id,
                claim_id, ins_plan_id, provider_id,
                alloc_date, amount, alloc_type
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                pat_id, alloc_id,
                procedure_map.get(proc_leg),
                payment_map.get(pay_leg),
                claim_map.get(claim_leg),
                ins_plan_map.get(planid),
                provider_map.get(prid),
                parse_date(row.get("ALLOCDATE") or ""),
                parse_decimal(row.get("AMOUNT") or "0"),
                clean(row.get("LTYPE")),
            ),
        )
        inserted += 1

        if inserted % 2000 == 0:
            conn.commit()

    conn.commit()
    print(f"  [s33] payment_allocations: {inserted} inserted, {skipped} skipped")
    return {}
