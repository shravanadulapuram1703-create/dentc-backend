"""Transactions — fee/coverage gaps (FEE-1).

Backs the fee-schedule section of
``docs/transactions/transactions_backend_devreport.md``:

- **FEE-1** ``procedure_codes.coverage_category`` — the legacy *insurance*
  coverage-category code (``01``, ``01A``, ``03A``, ``11B``, …) an ADA code
  bands into. ``insurance_coverage_rules`` stores every coverage percentage
  against those codes (876,732 rows on the migrated tenant), while the charge
  carries an ADA code, and nothing joined the two — so the estimate engine
  matched no band and returned 0 % insurance on every migrated plan. Denticon's
  ``Codes.INSCATEGORYID`` was read by the migration only to derive the display
  label and then dropped, so the link is reconstructed from the published CDT
  family ranges by ``scripts/seed_coverage_categories.py`` (dry-run by default).

  Nullable on purpose: a code that maps to no range stays NULL rather than being
  filed under "12 Non-covered Services", because "unknown" and "denied" are not
  the same answer. Indexed because ``/procedure-codes?coverage_category=`` is a
  first-class filter.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "procedure_codes",
        sa.Column("coverage_category", sa.String(20), nullable=True),
    )
    op.create_index(
        "ix_procedure_codes_coverage_category",
        "procedure_codes",
        ["coverage_category"],
    )


def downgrade() -> None:
    op.drop_index("ix_procedure_codes_coverage_category", table_name="procedure_codes")
    op.drop_column("procedure_codes", "coverage_category")
