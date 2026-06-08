"""add authentication module support (legacy onboarding + reset/activation tokens)

Revision ID: b9c0d1e2f3a4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-07

Resolves the Authentication backend dev-report:
- ALTER users: is_legacy_user, legacy_activation_completed, password_created_at (§3).
- CREATE auth_action_tokens (single-use, TTL) for forgot/reset + legacy
  activation (§2.1–2.5).

Additive; the new table is created from model metadata to avoid drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.db.models.identity import AuthActionToken

revision = "b9c0d1e2f3a4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None

_NEW_TABLES = [AuthActionToken.__table__]


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_legacy_user", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column(
            "legacy_activation_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("users", sa.Column("password_created_at", sa.DateTime(), nullable=True))
    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_NEW_TABLES)))
    op.drop_column("users", "password_created_at")
    op.drop_column("users", "legacy_activation_completed")
    op.drop_column("users", "is_legacy_user")
