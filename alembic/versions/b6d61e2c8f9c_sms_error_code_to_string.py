"""Widen sms_messages.error_code from Integer to String (RingCentral migration).

Twilio's error codes are numeric (e.g. 21211). RingCentral's are
alphanumeric strings (confirmed live, 2026-10-01: "MSG-242" sending-feature-
not-available, "SUB-521" webhook-not-reachable) — Integer can't hold them.
``USING error_code::text`` is lossless for the existing Twilio-era rows
(their values are already digit strings once cast).

Additive/widening only — no data loss, no rows touched beyond the type cast.

Revision ID: b6d61e2c8f9c
Revises: 8e4a6a8e5ab0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b6d61e2c8f9c"
down_revision = "8e4a6a8e5ab0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sms_messages",
        "error_code",
        type_=sa.String(length=20),
        existing_type=sa.Integer(),
        postgresql_using="error_code::text",
    )


def downgrade() -> None:
    # Best-effort: a RingCentral-era non-numeric code (e.g. "MSG-242") cannot
    # round-trip back to Integer and becomes NULL rather than failing the
    # downgrade outright.
    op.execute(
        "UPDATE sms_messages SET error_code = NULL "
        "WHERE error_code IS NOT NULL AND error_code !~ '^-?[0-9]+$'"
    )
    op.alter_column(
        "sms_messages",
        "error_code",
        type_=sa.Integer(),
        existing_type=sa.String(length=20),
        postgresql_using="error_code::integer",
    )
