"""
STEP 17 — patients
Source: RespParty.txt
NOTE: Every RPID in Denticon is a patient/guarantor. RPID == PATID means
      the patient is their own guarantor. We migrate ALL RPIDs as patients.
Returns: { rpid_str: patient_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import (
    clean, parse_date, parse_bool, map_gender, lookup
)


def run(conn, maps: dict) -> dict:
    tenant_map = maps["tenant_map"]
    office_map = maps["office_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("RespParty.txt")
    cur = conn.cursor()
    patient_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        rpid = (row.get("RPID") or "").strip()
        if not rpid:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        oid  = (row.get("OID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)
        office_id = office_map.get(oid)

        fname = clean(row.get("FNAME") or row.get("FIRSTNAME") or "")
        lname = clean(row.get("LNAME") or row.get("LASTNAME") or "")

        cur.execute(
            """
            INSERT INTO patients (
                tenant_id, home_office_id, legacy_id, chart_no,
                first_name, last_name, preferred_name, title, middle_initial,
                dob, gender, ssn, marital_status,
                phone, cell_phone, work_phone, email, preferred_contact,
                address_line1, address_line2, city, state, zip,
                is_finance_charge, send_statements, send_collections,
                no_auto_email, is_locked, hipaa_agreement,
                guardian_name, guardian_phone, referral_type, referred_by,
                patient_notes
            ) VALUES (
                %s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,%s,
                %s
            )
            ON CONFLICT (legacy_id) DO UPDATE SET
                first_name  = EXCLUDED.first_name,
                last_name   = EXCLUDED.last_name,
                email       = EXCLUDED.email,
                updated_at  = NOW()
            RETURNING id
            """,
            (
                tid, office_id, rpid,
                clean(row.get("CHARTNO") or row.get("CHART_NO")),
                fname, lname,
                clean(row.get("NICKNAME") or row.get("PREFERREDNAME")),
                clean(row.get("TITLE")),
                clean(row.get("MI") or row.get("MIDDLEINITIAL")),
                parse_date(row.get("BIRTHDATE") or row.get("DOB") or ""),
                map_gender(row.get("SEX") or row.get("GENDER") or ""),
                clean(row.get("SSN")),
                clean(row.get("MSTATUS") or row.get("MARITALSTATUS")),
                clean(row.get("HOMEPHONE") or row.get("PHONE")),
                clean(row.get("CELLPHONE") or row.get("MOBILEPHONE")),
                clean(row.get("WORKPHONE")),
                clean(row.get("EMAIL")),
                clean(row.get("PREFERREDCONTACT")),
                clean(row.get("ADDRESS1") or row.get("ADDRESS")),
                clean(row.get("ADDRESS2")),
                clean(row.get("CITY")),
                clean(row.get("STATE")),
                clean(row.get("ZIP")),
                parse_bool(row.get("ISFINCHARGE", "False")),
                not parse_bool(row.get("NOEMAILSTMT", "False")),  # NOEMAILSTMT=True → no stmt
                parse_bool(row.get("ISSENDCOLL", "False")),
                parse_bool(row.get("NOEMAILSTMT", "False")),
                parse_bool(row.get("ISLOCKED", "False")),
                parse_bool(row.get("HIPAASIGNED", "False")),
                clean(row.get("GUARDIANNAME")),
                clean(row.get("GUARDIANPHONE")),
                clean(row.get("REFERRALTYPE")),
                clean(row.get("REFERREDBY")),
                clean(row.get("NOTES") or row.get("PATIENTNOTES")),
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM patients WHERE legacy_id = %s", (rpid,))
            row_id = cur.fetchone()
        patient_map[rpid] = row_id[0]
        inserted += 1

        # Commit in batches to avoid long transactions
        if inserted % 500 == 0:
            conn.commit()
            print(f"    ...{inserted} patients inserted")

    conn.commit()
    print(f"  [s17] patients: {inserted} upserted, {skipped} skipped → map size {len(patient_map)}")
    return patient_map
