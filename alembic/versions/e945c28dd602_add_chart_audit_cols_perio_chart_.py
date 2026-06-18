"""add chart audit cols + perio_chart_templates (CHART-1/2a/3a/3b)

Revision ID: e945c28dd602
Revises: a0b1c2d3e4f5
Create Date: 2026-06-17

Fixes the frontend-reported charting-setup gaps:
- CHART-3a: chart_materials gains ``updated_at`` ("Modified On"). [TimestampMixin]
- CHART-3b: chart_materials gains ``updated_by`` ("Modified By"; FK -> users).
- CHART-2a: chart_colors gains ``updated_by`` ("Modified By"; FK -> users).
- CHART-1 : new ``perio_chart_templates`` — named, tenant-scoped Perio Setup
  Templates (cal_warning_level / fgm_level / start_voice / auto_advance JSON +
  created_by/updated_by audit), distinct from the per-user perio_chart_settings.

Hand-written (not the raw autogenerate, which also picked up unrelated pre-existing
index-naming drift across the whole schema — out of scope here).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e945c28dd602"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CHART-3a / CHART-3b — chart_materials audit columns.
    op.add_column("chart_materials", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("chart_materials", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_chart_materials_updated_by_users"),
        "chart_materials", "users", ["updated_by"], ["id"],
    )

    # CHART-2a — chart_colors "Modified By".
    op.add_column("chart_colors", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_chart_colors_updated_by_users"),
        "chart_colors", "users", ["updated_by"], ["id"],
    )

    # CHART-1 — Perio Setup Templates.
    op.create_table(
        "perio_chart_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("legacy_id", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("show_mgj", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pd_warning_level", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("cal_warning_level", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("bp_level", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("ip_level", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("fgm_level", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("start_voice", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_advance", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_perio_chart_templates_created_by_users")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_perio_chart_templates_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name=op.f("fk_perio_chart_templates_updated_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_perio_chart_templates")),
        sa.UniqueConstraint("tenant_id", "legacy_id", name="uq_perio_chart_templates_tenant_legacy"),
    )
    op.create_index(
        op.f("ix_perio_chart_templates_tenant_id"), "perio_chart_templates", ["tenant_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_perio_chart_templates_tenant_id"), table_name="perio_chart_templates")
    op.drop_table("perio_chart_templates")
    op.drop_constraint(op.f("fk_chart_colors_updated_by_users"), "chart_colors", type_="foreignkey")
    op.drop_column("chart_colors", "updated_by")
    op.drop_constraint(op.f("fk_chart_materials_updated_by_users"), "chart_materials", type_="foreignkey")
    op.drop_column("chart_materials", "updated_by")
    op.drop_column("chart_materials", "updated_at")
