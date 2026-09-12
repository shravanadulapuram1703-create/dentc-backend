"""Progress-note body normalisation (PN-12).

The Denticon importer stored ``progress_notes.notes_html`` with every ``&``
replaced by the token ``~^^~`` **on top of** the markup already being
entity-escaped once, so a typical migrated row reads::

    ~^^~lt;p~^^~gt;Lips: Normal~^^~lt;/p~^^~gt;

which is ``&lt;p&gt;Lips: Normal&lt;/p&gt;`` which is ``<p>Lips: Normal</p>``.
On the dev database 30,322 of 35,286 legacy rows (86 %) are encoded this way
and 13 carry the token in the plain ``notes`` column too. The plain column is
not a usable fallback either: it has a literal ``?`` wherever the source held a
non-breaking space, and roughly a fifth of the rows lost their line breaks.

This module is the **single** definition of the repair, shared by

* :mod:`scripts.repair_progress_note_content` — the one-off repair of the
  migrated rows,
* ``denticon_migration/migration/steps/s35_progress_notes.py`` — so a future
  migration run never re-introduces the token, and
* :class:`app.services.progress_notes_service.ProgressNoteCRUD` — which derives
  ``notes`` from ``notes_html`` when a client sends only the rich body, so the
  plain column ``search=`` matches against can never fall out of step again.

It is deliberately a *Python twin* of the frontend's ``noteContent.ts``: the
same token, the same single-level entity pass (so ``&amp;nbsp;`` becomes the
``&nbsp;`` entity, never a double-decode), the same tidy-ups. Nothing here
sanitises — the frontend's allow-list still runs on render, and the server
stores what the clinician wrote.
"""

from __future__ import annotations

import html as _html
import json
import re
from typing import Any

#: The importer's stand-in for ``&`` (survives a delimiter-based export).
LEGACY_AMP_TOKEN = "~^^~"

# One level of entity decoding — the *named* and *numeric* forms the corpus and
# the frontend decoder both know. A single regex pass cannot double-decode.
_ENTITY_RE = re.compile(r"&(lt|gt|amp|quot|#39|#34);")
_ENTITY_MAP = {"lt": "<", "gt": ">", "amp": "&", "quot": '"', "#34": '"', "#39": "'"}

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BLOCK_CLOSE_RE = re.compile(r"</(p|div|li|h[1-6]|tr)\s*>", re.IGNORECASE)
_BLOCK_OPEN_TAIL_RE = re.compile(r"<(ul|ol|table)\b[^>]*>", re.IGNORECASE)

# Legacy tidy-ups (regex-based on purpose: the corpus holds only <p>/<br>, and a
# DOM round-trip would re-serialise every app-written span).
_DOUBLE_P_OPEN_RE = re.compile(r"(<p>\s*)+<p>", re.IGNORECASE)
_DOUBLE_P_CLOSE_RE = re.compile(r"</p>(\s*</p>)+", re.IGNORECASE)
_INTER_BLOCK_WS_RE = re.compile(r"(</p>)\s+(<p\b)", re.IGNORECASE)
_EMPTY_P_RE = re.compile(r"<p>\s*</p>", re.IGNORECASE)
_TRAILING_EMPTY_P_RE = re.compile(r"(\s|<p>(?:\s|&nbsp;| )*</p>)+$", re.IGNORECASE)


def has_legacy_encoding(value: str | None) -> bool:
    """True when the value carries the importer's ``~^^~`` (= ``&``) encoding."""
    return bool(value) and LEGACY_AMP_TOKEN in value


def decode_legacy_markup(value: str) -> str:
    """Undo the import encoding: ``~^^~`` → ``&``, then **one** level of entity
    decoding so ``&lt;p&gt;`` becomes a real ``<p>`` while ``&amp;nbsp;``
    collapses to the ``&nbsp;`` entity. Values without the token pass through
    unchanged."""
    if not has_legacy_encoding(value):
        return value
    joined = value.replace(LEGACY_AMP_TOKEN, "&")
    return _ENTITY_RE.sub(lambda m: _ENTITY_MAP[m.group(1)], joined)


def tidy_note_html(value: str) -> str:
    """Remove the import artefacts without touching the content: doubly
    wrapped paragraphs (``<p><p>…</p></p>``), the ``\\r\\n`` the export left
    between paragraphs, paragraphs with nothing in them, and the trailing
    ``<p>&nbsp;</p>`` spacer the legacy editor appended to every save."""
    out = _DOUBLE_P_OPEN_RE.sub("<p>", value)
    out = _DOUBLE_P_CLOSE_RE.sub("</p>", out)
    out = _INTER_BLOCK_WS_RE.sub(r"\1\2", out)
    out = _EMPTY_P_RE.sub("", out)
    out = _TRAILING_EMPTY_P_RE.sub("", out)
    return out.strip()


def html_to_text(value: str | None) -> str:
    """Plain text for the ``notes`` column: ``<br>`` and block closers become
    newlines, tags are dropped, entities decoded, ``&nbsp;`` becomes a space.
    Mirrors the frontend's ``noteDisplayText`` so search and display agree."""
    if not value:
        return ""
    text = _BR_RE.sub("\n", value)
    text = _BLOCK_CLOSE_RE.sub("\n", text)
    text = _BLOCK_OPEN_TAIL_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = _html.unescape(text)
    text = text.replace(" ", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def drawing_payload(value: str | None) -> dict[str, Any] | None:
    """The Restorative freehand-drawing JSON some rows hold in ``notes_html``
    (``{"type": "rx-draw", "strokes": [...]}``), or ``None`` for real HTML."""
    if not value:
        return None
    body = value.strip()
    if not body.startswith("{"):
        return None
    try:
        parsed = json.loads(body)
    except ValueError:
        return None
    if isinstance(parsed, dict) and parsed.get("type") == "rx-draw":
        return parsed
    return None


def repair_note_content(
    notes: str | None, notes_html: str | None, *, regenerate_text: bool = False
) -> tuple[str | None, str | None, list[str]]:
    """Return ``(notes, notes_html, changes)`` with the PN-12 repairs applied.

    * ``notes_html`` carrying the token is decoded and tidied.
    * ``notes`` carrying the token is decoded and flattened to text.
    * When the HTML was repaired — or ``regenerate_text`` is set and the plain
      column disagrees with the HTML — ``notes`` is regenerated from the HTML.
      That is what fixes the ``?``-for-``&nbsp;`` mojibake and the collapsed
      line breaks: the plain export was lossy, the HTML export was not.
    * A drawing payload is left alone (moved by the repair script instead).

    ``changes`` names what happened, for the script's tally.
    """
    changes: list[str] = []
    new_notes, new_html = notes, notes_html

    if drawing_payload(notes_html) is not None:
        return notes, notes_html, changes

    if new_html is not None and has_legacy_encoding(new_html):
        new_html = tidy_note_html(decode_legacy_markup(new_html))
        changes.append("html_decoded")
    elif new_html is not None:
        tidied = tidy_note_html(new_html)
        if tidied != new_html:
            new_html = tidied
            changes.append("html_tidied")

    if new_notes is not None and has_legacy_encoding(new_notes):
        new_notes = html_to_text(decode_legacy_markup(new_notes))
        changes.append("notes_decoded")

    html_repaired = "html_decoded" in changes
    if new_html and (html_repaired or regenerate_text):
        derived = html_to_text(new_html)
        if derived != (new_notes or ""):
            new_notes = derived or None
            changes.append("notes_regenerated")

    return new_notes, new_html, changes


__all__ = [
    "LEGACY_AMP_TOKEN",
    "decode_legacy_markup",
    "drawing_payload",
    "has_legacy_encoding",
    "html_to_text",
    "repair_note_content",
    "tidy_note_html",
]
