"""``insurance_claims.opening_paid`` — carrier money that predates the app's own
coverage rows (INS-PAY-2 follow-up).

Why this exists
---------------
INS-PAY-2 asks for ``recalculate`` to **derive** ``total_paid`` instead of
echoing it, so a deleted or reversed remittance stops leaving the claim claiming
money no row backs. Deriving it from ``ledger_insurance_details`` alone is
correct for a claim this system posted — and catastrophic for a migrated one.

Measured on the migrated tenant before this revision:

* 96,314 claims, **79,038** carrying a non-zero ``total_paid``
* 12,191 ``ledger_insurance_details`` rows, only 216 attached to a claim, and
  **zero** of them carrying any ``*_ins_paid`` amount

The migrated ``total_paid`` comes from the Denticon claim export, not from
coverage rows, so a naive derivation would zero all 79,038 the first time anyone
opened one and hit Recalculate.

``opening_paid`` is that pre-existing carrier money, held separately so it can be
added to — never overwritten by — what the app posts. It is the same shape as
``patient_opening_balances``: A/R that predates the system, folded into a
computed total rather than pretended away.

The backfill runs **here**, in the same transaction as the column. A script
would leave a window in which ``recalculate`` had already been deployed and
``opening_paid`` was still NULL — and that window is exactly the bug.

``opening_paid = total_paid`` is safe for every claim today because no coverage
row carries money yet; the guard excludes any claim that does, so re-running is
still correct if that changes.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "insurance_claims",
        sa.Column("opening_paid", sa.Numeric(12, 2), nullable=True),
    )
    # Seed the baseline from what each claim already reports, but only where no
    # live coverage row accounts for it — a claim whose money IS backed by rows
    # must not be double-counted.
    op.execute(
        """
        UPDATE insurance_claims AS c
           SET opening_paid = c.total_paid
         WHERE c.total_paid <> 0
           AND NOT EXISTS (
                 SELECT 1
                   FROM ledger_insurance_details AS l
                  WHERE l.claim_id = c.id
                    AND l.is_void = false
                    AND COALESCE(l.prim_ins_paid, 0)
                      + COALESCE(l.sec_ins_paid, 0)
                      + COALESCE(l.ter_ins_paid, 0) <> 0
               )
        """
    )


def downgrade() -> None:
    op.drop_column("insurance_claims", "opening_paid")
