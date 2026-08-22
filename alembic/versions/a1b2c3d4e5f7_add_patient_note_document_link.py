"""Patient Notes document upload/download (NOTE-DOC-1).

Backs ``docs/patient_note_documents_backend_devreport.md``:

- NOTE-DOC-1 ``patient_notes.document_id`` — the file a "Documents (Upload)" /
  "Document (Scan)" note is about. Without it a file could be uploaded but
  nothing recorded that it belonged to a note, so re-opening the note could not
  find it. FK to ``patient_documents.id``, nullable (every other note type
  carries no file), indexed (the Notes list resolves the link per row).

The remaining gaps in that report are code/config, not schema: NOTE-DOC-2 is
``GCS_BUCKET_DOCUMENTS``, NOTE-DOC-3 removes the public ``/uploads`` mount,
NOTE-DOC-5 adds server-side validation, NOTE-DOC-4 seeds a ``document_type``
definitions group via ``scripts/seed_account_definitions.py``.

Revision ID: a1b2c3d4e5f7
Revises: f0a1b2c3d4e5
Create Date: 2026-08-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient_notes", sa.Column("document_id", sa.Integer(), nullable=True))
    op.create_index("ix_patient_notes_document_id", "patient_notes", ["document_id"])
    op.create_foreign_key(
        "fk_patient_notes_document_id",
        "patient_notes", "patient_documents",
        ["document_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_patient_notes_document_id", "patient_notes", type_="foreignkey")
    op.drop_index("ix_patient_notes_document_id", table_name="patient_notes")
    op.drop_column("patient_notes", "document_id")
