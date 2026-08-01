"""add Patient-Overview backend gaps (PO-2b/10/11)

- responsible_parties: legacy_id (PO-2b, resolve migrated guarantor id) + home_office_id (PO-11)
- patients: photo_document_id (PO-10, profile photo)

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-07-26

Additive.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("responsible_parties", sa.Column("legacy_id", sa.String(length=20), nullable=True))
    op.create_index("ix_responsible_parties_legacy_id", "responsible_parties", ["legacy_id"])
    op.add_column("responsible_parties", sa.Column("home_office_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_responsible_parties_home_office_id_offices",
        "responsible_parties", "offices", ["home_office_id"], ["id"],
    )
    op.add_column("patients", sa.Column("photo_document_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_patients_photo_document_id_patient_documents",
        "patients", "patient_documents", ["photo_document_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_patients_photo_document_id_patient_documents", "patients", type_="foreignkey")
    op.drop_column("patients", "photo_document_id")
    op.drop_constraint("fk_responsible_parties_home_office_id_offices", "responsible_parties", type_="foreignkey")
    op.drop_column("responsible_parties", "home_office_id")
    op.drop_index("ix_responsible_parties_legacy_id", table_name="responsible_parties")
    op.drop_column("responsible_parties", "legacy_id")
