"""add Fee Schedule fields (FEE-2, FEE-3, FEE-4)

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-06-14

Resolves insurance backend dev-report fee-schedule gaps:
- FEE-2: fee_schedule_entries.amb_code (legacy "AMB Code").
- FEE-3: fee_schedule_assignments.office_group_id (legacy "Office Group").
- FEE-4: fee_schedules.effective_date + version + parent_schedule_id
  (schedule-level effective date / "New Effective Date" versioning).

(FEE-1 restore is application-layer only — no schema change.)

Additive; all columns nullable (version defaults to 1).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # FEE-4
    op.add_column("fee_schedules", sa.Column("effective_date", sa.Date(), nullable=True))
    op.add_column("fee_schedules", sa.Column("version", sa.Integer(), nullable=True, server_default="1"))
    op.add_column("fee_schedules", sa.Column("parent_schedule_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_fee_schedules_parent_schedule_id_fee_schedules",
        "fee_schedules", "fee_schedules", ["parent_schedule_id"], ["id"],
    )

    # FEE-2
    op.add_column("fee_schedule_entries", sa.Column("amb_code", sa.String(length=20), nullable=True))

    # FEE-3
    op.add_column("fee_schedule_assignments", sa.Column("office_group_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_fee_schedule_assignments_office_group_id_office_groups",
        "fee_schedule_assignments", "office_groups", ["office_group_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_fee_schedule_assignments_office_group_id_office_groups",
        "fee_schedule_assignments", type_="foreignkey",
    )
    op.drop_column("fee_schedule_assignments", "office_group_id")

    op.drop_column("fee_schedule_entries", "amb_code")

    op.drop_constraint(
        "fk_fee_schedules_parent_schedule_id_fee_schedules", "fee_schedules", type_="foreignkey"
    )
    op.drop_column("fee_schedules", "parent_schedule_id")
    op.drop_column("fee_schedules", "version")
    op.drop_column("fee_schedules", "effective_date")
