"""add Security/Users settings schema (time-clock config, login restrictions)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-01

Resolves backend dev-report (Users module) gaps #3 and #4:
- ALTER users: patient_access_level (#4).
- CREATE user_time_clock_config (#3) and user_login_restrictions (#4).

Additive; new tables created from model metadata to avoid drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.db.models.access import UserLoginRestriction, UserTimeClockConfig

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None

_NEW_TABLES = [UserTimeClockConfig.__table__, UserLoginRestriction.__table__]


def upgrade() -> None:
    op.add_column("users", sa.Column("patient_access_level", sa.String(length=50), nullable=True))
    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_NEW_TABLES)))
    op.drop_column("users", "patient_access_level")
