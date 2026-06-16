"""add users.updated_by (Audit Information panel)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-09

Resolves docs/users/users_missing_fields_devreport.md gap #8: the Users detail
panel needs "Last Updated By". ``updated_at`` already exists (TimestampMixin);
this adds the matching ``updated_by`` actor column (FK -> users.id).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_updated_by_users", "users", "users", ["updated_by"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_updated_by_users", "users", type_="foreignkey")
    op.drop_column("users", "updated_by")
