"""Patient-note business logic — the note ↔ document link (NOTE-DOC-1).

A patient note of type *Documents (Upload)* / *Document (Scan)* is about a file.
The file itself is a first-class ``patient_documents`` row (uploaded to GCS under
``patient-documents/{tenant}/{patient}/{uuid}``); the note just points at it.

Two pieces live here:

* :class:`PatientNoteCRUD` — validates ``document_id`` on every write. A note may
  only reference a document in the **same tenant** and belonging to the **same
  patient**, because a note is displayed inside one patient's chart and a
  mis-pointed id would surface another patient's file there. That check has to be
  on the CRUD class rather than in the schema: it needs the database.
* :func:`enrich_patient_notes` — resolves the linked document (and the audit
  actor names) onto the read model in one batched query, so the Notes list can
  render a view/download link without a per-row fetch.

Deletion semantics (the open question in the dev report): deleting a note does
**not** delete the document. ``DELETE /patient-notes/{id}`` is a soft delete, the
document is a patient-level record that also shows in ``/patient-documents`` and
may be referenced by a consent, and un-deleting a note whose file had been
destroyed would be worse than an orphan. Removing the file is an explicit
``DELETE /patient-documents/{id}``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.crud.base import CRUDBase
from app.db.models import PatientDocument, PatientNote
from app.services import document_store


def _resolve_document(
    db: Session, tenant_id: int | None, document_id: int, patient_id: int | None
) -> PatientDocument:
    """The document a note is allowed to point at, or a readable 422/404."""
    doc = db.execute(
        select(PatientDocument).where(PatientDocument.id == document_id)
    ).scalar_one_or_none()
    if doc is None or doc.is_deleted or (tenant_id is not None and doc.tenant_id != tenant_id):
        raise NotFoundError(f"Document '{document_id}' was not found")
    if patient_id is not None and doc.patient_id != patient_id:
        raise ValidationError(
            "document_id belongs to a different patient",
            code="document_patient_mismatch",
            details={"document_patient_id": doc.patient_id, "note_patient_id": patient_id},
        )
    return doc


class PatientNoteCRUD(CRUDBase[PatientNote]):
    """Generic CRUD plus the ``document_id`` integrity check (NOTE-DOC-1)."""

    def create(self, db, data, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        document_id = data.get("document_id")
        if document_id is not None:
            _resolve_document(db, tenant_id, int(document_id), data.get("patient_id"))
        return super().create(db, data, tenant_id=tenant_id, created_by=created_by)

    def update(self, db, obj_id, data, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        if "document_id" in data and data["document_id"] is not None:
            # PATCH may carry document_id alone, so the patient to check against
            # is the payload's if present, else the note's stored one.
            note = self.get(db, obj_id, tenant_id=tenant_id)
            patient_id = data.get("patient_id", note.patient_id)
            _resolve_document(db, tenant_id, int(data["document_id"]), patient_id)
        return super().update(db, obj_id, data, tenant_id=tenant_id, updated_by=updated_by)


def enrich_patient_notes(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    """Attach the linked document + audit-actor names to ``PatientNoteRead``.

    Batched by distinct id, so the cost is independent of page size. ``file_url``
    is computed per row through ``document_store.public_url`` — a signed GCS URL
    expires, so it must be minted on read rather than read from the column.
    """
    from app.services.user_admin_service import resolve_user_names

    rows = list(items)
    doc_ids = {r.document_id for r in rows if getattr(r, "document_id", None) is not None}
    docs: dict[int, PatientDocument] = {}
    if doc_ids:
        docs = {
            d.id: d
            for d in db.execute(
                select(PatientDocument).where(
                    PatientDocument.id.in_(doc_ids),
                    PatientDocument.is_deleted.is_(False),
                )
            ).scalars()
        }

    actor_ids = {r.created_by for r in rows if getattr(r, "created_by", None) is not None}
    actor_ids |= {r.updated_by for r in rows if getattr(r, "updated_by", None) is not None}
    names = resolve_user_names(db, actor_ids)

    for r in rows:
        doc = docs.get(getattr(r, "document_id", None))
        r.document = (
            {
                "id": doc.id,
                "file_name": doc.file_name,
                "content_type": doc.content_type,
                "file_size": doc.file_size,
                "document_type": doc.document_type,
                "description": doc.description,
                "file_url": document_store.public_url(doc),
                "storage_backend": doc.storage_backend,
                "created_at": doc.created_at,
            }
            if doc is not None
            else None
        )
        r.created_by_name = names.get(r.created_by) if r.created_by is not None else None
        r.updated_by_name = names.get(r.updated_by) if r.updated_by is not None else None
