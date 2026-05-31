"""
STEP 18 — insurance_subscribers
Source: RespInsplan.txt
Returns: { respplanid_str: subscriber_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import (
    clean, parse_date, parse_decimal, map_gender, map_elig_status
)


def run(conn, maps: dict) -> dict:
    tenant_map   = maps["tenant_map"]
    ins_plan_map = maps["ins_plan_map"]
    patient_map  = maps["patient_map"]
    office_map   = maps["office_map"]
    default_tid  = next(iter(tenant_map.values()))

    if not ins_plan_map:
        print("  [s18] WARNING: ins_plan_map is empty — run steps 7-9 first (e.g. --from 7 --steps 7-11)")

    src = cfg.src("RespInsplan.txt")
    cur = conn.cursor()
    sub_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        respplanid = (row.get("RESPPLANID") or "").strip()
        planid     = (row.get("INSPLANID") or "").strip()
        rpid       = (row.get("RPID") or "").strip()
        if not respplanid or not planid:
            skipped += 1
            continue

        plan_db_id = ins_plan_map.get(planid)
        if not plan_db_id:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        oid  = (row.get("OID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)

        cur.execute(
            """
            INSERT INTO insurance_subscribers (
                tenant_id, legacy_id, ins_plan_id, subscriber_patient_id, office_id,
                sub_first_name, sub_last_name, sub_mi,
                sub_address, sub_city, sub_state, sub_zip,
                sub_dob, sub_gender, sub_ssn, sub_member_id, group_number,
                effective_date, term_date,
                family_max_remaining, family_ded_remaining, ortho_remaining,
                anniversary_date, elig_status, elig_verified_on, elig_verified_by, elig_notes,
                notes
            ) VALUES (
                %s,%s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,
                %s,%s,%s,
                %s,%s,%s,%s,%s,
                %s
            )
            ON CONFLICT (legacy_id) DO UPDATE SET
                elig_status = EXCLUDED.elig_status,
                updated_at  = NOW()
            RETURNING id
            """,
            (
                tid, respplanid, plan_db_id,
                patient_map.get(rpid),
                office_map.get(oid),
                clean(row.get("SUBFNAME")),
                clean(row.get("SUBLNAME")),
                clean(row.get("SUBMI")),
                clean(row.get("SUBADDRESS") or row.get("SUBADDRESS1")),
                clean(row.get("SUBCITY")),
                clean(row.get("SUBSTATE")),
                clean(row.get("SUBZIP")),
                parse_date(row.get("SUBBIRTHDATE") or ""),
                map_gender(row.get("SEX") or ""),
                clean(row.get("SUBSSN")),
                clean(row.get("SUBID")),
                clean(row.get("GROUPNO")),
                parse_date(row.get("SUBPLANEFFDATE") or ""),
                parse_date(row.get("SUBPLANTERMDATE") or ""),
                parse_decimal(row.get("FAMMAXREM") or "0"),
                parse_decimal(row.get("FAMDEDREM") or "0"),
                parse_decimal(row.get("FAMORTHOREM") or "0"),
                parse_date(row.get("ANNIVDATE") or ""),
                map_elig_status(row.get("ELIGVERIFIED") or ""),
                None,  # elig_verified_on — parse if field present
                clean(row.get("ELIGVERIFIEDBY")),
                clean(row.get("ELIGNOTES")),
                clean(row.get("NOTES")),
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM insurance_subscribers WHERE legacy_id = %s", (respplanid,))
            row_id = cur.fetchone()
        sub_map[respplanid] = row_id[0]
        inserted += 1

        if inserted % 500 == 0:
            conn.commit()

    conn.commit()
    print(f"  [s18] insurance_subscribers: {inserted} upserted, {skipped} skipped → map size {len(sub_map)}")
    return sub_map
