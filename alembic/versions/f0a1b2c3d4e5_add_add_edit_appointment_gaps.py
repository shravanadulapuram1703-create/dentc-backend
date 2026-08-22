"""Add/Edit Appointment gaps (APPT-PROC-1..3, APPT-5, APPT-7).

Backs ``docs/scheduler/add_edit_appointment_backend_devreport.md``:

- APPT-PROC-1 ``appointment_procedures.duration_minutes`` — per-line chair time,
  so **Calc Time** survives a reload instead of resetting to 0.
- APPT-PROC-2 ``appointment_procedures.provider_units`` — the legacy "P. Units"
  column (always 1 until now because there was nowhere to put it).
- APPT-PROC-3 ``appointment_procedures.bill_to`` — patient vs insurance billing
  intent per line.
- APPT-5     ``appointments.lab_dds`` — the LAB section's DDS input; the read
  model already had lab_cost/sent/due/received but not who the case is for.
- APPT-7     ``campaigns`` — the catalog behind the appointment's Campaign ID box
  (which was free text with nothing to pick from). ``appointments.campaign_id``
  stays a string, so this is additive on the wire.

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-08-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── APPT-PROC-1/2/3: per-line appointment procedure columns ──────────────
    op.add_column(
        "appointment_procedures",
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
    )
    # server_default so the existing ~N rows land on 1 (the legacy implicit value)
    # rather than NULL; the column stays NOT NULL for the ORM's default=1.
    op.add_column(
        "appointment_procedures",
        sa.Column("provider_units", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "appointment_procedures",
        sa.Column("bill_to", sa.String(length=1), nullable=True),
    )

    # ── APPT-5: LAB → DDS ────────────────────────────────────────────────────
    op.add_column("appointments", sa.Column("lab_dds", sa.String(length=100), nullable=True))

    # ── APPT-7: campaign catalog ─────────────────────────────────────────────
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("office_id", sa.Integer(), sa.ForeignKey("offices.id"), nullable=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(length=50), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_campaigns_tenant_code"),
    )
    op.create_index("ix_campaigns_tenant_id", "campaigns", ["tenant_id"])
    op.create_index("ix_campaigns_code", "campaigns", ["code"])


def downgrade() -> None:
    op.drop_index("ix_campaigns_code", table_name="campaigns")
    op.drop_index("ix_campaigns_tenant_id", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_column("appointments", "lab_dds")
    op.drop_column("appointment_procedures", "bill_to")
    op.drop_column("appointment_procedures", "provider_units")
    op.drop_column("appointment_procedures", "duration_minutes")
