"""
STEP 6 — insurance_carriers
Source: Carrier.txt
Returns: { carrierid_str: carrier_db_id }

Captures the full Carrier.txt column set: type/claim/fee flags, national & VBS
identifiers, contact, ref number, CDA counter, and the legacy audit stamps.
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import clean, parse_datetime

COLS = [
    "tenant_id", "legacy_id", "name", "carrier_type",
    "payer_id", "national_id", "claim_type", "fee_id",
    "phone", "phone2", "address", "address2", "city", "state", "zip",
    "website", "contact", "notes", "ref_num",
    "vbs_id", "vbs_pgid", "cda_carrier_transaction_counter",
    "created_on", "created_by", "modified_on", "modified_by",
]

# Re-running updates every mapped column in place (ids are preserved).
_UPDATE = ", ".join(
    f"{c} = EXCLUDED.{c}" for c in COLS if c not in ("tenant_id", "legacy_id")
)


def run(conn, maps: dict) -> dict:
    tenant_map = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("Carrier.txt")
    skipped = 0
    buf = BulkBuffer(
        conn, "insurance_carriers", COLS,
        conflict=f"ON CONFLICT (legacy_id) DO UPDATE SET {_UPDATE}",
        returning="id, legacy_id",
        dedup_index=COLS.index("legacy_id"),
        flush_every=10000, page_size=2000, label="insurance_carriers",
    )

    for row in read_denticon_file(src):
        cid = (row.get("CARRIERID") or "").strip()
        if not cid:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)
        name = clean(row.get("CARRIERNAME") or row.get("NAME")) or f"Carrier {cid}"

        buf.add((
            tid, cid, name,
            clean(row.get("CARRIERTYPE")),
            clean(row.get("PAYERID") or row.get("ELECTRONICPAYERID")),
            clean(row.get("NATIONALID")),
            clean(row.get("CLAIMTYPE")),
            clean(row.get("FEEID")),
            clean(row.get("PHONE")),
            clean(row.get("PHONE2")),
            clean(row.get("ADDRESS1") or row.get("ADDRESS")),
            clean(row.get("ADDRESS2")),
            clean(row.get("CITY")),
            clean(row.get("STATE")),
            clean(row.get("ZIP")),
            clean(row.get("WEBSITE")),
            clean(row.get("CONTACT")),
            clean(row.get("NOTES")),
            clean(row.get("REFNUM")),
            clean(row.get("VBSID")),
            clean(row.get("VBSPGID")),
            clean(row.get("CDACARRIERTRANSACTIONCOUNTER")),
            parse_datetime(row.get("CREATEDON") or ""),
            clean(row.get("CREATEDBY")),
            parse_datetime(row.get("MODIFIEDON") or ""),
            clean(row.get("MODIFIEDBY")),
        ))

    buf.flush()
    carrier_map = {str(legacy): pk for pk, legacy in buf.returned}
    print(f"  [s06] insurance_carriers: {buf.inserted} upserted, {skipped} skipped → map size {len(carrier_map)}")
    return carrier_map
