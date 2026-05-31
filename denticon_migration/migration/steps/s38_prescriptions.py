"""
STEP 38 — prescriptions
Source: PatRx.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_date, parse_int, parse_bool


def run(conn, maps: dict) -> dict:
    patient_map  = maps["patient_map"]
    office_map   = maps["office_map"]
    provider_map = maps.get("provider_map", {})
    rx_lib_map   = maps.get("rx_lib_map", {})

    src = cfg.src("PatRx.txt")
    if not src.exists():
        print("  [s38] prescriptions: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        rx_id  = (row.get("PATRXID") or "").strip()
        rpid   = (row.get("PATID") or row.get("RPID") or "").strip()
        pat_id = patient_map.get(rpid)

        if not pat_id:
            skipped += 1
            continue

        drug = clean(row.get("DrugName") or row.get("DRUGNAME") or row.get("DRUG")) or ""
        if not drug:
            skipped += 1
            continue

        oid  = (row.get("OID") or "").strip()
        prid = (row.get("PROVIDERID") or "").strip()
        rxref = (row.get("RXRefID") or row.get("RXREFID") or "").strip()

        cur.execute(
            """
            INSERT INTO prescriptions (
                patient_id, office_id, legacy_id, library_rx_id,
                rx_date, drug_name, dispense, sig, refills, is_as_written,
                provider_id, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                pat_id,
                office_map.get(oid),
                rx_id,
                rx_lib_map.get(rxref),
                parse_date(row.get("RXDATE") or row.get("ACTDATE") or ""),
                drug,
                clean(row.get("Dispense") or row.get("DISPENSE")),
                clean(row.get("Sig") or row.get("SIG")),
                parse_int(row.get("Refill") or row.get("REFILL"), 0),
                parse_bool(row.get("IsAsWritten") or row.get("ISASWRITTEN") or "False"),
                provider_map.get(prid),
                clean(row.get("NOTES")),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s38] prescriptions: {inserted} inserted, {skipped} skipped")
    return {}
