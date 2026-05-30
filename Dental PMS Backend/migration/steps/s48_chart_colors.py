"""
STEP 48 — chart_colors
Source: CHARTCOLORS.txt  (HAS DATA)
Tooth chart color/pattern category definitions (Pre-existing, Completed, etc.)
Returns: { categoryid_str: chart_color_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_int


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("CHARTCOLORS.txt")
    if not src.exists():
        print("  [s48] chart_colors: file not found, skipping")
        return {}

    cur = conn.cursor()
    color_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        cat_id = (row.get("CATEGORYID") or "").strip()
        if not cat_id:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)
        name = clean(row.get("CATNAME")) or f"Category {cat_id}"

        cur.execute(
            """
            INSERT INTO chart_colors (
                tenant_id, legacy_id, category_type, name,
                stroke_color, fill_type, fill_color, fill_color2,
                fill_pattern, gradient_angle, gradient_method,
                created_by, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                tid, cat_id,
                parse_int(row.get("CATTYPE")),
                name,
                clean(row.get("STROKECOLOR")),
                clean(row.get("FILLTYPE")),
                clean(row.get("FILLCOLOR")),
                clean(row.get("FILLCOLOR2")),
                clean(row.get("FILLPATTERN")),
                clean(row.get("GRADANGLE")),
                clean(row.get("GRADMETHOD")),
                clean(row.get("CREATEDBY")),
                None,
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM chart_colors WHERE legacy_id = %s AND tenant_id = %s",
                        (cat_id, tid))
            row_id = cur.fetchone()
        if row_id:
            color_map[cat_id] = row_id[0]
        inserted += 1

    conn.commit()
    print(f"  [s48] chart_colors: {inserted} inserted, {skipped} skipped → map size {len(color_map)}")
    return color_map
