"""add Security/Users structural fields (short_id, report-access provider, customs, signature, image)

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-06-09

Resolves docs/users/users_missing_fields_devreport.md (structural gaps 1-5):
- ALTER users: short_id (#1, unique per tenant), report_access_provider_id (#2,
  FK -> providers.id), custom_1/custom_2 (#3), signature_data (#4), image_url (#5).

Additive only; mirrors the model in app/db/models/identity.py.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("short_id", sa.String(length=6), nullable=True))
    op.add_column("users", sa.Column("report_access_provider_id", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("custom_1", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("custom_2", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("signature_data", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.create_index("ix_users_short_id", "users", ["short_id"])
    op.create_unique_constraint("uq_users_tenant_short_id", "users", ["tenant_id", "short_id"])
    op.create_foreign_key(
        "fk_users_report_access_provider_id_providers",
        "users", "providers", ["report_access_provider_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_report_access_provider_id_providers", "users", type_="foreignkey")
    op.drop_constraint("uq_users_tenant_short_id", "users", type_="unique")
    op.drop_index("ix_users_short_id", table_name="users")
    op.drop_column("users", "image_url")
    op.drop_column("users", "signature_data")
    op.drop_column("users", "custom_2")
    op.drop_column("users", "custom_1")
    op.drop_column("users", "report_access_provider_id")
    op.drop_column("users", "short_id")
