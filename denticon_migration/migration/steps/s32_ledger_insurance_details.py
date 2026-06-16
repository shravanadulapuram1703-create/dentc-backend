"""
STEP 32 — ledger_insurance_details
Source: LedgerInsDetail_Archive.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import clean, parse_decimal, parse_bool

COLS = [
    "patient_id", "procedure_id", "legacy_ledger_id", "claim_id", "office_id",
    "prim_estimated", "prim_ind_max", "prim_deductible",
    "prim_ins_paid", "prim_ins_adjust",
    "sec_estimated", "sec_ins_paid", "sec_ins_adjust",
    "ter_ins_paid",
    "prim_ins_plan_id", "sec_ins_plan_id", "ter_ins_plan_id",
    "prim_posted", "sec_posted",
]


def run(conn, maps: dict) -> dict:
    patient_map   = maps["patient_map"]
    office_map    = maps["office_map"]
    procedure_map = maps.get("procedure_map", {})
    claim_map     = maps.get("claim_map", {})
    ins_plan_map  = maps.get("ins_plan_map", {})

    src = cfg.src("LedgerInsDetail_Archive.txt")
    if not src.exists():
        print("  [s32] ledger_insurance_details: file not found, skipping")
        return {}

    skipped = 0
    buf = BulkBuffer(
        conn, "ledger_insurance_details", COLS,
        conflict="ON CONFLICT DO NOTHING",
        flush_every=20000, page_size=2000, label="ledger_insurance_details",
    )

    for row in read_denticon_file(src):
        ledger_id = (row.get("LEDGERID") or "").strip()
        rpid      = (row.get("PATID") or "").strip()
        pat_id    = patient_map.get(rpid)

        if not pat_id:
            skipped += 1
            continue

        claim_legacy = (row.get("CLAIMID") or "").strip()
        oid = (row.get("OID") or "").strip()

        buf.add((
            pat_id,
            procedure_map.get(ledger_id),
            ledger_id,
            claim_map.get(claim_legacy),
            office_map.get(oid),
            parse_decimal(row.get("PRIMEST") or "0"),
            parse_decimal(row.get("PRIMINDMAX") or "0"),
            parse_decimal(row.get("PRIMDED") or "0"),
            parse_decimal(row.get("PRIMINSPAID") or "0"),
            parse_decimal(row.get("PRIMINSADJUST") or "0"),
            parse_decimal(row.get("SECEST") or "0"),
            parse_decimal(row.get("SECINSPAID") or "0"),
            parse_decimal(row.get("SECINSADJUST") or "0"),
            parse_decimal(row.get("TERINSPAID") or "0"),
            ins_plan_map.get((row.get("PRIMINSPLANID") or "").strip()),
            ins_plan_map.get((row.get("SECINSPLANID") or "").strip()),
            ins_plan_map.get((row.get("TERINSPLANID") or "").strip()),
            parse_bool(row.get("PRIMINSPOSTED", "False")),
            parse_bool(row.get("SECINSPOSTED", "False")),
        ))

    buf.flush()
    print(f"  [s32] ledger_insurance_details: {buf.inserted} inserted, {skipped} skipped")
    return {}
