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

from pydantic import BaseModel, Field

from app.db import models as m
from app.schemas.common import ORMModel
from app.schemas.factory import build_schemas

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
    signed_at: Optional[datetime] = None
    is_struck_off: bool
    struck_off_at: Optional[datetime] = None  # PN-4
    struck_off_by: Optional[int] = None  # PN-4
    # REST-10: first-class freehand drawing persistence.
    drawing_strokes: Optional[list] = None
    drawing_doc_id: Optional[int] = None
    is_deleted: bool
    created_by: Optional[int] = None
    created_at: datetime
    # PN-5: resolved actor display names (None when unresolved).
    created_by_name: Optional[str] = None
    signed_by_name: Optional[str] = None
    struck_off_by_name: Optional[str] = None
    # PN-7: server-computed lock state (signed or created before today).
    is_locked: bool = False
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
    signed_at: Optional[datetime] = None


# ── PN-3: per-note attachments ───────────────────────────────────────────────
ProgressNoteAttachmentRead = build_schemas(
    m.ProgressNoteAttachment, "ProgressNoteAttachment", read_exclude=("file_path",)
)[2]


# ── PN-6: macro category lookup ──────────────────────────────────────────────
class NoteMacroCategory(BaseModel):
    category: str
    macro_count: int = Field(..., description="Number of macros in this category")
