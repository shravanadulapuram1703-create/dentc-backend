"""add Security/Groups rights catalog + group->rights assignment tables

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-06-09

Resolves docs/users/groups_backend_devreport.md gaps #1 and #2:
- CREATE permissions          — global assignable-rights catalog (not tenant-scoped).
- CREATE user_group_rights    — tenant-scoped M:N join (user_groups <-> permissions).

Additive; tables are created from model metadata to avoid drift. The catalog rows
are seeded separately by ``python -m scripts.seed_permissions`` (parses
``data/Groups.txt``), keeping schema and data concerns apart.
"""

from __future__ import annotations

from alembic import op

from app.db.base import Base
from app.db.models.access import Permission, UserGroupRight

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None

# permissions first (user_group_rights FKs it).
_NEW_TABLES = [Permission.__table__, UserGroupRight.__table__]


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_NEW_TABLES)))
