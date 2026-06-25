"""add patient insurance gaps (INS-PT-1/2/3/4/6)

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-06-24

Addresses the frontend patient-insurance (Add/Edit Plan) dev-report:
- INS-PT-1: ``insurance_subscribers.marital_status``.
- INS-PT-2: ``insurance_subscribers.sub_phone``.
- INS-PT-4: ``insurance_subscribers.sub_address2`` (2nd address line).
- INS-PT-6: ``insurance_subscribers.plan_effective_date`` / ``plan_term_date``
  (legacy Eligibility grid "Plan Date" vs the existing subscriber "Sub Date").
- INS-PT-3: ``patient_insurance.sec_sub_rel_to_prim_sub``.

INS-PT-5 (eligibility verify) is an endpoint over existing columns — no schema
change. Hand-written (scoped to the two affected tables only).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("insurance_subscribers", sa.Column("sub_address2", sa.String(length=255), nullable=True))
    op.add_column("insurance_subscribers", sa.Column("marital_status", sa.String(length=20), nullable=True))
    op.add_column("insurance_subscribers", sa.Column("sub_phone", sa.String(length=20), nullable=True))
    op.add_column("insurance_subscribers", sa.Column("plan_effective_date", sa.Date(), nullable=True))
    op.add_column("insurance_subscribers", sa.Column("plan_term_date", sa.Date(), nullable=True))

    op.add_column(
        "patient_insurance",
        sa.Column("sec_sub_rel_to_prim_sub", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("patient_insurance", "sec_sub_rel_to_prim_sub")
    op.drop_column("insurance_subscribers", "plan_term_date")
    op.drop_column("insurance_subscribers", "plan_effective_date")
    op.drop_column("insurance_subscribers", "sub_phone")
    op.drop_column("insurance_subscribers", "marital_status")
    op.drop_column("insurance_subscribers", "sub_address2")
