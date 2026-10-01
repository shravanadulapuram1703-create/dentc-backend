"""Add ringcentral_sms_subscriptions (SMS-2 webhook subscription tracking).

Platform-wide (not tenant-scoped), expected to hold exactly one row —
tracks the single active RingCentral Subscription registered for SMS
message-store events, so sms_service.ensure_subscription knows when to
renew it (RingCentral subscriptions expire, confirmed live max 7 days,
unlike Twilio's set-once-on-the-number webhook config).

Additive only.

Revision ID: fc6450e398ee
Revises: b6d61e2c8f9c
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "fc6450e398ee"
down_revision = "b6d61e2c8f9c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ringcentral_sms_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("subscription_id", sa.String(length=64), nullable=False),
        sa.Column("webhook_url", sa.String(length=500), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_renewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_ringcentral_sms_subscriptions_subscription_id",
        "ringcentral_sms_subscriptions",
        ["subscription_id"],
    )


def downgrade() -> None:
    op.drop_table("ringcentral_sms_subscriptions")
