"""Add Transactions-module backend gaps.

Backs docs in ``transactions/transactions_backend_devreport.md``:

- INS-1  remittance identifiers on ``ledger_insurance_details`` (check/bank/EOB/
  EFT-trace + payment date/method + created_by).
- CHG-5  ``patient_payments.bank_number`` (deposit Bank #).
- CHG-6  ``patient_procedures.hygienist_id`` (second/hygiene provider).
- ADJ-1  ``patient_adjustments.write_off_type`` (contractual|provider|insurance|courtesy).
- CHG-2  ``procedure_codes`` structured anatomy/surface/material rule objects.
- REF-1/2  ``patient_refunds`` table (auditable refunds / reversals).
- STMT-1/2  ``patient_statements`` table (generated statement snapshots).
- CHG-4  ``explosion_codes`` + ``explosion_code_items`` (multi-procedure codes).

Revision ID: c7d8e9f0a1b2
Revises: b3c4d5e6f7a8
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── additive columns ──────────────────────────────────────────────────────
    op.add_column("patient_payments", sa.Column("bank_number", sa.String(length=100), nullable=True))
    op.add_column("patient_procedures", sa.Column("hygienist_id", sa.String(length=50), nullable=True))
    op.create_foreign_key(
        "fk_patient_procedures_hygienist_id_providers",
        "patient_procedures", "providers", ["hygienist_id"], ["id"],
    )
    op.add_column("patient_adjustments", sa.Column("write_off_type", sa.String(length=20), nullable=True))

    for col in ("payment_date",):
        op.add_column("ledger_insurance_details", sa.Column(col, sa.Date(), nullable=True))
    for col, length in (
        ("payment_method", 50), ("check_number", 100), ("bank_number", 100),
        ("eob_number", 100), ("eft_trace_number", 100),
    ):
        op.add_column("ledger_insurance_details", sa.Column(col, sa.String(length=length), nullable=True))
    op.add_column("ledger_insurance_details", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_ledger_insurance_details_created_by_users",
        "ledger_insurance_details", "users", ["created_by"], ["id"],
    )

    for col in ("anatomy_rules", "surface_rules", "material_rules"):
        op.add_column("procedure_codes", sa.Column(col, sa.JSON(), nullable=True))

    # ── patient_refunds (REF-1/2) ─────────────────────────────────────────────
    op.create_table(
        "patient_refunds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=True),
        sa.Column("refund_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("refund_method", sa.String(length=50), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("reason_code", sa.String(length=50), nullable=True),
        sa.Column("source_payment_id", sa.String(length=50), nullable=True),
        sa.Column("reversed_type", sa.String(length=20), nullable=True),
        sa.Column("reversed_id", sa.String(length=50), nullable=True),
        sa.Column("check_number", sa.String(length=100), nullable=True),
        sa.Column("reference_number", sa.String(length=100), nullable=True),
        sa.Column("authorized_by", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_void", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_patient_refunds_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], name="fk_patient_refunds_patient_id_patients"),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_patient_refunds_office_id_offices"),
        sa.ForeignKeyConstraint(
            ["source_payment_id"], ["patient_payments.id"],
            name="fk_patient_refunds_source_payment_id_patient_payments",
        ),
        sa.ForeignKeyConstraint(["authorized_by"], ["users.id"], name="fk_patient_refunds_authorized_by_users"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_patient_refunds_created_by_users"),
        sa.PrimaryKeyConstraint("id", name="pk_patient_refunds"),
    )
    op.create_index("ix_patient_refunds_tenant_id", "patient_refunds", ["tenant_id"])
    op.create_index("ix_patient_refunds_patient_id", "patient_refunds", ["patient_id"])

    # ── patient_statements (STMT-1/2) ─────────────────────────────────────────
    op.create_table(
        "patient_statements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=True),
        sa.Column("statement_date", sa.Date(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("opening_balance", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("total_charges", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("total_payments", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("total_adjustments", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("closing_balance", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("aging_current", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("aging_30", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("aging_60", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("aging_90", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("aging_120", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("batch_id", sa.String(length=50), nullable=True),
        sa.Column("delivery_method", sa.String(length=20), nullable=True),
        sa.Column("delivery_status", sa.String(length=20), server_default="generated", nullable=False),
        sa.Column("delivered_to", sa.String(length=255), nullable=True),
        sa.Column("delivered_at", sa.Date(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_patient_statements_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], name="fk_patient_statements_patient_id_patients"),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_patient_statements_office_id_offices"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_patient_statements_created_by_users"),
        sa.PrimaryKeyConstraint("id", name="pk_patient_statements"),
    )
    op.create_index("ix_patient_statements_tenant_id", "patient_statements", ["tenant_id"])
    op.create_index("ix_patient_statements_patient_id", "patient_statements", ["patient_id"])
    op.create_index("ix_patient_statements_batch_id", "patient_statements", ["batch_id"])

    # ── explosion_codes + items (CHG-4) ───────────────────────────────────────
    op.create_table(
        "explosion_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_explosion_codes_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_explosion_codes_office_id_offices"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_explosion_codes_created_by_users"),
        sa.PrimaryKeyConstraint("id", name="pk_explosion_codes"),
        sa.UniqueConstraint("tenant_id", "office_id", "code", name="uq_explosion_codes_tenant_office_code"),
    )
    op.create_index("ix_explosion_codes_tenant_id", "explosion_codes", ["tenant_id"])
    op.create_table(
        "explosion_code_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("explosion_code_id", sa.Integer(), nullable=False),
        sa.Column("procedure_code", sa.String(length=20), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("default_fee", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("tooth", sa.String(length=10), nullable=True),
        sa.Column("surface", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["explosion_code_id"], ["explosion_codes.id"],
            name="fk_explosion_code_items_explosion_code_id_explosion_codes",
        ),
        sa.ForeignKeyConstraint(
            ["procedure_code"], ["procedure_codes.code"],
            name="fk_explosion_code_items_procedure_code_procedure_codes",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_explosion_code_items"),
    )
    op.create_index(
        "ix_explosion_code_items_explosion_code_id", "explosion_code_items", ["explosion_code_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_explosion_code_items_explosion_code_id", table_name="explosion_code_items")
    op.drop_table("explosion_code_items")
    op.drop_index("ix_explosion_codes_tenant_id", table_name="explosion_codes")
    op.drop_table("explosion_codes")
    op.drop_index("ix_patient_statements_batch_id", table_name="patient_statements")
    op.drop_index("ix_patient_statements_patient_id", table_name="patient_statements")
    op.drop_index("ix_patient_statements_tenant_id", table_name="patient_statements")
    op.drop_table("patient_statements")
    op.drop_index("ix_patient_refunds_patient_id", table_name="patient_refunds")
    op.drop_index("ix_patient_refunds_tenant_id", table_name="patient_refunds")
    op.drop_table("patient_refunds")

    for col in ("material_rules", "surface_rules", "anatomy_rules"):
        op.drop_column("procedure_codes", col)
    op.drop_constraint(
        "fk_ledger_insurance_details_created_by_users", "ledger_insurance_details", type_="foreignkey"
    )
    for col in ("created_by", "eft_trace_number", "eob_number", "bank_number",
                "check_number", "payment_method", "payment_date"):
        op.drop_column("ledger_insurance_details", col)
    op.drop_column("patient_adjustments", "write_off_type")
    op.drop_constraint(
        "fk_patient_procedures_hygienist_id_providers", "patient_procedures", type_="foreignkey"
    )
    op.drop_column("patient_procedures", "hygienist_id")
    op.drop_column("patient_payments", "bank_number")
