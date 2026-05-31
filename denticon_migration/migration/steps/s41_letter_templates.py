"""
STEP 41 — letter_templates
Source: LETTERS.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, parse_bool


def _trunc(val: str | None, max_len: int) -> str | None:
    text = clean(val)
    if not text:
        return None
    return text[:max_len]


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("LETTERS.txt")
    if not src.exists():
        print("  [s41] letter_templates: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        letter_id = (row.get("LETTERID") or "").strip()
        pgid = (row.get("PGID") or "").strip()

        # LETTERS.txt has many malformed rows from embedded commas in HTML bodies
        if not letter_id.isdigit() or pgid not in tenant_map:
            skipped += 1
            continue

        tid  = tenant_map.get(pgid, default_tid)
        name = clean(row.get("NAME")) or f"Letter {letter_id}"

        active_val = row.get("Active") or row.get("ACTIVE") or "Y"
        is_active  = parse_bool(active_val)

        cur.execute(
            """
            INSERT INTO letter_templates
                (tenant_id, legacy_id, name, letter_type, channel, title, body_html, is_active)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (legacy_id) DO UPDATE SET
                name      = EXCLUDED.name,
                title     = EXCLUDED.title,
                body_html = EXCLUDED.body_html,
                is_active = EXCLUDED.is_active
            """,
            (
                tid, letter_id, name,
                _trunc(row.get("TYPE"), 10),
                _trunc(row.get("LType") or row.get("LTYPE"), 20),
                _trunc(row.get("TITLE"), 255),
                clean(row.get("BODY")),
                is_active,
            ),
        )
        inserted += 1

    conn.commit()
    print(f"  [s41] letter_templates: {inserted} inserted, {skipped} skipped")
    return {}
