"""Lab Tracking (M12) gaps

Revision ID: 587baa6a0ba7
Revises: 9de6ac649cba
Create Date: 2026-09-11

Frontend report: ``docs/lab-tracking/lab_tracking_backend_devreport.md``
(LAB-1..11).

``labs`` (LAB-1)
    the dental-lab vendor catalog. A lab case is an appointment with lab
    fields; nothing recorded *which* lab it went to.

``appointments``
    lab_vendor_id (FK -> labs, LAB-1) and lab_short_notice (LAB-1). Both
    additive; ``lab_short_notice`` is NOT NULL DEFAULT false so migrated rows
    read as "not a rush" rather than NULL.

Indexes: ``appointments(office_id, has_lab)`` so the office-wide lab view
(LAB-5) is an index scan over the lab cases rather than a scan of the
appointment book; ``appointments(lab_vendor_id)`` for the vendor roll-up.

No legacy backfill: the Denticon ``Appointments`` export carries ISLAB /
LABCOST / LABSENTON / LABDUEON / LABRECVDON (all migrated by ``s26``) and no
lab-vendor or short-notice column, so there is nothing to recover.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "587baa6a0ba7"
down_revision = "9de6ac649cba"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "labs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("office_id", sa.Integer(), sa.ForeignKey("offices.id"), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("fax", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=True),
        sa.Column("zip", sa.String(length=20), nullable=True),
        sa.Column("default_turnaround_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_labs_tenant_id", "labs", ["tenant_id"])
    op.create_index("ix_labs_name", "labs", ["name"])

    op.add_column(
        "appointments",
        sa.Column("lab_vendor_id", sa.Integer(), sa.ForeignKey("labs.id"), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("lab_short_notice", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_appointments_lab_vendor_id", "appointments", ["lab_vendor_id"])
    # LAB-2/5: the lab views always filter has_lab = true (a few % of the book);
    # office_id first because every office-wide read scopes on it.
    op.create_index("ix_appointments_office_has_lab", "appointments", ["office_id", "has_lab"])


def downgrade() -> None:
    op.drop_index("ix_appointments_office_has_lab", table_name="appointments")
    op.drop_index("ix_appointments_lab_vendor_id", table_name="appointments")
    op.drop_column("appointments", "lab_short_notice")
    op.drop_column("appointments", "lab_vendor_id")
    op.drop_index("ix_labs_name", table_name="labs")
    op.drop_index("ix_labs_tenant_id", table_name="labs")
    op.drop_table("labs")
