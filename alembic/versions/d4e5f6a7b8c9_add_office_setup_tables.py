"""add Office Setup module schema (Setup -> Offices)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-01

Resolves backend dev-report gaps #11–#17:
- ALTER offices: billing/fee/group/opening/phone-2 columns (#11).
- ALTER account_holidays: nullable office_id so holidays can be office-scoped (#15).
- CREATE office_statement_settings (#12), office_integrations (#13),
  office_schedule_days (#14), office_advanced_settings (#16),
  office_smart_assist + office_smart_assist_items (#17).

Additive; new office tables created from model metadata to avoid drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.db.models.office_setup import (
    OfficeAdvancedSettings,
    OfficeIntegrations,
    OfficeScheduleDay,
    OfficeSmartAssist,
    OfficeSmartAssistItem,
    OfficeStatementSettings,
)

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

_NEW_TABLES = [
    OfficeStatementSettings.__table__,
    OfficeIntegrations.__table__,
    OfficeScheduleDay.__table__,
    OfficeAdvancedSettings.__table__,
    OfficeSmartAssist.__table__,
    OfficeSmartAssistItem.__table__,
]

_OFFICE_COLS = [
    ("phone_2", sa.String(length=20)),
    ("phone_ext", sa.String(length=10)),
    ("tax_id", sa.String(length=50)),
    ("billing_provider_id", sa.String(length=50)),
    ("use_billing_license", sa.Boolean(), "false"),
    ("office_group_id", sa.Integer()),
    ("opening_date", sa.Date()),
    ("default_fee_schedule_id", sa.Integer()),
    ("default_ucr_fee_schedule_id", sa.Integer()),
]


def upgrade() -> None:
    for name, type_, *default in _OFFICE_COLS:
        server_default = default[0] if default else None
        op.add_column(
            "offices",
            sa.Column(name, type_, nullable=True, server_default=server_default),
        )
    op.create_foreign_key("fk_offices_billing_provider_id_providers", "offices", "providers", ["billing_provider_id"], ["id"])
    op.create_foreign_key("fk_offices_office_group_id_office_groups", "offices", "office_groups", ["office_group_id"], ["id"])
    op.create_foreign_key("fk_offices_default_fee_schedule_id_fee_schedules", "offices", "fee_schedules", ["default_fee_schedule_id"], ["id"])
    op.create_foreign_key("fk_offices_default_ucr_fee_schedule_id_fee_schedules", "offices", "fee_schedules", ["default_ucr_fee_schedule_id"], ["id"])

    op.add_column("account_holidays", sa.Column("office_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_account_holidays_office_id_offices", "account_holidays", "offices", ["office_id"], ["id"])
    op.create_index("ix_account_holidays_office_id", "account_holidays", ["office_id"])

    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_NEW_TABLES)))

    op.drop_index("ix_account_holidays_office_id", table_name="account_holidays")
    op.drop_constraint("fk_account_holidays_office_id_offices", "account_holidays", type_="foreignkey")
    op.drop_column("account_holidays", "office_id")

    for fk in (
        "fk_offices_default_ucr_fee_schedule_id_fee_schedules",
        "fk_offices_default_fee_schedule_id_fee_schedules",
        "fk_offices_office_group_id_office_groups",
        "fk_offices_billing_provider_id_providers",
    ):
        op.drop_constraint(fk, "offices", type_="foreignkey")
    for name, *_ in reversed(_OFFICE_COLS):
        op.drop_column("offices", name)
