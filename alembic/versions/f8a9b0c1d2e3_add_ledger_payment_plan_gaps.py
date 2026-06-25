"""add ledger payment-plan gaps (AL-3)

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-06-24

Account-ledger dev-report AL-3 (Contracts panel):
- ``patient_payment_plans.plan_type`` ('regular' | 'ortho') — discriminate the
  Regular-Patient vs Ortho-Patient contract panels.
- ``patient_ins_payment_plans`` / ``patient_sec_ins_payment_plans`` gain
  ``plan_amount`` / ``down_payment`` / ``rem_total_amt`` / ``rem_payments`` so the
  insurance panels show more than Next Per. Amt / Next Date.

AL-1/2/4/5/6/7 are served by the new ``GET /patients/{id}/account-ledger`` endpoint
over existing data — no schema change. Hand-written (scoped to the three tables).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None

_INS_TABLES = ("patient_ins_payment_plans", "patient_sec_ins_payment_plans")


def upgrade() -> None:
    op.add_column(
        "patient_payment_plans",
        sa.Column("plan_type", sa.String(length=20), nullable=False, server_default="regular"),
    )
    for tbl in _INS_TABLES:
        op.add_column(tbl, sa.Column("plan_amount", sa.Numeric(12, 2), nullable=True))
        op.add_column(tbl, sa.Column("down_payment", sa.Numeric(12, 2), nullable=True))
        op.add_column(tbl, sa.Column("rem_total_amt", sa.Numeric(12, 2), nullable=True))
        op.add_column(tbl, sa.Column("rem_payments", sa.Integer(), nullable=True))


def downgrade() -> None:
    for tbl in _INS_TABLES:
        op.drop_column(tbl, "rem_payments")
        op.drop_column(tbl, "rem_total_amt")
        op.drop_column(tbl, "down_payment")
        op.drop_column(tbl, "plan_amount")
    op.drop_column("patient_payment_plans", "plan_type")
