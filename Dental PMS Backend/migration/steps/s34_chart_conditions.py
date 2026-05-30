"""
STEP 34 — chart_conditions
Source: ChartActivity.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_date, parse_bool


def run(conn, maps: dict) -> dict:
    patient_map   = maps["patient_map"]
    office_map    = maps["office_map"]
    provider_map  = maps.get("provider_map", {})
    material_map  = maps.get("material_map", {})
    proc_code_set = maps.get("proc_code_set", set())

    src = cfg.src("ChartActivity.txt")
    if not src.exists():
        print("  [s34] chart_conditions: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        chart_id = (row.get("CHARTID") or "").strip()
        rpid     = (row.get("PATID") or row.get("RPID") or "").strip()
        pat_id   = patient_map.get(rpid)

        if not pat_id:
            skipped += 1
            continue

        oid      = (row.get("OID") or "").strip()
        prid     = (row.get("PROVIDERID") or "").strip()
        mat_id   = (row.get("MATERIALID") or "").strip()
        code     = (row.get("CODE") or row.get("ADACODE") or "").strip()
        code_fk  = code if (proc_code_set and code in proc_code_set) else None

        cur.execute(
            """
            INSERT INTO chart_conditions (
                patient_id, office_id, legacy_id, activity_date,
                tooth, surface, region, area,
                description, condition_code, procedure_code,
                provider_id, material_id, chart_as, is_inactive, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                pat_id,
                office_map.get(oid),
                chart_id,
                parse_date(row.get("ACTDATE") or ""),
                clean(row.get("TH") or row.get("TOOTH")),
                clean(row.get("SURF") or row.get("SURFACE")),
                clean(row.get("REGION")),
                clean(row.get("AREA")),
                clean(row.get("DESCR") or row.get("DESCRIPTION")),
                clean(row.get("CONDITIONCODE") or row.get("CONDITION")),
                code_fk,
                provider_map.get(prid),
                material_map.get(mat_id) if mat_id else None,
                clean(row.get("CHARTAS")),
                parse_bool(row.get("ISINACTIVE", "False")),
                clean(row.get("NOTES")),
            ),
        )
        inserted += 1

        if inserted % 2000 == 0:
            conn.commit()

    conn.commit()
    print(f"  [s34] chart_conditions: {inserted} inserted, {skipped} skipped")
    return {}
