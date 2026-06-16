"""add Insurance Setup carrier/employer fields + audit

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-13

Resolves insurance backend dev-report gaps:
- INS-3: carrier capability flags + insurance_type.
- INS-4: carrier fax + email.
- INS-5: employer salesrep + contact_person.
- INS-6: server-maintained modified audit (updated_at/updated_by) on both
  insurance_carriers and employers (+ employer created_by actor).

(INS-1 carrier_type filter, INS-2 is_dental discriminator and INS-8 stable
pagination are application-layer only — no schema change.)

Additive; all columns nullable.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None

_CARRIER_COLS = [
    ("fax", sa.String(length=20)),
    ("email", sa.String(length=255)),
    ("supports_realtime_eligibility", sa.Boolean()),
    ("supports_claim_status", sa.Boolean()),
    ("supports_dxc_attachment", sa.Boolean()),
    ("insurance_type", sa.String(length=50)),
    ("updated_at", sa.DateTime()),
    ("updated_by", sa.Integer()),
]

_EMPLOYER_COLS = [
    ("salesrep", sa.String(length=255)),
    ("contact_person", sa.String(length=255)),
    ("updated_at", sa.DateTime()),
    ("created_by", sa.Integer()),
    ("updated_by", sa.Integer()),
]


def upgrade() -> None:
    for name, type_ in _CARRIER_COLS:
        op.add_column("insurance_carriers", sa.Column(name, type_, nullable=True))
    op.create_foreign_key(
        "fk_insurance_carriers_updated_by_users", "insurance_carriers", "users",
        ["updated_by"], ["id"],
    )

    for name, type_ in _EMPLOYER_COLS:
        op.add_column("employers", sa.Column(name, type_, nullable=True))
    op.create_foreign_key(
        "fk_employers_created_by_users", "employers", "users", ["created_by"], ["id"]
    )
    op.create_foreign_key(
        "fk_employers_updated_by_users", "employers", "users", ["updated_by"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_employers_updated_by_users", "employers", type_="foreignkey")
    op.drop_constraint("fk_employers_created_by_users", "employers", type_="foreignkey")
    for name, _ in reversed(_EMPLOYER_COLS):
        op.drop_column("employers", name)

    op.drop_constraint("fk_insurance_carriers_updated_by_users", "insurance_carriers", type_="foreignkey")
    for name, _ in reversed(_CARRIER_COLS):
        op.drop_column("insurance_carriers", name)
