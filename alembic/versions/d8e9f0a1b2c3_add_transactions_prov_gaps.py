"""Transactions module — remaining gaps (ADJ-1 allocation, PROV-1 index).

Backs the second pass over ``docs/transactions_backend_devreport.md``:

- ADJ-1  ``payment_allocations.adjustment_id`` — lets one adjustment be split
  across specific outstanding procedures (the payment side already allocates
  through this table; the adjustment side had no allocation store at all).
- PROV-1 index on ``provider_offices.provider_id`` — the office↔provider join is
  now read from the provider direction too (``GET /providers?office_id=`` unions
  the assignment with the legacy home-office scalar).

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ADJ-1: per-procedure adjustment allocation ────────────────────────────
    op.add_column(
        "payment_allocations", sa.Column("adjustment_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_payment_allocations_adjustment_id_patient_adjustments",
        "payment_allocations", "patient_adjustments", ["adjustment_id"], ["id"],
    )
    op.create_index(
        "ix_payment_allocations_adjustment_id", "payment_allocations", ["adjustment_id"]
    )
    # The per-procedure "Pat Paid / Pat Adj" rollup (CHG-5) scans by procedure.
    op.create_index(
        "ix_payment_allocations_procedure_id", "payment_allocations", ["procedure_id"]
    )
    op.create_index(
        "ix_patient_adjustments_procedure_id", "patient_adjustments", ["procedure_id"]
    )

    # ── PROV-1: provider→office lookups (union with the home-office scalar) ────
    op.create_index("ix_provider_offices_provider_id", "provider_offices", ["provider_id"])


def downgrade() -> None:
    op.drop_index("ix_provider_offices_provider_id", table_name="provider_offices")
    op.drop_index("ix_patient_adjustments_procedure_id", table_name="patient_adjustments")
    op.drop_index("ix_payment_allocations_procedure_id", table_name="payment_allocations")
    op.drop_index("ix_payment_allocations_adjustment_id", table_name="payment_allocations")
    op.drop_constraint(
        "fk_payment_allocations_adjustment_id_patient_adjustments",
        "payment_allocations", type_="foreignkey",
    )
    op.drop_column("payment_allocations", "adjustment_id")
