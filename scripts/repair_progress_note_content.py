"""PN-12: repair the legacy-imported progress-note bodies.

The Denticon importer stored ``notes_html`` with every ``&`` replaced by the
token ``~^^~`` on top of the markup already being entity-escaped once, so the
Progress Notes grid showed ``~^^~lt;p~^^~gt;…`` for practically every migrated
note. The plain ``notes`` column is not a fallback: it holds a ``?`` where the
source had a non-breaking space and a fifth of the rows lost their line breaks.

What one run does (rules live in :mod:`app.services.progress_note_content`,
shared with the importer and the write path so they cannot drift):

1. ``notes_html`` carrying the token: ``~^^~`` → ``&``, **one** level of entity
   decoding, then the import artefacts are removed (``<p><p>…</p></p>``, the
   ``\\r\\n`` between paragraphs, empty and trailing ``<p>&nbsp;</p>``).
2. ``notes`` carrying the token: same decode, flattened to text.
3. ``notes`` regenerated from the repaired HTML for every legacy row whose
   plain column disagrees with it (block tags → newline, entities decoded,
   ``&nbsp;`` → space) — this is what ``search=`` and server reports match on.
4. The Restorative freehand rows whose ``notes_html`` is stroke JSON
   (``{"type":"rx-draw",…}``) move to ``drawing_strokes`` (REST-10's column),
   ``notes_html`` cleared — unless ``--keep-drawings``.
5. A repaired row that carries a signature ``content_hash`` is re-hashed: the
   signer saw the *decoded* body (the frontend decoded on render), so the
   repaired content is what the signature attests to.

``updated_at`` is left untouched on purpose — a data repair is not a clinical
edit, and "Modified today" on 30,000 notes would be a lie.

Dry run by default. ``--apply`` writes; before the first write every changed
row's original ``notes`` / ``notes_html`` / ``drawing_strokes`` / ``content_hash``
is appended to a JSONL backup (``--backup PATH``) so the run can be reversed
with ``--restore PATH``.

    python -m scripts.repair_progress_note_content                 # dry run + tallies
    python -m scripts.repair_progress_note_content --apply
    python -m scripts.repair_progress_note_content --restore backups/progress_note_content_<ts>.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, bindparam, select, update

from app.db.models import ProgressNote
from app.db.session import SessionLocal
from app.services import signature_service as sig_svc
from app.services.progress_note_content import (
    LEGACY_AMP_TOKEN,
    drawing_payload,
    repair_note_content,
)

BATCH = 500  # 2,000 wide-text rows per executemany tripped the 30 s statement timeout

# Executed on the Core connection as a plain executemany: the ORM session's
# bulk-UPDATE path wants primary keys under the column name and would try to
# synchronise an identity map nothing was loaded into.
_UPDATE = (
    update(ProgressNote.__table__)
    .where(ProgressNote.id == bindparam("_id"))
    .values(
        notes=bindparam("notes"),
        notes_html=bindparam("notes_html"),
        # none_as_null: a Python None must land as SQL NULL, not the JSON
        # literal ``null`` — the restorative chart selects drawings with
        # ``drawing_strokes IS NOT NULL`` and would list every note otherwise.
        drawing_strokes=bindparam("drawing_strokes", type_=JSON(none_as_null=True)),
        content_hash=bindparam("content_hash"),
        # Explicit so the ORM ``onupdate`` does not stamp the repair as an edit.
        updated_at=bindparam("updated_at"),
    )
)


def _candidates(db, after_id: int, limit: int = BATCH):  # noqa: ANN001, ANN202
    return db.execute(
        select(ProgressNote)
        .where(
            ProgressNote.id > after_id,
            (ProgressNote.notes_html.is_not(None)) | (ProgressNote.notes.like(f"%{LEGACY_AMP_TOKEN}%")),
        )
        .order_by(ProgressNote.id)
        .limit(limit)
    ).scalars().all()


def _plan_row(note: ProgressNote, *, keep_drawings: bool) -> tuple[dict | None, list[str]]:
    """The row's new column values (or ``None`` when nothing changes) + tags."""
    drawing = drawing_payload(note.notes_html)
    if drawing is not None:
        if keep_drawings or note.drawing_strokes is not None:
            return None, ["drawing_kept"]
        strokes = drawing.get("strokes")
        if not isinstance(strokes, list):
            return None, ["drawing_unparseable"]
        return (
            {
                "notes": note.notes,
                "notes_html": None,
                "drawing_strokes": strokes,
                "content_hash": note.content_hash,
            },
            ["drawing_moved"],
        )

    new_notes, new_html, changes = repair_note_content(
        note.notes, note.notes_html, regenerate_text=note.legacy_id is not None
    )
    if not changes:
        return None, []
    content_hash = note.content_hash
    if content_hash is not None:
        probe = ProgressNote(
            notes=new_notes, notes_html=new_html, tooth=note.tooth, surface=note.surface,
            region=note.region, note_date=note.note_date, drawing_strokes=note.drawing_strokes,
        )
        content_hash = sig_svc.progress_note_content_hash(probe)
        changes.append("content_hash_restamped")
    return (
        {
            "notes": new_notes,
            "notes_html": new_html,
            "drawing_strokes": note.drawing_strokes,
            "content_hash": content_hash,
        },
        changes,
    )


def run(*, apply: bool, backup: Path, keep_drawings: bool, batch: int = BATCH) -> None:
    db = SessionLocal()
    stats: Counter = Counter()
    samples: dict[str, int] = {}
    backup_fh = None
    try:
        after = 0
        while True:
            rows = _candidates(db, after, batch)
            if not rows:
                break
            after = rows[-1].id
            pending: list[dict] = []
            for note in rows:
                stats["scanned"] += 1
                values, tags = _plan_row(note, keep_drawings=keep_drawings)
                for tag in tags:
                    stats[tag] += 1
                    samples.setdefault(tag, note.id)
                if values is None:
                    continue
                stats["rows_changed"] += 1
                if apply:
                    if backup_fh is None:
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        backup_fh = backup.open("a", encoding="utf-8")
                    backup_fh.write(json.dumps({
                        "id": note.id,
                        "notes": note.notes,
                        "notes_html": note.notes_html,
                        "drawing_strokes": note.drawing_strokes,
                        "content_hash": note.content_hash,
                    }, ensure_ascii=False) + "\n")
                    pending.append({"_id": note.id, "updated_at": note.updated_at, **values})
            if apply and pending:
                backup_fh.flush()
                db.connection().execute(_UPDATE, pending)
                db.commit()
            db.expunge_all()
    finally:
        if backup_fh is not None:
            backup_fh.close()
        db.close()

    mode = "APPLIED" if apply else "DRY RUN"
    print(f"[{mode}] progress_notes content repair")
    for key in sorted(stats):
        sample = f"   e.g. id {samples[key]}" if key in samples else ""
        print(f"  {key:>24}: {stats[key]:>7}{sample}")
    if apply and stats["rows_changed"]:
        print(f"  backup: {backup}")
    if not apply:
        print("  (dry run - re-run with --apply to write)")


def restore(backup: Path) -> None:
    """Put the backed-up columns back, row by row (the inverse of ``--apply``)."""
    db = SessionLocal()
    restored = 0
    try:
        rows: list[dict] = []
        with backup.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                rows.append({
                    "_id": rec["id"], "notes": rec["notes"], "notes_html": rec["notes_html"],
                    "drawing_strokes": rec["drawing_strokes"], "content_hash": rec["content_hash"],
                    "updated_at": None,
                })
        for i in range(0, len(rows), BATCH):
            chunk = rows[i : i + BATCH]
            # Keep whatever updated_at the row has now.
            current = dict(
                db.execute(
                    select(ProgressNote.id, ProgressNote.updated_at).where(
                        ProgressNote.id.in_([r["_id"] for r in chunk])
                    )
                ).all()
            )
            for r in chunk:
                r["updated_at"] = current.get(r["_id"])
            db.connection().execute(_UPDATE, chunk)
            db.commit()
            restored += len(chunk)
    finally:
        db.close()
    print(f"[RESTORED] {restored} rows from {backup}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--keep-drawings", action="store_true",
                        help="leave rx-draw JSON rows in notes_html instead of moving them to drawing_strokes")
    parser.add_argument("--backup", type=Path, default=None,
                        help="JSONL file to write the originals to on --apply "
                             "(default: backups/progress_note_content_<timestamp>.jsonl)")
    parser.add_argument("--batch-size", type=int, default=BATCH,
                        help=f"rows per UPDATE round-trip (default {BATCH})")
    parser.add_argument("--restore", type=Path, default=None,
                        help="reverse a previous --apply from its backup file")
    args = parser.parse_args(argv)

    if args.restore is not None:
        restore(args.restore)
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = args.backup or Path("backups") / f"progress_note_content_{stamp}.jsonl"
    run(apply=args.apply, backup=backup, keep_drawings=args.keep_drawings, batch=args.batch_size)


if __name__ == "__main__":
    main(sys.argv[1:])
