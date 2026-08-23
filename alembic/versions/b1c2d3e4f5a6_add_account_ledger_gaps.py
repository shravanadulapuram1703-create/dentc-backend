"""Account Ledger second pass (AL-6 / AL-10).

Backs ``docs/account-ledger/account_ledger_backend_devreport.md``:

- **AL-10** ``patient_procedures.created_by_legacy`` / ``patient_payments.created_by_legacy``
  — the legacy ``LEDGER.CREATEDBY`` login string. The ledger's **User** column was
  blank for every migrated row because the migration dropped the column entirely;
  ``created_by`` alone cannot carry it, since a login that no longer has a ``users``
  row would still resolve to ``NULL``. The raw string is kept alongside the FK so the
  column reads for historical activity too.
- **AL-6** ``patient_procedures.duration_minutes`` — ``LEDGER.DURATION``, the chair
  time booked against the charge, behind the ledger's ``Durati…`` column. Nullable on
  purpose: "not recorded" must stay distinguishable from "0 minutes".

The remaining AL items in that report are code, not schema: AL-9 is the payment
sign convention (``app/services/ledger_sign.py``), AL-8 adds claim rows to the feed,
AL-11 adds ``scope=account``, AL-12 extends the patient context. ``created_by`` /
``claim_id`` / ``duration_minutes`` are populated from the source export by
``scripts/backfill_ledger_source_fields.py``.

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f7
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient_procedures", sa.Column("created_by_legacy", sa.String(50), nullable=True))
    op.add_column("patient_procedures", sa.Column("duration_minutes", sa.Integer(), nullable=True))
    op.add_column("patient_payments", sa.Column("created_by_legacy", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("patient_payments", "created_by_legacy")
    op.drop_column("patient_procedures", "duration_minutes")
    op.drop_column("patient_procedures", "created_by_legacy")
