"""Patient-note DTOs (NOTE-DOC-1).

``PatientNoteCreate``/``PatientNoteUpdate`` are the generated shapes plus the new
``document_id``. ``PatientNoteRead`` adds an embedded ``document`` block so the
Notes list renders a view/download link straight from the note row — without it
every note of type *Documents (Upload)* would need a second
``GET /patient-documents/{id}`` just to learn the file's name and URL, which is
exactly the per-row fan-out the rest of this API removed.

The embedded ``file_url`` is resolved at read time (a signed GCS URL is
short-lived), so it is never persisted — see ``document_store.public_url``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, create_model

from app.db.models import PatientNote
from app.schemas.factory import build_schemas


class PatientNoteDocumentRef(BaseModel):
    """The attached document, denormalised onto the note.

    Deliberately a subset of ``PatientDocumentRead``: enough to render a link and
    a file chip (name, type, size), never the internal ``file_path``.
    """

    id: int
    file_name: str
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    document_type: Optional[str] = None
    description: Optional[str] = None
    # Authenticated proxy URL, or a short-lived signed GCS URL. Never a gs:// URI
    # and never the public /uploads path (NOTE-DOC-3).
    file_url: Optional[str] = None
    storage_backend: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


PatientNoteCreate, PatientNoteUpdate, _ = build_schemas(PatientNote, "PatientNote")

_patient_note_read_base = build_schemas(PatientNote, "PatientNoteFull")[2]
PatientNoteRead = create_model(
    "PatientNoteRead", __base__=_patient_note_read_base,
    # Populated by ``patient_note_service.enrich_patient_notes``; null for the
    # note types that carry no file.
    document=(Optional[PatientNoteDocumentRef], None),
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
)
