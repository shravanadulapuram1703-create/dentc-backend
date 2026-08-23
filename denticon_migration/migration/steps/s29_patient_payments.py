"""
STEP 29 — patient_payments
Source: LEDGER/*.txt (36 split files) + Ledger_archive.txt
        Only rows where LTYPE IN ('P', 'I', 'A')
NOTE: patient_payments.id is VARCHAR(50) → "PAY-{LEDGERID}"
Returns: { ledgerid_str: payment_varchar_pk }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file, read_folder
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import (
    clean, parse_date, parse_datetime, parse_decimal, parse_bool,
    route_ledger_row, map_payment_method, LTYPE_PAYMENT_TYPE
)

COLS = [
    "id", "patient_id", "office_id", "legacy_id", "is_archived",
    "payment_date", "amount", "payment_type", "payment_method",
    "check_number", "provider_id", "notes", "is_void",
    # AL-10: who posted it — see s28.
    "created_by", "created_by_legacy", "created_at",
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
    patient_map  = maps["patient_map"]
    provider_map = maps["provider_map"]
    office_map   = maps["office_map"]
    user_map     = {str(k).strip().lower(): v for k, v in maps.get("user_map", {}).items()}

    payment_map: dict[str, str] = {}
    skipped = 0
    buf = BulkBuffer(
        conn, "patient_payments", COLS,
        conflict="ON CONFLICT (id) DO NOTHING",
        flush_every=20000, page_size=2000, label="payments",
    )

    for row, is_archived in _rows():
        if route_ledger_row(row) != "patient_payments":
            continue

        ledger_id = (row.get("LEDGERID") or "").strip()
        rpid      = (row.get("PATID") or row.get("RPID") or "").strip()
        pat_id    = patient_map.get(rpid)

        if not ledger_id or not pat_id:
            skipped += 1
            continue

        pay_date = parse_date(row.get("TRANDATE") or "")
        if not pay_date:
            skipped += 1
            continue

        ltype = (row.get("LTYPE") or "").strip()
        db_pk = f"PAY-{ledger_id}"
        oid   = (row.get("OID") or "").strip()
        prid  = (row.get("PROVIDERID") or "").strip()

        # Amount: AMOUNT is the raw amount. For adjustments it may be negative.
        amount = parse_decimal(row.get("AMOUNT") or "0")

        buf.add((
            db_pk, pat_id,
            office_map.get(oid),
            ledger_id, is_archived,
            pay_date, amount,
            LTYPE_PAYMENT_TYPE.get(ltype, "patient"),
            map_payment_method(row.get("TYPE2") or ""),
            clean(row.get("CHECKNO")),
            provider_map.get(prid),
            clean(row.get("NOTES")),
            parse_bool(row.get("ISVOID", "False")),
            user_map.get((row.get("CREATEDBY") or "").strip().lower()),
            clean(row.get("CREATEDBY")),
            parse_datetime(row.get("CREATEDON") or ""),
        ))
        payment_map[ledger_id] = db_pk

    buf.flush()
    print(f"  [s29] patient_payments: {buf.inserted} inserted, {skipped} skipped → map size {len(payment_map)}")
    return payment_map
