"""Patient document owning module (IMG-DOC-1/3/5).

``patient_documents.context`` records which screen owns a row (Documents,
Imaging, Notes, Patient Photo, Letters, Consent, Progress Notes, Restorative,
Treatment Plans). Eight writers share the table and nothing said which one a
row belonged to, so the Imaging gallery inferred it and showed insurance cards
among the radiographs.

The backfill runs **inside** this revision, not in a follow-up script: the
moment ``?context=imaging`` is deployed, a NULL/default owner on a pre-existing
radiograph makes it vanish from the gallery, and that window is the bug. The
rule is ``document_vocabulary.backfill_case`` — the same expression
``scripts/backfill_document_context.py`` counts in its dry run.

Also ``updated_at`` / ``updated_by`` for the IMG-DOC-5 PATCH, and an index on
``(patient_id, context)`` for the per-screen list.

Revision ID: 03bbb54c0b12
Revises: 81e09d9576e9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "03bbb54c0b12"
down_revision = "81e09d9576e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("patient_documents") as b:
        b.add_column(sa.Column("context", sa.String(30), nullable=True))
        b.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("updated_by", sa.Integer(), nullable=True))
        b.create_foreign_key(
            "fk_patient_documents_updated_by_users", "users", ["updated_by"], ["id"]
        )

    from app.db.models import PatientDocument  # noqa: PLC0415
    from app.services.document_vocabulary import backfill_case  # noqa: PLC0415

    bind = op.get_bind()
    table = PatientDocument.__table__
    bind.execute(
        sa.update(table).where(table.c.context.is_(None)).values(context=backfill_case())
    )

    with op.batch_alter_table("patient_documents") as b:
        b.alter_column(
            "context", existing_type=sa.String(30), nullable=False,
            server_default="documents",
        )
    op.create_index(
        "ix_patient_documents_patient_context", "patient_documents", ["patient_id", "context"]
    )


def downgrade() -> None:
    op.drop_index("ix_patient_documents_patient_context", table_name="patient_documents")
    with op.batch_alter_table("patient_documents") as b:
        b.drop_constraint("fk_patient_documents_updated_by_users", type_="foreignkey")
        b.drop_column("updated_by")
        b.drop_column("updated_at")
        b.drop_column("context")
