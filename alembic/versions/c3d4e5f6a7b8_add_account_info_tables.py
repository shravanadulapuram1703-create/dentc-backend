"""add Account Information module tables (Setup -> Account Info)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-01

Net-new, tenant-scoped tables backing the Account Information screen:
account_settings, account_communications, office_phone_assignments,
account_holidays, account_consents. Additive — no changes to migrated tables.

Tables are created directly from the SQLAlchemy model metadata so the migration
never drifts from the models (account_settings alone has 80 columns).
"""

from __future__ import annotations

from alembic import op

from app.db.base import Base
from app.db.models.account import (
    AccountCommunications,
    AccountConsent,
    AccountHoliday,
    AccountSettings,
    OfficePhoneAssignment,
)

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None

_TABLES = [
    AccountSettings.__table__,
    AccountCommunications.__table__,
    OfficePhoneAssignment.__table__,
    AccountHoliday.__table__,
    AccountConsent.__table__,
]


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_TABLES)))
