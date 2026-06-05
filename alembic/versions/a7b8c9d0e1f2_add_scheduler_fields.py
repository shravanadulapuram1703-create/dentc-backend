"""add Scheduler-module fields (operatory provider, patient resp/type, definition color)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-02

Resolves Scheduler dev-report gaps:
- #1  operatories.provider_id  (default provider per operatory column)
- #8  patients.responsible_party_id, patients.patient_type
- #4  definitions.color, definitions.sort_order (backend-driven status colors/order)

All additive nullable columns; no data backfill required.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operatories", sa.Column("provider_id", sa.String(length=50), nullable=True))
    op.create_foreign_key("fk_operatories_provider_id_providers", "operatories", "providers", ["provider_id"], ["id"])

    op.add_column("patients", sa.Column("responsible_party_id", sa.String(length=50), nullable=True))
    op.add_column("patients", sa.Column("patient_type", sa.String(length=50), nullable=True))

    op.add_column("definitions", sa.Column("color", sa.String(length=20), nullable=True))
    op.add_column("definitions", sa.Column("sort_order", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("definitions", "sort_order")
    op.drop_column("definitions", "color")
    op.drop_column("patients", "patient_type")
    op.drop_column("patients", "responsible_party_id")
    op.drop_constraint("fk_operatories_provider_id_providers", "operatories", type_="foreignkey")
    op.drop_column("operatories", "provider_id")
