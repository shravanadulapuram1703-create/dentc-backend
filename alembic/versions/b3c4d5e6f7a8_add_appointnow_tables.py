"""Add AppointNow online-booking tables.

Backs the external booking module (docs/book/appointnow_backend_devreport.md):

- ``appointnow_reasons``  per-office booking-reason catalog (AN-1 / AN-3).
- ``booking_requests``    the public intake queue (AN-3..5, AN-8, AN-13) with a
  UUIDv7 string PK (time-sortable inbox paging) and a soft-hold column.

Indexes (AN-13): ``(tenant_id, office_id, status, created_at)`` for the inbox/badge
and ``(tenant_id, office_id, slot_date)`` for availability + expiry sweeps.

Revision ID: b3c4d5e6f7a8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "appointnow_reasons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("requires_provider", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name="fk_appointnow_reasons_tenant_id_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["office_id"], ["offices.id"],
            name="fk_appointnow_reasons_office_id_offices",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"],
            name="fk_appointnow_reasons_updated_by_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_appointnow_reasons"),
        sa.UniqueConstraint("office_id", "reason_code", name="uq_appointnow_reasons_office_code"),
    )
    op.create_index(
        "ix_appointnow_reasons_tenant_id", "appointnow_reasons", ["tenant_id"]
    )
    op.create_index(
        "ix_appointnow_reasons_office_id", "appointnow_reasons", ["office_id"]
    )

    op.create_table(
        "booking_requests",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("reason_id", sa.String(length=50), nullable=True),
        sa.Column("reason_label", sa.String(length=200), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("provider_id", sa.String(length=50), nullable=True),
        sa.Column("provider_name", sa.String(length=255), nullable=True),
        sa.Column("slot_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("is_new_patient", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("hold_expires_at", sa.DateTime(), nullable=True),
        sa.Column("appointment_id", sa.String(length=50), nullable=True),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
        sa.Column("actioned_by", sa.Integer(), nullable=True),
        sa.Column("actioned_at", sa.DateTime(), nullable=True),
        sa.Column("source_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name="fk_booking_requests_tenant_id_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["office_id"], ["offices.id"],
            name="fk_booking_requests_office_id_offices",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["providers.id"],
            name="fk_booking_requests_provider_id_providers",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.id"],
            name="fk_booking_requests_appointment_id_appointments",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"],
            name="fk_booking_requests_patient_id_patients",
        ),
        sa.ForeignKeyConstraint(
            ["actioned_by"], ["users.id"],
            name="fk_booking_requests_actioned_by_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_booking_requests"),
    )
    op.create_index("ix_booking_requests_tenant_id", "booking_requests", ["tenant_id"])
    op.create_index("ix_booking_requests_office_id", "booking_requests", ["office_id"])
    op.create_index(
        "ix_booking_requests_office_status",
        "booking_requests",
        ["tenant_id", "office_id", "status", "created_at"],
    )
    op.create_index(
        "ix_booking_requests_office_slot",
        "booking_requests",
        ["tenant_id", "office_id", "slot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_booking_requests_office_slot", table_name="booking_requests")
    op.drop_index("ix_booking_requests_office_status", table_name="booking_requests")
    op.drop_index("ix_booking_requests_office_id", table_name="booking_requests")
    op.drop_index("ix_booking_requests_tenant_id", table_name="booking_requests")
    op.drop_table("booking_requests")
    op.drop_index("ix_appointnow_reasons_office_id", table_name="appointnow_reasons")
    op.drop_index("ix_appointnow_reasons_tenant_id", table_name="appointnow_reasons")
    op.drop_table("appointnow_reasons")
