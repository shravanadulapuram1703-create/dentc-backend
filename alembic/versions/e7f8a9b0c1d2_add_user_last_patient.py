"""add user last_patient_id (PDP-3)

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-06-24

Persistent default-patient selection (persistent-patient-selection dev-report):
- PDP-3: ``users.last_patient_id`` (nullable FK → patients.id, ON DELETE SET NULL)
  so a hard-deleted patient can't strand the user; soft-deleted/cross-tenant are
  filtered to null at read time (PDP-4, enforced in the service).

PDP-1/2/4 are endpoints/validation over this column — no further schema change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_patient_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_users_last_patient_id_patients"),
        "users", "patients", ["last_patient_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_users_last_patient_id_patients"), "users", type_="foreignkey")
    op.drop_column("users", "last_patient_id")
