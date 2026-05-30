"""
STEP 44 — imaging_templates
Source: IMAGETEMPLATE.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    office_map  = maps["office_map"]
    default_oid = next(iter(office_map.values()))

    src = cfg.src("IMAGETEMPLATE.txt")
    if not src.exists():
        print("  [s44] imaging_templates: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        tmpl_id = (row.get("TEMPLATEID") or "").strip()
        if not tmpl_id:
            skipped += 1
            continue

        oid  = (row.get("OID") or "").strip()
        name = clean(row.get("TEMPLATENAME") or row.get("NAME")) or f"Template {tmpl_id}"

        cur.execute(
            """
            INSERT INTO imaging_templates
                (office_id, legacy_id, name, template_type, dentition)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                office_map.get(oid, default_oid),
                tmpl_id, name,
                clean(row.get("TEMPLATETYPE")),
                clean(row.get("DENTITION")),
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s44] imaging_templates: {inserted} inserted, {skipped} skipped")
    return {}
