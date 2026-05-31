"""
STEP 8 — insurance_coverage_rules
Source: INSCOVERAGE/*.txt  (11 split files — concat all)
Returns: {} (no downstream FKs needed)
"""

from migration.config import cfg
from migration.utils.reader import read_folder
from migration.utils.parsers import clean, parse_decimal, parse_bool, parse_int


def run(conn, maps: dict) -> dict:
    ins_plan_map = maps["ins_plan_map"]
    folder = cfg.src("INSCOVERAGE")
    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_folder(folder):
        planid = (row.get("INSPLANID") or "").strip()
        cov_id = (row.get("INSCOVERAGEID") or "").strip()
        plan_db_id = ins_plan_map.get(planid)
        if not plan_db_id or not cov_id:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO insurance_coverage_rules (
                ins_plan_id, legacy_id, start_code, end_code,
                category, description, coverage_pct, ded_waived,
                freq_limit, age_limit, wait_period
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                plan_db_id, cov_id,
                clean(row.get("STARTCODE")) or "",
                clean(row.get("ENDCODE")) or "",
                clean(row.get("INSCATEGORY")),
                clean(row.get("DESCR")),
                parse_decimal(row.get("PCT") or "0"),
                parse_bool(row.get("DEDWAIVED", "0")),
                clean(row.get("FREQLIMIT")),
                clean(row.get("AGELIMIT")),
                clean(row.get("WAITPERIOD")),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s08] insurance_coverage_rules: {inserted} inserted, {skipped} skipped")
    return {}
