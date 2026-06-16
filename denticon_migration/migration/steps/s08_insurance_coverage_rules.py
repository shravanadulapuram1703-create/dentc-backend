"""
STEP 8 — insurance_coverage_rules
Source: INSCOVERAGE/*.txt  (11 split files — concat all)
Returns: {} (no downstream FKs needed)
"""

from migration.config import cfg
from migration.utils.reader import read_folder
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import clean, parse_decimal, parse_bool, parse_int

COLS = [
    "ins_plan_id", "legacy_id", "start_code", "end_code",
    "category", "description", "coverage_pct", "ded_waived",
    "freq_limit", "age_limit", "wait_period",
]


def run(conn, maps: dict) -> dict:
    ins_plan_map = maps["ins_plan_map"]
    folder = cfg.src("INSCOVERAGE")

    # This table has no natural unique key (only a serial PK), so re-running with
    # ON CONFLICT DO NOTHING would duplicate every row. Truncate for a clean,
    # idempotent full reload. Leaf table — nothing references it.
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE insurance_coverage_rules RESTART IDENTITY")
    conn.commit()

    skipped = 0
    buf = BulkBuffer(
        conn, "insurance_coverage_rules", COLS,
        conflict="ON CONFLICT DO NOTHING",
        flush_every=20000, page_size=2000, label="coverage_rules",
    )

    for row in read_folder(folder):
        planid = (row.get("INSPLANID") or "").strip()
        cov_id = (row.get("INSCOVERAGEID") or "").strip()
        plan_db_id = ins_plan_map.get(planid)
        if not plan_db_id or not cov_id:
            skipped += 1
            continue

        buf.add((
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
        ))

    buf.flush()
    print(f"  [s08] insurance_coverage_rules: {buf.inserted} inserted, {skipped} skipped")
    return {}
