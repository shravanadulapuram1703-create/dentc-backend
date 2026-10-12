"""Office delete stamp (OFF-QA-15/16).

``offices.deleted_at`` / ``deleted_by`` tell a deleted office apart from one set
Inactive; ``deleted_operatory_ids`` remembers the chairs the delete switched off
so a reactivate restores exactly those. All nullable: no existing office was
deleted through the new path, so nothing to backfill.

Revision ID: 81e09d9576e9
Revises: 8d1ef924bb92
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "81e09d9576e9"
down_revision = "8d1ef924bb92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("offices") as b:
        b.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("deleted_by", sa.Integer(), nullable=True))
        b.add_column(sa.Column("deleted_operatory_ids", sa.JSON(), nullable=True))
        b.create_foreign_key("fk_offices_deleted_by_users", "users", ["deleted_by"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("offices") as b:
        b.drop_constraint("fk_offices_deleted_by_users", type_="foreignkey")
        b.drop_column("deleted_operatory_ids")
        b.drop_column("deleted_by")
        b.drop_column("deleted_at")
