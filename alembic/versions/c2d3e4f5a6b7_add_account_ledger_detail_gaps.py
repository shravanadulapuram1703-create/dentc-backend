"""Account Ledger — Edit-window / allocation gaps (AL-13, AL-15).

Backs the AL-13..17 section of
``docs/account-ledger/account_ledger_backend_devreport.md``:

- **AL-13** the Modified By/On pair the Edit Treatment and Edit Payment windows
  render disabled: ``updated_at``/``updated_by`` on ``patient_procedures`` and
  ``patient_payments`` (both had ``created_*`` only). Named to match the engine —
  ``CRUDBase.update`` already stamps ``updated_by``, so they populate themselves
  from here on. Plus ``patient_payments.eob_number`` (a patient-side payment
  entered from an EOB had nowhere to put the number; INS-1's
  ``ledger_insurance_details.eob_number`` only covers carrier remittances) and
  ``patient_procedures.fee_schedule_id`` (which schedule produced ``fee``).
- **AL-15** ``patient_procedures.pat_paid`` / ``pat_adjust`` — the per-procedure
  patient money from ``LEDGER.PATPAID`` / ``PATADJUST``. The roll-ups behind
  ``/patient-procedures/{id}/allocations-summary`` were always ``0`` because
  ``payment_allocations`` cannot supply them: the Denticon allocation export holds
  6,951 rows for 1.33M payments and **every ``AMOUNT`` in it is ``0.0000``**
  (AL-16), so there was nothing to sum. These two columns are the only surviving
  record of what was applied to a charge, and they are in the LEDGER export the
  migration already reads.

Populated for migrated rows by ``scripts/backfill_ledger_source_fields.py``.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # AL-13 — the audit pair.
    for table in ("patient_procedures", "patient_payments"):
        op.add_column(table, sa.Column("updated_at", sa.DateTime(), nullable=True))
        op.add_column(table, sa.Column("updated_by", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_updated_by", table, "users", ["updated_by"], ["id"]
        )

    # AL-13 — fields the Edit windows had nowhere to store.
    op.add_column("patient_payments", sa.Column("eob_number", sa.String(50), nullable=True))
    op.add_column("patient_procedures", sa.Column("fee_schedule_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_patient_procedures_fee_schedule_id",
        "patient_procedures", "fee_schedules", ["fee_schedule_id"], ["id"],
    )

    # AL-15 — per-procedure applied patient money.
    op.add_column("patient_procedures", sa.Column("pat_paid", sa.Numeric(12, 2), nullable=True))
    op.add_column("patient_procedures", sa.Column("pat_adjust", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("patient_procedures", "pat_adjust")
    op.drop_column("patient_procedures", "pat_paid")
    op.drop_constraint(
        "fk_patient_procedures_fee_schedule_id", "patient_procedures", type_="foreignkey"
    )
    op.drop_column("patient_procedures", "fee_schedule_id")
    op.drop_column("patient_payments", "eob_number")
    for table in ("patient_procedures", "patient_payments"):
        op.drop_constraint(f"fk_{table}_updated_by", table, type_="foreignkey")
        op.drop_column(table, "updated_by")
        op.drop_column(table, "updated_at")
