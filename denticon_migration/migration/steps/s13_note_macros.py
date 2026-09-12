"""
STEP 13 — note_macros
Source: ChartNotesMacros.txt (+ DEFINITIONS.txt for the category labels)
Returns: {}

PN-6 / NM-2: ``Macrocat`` is a Denticon DEFINITIONSID (``179``), and the
label lives in ``DEFINITIONS.txt`` under ``DEFGROUP = NOTESMACROS``
(``179 → DIAGNOSTIC``). Earlier runs stored the code, so every Category
dropdown rendered ``179``. The label is resolved here; an unmapped code is
stored as written (the API resolves it again on read).
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean

CATEGORY_GROUP = "NOTESMACROS"


def _category_labels() -> dict[tuple[str, str], str]:
    """``{(PGID, DEFINITIONSID): DESCR}`` for the NOTESMACROS group."""
    src = cfg.src("DEFINITIONS.txt")
    labels: dict[tuple[str, str], str] = {}
    if not src.exists():
        return labels
    for row in read_denticon_file(src, apply_limit=False):
        if (clean(row.get("DEFGROUP")) or "").upper() != CATEGORY_GROUP:
            continue
        def_id = (row.get("DEFINITIONSID") or "").strip()
        label = clean(row.get("DESCR") or row.get("DESCRIPTION"))
        if def_id and label:
            labels[((row.get("PGID") or "").strip(), def_id)] = label
    return labels


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("ChartNotesMacros.txt")
    if not src.exists():
        print("  [s13] note_macros: file not found, skipping")
        return {}

    labels = _category_labels()
    cur = conn.cursor()
    inserted = skipped = unlabelled = 0

    for row in read_denticon_file(src):
        mid = (row.get("MACROID") or "").strip()
        if not mid:
            skipped += 1
            continue

        name    = clean(row.get("MACRONAME")) or f"Macro {mid}"
        content = clean(row.get("MACROVALUE") or row.get("CONTENT")) or ""
        pgid    = (row.get("PGID") or "").strip()
        tid     = tenant_map.get(pgid, default_tid)

        code = clean(row.get("Macrocat") or row.get("MACROCAT"))
        category = labels.get((pgid, code)) if code else None
        if code and category is None:
            # Any PGID with that id (the export is single-practice in practice).
            category = next((v for (_, k), v in labels.items() if k == code), None)
        if code and category is None:
            unlabelled += 1
            category = code

        cur.execute(
            """
            INSERT INTO note_macros (tenant_id, legacy_id, name, content, category)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (tid, mid, name, content, category),
        )
        inserted += 1

    conn.commit()
    print(f"  [s13] note_macros: {inserted} inserted, {skipped} skipped, "
          f"{unlabelled} with a category code no NOTESMACROS definition names")
    return {}
