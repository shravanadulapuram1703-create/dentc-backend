"""Insurance Payment window — INS-PAY-1/2/4/5/6.

Backs ``docs/patient-insurance/insurance_payment_backend_devreport.md``.

- **INS-PAY-2 is the critical one.** ``record_insurance_payment`` rolled the paid
  amount forward onto ``insurance_claims.total_paid`` and nothing ever rolled it
  back: ``DELETE /ledger-insurance-details/{id}`` really removed the row, and
  ``recalculate`` recomputed ``total_billed``/``est_insurance`` from the
  procedures but simply echoed the stored ``total_paid``. A mis-keyed remittance
  therefore overstated what the carrier had paid **permanently**, correctable
  only by hand-PATCHing the claim. The fix is two-sided: ``recalculate`` now
  derives ``total_paid`` from the surviving coverage rows (so even a hard delete
  self-heals), and a posted remittance gains ``is_void``/``void_reason``/
  ``voided_at``/``voided_by`` so it can be **reversed with an audit trail**
  instead of deleted — the same shape ``patient_payments.is_void`` has.

- **INS-PAY-5** completes the per-tier matrix on ``ledger_insurance_details``.
  ``sec_deductible`` and every tertiary column but ``ter_ins_paid``/
  ``ter_ins_plan_id`` were missing, so a secondary remittance could not carry a
  deductible and a tertiary one could not be posted at all. Each tier now has
  estimated / deductible / ins_paid / ins_adjust / plan_id / posted, so all
  three post through one path instead of the primary being a special case.

- **INS-PAY-1** ``ledger_insurance_details.notes``. The remittance note was being
  appended to the *claim's* notes with a synthetic ``[date] Ins payment …``
  prefix — one line's note applied to the whole claim, and unparseable.

- **INS-PAY-4** the window's claim-level "Enter Adjustment" ($ or %). The money
  stays per-procedure because that is what the ledger reconciles against, but
  the user's intent ("a 10% claim write-off") had nowhere to live once it was
  distributed. ``write_off_mode``/``write_off_value`` record what was typed;
  ``write_off_amount`` is the distributed total.

- **INS-PAY-6** ``patient_payments.eft_trace_number``. ``eob_number`` already
  exists (AL-13) — the report's frontend client was stale — but an EFT landing
  on the account via "Insurance Check to Previous Balance" had no trace number.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None

_MONEY = sa.Numeric(12, 2)

# INS-PAY-5: the columns that complete the secondary/tertiary tiers.
_TIER_COLUMNS = (
    "sec_deductible",
    "ter_estimated",
    "ter_deductible",
    "ter_ins_adjust",
)


def upgrade() -> None:
    # ── INS-PAY-5 ────────────────────────────────────────────────────────────
    for column in _TIER_COLUMNS:
        op.add_column("ledger_insurance_details", sa.Column(column, _MONEY, nullable=True))
    op.add_column(
        "ledger_insurance_details",
        sa.Column("ter_posted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # ── INS-PAY-1 ────────────────────────────────────────────────────────────
    op.add_column("ledger_insurance_details", sa.Column("notes", sa.Text(), nullable=True))

    # ── INS-PAY-2 ────────────────────────────────────────────────────────────
    op.add_column(
        "ledger_insurance_details",
        sa.Column("is_void", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("ledger_insurance_details", sa.Column("void_reason", sa.Text(), nullable=True))
    op.add_column("ledger_insurance_details", sa.Column("voided_at", sa.DateTime(), nullable=True))
    op.add_column("ledger_insurance_details", sa.Column("voided_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_ledger_insurance_details_voided_by_users",
        "ledger_insurance_details", "users", ["voided_by"], ["id"],
    )
    # ``recalculate`` sums the live coverage rows for one claim on every post and
    # every reversal, so that lookup is now on the hot path.
    op.create_index(
        "ix_ledger_insurance_details_claim_id_is_void",
        "ledger_insurance_details",
        ["claim_id", "is_void"],
    )

    # ── INS-PAY-4 ────────────────────────────────────────────────────────────
    op.add_column("insurance_claims", sa.Column("write_off_amount", _MONEY, nullable=True))
    op.add_column("insurance_claims", sa.Column("write_off_mode", sa.String(10), nullable=True))
    op.add_column("insurance_claims", sa.Column("write_off_value", _MONEY, nullable=True))

    # ── INS-PAY-6 ────────────────────────────────────────────────────────────
    op.add_column(
        "patient_payments", sa.Column("eft_trace_number", sa.String(100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("patient_payments", "eft_trace_number")
    op.drop_column("insurance_claims", "write_off_value")
    op.drop_column("insurance_claims", "write_off_mode")
    op.drop_column("insurance_claims", "write_off_amount")
    op.drop_index(
        "ix_ledger_insurance_details_claim_id_is_void", table_name="ledger_insurance_details"
    )
    op.drop_constraint(
        "fk_ledger_insurance_details_voided_by_users",
        "ledger_insurance_details", type_="foreignkey",
    )
    op.drop_column("ledger_insurance_details", "voided_by")
    op.drop_column("ledger_insurance_details", "voided_at")
    op.drop_column("ledger_insurance_details", "void_reason")
    op.drop_column("ledger_insurance_details", "is_void")
    op.drop_column("ledger_insurance_details", "notes")
    op.drop_column("ledger_insurance_details", "ter_posted")
    for column in reversed(_TIER_COLUMNS):
        op.drop_column("ledger_insurance_details", column)
