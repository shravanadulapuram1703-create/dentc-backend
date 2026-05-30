"""
STEP 25 — treatment_plans
Source: Derived from AppointmentDetails.txt + AppointmentDetail_ARCHIVE.txt
        (any row where TREATPLANID != 0 and TREATPLANID != '' creates a plan)
Returns: { treatplanid_str: plan_varchar_pk }
NOTE: treatment_plans.id is VARCHAR(50) — we use "TP-{TREATPLANID}" as PK
      so it's deterministic across re-runs.
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_datetime


def _collect_plans(src, patient_map, office_map):
    """
    Scan an AppointmentDetails file and return a dict of
    { treatplanid: {patient_id, office_id, created_at} }
    """
    plans: dict[str, dict] = {}
    for row in read_denticon_file(src):
        tpid = (row.get("TREATPLANID") or "").strip()
        if not tpid or tpid == "0":
            continue
        if tpid in plans:
            continue
        # patient comes via PATID (in AppointmentHeader); we use APPTID-level info
        # AppointmentDetails has no PATID — we'll enrich from appointment header later.
        # For now, store minimal info; patient_id is resolved in s26 after appointments.
        plans[tpid] = {
            "office_id": office_map.get((row.get("OID") or "").strip()),
            "created_at": parse_datetime(row.get("CREATEDDATE") or ""),
        }
    return plans


def run(conn, maps: dict) -> dict:
    patient_map = maps["patient_map"]
    office_map  = maps["office_map"]

    # We need PATID from AppointmentHeader to assign patient_id to plans.
    # Build a map: TREATPLANID → PATID from the header file.
    appt_detail_files = [
        cfg.src("AppointmentDetails.txt"),
        cfg.src("AppointmentDetail_ARCHIVE.txt"),
    ]
    header_src = cfg.src("AppointmentHeader.txt")

    # appt_id → {patid, oid} from header
    appt_patient_map: dict[str, tuple] = {}
    if header_src.exists():
        for row in read_denticon_file(header_src, apply_limit=False):
            aid  = (row.get("APPTID") or "").strip()
            rpid = (row.get("PATID") or row.get("RPID") or "").strip()
            oid  = (row.get("OID") or "").strip()
            if aid:
                appt_patient_map[aid] = (rpid, oid)

    # Now scan detail files: APPTID → TREATPLANID, resolve PATID via appt_patient_map
    txplan_map: dict[str, str] = {}  # treatplanid → varchar PK
    inserted = 0
    cur = conn.cursor()

    seen: dict[str, tuple] = {}  # treatplanid → (patient_id, office_id)
    for f in appt_detail_files:
        if not f.exists():
            continue
        for row in read_denticon_file(f):
            tpid = (row.get("TREATPLANID") or "").strip()
            if not tpid or tpid == "0":
                continue
            if tpid in seen:
                continue
            appt_id = (row.get("APPTID") or "").strip()
            rpid, oid = appt_patient_map.get(appt_id, ("", ""))
            pat_id = patient_map.get(rpid)
            if not pat_id:
                continue
            seen[tpid] = (pat_id, office_map.get(oid))

    for tpid, (pat_id, office_id) in seen.items():
        db_pk = f"TP-{tpid}"
        cur.execute(
            """
            INSERT INTO treatment_plans (id, patient_id, office_id, legacy_id, name, status)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (db_pk, pat_id, office_id, tpid, f"Treatment Plan {tpid}", "Active"),
        )
        txplan_map[tpid] = db_pk
        inserted += 1

    conn.commit()
    print(f"  [s25] treatment_plans: {inserted} inserted → map size {len(txplan_map)}")
    return txplan_map
