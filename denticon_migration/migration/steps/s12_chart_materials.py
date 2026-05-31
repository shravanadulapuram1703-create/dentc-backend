"""
STEP 12 — chart_materials
Source: ChartMaterials.txt
Returns: { materialid_str: material_db_id }
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("ChartMaterials.txt")
    if not src.exists():
        print("  [s12] chart_materials: file not found, skipping")
        return {}

    cur = conn.cursor()
    material_map: dict[str, int] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        mid = (row.get("MATERIALID") or "").strip()
        if not mid:
            skipped += 1
            continue

        name = clean(row.get("MATNAME") or row.get("NAME")) or f"Material {mid}"
        pgid = (row.get("PGID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)

        cur.execute(
            """
            INSERT INTO chart_materials (tenant_id, legacy_id, name, pattern, color)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (tid, mid, name, clean(row.get("MATPATTERN")), clean(row.get("MATCOLOR"))),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM chart_materials WHERE legacy_id = %s", (mid,))
            row_id = cur.fetchone()
        if row_id:
            material_map[mid] = row_id[0]
        inserted += 1

    conn.commit()
    print(f"  [s12] chart_materials: {inserted} upserted, {skipped} skipped → map size {len(material_map)}")
    return material_map
