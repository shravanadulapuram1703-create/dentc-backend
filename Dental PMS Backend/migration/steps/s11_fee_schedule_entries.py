"""
STEP 11 — fee_schedule_entries
Source: FeeScheD.txt
Depends on: fee_schedules, procedure_codes
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import parse_decimal, parse_date, clean


def run(conn, maps: dict) -> dict:
    fee_sched_map = maps["fee_sched_map"]
    proc_code_set = maps.get("proc_code_set", set())

    src = cfg.src("FeeScheD.txt")
    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        feeid = (row.get("FEEID") or "").strip()
        code  = (row.get("CODE") or row.get("ADACODE") or "").strip()
        fs_id = fee_sched_map.get(feeid)

        if not fs_id or not code or code not in proc_code_set:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO fee_schedule_entries
                (fee_schedule_id, procedure_code, patient_fee, insurance_fee, effective_date)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (fee_schedule_id, procedure_code) DO UPDATE SET
                patient_fee   = EXCLUDED.patient_fee,
                insurance_fee = EXCLUDED.insurance_fee
            """,
            (
                fs_id, code,
                parse_decimal(row.get("PATAMT") or row.get("UCRAMOUNT") or "0"),
                parse_decimal(row.get("INSAMT") or "0"),
                parse_date(row.get("EFFECTIVEDATE") or ""),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s11] fee_schedule_entries: {inserted} inserted, {skipped} skipped")
    return {}
