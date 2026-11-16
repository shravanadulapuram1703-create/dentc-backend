"""Family accounts + typed guarantor (RP-1/3/4/8/9/16).

* ``accounts``, ``account_parties``, ``account_change_events``.
* ``patients.account_id`` / ``guarantor_patient_id`` / ``guarantor_party_id``
  (+ ``ck_patients_single_guarantor``): the typed replacement for the overloaded
  ``responsible_party_id`` string, which stays as a computed alias.
* ``patient_payments.account_id`` / ``account_payment_id`` and
  ``patient_statements.account_id`` / ``statement_scope`` (RP-9).

The backfill runs **inside** this revision (``account_backfill.backfill``, the
same function ``scripts/backfill_patient_accounts.py`` re-runs): the moment the
account-scoped reads are deployed, a patient with no account would read as an
account of nobody, and that window is the bug. FKs and indexes are added after
the backfill so the 1.3M-row payment stamp on a migrated DB is a plain UPDATE.

Revision ID: 9435491c1d19
Revises: 03bbb54c0b12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "9435491c1d19"
down_revision = "03bbb54c0b12"
branch_labels = None
depends_on = None


def _audit_cols() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_no", sa.String(30)),
        sa.Column("legacy_key", sa.String(50)),
        sa.Column("primary_guarantor_patient_id", sa.Integer()),
        sa.Column("primary_guarantor_party_id", sa.Integer(),
                  sa.ForeignKey("responsible_parties.id")),
        sa.Column("home_office_id", sa.Integer(), sa.ForeignKey("offices.id")),
        sa.Column("send_statements", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("no_email_statement", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("send_collections", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("collection_agency_id", sa.Integer(), sa.ForeignKey("collection_agencies.id")),
        sa.Column("is_finance_charge", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("statement_message", sa.Text()),
        sa.Column("financial_notes", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("merged_into_account_id", sa.Integer()),
        sa.Column("merged_at", sa.DateTime()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        *_audit_cols(),
        sa.CheckConstraint(
            "primary_guarantor_patient_id IS NULL OR primary_guarantor_party_id IS NULL",
            name="ck_accounts_single_primary",
        ),
    )
    op.create_table(
        "account_parties",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id")),
        sa.Column("responsible_party_id", sa.Integer(), sa.ForeignKey("responsible_parties.id")),
        sa.Column("role", sa.String(20), nullable=False, server_default="secondary"),
        sa.Column("responsibility_pct", sa.Numeric(5, 2)),
        sa.Column("receives_statements", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        *_audit_cols(),
        sa.CheckConstraint(
            "(patient_id IS NULL) <> (responsible_party_id IS NULL)",
            name="ck_account_parties_one_person",
        ),
    )
    for col in ("tenant_id", "account_id", "patient_id", "responsible_party_id"):
        op.create_index(f"ix_account_parties_{col}", "account_parties", [col])
    op.create_table(
        "account_change_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id")),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("old_account_id", sa.Integer(), sa.ForeignKey("accounts.id")),
        sa.Column("new_account_id", sa.Integer(), sa.ForeignKey("accounts.id")),
        sa.Column("old_guarantor", sa.JSON()),
        sa.Column("new_guarantor", sa.JSON()),
        sa.Column("move_open_balance", sa.Boolean()),
        sa.Column("moved_balance", sa.Numeric(12, 2)),
        sa.Column("effective_date", sa.Date()),
        sa.Column("details", sa.JSON()),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    for col in ("tenant_id", "patient_id", "old_account_id", "new_account_id"):
        op.create_index(f"ix_account_change_events_{col}", "account_change_events", [col])

    with op.batch_alter_table("patients") as b:
        b.add_column(sa.Column("account_id", sa.Integer()))
        b.add_column(sa.Column("guarantor_patient_id", sa.Integer()))
        b.add_column(sa.Column("guarantor_party_id", sa.Integer()))
    with op.batch_alter_table("patient_payments") as b:
        b.add_column(sa.Column("account_id", sa.Integer()))
        b.add_column(sa.Column("account_payment_id", sa.String(50)))
    with op.batch_alter_table("patient_statements") as b:
        b.add_column(sa.Column("account_id", sa.Integer()))
        b.add_column(sa.Column("statement_scope", sa.String(10), nullable=False,
                               server_default="patient"))

    from app.services.account_backfill import backfill  # noqa: PLC0415

    summary = backfill(op.get_bind())
    print(f"  [RP backfill] {summary}")

    op.create_foreign_key("fk_accounts_primary_guarantor_patient_id", "accounts", "patients",
                          ["primary_guarantor_patient_id"], ["id"])
    op.create_foreign_key("fk_accounts_merged_into", "accounts", "accounts",
                          ["merged_into_account_id"], ["id"])
    op.create_foreign_key("fk_patients_account_id", "patients", "accounts", ["account_id"], ["id"])
    op.create_foreign_key("fk_patients_guarantor_patient_id", "patients", "patients",
                          ["guarantor_patient_id"], ["id"])
    op.create_foreign_key("fk_patients_guarantor_party_id", "patients", "responsible_parties",
                          ["guarantor_party_id"], ["id"])
    op.create_check_constraint("ck_patients_single_guarantor", "patients",
                               "guarantor_patient_id IS NULL OR guarantor_party_id IS NULL")
    op.create_foreign_key("fk_patient_payments_account_id", "patient_payments", "accounts",
                          ["account_id"], ["id"])
    op.create_foreign_key("fk_patient_statements_account_id", "patient_statements", "accounts",
                          ["account_id"], ["id"])
    op.create_unique_constraint("uq_accounts_tenant_account_no", "accounts",
                                ["tenant_id", "account_no"])
    op.create_index("ix_accounts_tenant_id", "accounts", ["tenant_id"])
    op.create_index("ix_accounts_tenant_legacy_key", "accounts", ["tenant_id", "legacy_key"])
    op.create_index("ix_accounts_primary_guarantor_patient_id", "accounts",
                    ["primary_guarantor_patient_id"])
    op.create_index("ix_accounts_primary_guarantor_party_id", "accounts",
                    ["primary_guarantor_party_id"])
    op.create_index("ix_patients_account_id", "patients", ["account_id"])
    op.create_index("ix_patients_guarantor_patient_id", "patients", ["guarantor_patient_id"])
    op.create_index("ix_patients_guarantor_party_id", "patients", ["guarantor_party_id"])
    op.create_index("ix_patient_payments_account_id", "patient_payments", ["account_id"])
    op.create_index("ix_patient_payments_account_payment_id", "patient_payments",
                    ["account_payment_id"])
    op.create_index("ix_patient_statements_account_id", "patient_statements", ["account_id"])


def downgrade() -> None:
    for name, table in (
        ("ix_patient_statements_account_id", "patient_statements"),
        ("ix_patient_payments_account_payment_id", "patient_payments"),
        ("ix_patient_payments_account_id", "patient_payments"),
        ("ix_patients_guarantor_party_id", "patients"),
        ("ix_patients_guarantor_patient_id", "patients"),
        ("ix_patients_account_id", "patients"),
    ):
        op.drop_index(name, table_name=table)
    op.drop_constraint("fk_patient_statements_account_id", "patient_statements", type_="foreignkey")
    op.drop_constraint("fk_patient_payments_account_id", "patient_payments", type_="foreignkey")
    op.drop_constraint("ck_patients_single_guarantor", "patients", type_="check")
    op.drop_constraint("fk_patients_guarantor_party_id", "patients", type_="foreignkey")
    op.drop_constraint("fk_patients_guarantor_patient_id", "patients", type_="foreignkey")
    op.drop_constraint("fk_patients_account_id", "patients", type_="foreignkey")
    with op.batch_alter_table("patient_statements") as b:
        b.drop_column("statement_scope")
        b.drop_column("account_id")
    with op.batch_alter_table("patient_payments") as b:
        b.drop_column("account_payment_id")
        b.drop_column("account_id")
    with op.batch_alter_table("patients") as b:
        b.drop_column("guarantor_party_id")
        b.drop_column("guarantor_patient_id")
        b.drop_column("account_id")
    op.drop_table("account_change_events")
    op.drop_table("account_parties")
    op.drop_table("accounts")
