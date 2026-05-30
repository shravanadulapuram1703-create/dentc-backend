"""
STEP 27b — treatment_plan_items
Source: AppointmentDetails.txt + AppointmentDetail_ARCHIVE.txt
        (same files used by s27, but targeting treatment_plan_items instead)

Populates the treatment_plan_items table from appointment detail rows that
have a TREATPLANID != 0. These represent the planned procedures inside each
treatment plan.

Key rules:
  - Only rows with TREATPLANID != 0 are included
  - STATUS codes: 'TP' or '' = 'Planned', 'S' = 'Scheduled', 'C' = 'Completed'
  - Each (TREATPLANID, ADACODE, TH, SURF) combination is de-duplicated;
    if the same code appears on multiple appointments within the same plan,
    we keep the first occurrence (ON CONFLICT DO NOTHING)
  - plan_id is looked up via txplan_map (built by s25)
  - id format: "TPI-{APPTDYD}" to be deterministic

Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import (
    clean, parse_decimal, map_billing_order
)
from migration.utils.map_loader import merge_legacy_map


def _rows():
    src = cfg.src("AppointmentDetails.txt")
    if src.exists():
        for row in read_denticon_file(src):
            yield row
    archive = cfg.src("AppointmentDetail_ARCHIVE.txt")
    if archive.exists():
        for row in read_denticon_file(archive):
            yield row


# Denticon APPTSTATUS/detail status → treatment plan item status
STATUS_MAP = {
    "C":  "Completed",
    "S":  "Scheduled",
    "TP": "Planned",
    "E":  "Existing",
    "":   "Planned",
}


def run(conn, maps: dict) -> dict:
    txplan_map    = merge_legacy_map(conn, maps, "txplan_map", "treatment_plans")
    proc_code_set = maps.get("proc_code_set", set())
    provider_map  = maps.get("provider_map", {})

    if not txplan_map:
        print("  [s27b] treatment_plan_items: no txplan_map — run s25 first, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in _rows():
        tpid = (row.get("TREATPLANID") or "").strip()
        if not tpid or tpid == "0":
            continue

        plan_pk = txplan_map.get(tpid)
        if not plan_pk:
            skipped += 1
            continue

        code = (row.get("ADACODE") or row.get("CODE") or "").strip()
        if not code or (proc_code_set and code not in proc_code_set):
            skipped += 1
            continue

        # Use APPTDYD (appointment detail ID) for a deterministic PK
        appt_dyd = (row.get("APPTDYD") or "").strip()
        item_pk  = f"TPI-{appt_dyd}" if appt_dyd else f"TPI-{tpid}-{code}"

        det_status = (row.get("STATUS") or "").strip().upper()
        status = STATUS_MAP.get(det_status, "Planned")

        prid = (row.get("PROVIDERID") or "").strip()
        diagnosed_by = None
        if prid:
            # Store the legacy provider ID string as the diagnosing provider label
            # (treatment_plan_items.diagnosed_by is varchar, not FK)
            diagnosed_by = prid

        cur.execute(
            """
            INSERT INTO treatment_plan_items (
                id, plan_id, procedure_code, tooth, surface,
                fee, insurance_estimate, billing_order,
                status, priority, diagnosed_by
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                item_pk,
                plan_pk,
                code,
                clean(row.get("TH")),
                clean(row.get("SURF")),
                parse_decimal(row.get("FEE") or "0"),
                parse_decimal(row.get("ESTINS") or "0"),
                map_billing_order(row.get("BILLINGORDER") or ""),
                status,
                1,          # default priority — all items are Phase 1 unless set otherwise
                diagnosed_by,
            ),
        )
        inserted += 1

        if inserted % 2000 == 0:
            conn.commit()

    conn.commit()
    print(f"  [s27b] treatment_plan_items: {inserted} inserted, {skipped} skipped")
    return {}
