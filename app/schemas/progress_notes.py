"""Progress-notes schemas (addresses the frontend progress-notes dev-report).

Single source of truth for the progress-note Create/Update/Read shapes (imported
by both the registry and the supplemental router), plus the sign/attachment/macro
DTOs. Customisations over the plain factory output:

- **PN-4** ``struck_off_at`` / ``struck_off_by`` on the read model.
- **PN-5** ``created_by_name`` / ``signed_by_name`` / ``struck_off_by_name``.
- **PN-7** computed ``is_locked``.
- **PN-3** ``attachment_count`` (+ attachment read shape).
- **PN-2** optional credential body for ``/sign``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, create_model

from app.db import models as m
from app.schemas.common import ORMModel
from app.schemas.factory import build_schemas
from app.core.datetimes import UtcDatetime

# Create/Update reuse the generic factory output (no field customisation needed).
ProgressNoteCreate, ProgressNoteUpdate, _ = build_schemas(m.ProgressNote, "ProgressNote")


class ProgressNoteRead(ORMModel):
    id: int
    patient_id: int
    office_id: Optional[int] = None
    legacy_id: Optional[str] = None
    note_date: Optional[date] = None
    notes: Optional[str] = None
    notes_html: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    region: Optional[str] = None
    signed_by: Optional[int] = None
    signed_at: Optional[UtcDatetime] = None
    # SIG-7: hash of the content as signed + the derived status
    # (signed | stale | unverifiable | unsigned).
    content_hash: Optional[str] = None
    signature_status: Optional[str] = None
    is_struck_off: bool
    struck_off_at: Optional[UtcDatetime] = None  # PN-4
    struck_off_by: Optional[int] = None  # PN-4
    # REST-10: first-class freehand drawing persistence.
    drawing_strokes: Optional[list] = None
    drawing_doc_id: Optional[int] = None
    is_deleted: bool
    created_by: Optional[int] = None
    created_at: UtcDatetime
    # PN-11: the "Modified" half of Created / Modified. ``updated_by`` is stamped
    # by the engine on a real change only (a no-op PATCH leaves both alone).
    updated_at: Optional[UtcDatetime] = None
    updated_by: Optional[int] = None
    # PN-5: resolved actor display names (None when unresolved).
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    signed_by_name: Optional[str] = None
    struck_off_by_name: Optional[str] = None
    # PN-7/PN-9: server-computed lock state — signed, or created before *today
    # in the note's office* (never the UTC date). ``locks_at`` is the instant
    # the text locks (office-local midnight after creation, as UTC); null once
    # the note is locked. ``timezone`` names the zone the day was judged in.
    is_locked: bool = False
    locks_at: Optional[UtcDatetime] = None
    timezone: Optional[str] = None
    # PN-3: number of (non-deleted) attachments on this note.
    attachment_count: int = 0


# ── PN-2: optional over-the-shoulder credentials on /sign ────────────────────
class ProgressNoteSignRequest(BaseModel):
    """Empty/omitted → sign as the authenticated caller. Supplying valid
    ``username``+``password`` signs as that (verified) user instead."""

    username: Optional[str] = None
    password: Optional[str] = None


class ProgressNoteSignResult(BaseModel):
    id: int
    signed_by: Optional[int] = None
    signed_by_name: Optional[str] = None
    signed_at: Optional[UtcDatetime] = None


# ── PN-3: per-note attachments ───────────────────────────────────────────────
ProgressNoteAttachmentRead = build_schemas(
    m.ProgressNoteAttachment, "ProgressNoteAttachment", read_exclude=("file_path",)
)[2]


# ── PN-6: macro category lookup ──────────────────────────────────────────────
class NoteMacroCategory(BaseModel):
    """PN-6: ``category`` is the stored value (the dropdown's filter key);
    ``label`` is what to render — the ``NOTESMACROS`` definition's description
    when the stored value is still a Denticon category *code*, else the value
    itself."""

    category: str
    label: str = Field(..., description="Human-readable label for the Category dropdown")
    macro_count: int = Field(..., description="Number of macros in this category")


# ── Notes Macros Setup (NM-3/5/6/7, pick_list_setup_backend_devreport §2) ────
_MacroCreate, _MacroUpdate, _MacroReadBase = build_schemas(m.NoteMacro, "NoteMacroBase")


class NoteMacroCreate(_MacroCreate):  # type: ignore[valid-type, misc]
    """NM-5: a macro with the same name in the same category is a 409
    ``duplicate_note_macro``; ``allow_duplicate`` is the dialog's override."""

    allow_duplicate: bool = False


class NoteMacroUpdate(_MacroUpdate):  # type: ignore[valid-type, misc]
    allow_duplicate: bool = False


# NM-3: created_by / updated_by resolved to display names.
# PN-6: category_label — the stored category resolved through the tenant's
# NOTESMACROS definitions when it is still a Denticon code (defensive: the
# normaliser rewrites stored codes to labels, but an unrepaired tenant or an
# older importer run must not render "179").
NoteMacroRead = create_model(
    "NoteMacroRead", __base__=_MacroReadBase,
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
    category_label=(Optional[str], None),
)


class NoteMacroMatch(BaseModel):
    id: int
    name: str
    category: str | None = None
    legacy_id: str | None = None


class NoteMacroAvailabilityResult(BaseModel):
    """NM-5 probe — ``taken`` is exactly the condition the save path 409s on."""

    name: str
    category: str | None = None
    taken: bool
    matches: list[NoteMacroMatch] = Field(default_factory=list)
    other_category_matches: list[NoteMacroMatch] = Field(default_factory=list)
    override_field: str = "allow_duplicate"


class NoteMacroLimits(BaseModel):
    name_max_length: int
    category_max_length: int
    duplicate_key_fields: list[str]
    override_field: str
