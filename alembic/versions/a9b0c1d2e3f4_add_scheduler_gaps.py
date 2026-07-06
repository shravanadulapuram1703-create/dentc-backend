"""add scheduler gaps (SCHED G3/G5/G6/G8)

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-07-05

Scheduler consolidated dev-report:
- G3: appointments cancellation metadata (note / reason / add_to_call_list).
- G5: appointments created_by / updated_by (pop-out attribution).
- G8: appointments posted_on (paired with is_posted).
- G6: appointment_procedures est_patient (patient portion per line).

G1/G2/G4 (feed enrichment) and the provider/status feed filters are read-side —
no schema change. Hand-written (scoped to the two scheduling tables).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("posted_on", sa.DateTime(), nullable=True))
    op.add_column("appointments", sa.Column("cancellation_note", sa.Text(), nullable=True))
    op.add_column("appointments", sa.Column("cancellation_reason", sa.String(length=50), nullable=True))
    op.add_column(
        "appointments",
        sa.Column("add_to_call_list", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("appointments", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("appointments", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(op.f("fk_appointments_created_by_users"),
                          "appointments", "users", ["created_by"], ["id"])
    op.create_foreign_key(op.f("fk_appointments_updated_by_users"),
                          "appointments", "users", ["updated_by"], ["id"])

    op.add_column("appointment_procedures", sa.Column("est_patient", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("appointment_procedures", "est_patient")
    op.drop_constraint(op.f("fk_appointments_updated_by_users"), "appointments", type_="foreignkey")
    op.drop_constraint(op.f("fk_appointments_created_by_users"), "appointments", type_="foreignkey")
    op.drop_column("appointments", "updated_by")
    op.drop_column("appointments", "created_by")
    op.drop_column("appointments", "add_to_call_list")
    op.drop_column("appointments", "cancellation_reason")
    op.drop_column("appointments", "cancellation_note")
    op.drop_column("appointments", "posted_on")
