"""
STEP 28 — patient_procedures
Source: LEDGER/*.txt (36 split files) + Ledger_archive.txt
        Only rows where LTYPE = 'C' (charges)
NOTE: patient_procedures.id is VARCHAR(50) → "PROC-{LEDGERID}"
Returns: { ledgerid_str: proc_varchar_pk }
"""

import itertools
from migration.config import cfg
from migration.utils.reader import read_denticon_file, read_folder
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import (
    clean, parse_date, parse_datetime, parse_decimal, parse_bool, parse_int,
    map_billing_order, route_ledger_row
)

COLS = [
    "id", "patient_id", "appointment_id", "procedure_code", "legacy_id", "is_archived",
    "date_of_service", "provider_id", "office_id",
    "tooth", "surface",
    "fee", "ucr_fee", "insurance_estimate",
    "apply_to", "billing_order",
    "billing_status", "hold_claim", "is_void",
    "material_id", "notes",
    # AL-6/AL-10: DURATION and CREATEDBY/CREATEDON used to be dropped, so the
    # ledger's Durati… and User columns were blank for every migrated row.
    # LEDGER.CLAIMID (which is what makes `unbilled` trustworthy) is NOT set here —
    # insurance_claims is step 30, so the FK would not yet resolve; both it and the
    # already-migrated rows are handled by
    # scripts/backfill_ledger_source_fields.py, which runs after the full pass.
    "duration_minutes", "created_by", "created_by_legacy", "created_at",
    # AL-15: PATPAID/PATADJUST are the only surviving record of what was applied
    # to a charge — the allocation export's AMOUNT is 0.0000 on every row (AL-16).
    "pat_paid", "pat_adjust",
]


def _rows():
    folder = cfg.src("LEDGER")
    if folder.exists():
        for row in read_folder(folder):
            yield row, False
    archive = cfg.src("Ledger_archive.txt")
    if archive.exists():
        for row in read_denticon_file(archive):
            yield row, True


def run(conn, maps: dict) -> dict:
    patient_map   = maps["patient_map"]
    provider_map  = maps["provider_map"]
    office_map    = maps["office_map"]
    appt_map      = maps.get("appt_map", {})
    proc_code_set = maps.get("proc_code_set", set())
    material_map  = maps.get("material_map", {})
    # AL-10: CREATEDBY holds the Denticon login (SHORTID); users.legacy_id is keyed
    # on the same string. Matched case-insensitively — the export is inconsistent.
    user_map      = {str(k).strip().lower(): v for k, v in maps.get("user_map", {}).items()}

    procedure_map: dict[str, str] = {}
    skipped = 0
    buf = BulkBuffer(
        conn, "patient_procedures", COLS,
        conflict="ON CONFLICT (id) DO NOTHING",
        flush_every=20000, page_size=2000, label="procedures",
    )

    for row, is_archived in _rows():
        if route_ledger_row(row) != "patient_procedures":
            continue

        ledger_id = (row.get("LEDGERID") or "").strip()
        rpid      = (row.get("PATID") or row.get("RPID") or "").strip()
        code      = (row.get("ADACODE") or row.get("CODE") or "").strip()
        pat_id    = patient_map.get(rpid)

        if not ledger_id or not pat_id or not code:
            skipped += 1
            continue
        if proc_code_set and code not in proc_code_set:
            skipped += 1
            continue

        dos = parse_date(row.get("DOSDATE") or row.get("TRANDATE") or "")
        if not dos:
            skipped += 1
            continue

        oid  = (row.get("OID") or "").strip()
        prid = (row.get("PROVIDERID") or "").strip()
        provider_pk = provider_map.get(prid)
        if not provider_pk:
            skipped += 1
            continue

        db_pk   = f"PROC-{ledger_id}"
        appt_id = (row.get("APPTDID") or row.get("APPTID") or "").strip()

        buf.add((
            db_pk, pat_id,
            appt_map.get(appt_id),
            code, ledger_id, is_archived,
            dos, provider_pk,
            office_map.get(oid),
            clean(row.get("TH")),
            clean(row.get("SURF")),
            parse_decimal(row.get("AMOUNT") or "0"),
            parse_decimal(row.get("UCRFEE") or "0"),
            parse_decimal(row.get("ESTINS") or "0"),
            clean(row.get("APPLYTO")),
            map_billing_order(row.get("BILLINGORDER") or ""),
            "paid" if parse_decimal(row.get("PATPAID") or "0") > 0 else "not_billed",
            parse_bool(row.get("ISHOLDCLAIM", "False")),
            parse_bool(row.get("ISVOID", "False")),
            material_map.get((row.get("MATERIALID") or "").strip()),
            clean(row.get("NOTES")),
            parse_int(row.get("DURATION")),
            user_map.get((row.get("CREATEDBY") or "").strip().lower()),
            clean(row.get("CREATEDBY")),
            parse_datetime(row.get("CREATEDON") or ""),
            parse_decimal(row.get("PATPAID") or "0"),
            parse_decimal(row.get("PATADJUST") or "0"),
        ))
        procedure_map[ledger_id] = db_pk

    buf.flush()
    print(f"  [s28] patient_procedures: {buf.inserted} inserted, {skipped} skipped → map size {len(procedure_map)}")
    return procedure_map
