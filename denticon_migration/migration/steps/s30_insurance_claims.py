"""
STEP 30 — insurance_claims
Source: CLAIMH/*.txt (2 split files — concat both)
NOTE: insurance_claims.id is VARCHAR(50) → "CLM-{CLAIMID}"
Returns: { claimid_str: claim_varchar_pk }
"""

from migration.config import cfg
from migration.utils.reader import read_folder
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import (
    clean, parse_date, parse_decimal, parse_bool,
    map_claim_status, map_billing_order
)

COLS = [
    "id", "patient_id", "office_id", "legacy_id", "claim_number",
    "status", "claim_type", "billing_order",
    "total_billed", "total_paid",
    "submitted_date", "paid_date",
    "carrier_id", "ins_plan_id", "is_preauth",
]


def run(conn, maps: dict) -> dict:
    patient_map  = maps["patient_map"]
    office_map   = maps["office_map"]
    carrier_map  = maps.get("carrier_map", {})
    ins_plan_map = maps.get("ins_plan_map", {})
    provider_map = maps.get("provider_map", {})

    folder = cfg.src("CLAIMH")
    claim_map: dict[str, str] = {}
    skipped = 0
    buf = BulkBuffer(
        conn, "insurance_claims", COLS,
        conflict=(
            "ON CONFLICT (id) DO UPDATE SET "
            "status = EXCLUDED.status, total_paid = EXCLUDED.total_paid"
        ),
        dedup_index=COLS.index("id"),
        flush_every=20000, page_size=2000, label="insurance_claims",
    )

    for row in read_folder(folder):
        claim_id = (row.get("CLAIMID") or "").strip()
        rpid     = (row.get("PATID") or row.get("RPID") or "").strip()
        pat_id   = patient_map.get(rpid)

        if not claim_id or not pat_id:
            skipped += 1
            continue

        db_pk   = f"CLM-{claim_id}"
        oid     = (row.get("OID") or "").strip()
        cid     = (row.get("CARRIERID") or "").strip()
        planid  = (row.get("RESPPLANID") or row.get("INSPLANID") or "").strip()
        billing = (row.get("BILLINGORDER") or "D").strip()[:1].upper()
        claim_type = "secondary" if billing == "S" else "primary"

        buf.add((
            db_pk, pat_id,
            office_map.get(oid),
            claim_id,
            claim_id,          # claim_number = legacy CLAIMID
            map_claim_status(row.get("CLAIMSTATUS") or ""),
            claim_type,
            map_billing_order(row.get("BILLINGORDER") or ""),
            parse_decimal(row.get("CLAIMAMT") or "0"),
            parse_decimal(row.get("RECVDAMT") or "0"),
            parse_date(row.get("CLAIMSENTDATE") or ""),
            parse_date(row.get("PAIDDATE") or row.get("RECVDDATE") or ""),
            carrier_map.get(cid),
            ins_plan_map.get(planid),
            parse_bool(row.get("ISPREAUTH", "False")),
        ))
        claim_map[claim_id] = db_pk

    buf.flush()
    print(f"  [s30] insurance_claims: {buf.inserted} upserted, {skipped} skipped → map size {len(claim_map)}")
    return claim_map
