"""
STEP 27 — appointment_procedures
Source: AppointmentDetails.txt  (active)
        AppointmentDetail_ARCHIVE.txt (archived)
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import (
    clean, parse_decimal, parse_bool, parse_int, map_billing_order
)
from migration.utils.map_loader import merge_legacy_map


def _rows():
    src = cfg.src("AppointmentDetails.txt")
    if src.exists():
        for row in read_denticon_file(src):
            yield row, False
    archive = cfg.src("AppointmentDetail_ARCHIVE.txt")
    if archive.exists():
        for row in read_denticon_file(archive):
            yield row, True


def run(conn, maps: dict) -> dict:
    appt_map      = merge_legacy_map(conn, maps, "appt_map", "appointments")
    provider_map  = maps.get("provider_map", {})
    txplan_map    = merge_legacy_map(conn, maps, "txplan_map", "treatment_plans")
    material_map  = maps.get("material_map", {})
    proc_code_set = maps.get("proc_code_set", set())

    if not appt_map:
        print("  [s27] appointment_procedures: no appointments in DB — run s26 first")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row, is_archived in _rows():
        appt_id = (row.get("APPTID") or "").strip()
        code    = (row.get("ADACODE") or row.get("CODE") or "").strip()
        appt_pk = appt_map.get(appt_id)

        if not appt_pk or not code:
            skipped += 1
            continue
        if proc_code_set and code not in proc_code_set:
            skipped += 1
            continue

        prid   = (row.get("PROVIDERID") or "").strip()
        tpid   = (row.get("TREATPLANID") or "").strip()
        mat_id = (row.get("MATERIALID") or "").strip()

        # Map Denticon STATUS to our status
        det_status = (row.get("STATUS") or "S").strip().upper()
        status_map = {"C": "Completed", "S": "Scheduled", "TP": "Planned",
                      "E": "Existing", "": "Planned"}
        status = status_map.get(det_status, "Planned")

        cur.execute(
            """
            INSERT INTO appointment_procedures (
                appointment_id, procedure_code, provider_id, treatment_plan_id,
                tooth, surface, fee, insurance_estimate, billing_order,
                status, material_id, is_archived
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                appt_pk, code,
                provider_map.get(prid),
                txplan_map.get(tpid) if tpid and tpid != "0" else None,
                clean(row.get("TH")),
                clean(row.get("SURF")),
                parse_decimal(row.get("FEE") or "0"),
                parse_decimal(row.get("ESTINS") or "0"),
                map_billing_order(row.get("BILLINGORDER") or ""),
                status,
                material_map.get(mat_id) if mat_id else None,
                is_archived,
            ),
        )
        inserted += 1

        if inserted % 2000 == 0:
            conn.commit()

    conn.commit()
    print(f"  [s27] appointment_procedures: {inserted} inserted, {skipped} skipped")
    return {}
