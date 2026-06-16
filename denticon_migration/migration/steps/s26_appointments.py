"""
STEP 26 — appointments
Source: AppointmentHeader.txt  (active)
        APPTH_ARCHIVE/*.txt    (archived — same columns, 2 files)
NOTE: appointments.id is VARCHAR(50) — use "APPT-{APPTID}" for determinism.
      Blocked slots (PATID=0 or ISBLOCKED=True) are stored with is_blocked=True.
Returns: { apptid_str: appt_varchar_pk }
"""

import itertools
from datetime import datetime, timedelta
from migration.config import cfg
from migration.utils.reader import read_denticon_file, read_folder
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import (
    clean, parse_date, parse_datetime, parse_bool, parse_int, parse_decimal,
    map_appt_status
)

COLS = [
    "id", "patient_id", "provider_id", "operatory_id", "office_id",
    "legacy_id", "is_archived", "date", "start_time", "end_time", "duration",
    "status", "is_missed", "is_cancelled", "is_posted",
    "procedure_label", "notes",
    "has_lab", "lab_cost", "lab_sent_on", "lab_due_on", "lab_received_on",
    "is_blocked", "campaign_id", "treatment_plan_id",
]


def _rows():
    """Yield all appointment header rows (active + archived)."""
    src = cfg.src("AppointmentHeader.txt")
    if src.exists():
        for row in read_denticon_file(src):
            yield row, False
    archive_dir = cfg.src("APPTH_ARCHIVE")
    if archive_dir.exists():
        for row in read_folder(archive_dir):
            yield row, True


def run(conn, maps: dict) -> dict:
    patient_map   = maps["patient_map"]
    provider_map  = maps["provider_map"]
    operatory_map = maps["operatory_map"]
    office_map    = maps["office_map"]
    txplan_map    = maps.get("txplan_map", {})
    default_oid   = next(iter(office_map.values()))

    appt_map: dict[str, str] = {}
    skipped = 0
    buf = BulkBuffer(
        conn, "appointments", COLS,
        conflict=(
            "ON CONFLICT (id) DO UPDATE SET "
            "status = EXCLUDED.status, "
            "updated_at = NOW()"
        ),
        dedup_index=COLS.index("id"),
        flush_every=20000, page_size=2000, label="appointments",
    )

    for row, is_archived in _rows():
        appt_id = (row.get("APPTID") or "").strip()
        if not appt_id:
            skipped += 1
            continue

        rpid = (row.get("PATID") or "").strip()
        is_blocked = parse_bool(row.get("ISBLOCKED", "False")) or rpid == "0"
        pat_id = patient_map.get(rpid) if not is_blocked else None
        if not is_blocked and not pat_id:
            skipped += 1
            continue

        oid  = (row.get("OID") or "").strip()
        prid = (row.get("PROVIDERID") or "").strip()
        opid = (row.get("OPERATORYID") or "").strip()
        office_id    = office_map.get(oid, default_oid)
        provider_pk  = provider_map.get(prid)
        operatory_pk = operatory_map.get(opid)

        if not provider_pk:
            skipped += 1
            continue

        appt_date = parse_date(row.get("APPTDATE") or "")
        if not appt_date:
            skipped += 1
            continue

        # Calculate start_time and end_time from APPTDATE (datetime) + APPTLENGTH (minutes)
        dt_full = parse_datetime(row.get("APPTDATE") or "")
        if dt_full:
            start_t = dt_full.time()
            duration = parse_int(row.get("APPTLENGTH"), 60)
            end_dt   = dt_full + timedelta(minutes=duration)
            end_t    = end_dt.time()
        else:
            start_t  = datetime.strptime("08:00", "%H:%M").time()
            duration = parse_int(row.get("APPTLENGTH"), 60)
            end_t    = datetime.strptime("09:00", "%H:%M").time()

        db_pk = f"APPT-{appt_id}"
        tpid  = (row.get("TREATPLANID") or "").strip()
        tp_pk = txplan_map.get(tpid) if tpid and tpid != "0" else None

        buf.add((
            db_pk, pat_id, provider_pk, operatory_pk, office_id,
            appt_id, is_archived, appt_date, start_t, end_t, duration,
            map_appt_status(row),
            parse_bool(row.get("ISMISSED", "False")),
            parse_bool(row.get("ISCANCELLED", "False")),
            parse_bool(row.get("ISPOSTED", "False")),
            clean(row.get("PRODTYPE")),
            clean(row.get("APPTNOTES") or row.get("NOTES")),
            parse_bool(row.get("ISLAB", "False")),
            parse_decimal(row.get("LABCOST") or "0"),
            parse_date(row.get("LABSENTON") or ""),
            parse_date(row.get("LABDUEON") or ""),
            parse_date(row.get("LABRECVDON") or ""),
            is_blocked,
            clean(row.get("CAMPAIGN")),
            tp_pk,
        ))
        appt_map[appt_id] = db_pk

    buf.flush()
    print(f"  [s26] appointments: {buf.inserted} upserted, {skipped} skipped → map size {len(appt_map)}")
    return appt_map
