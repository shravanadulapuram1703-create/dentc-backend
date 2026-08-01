"""add patients.updated_by (PE-4)

Last-editor attribution ("Modified By") on the patient record, mirroring the
existing created_by. CRUDBase.update stamps it on every PATCH; PatientRead
resolves created_by/updated_by to display names via enrich_patient_office.

Revision ID: c0d1e2f3a4b6
Revises: a8b9c0d1e2f3
Create Date: 2026-07-26

Additive.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0d1e2f3a4b6"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_patients_updated_by_users", "patients", "users", ["updated_by"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_patients_updated_by_users", "patients", type_="foreignkey")
    op.drop_column("patients", "updated_by")
