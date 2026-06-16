"""add Referral Info fields (referral dev-report gaps 1-4)

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-06-14

Adds the legacy Referral Info grid columns with no current home:
e_referral_id, practice_name, contact_name, cost — all nullable.

(The referral_type direction enum is seeded via scripts.seed_account_definitions
and the demographics feed already exists as referral-demog-* — app-layer only.)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d7e8f9a0b1c2"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None

_COLS = [
    ("e_referral_id", sa.String(length=50)),
    ("practice_name", sa.String(length=255)),
    ("contact_name", sa.String(length=255)),
    ("cost", sa.Numeric(12, 2)),
]


def upgrade() -> None:
    for name, type_ in _COLS:
        op.add_column("referrals", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLS):
        op.drop_column("referrals", name)
