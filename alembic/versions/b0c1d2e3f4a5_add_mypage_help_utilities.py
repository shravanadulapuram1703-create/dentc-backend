"""add my-page / help / utilities tables (MP-3/6, HELP-1, UTIL-1/2)

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-07-05

- MP-3: ``user_tasks`` (personal to-dos).
- MP-6: ``notifications`` (per-user alerts inbox).
- HELP-1/4: ``support_tickets`` (durable ticket audit + Jira mirror).
- UTIL-1/2: ``utility_runs`` (execution/audit history for admin utilities).

MP-1/2/4/7 and UTIL-3 are endpoints over existing tables — no schema change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="normal"),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_user_tasks_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_tasks_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_tasks")),
    )
    op.create_index(op.f("ix_user_tasks_tenant_id"), "user_tasks", ["tenant_id"])
    op.create_index(op.f("ix_user_tasks_user_id"), "user_tasks", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("ref_type", sa.String(length=50), nullable=True),
        sa.Column("ref_id", sa.String(length=50), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_notifications_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(op.f("ix_notifications_tenant_id"), "notifications", ["tenant_id"])
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"])

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("reporter_user_id", sa.Integer(), nullable=True),
        sa.Column("project_key", sa.String(length=20), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("issue_type", sa.String(length=30), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=True),
        sa.Column("module", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="Open"),
        sa.Column("jira_issue_key", sa.String(length=50), nullable=True),
        sa.Column("jira_issue_url", sa.String(length=500), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("attachments", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_support_tickets_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["reporter_user_id"], ["users.id"], name=op.f("fk_support_tickets_reporter_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_tickets")),
    )
    op.create_index(op.f("ix_support_tickets_tenant_id"), "support_tickets", ["tenant_id"])
    op.create_index(op.f("ix_support_tickets_reporter_user_id"), "support_tickets", ["reporter_user_id"])
    op.create_index(op.f("ix_support_tickets_jira_issue_key"), "support_tickets", ["jira_issue_key"])

    op.create_table(
        "utility_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("utility_id", sa.String(length=100), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=True),
        sa.Column("run_by", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="submitted"),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("logs", sa.JSON(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_utility_runs_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name=op.f("fk_utility_runs_office_id_offices")),
        sa.ForeignKeyConstraint(["run_by"], ["users.id"], name=op.f("fk_utility_runs_run_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_utility_runs")),
    )
    op.create_index(op.f("ix_utility_runs_tenant_id"), "utility_runs", ["tenant_id"])
    op.create_index(op.f("ix_utility_runs_utility_id"), "utility_runs", ["utility_id"])


def downgrade() -> None:
    op.drop_table("utility_runs")
    op.drop_table("support_tickets")
    op.drop_table("notifications")
    op.drop_table("user_tasks")
