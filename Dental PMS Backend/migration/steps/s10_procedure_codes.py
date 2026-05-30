"""
STEP 10 — procedure_codes
Source: Codes.txt
Returns: { code_str: code_str }  (PK is the code itself)
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_decimal, parse_int, parse_bool


# Denticon INSCATEGORYID → human label
CATEGORY_MAP = {
    "0": "Diagnostic",
    "1": "Preventive",
    "2": "Restorative",
    "3": "Endodontics",
    "4": "Periodontics",
    "5": "Prosthodontics",
    "6": "Oral Surgery",
    "7": "Orthodontics",
    "8": "Adjunctive",
    "9": "Implant Services",
    "10": "Maxillofacial Prosthetics",
    "11": "Other",
}


def run(conn, maps: dict) -> dict:
    src = cfg.src("Codes.txt")
    cur = conn.cursor()
    proc_code_set: set[str] = set()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        code = (row.get("CODE") or row.get("ADACODE") or "").strip()
        if not code:
            skipped += 1
            continue

        cat_id  = (row.get("INSCATEGORYID") or "11").strip()
        category = CATEGORY_MAP.get(cat_id, "Other")
        desc = clean(row.get("DESCR") or row.get("DESCRIPTION")) or code

        cur.execute(
            """
            INSERT INTO procedure_codes (
                code, legacy_code, description, category, default_fee,
                default_duration_minutes, requires_tooth, requires_surface,
                requires_quadrant, requires_lab, is_ortho, billing_order,
                recall_interval, recall_unit
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (code) DO UPDATE SET
                description = EXCLUDED.description,
                default_fee = EXCLUDED.default_fee
            """,
            (
                code, code, desc, category,
                parse_decimal(row.get("UCRFEE") or row.get("FEE") or "0"),
                parse_int(row.get("DURATION") or row.get("DEFAULTDURATION")),
                parse_bool(row.get("TOOTHREQ") or row.get("REQUIRESTOOTH", "False")),
                parse_bool(row.get("SURFREQ") or row.get("REQUIRESSURF", "False")),
                parse_bool(row.get("QUADREQ") or row.get("REQUIRESQUAD", "False")),
                parse_bool(row.get("LABREQ") or "False"),
                parse_bool(row.get("ISORTHO") or "False"),
                clean(row.get("BILLINGORDER")),
                parse_int(row.get("RECALLINT")),
                clean(row.get("RECALLUNIT")),
            ),
        )
        proc_code_set.add(code)
        inserted += 1

    conn.commit()
    print(f"  [s10] procedure_codes: {inserted} upserted, {skipped} skipped → {len(proc_code_set)} codes")
    return {"proc_code_set": proc_code_set}
