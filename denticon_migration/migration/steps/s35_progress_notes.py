"""
STEP 35 — progress_notes
Source: ProgressNotes_Archive.txt
Returns: {}

PN-12: the raw ``NOTESHTML`` column is entity-escaped once *and* has every
``&`` replaced by the token ``~^^~`` (a delimiter-survival trick in the
export). Earlier runs stored it verbatim, so 30,322 of 35,286 notes rendered
as ``~^^~lt;p~^^~gt;…`` in the app. The decode + tidy + plain-text derivation
live once in ``app.services.progress_note_content`` (the same module the API
write path and ``scripts/repair_progress_note_content.py`` use), so the
importer, the repair and the app can never disagree on what a note says.
"""

import sys
from pathlib import Path

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import clean, parse_date, parse_bool

# The backend package lives two levels above ``denticon_migration/``; the
# content rules are pure stdlib so importing them pulls in no DB/session code.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from app.services.progress_note_content import repair_note_content  # noqa: E402


def _trunc(val: str | None, max_len: int) -> str | None:
    text = clean(val)
    if not text:
        return None
    return text[:max_len]


COLS = [
    "patient_id", "office_id", "legacy_id", "note_date",
    "notes", "notes_html", "tooth", "is_deleted",
]


def run(conn, maps: dict) -> dict:
    patient_map = maps["patient_map"]
    office_map  = maps["office_map"]

    src = cfg.src("ProgressNotes_Archive.txt")
    if not src.exists():
        print("  [s35] progress_notes: file not found, skipping")
        return {}

    skipped = decoded = 0
    buf = BulkBuffer(
        conn, "progress_notes", COLS,
        conflict="ON CONFLICT DO NOTHING",
        flush_every=20000, page_size=2000, label="progress_notes",
    )

    for row in read_denticon_file(src):
        note_id = (row.get("PROGNOTESID") or "").strip()
        rpid    = (row.get("PATID") or row.get("RPID") or "").strip()
        pat_id  = patient_map.get(rpid)

        if not pat_id:
            skipped += 1
            continue

        oid = (row.get("OID") or "").strip()

        # PN-12: decode the export encoding and derive the plain column from
        # the HTML — the plain export lost line breaks and wrote ``?`` for
        # ``&nbsp;``, the HTML export did not.
        notes, notes_html, changes = repair_note_content(
            clean(row.get("NOTES") or row.get("NOTE")),
            clean(row.get("NOTESHTML") or row.get("HTMLNOTES")),
            regenerate_text=True,
        )
        if "html_decoded" in changes:
            decoded += 1

        buf.add((
            pat_id,
            office_map.get(oid),
            note_id,
            parse_date(row.get("ACTDATE") or row.get("NOTEDATE") or ""),
            notes,
            notes_html,
            _trunc(row.get("TH") or row.get("TOOTH"), 255),
            parse_bool(row.get("ISDELETED", "False")),
        ))

    buf.flush()
    print(f"  [s35] progress_notes: {buf.inserted} inserted, {skipped} skipped, "
          f"{decoded} bodies decoded from the ~^^~ encoding")
    return {}
