"""add user access sub-resource tables (Phase 4)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-31

Net-new tables for UserSetup advanced tabs: user_preferences, user_groups,
user_group_memberships, user_ip_rules. Additive; no changes to migrated tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pref_key", sa.String(length=100), nullable=False),
        sa.Column("pref_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "pref_key", name="uq_user_preferences_user_key"),
    )
    op.create_index("ix_user_preferences_tenant_id", "user_preferences", ["tenant_id"])
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])

    op.create_table(
        "user_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_user_groups_tenant_id", "user_groups", ["tenant_id"])

    op.create_table(
        "user_group_memberships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("user_groups.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "group_id", name="uq_user_group_memberships_user_group"),
    )
    op.create_index("ix_user_group_memberships_tenant_id", "user_group_memberships", ["tenant_id"])
    op.create_index("ix_user_group_memberships_user_id", "user_group_memberships", ["user_id"])
    op.create_index("ix_user_group_memberships_group_id", "user_group_memberships", ["group_id"])

    op.create_table(
        "user_ip_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("rule_type", sa.String(length=10), nullable=False, server_default="allow"),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_user_ip_rules_tenant_id", "user_ip_rules", ["tenant_id"])
    op.create_index("ix_user_ip_rules_user_id", "user_ip_rules", ["user_id"])


def downgrade() -> None:
    op.drop_table("user_ip_rules")
    op.drop_table("user_group_memberships")
    op.drop_table("user_groups")
    op.drop_table("user_preferences")
