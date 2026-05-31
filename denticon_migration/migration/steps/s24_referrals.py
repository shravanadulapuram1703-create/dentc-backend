"""
STEP 24 — referrals
Source: Referrals.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    office_map  = maps["office_map"]
    patient_map = maps["patient_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("Referrals.txt")
    if not src.exists():
        print("  [s24] referrals: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        ref_id = (row.get("REFERRALID") or "").strip()
        if not ref_id:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        oid  = (row.get("OID") or "").strip()
        rpid = (row.get("RPID") or row.get("PATID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)

        cur.execute(
            """
            INSERT INTO referrals (
                tenant_id, office_id, legacy_id, referral_type, patient_id,
                first_name, last_name, address, city, state, zip,
                phone, email, npi, specialty, reason_code, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                tid, office_map.get(oid), ref_id,
                clean(row.get("TYPE") or row.get("REFERRALTYPE")),
                patient_map.get(rpid),
                clean(row.get("FNAME") or row.get("FIRSTNAME")),
                clean(row.get("LNAME") or row.get("LASTNAME")),
                clean(row.get("ADDRESS1") or row.get("ADDRESS")),
                clean(row.get("CITY")),
                clean(row.get("STATE")),
                clean(row.get("ZIP")),
                clean(row.get("PHONE")),
                clean(row.get("EMAIL")),
                clean(row.get("NPI")),
                clean(row.get("SPECIALTY")),
                clean(row.get("TYPE2")),
                clean(row.get("NOTES")),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s24] referrals: {inserted} inserted, {skipped} skipped")
    return {}
