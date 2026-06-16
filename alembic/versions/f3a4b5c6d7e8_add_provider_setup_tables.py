"""add Provider Setup module schema (Setup -> Providers)

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-13

Resolves provider setup backend dev-report gaps #1–#7:
- ALTER providers: user_id (#6) + Info "Provider/Advanced Settings" columns (#7).
- CREATE provider_schedule_days (#1), provider_holidays (#2), provider_watermarks (#3),
  provider_referral_offices (#4), provider_carrier_logins (#5).

Additive; new tables created from model metadata to avoid drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.db.models.provider_setup import (
    ProviderCarrierLogin,
    ProviderHoliday,
    ProviderReferralOffice,
    ProviderScheduleDay,
    ProviderWatermark,
)

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None

_NEW_TABLES = [
    ProviderScheduleDay.__table__,
    ProviderHoliday.__table__,
    ProviderWatermark.__table__,
    ProviderReferralOffice.__table__,
    ProviderCarrierLogin.__table__,
]

# name, type, [server_default]
_PROVIDER_COLS = [
    ("user_id", sa.Integer()),
    ("scheduler_color", sa.String(length=20)),
    ("is_ortho_provider", sa.Boolean(), "false"),
    ("visible_in_appointnow", sa.Boolean(), "true"),
    ("default_provider_time", sa.Integer()),
    ("is_billing_provider", sa.Boolean(), "false"),
    ("dosespot_user_id", sa.String(length=100)),
    ("updox_direct_address", sa.String(length=255)),
    ("denticon_user_id", sa.String(length=100)),
    ("print_separate_claim_form", sa.Boolean(), "false"),
    ("ortho_questionnaire_template", sa.String(length=100)),
    ("custom_1", sa.String(length=255)),
    ("custom_2", sa.String(length=255)),
]


def upgrade() -> None:
    for name, type_, *default in _PROVIDER_COLS:
        server_default = default[0] if default else None
        op.add_column(
            "providers",
            sa.Column(name, type_, nullable=True, server_default=server_default),
        )
    op.create_foreign_key("fk_providers_user_id_users", "providers", "users", ["user_id"], ["id"])
    op.create_index("ix_providers_user_id", "providers", ["user_id"])

    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_NEW_TABLES)))

    op.drop_index("ix_providers_user_id", table_name="providers")
    op.drop_constraint("fk_providers_user_id_users", "providers", type_="foreignkey")
    for name, *_ in reversed(_PROVIDER_COLS):
        op.drop_column("providers", name)
