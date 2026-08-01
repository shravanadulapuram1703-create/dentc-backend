"""add payment-plan (Ortho + Regular contract) gaps

Closes the schema half of docs/payment-plans/payment_plans_backend_devreport.md:

* ortho_plans   — OPP-1..8, OPP-10, OPP-11, PP-7 (two billing codes, preferred
  provider, insert class, patient-sub-plan setup date/notes/remarks, financial
  disclosure, tokenised payment method, per-tier print flags, a secondary
  insurance sub-plan symmetric with the primary, plan-level treatment duration,
  resolvable created/updated actors + created-at office).
* patient_payment_plans — RPP-1..4, RPP-6, PP-7 (treatment-plan amount + typed
  link, billing code, financial disclosure, tokenised payment method, total of
  payments, resolvable actors).
* patient_ins_payment_plans / patient_sec_ins_payment_plans — PP-6 (ortho_plan_id).
* patient_plan_installments — OPP-9 / RPP-5 (patient-side instalment store).
* PP-5 — composite indexes for the patient-balance aggregate.

Revision ID: e1f2a3b4c5d6
Revises: c0d1e2f3a4b6
Create Date: 2026-07-27

Additive: every column is nullable or carries a server default, and no existing
column is renamed or retyped, so the migration is safe on populated tenants.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "c0d1e2f3a4b6"
branch_labels = None
depends_on = None

_FALSE = sa.text("false")

# (name, type) — nullable columns added to ortho_plans.
_ORTHO_COLS = [
    # OPP-1: the Initial (banding/comprehensive) billing code. `procedure_code`
    # keeps its wire name and remains the *periodic* code.
    ("initial_procedure_code", sa.String(20)),
    ("pref_provider_id", sa.String(50)),          # OPP-2
    ("insert_class", sa.String(50)),              # OPP-3
    ("pat_setup_date", sa.Date()),                # OPP-4
    ("pat_notes", sa.Text()),
    ("remarks", sa.Text()),
    ("financial_disclosure", sa.String(100)),     # OPP-5
    # OPP-6 — tokenised payment method. No PAN, no CVV: card data lives in a
    # PCI-compliant vault and only the token reference is stored here.
    ("payment_code", sa.String(50)),
    ("payment_token_id", sa.String(100)),
    ("card_holder_name", sa.String(100)),
    ("card_last4", sa.String(4)),
    ("card_exp_month", sa.Integer()),
    ("card_exp_year", sa.Integer()),
    # OPP-7
    ("ins_mon_claim_print_fee", sa.Numeric(12, 2)),
    ("sec_ins_mon_claim_print_fee", sa.Numeric(12, 2)),
    # OPP-8 — secondary insurance sub-plan made symmetric with the primary.
    ("sec_ins_setup_date", sa.Date()),
    ("sec_ins_down_pay", sa.Numeric(12, 2)),
    ("sec_ins_interval", sa.String(20)),
    ("sec_ins_num_payments", sa.Integer()),
    ("sec_ins_rem_payments", sa.Integer()),
    ("sec_ins_rem_amt", sa.Numeric(12, 2)),
    ("sec_ins_first_due_date", sa.Date()),
    ("sec_ins_months_remaining", sa.Integer()),
    # OPP-10
    ("tx_duration_months", sa.Integer()),
    ("months_remaining", sa.Integer()),
    # OPP-11 / PP-7
    ("created_by_id", sa.Integer()),
    ("updated_by", sa.Integer()),
    ("created_office_id", sa.Integer()),
]

_ORTHO_BOOL_COLS = [
    "post_down_payment_with_card",       # OPP-6
    "ins_suppress_periodic_printing",    # OPP-7
    "sec_ins_suppress_periodic_printing",
]

_PLAN_COLS = [
    ("tx_plan_amt", sa.Numeric(12, 2)),        # RPP-1
    ("treatment_plan_id", sa.String(50)),      # RPP-1 (typed link)
    ("billing_code", sa.String(50)),           # RPP-2
    ("financial_disclosure", sa.String(100)),  # RPP-3
    ("payment_code", sa.String(50)),           # RPP-4 (see OPP-6)
    ("payment_token_id", sa.String(100)),
    ("card_holder_name", sa.String(100)),
    ("card_last4", sa.String(4)),
    ("card_exp_month", sa.Integer()),
    ("card_exp_year", sa.Integer()),
    ("total_of_payments", sa.Numeric(12, 2)),  # RPP-6
    ("created_by_id", sa.Integer()),           # PP-7
    ("updated_by", sa.Integer()),
]


def upgrade() -> None:
    # ── ortho_plans ──────────────────────────────────────────────────────────
    for name, type_ in _ORTHO_COLS:
        op.add_column("ortho_plans", sa.Column(name, type_, nullable=True))
    for name in _ORTHO_BOOL_COLS:
        op.add_column(
            "ortho_plans",
            sa.Column(name, sa.Boolean(), nullable=False, server_default=_FALSE),
        )
    op.create_foreign_key(
        "fk_ortho_plans_initial_procedure_code", "ortho_plans", "procedure_codes",
        ["initial_procedure_code"], ["code"],
    )
    op.create_foreign_key(
        "fk_ortho_plans_pref_provider", "ortho_plans", "providers",
        ["pref_provider_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_ortho_plans_created_by", "ortho_plans", "users", ["created_by_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_ortho_plans_updated_by", "ortho_plans", "users", ["updated_by"], ["id"]
    )
    op.create_foreign_key(
        "fk_ortho_plans_created_office", "ortho_plans", "offices",
        ["created_office_id"], ["id"],
    )

    # ── patient_payment_plans ────────────────────────────────────────────────
    for name, type_ in _PLAN_COLS:
        op.add_column("patient_payment_plans", sa.Column(name, type_, nullable=True))
    op.add_column(
        "patient_payment_plans",
        sa.Column(
            "post_down_payment_with_card", sa.Boolean(),
            nullable=False, server_default=_FALSE,
        ),
    )
    op.create_index(
        "ix_patient_payment_plans_treatment_plan_id", "patient_payment_plans", ["treatment_plan_id"]
    )
    op.create_foreign_key(
        "fk_patient_payment_plans_treatment_plan", "patient_payment_plans", "treatment_plans",
        ["treatment_plan_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_patient_payment_plans_created_by", "patient_payment_plans", "users",
        ["created_by_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_patient_payment_plans_updated_by", "patient_payment_plans", "users",
        ["updated_by"], ["id"],
    )

    # ── PP-6: tie an instalment row back to the contract that generated it ───
    for table in ("patient_ins_payment_plans", "patient_sec_ins_payment_plans"):
        op.add_column(table, sa.Column("ortho_plan_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{table}_ortho_plan_id", table, ["ortho_plan_id"])
        op.create_foreign_key(
            f"fk_{table}_ortho_plan", table, "ortho_plans", ["ortho_plan_id"], ["id"]
        )

    # ── OPP-9 / RPP-5: patient-side instalment store ─────────────────────────
    op.create_table(
        "patient_plan_installments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("plan_side", sa.String(10), nullable=False, server_default="patient"),
        sa.Column("ortho_plan_id", sa.Integer(), sa.ForeignKey("ortho_plans.id"), nullable=True),
        sa.Column(
            "payment_plan_id", sa.Integer(),
            sa.ForeignKey("patient_payment_plans.id"), nullable=True,
        ),
        sa.Column("periodic_order", sa.Integer(), nullable=True),
        sa.Column("periodic_date", sa.Date(), nullable=True),
        sa.Column("periodic_amt", sa.Numeric(12, 2), nullable=True),
        sa.Column("plan_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("down_payment", sa.Numeric(12, 2), nullable=True),
        sa.Column("rem_total_amt", sa.Numeric(12, 2), nullable=True),
        sa.Column("rem_payments", sa.Integer(), nullable=True),
        sa.Column("is_billed", sa.Boolean(), nullable=False, server_default=_FALSE),
        sa.Column("billing_code", sa.String(50), nullable=True),
        sa.Column("ledger_id", sa.String(50), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for column in ("tenant_id", "patient_id", "ortho_plan_id", "payment_plan_id"):
        op.create_index(
            f"ix_patient_plan_installments_{column}", "patient_plan_installments", [column]
        )

    # ── PP-5: the balance aggregate scans these two tables per patient ───────
    op.create_index(
        "ix_patient_procedures_patient_dos", "patient_procedures", ["patient_id", "date_of_service"]
    )
    op.create_index(
        "ix_patient_payments_patient_date", "patient_payments", ["patient_id", "payment_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_patient_payments_patient_date", table_name="patient_payments")
    op.drop_index("ix_patient_procedures_patient_dos", table_name="patient_procedures")

    op.drop_table("patient_plan_installments")

    for table in ("patient_ins_payment_plans", "patient_sec_ins_payment_plans"):
        op.drop_constraint(f"fk_{table}_ortho_plan", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_ortho_plan_id", table_name=table)
        op.drop_column(table, "ortho_plan_id")

    for constraint in (
        "fk_patient_payment_plans_updated_by", "fk_patient_payment_plans_created_by",
        "fk_patient_payment_plans_treatment_plan",
    ):
        op.drop_constraint(constraint, "patient_payment_plans", type_="foreignkey")
    op.drop_index("ix_patient_payment_plans_treatment_plan_id", table_name="patient_payment_plans")
    op.drop_column("patient_payment_plans", "post_down_payment_with_card")
    for name, _ in reversed(_PLAN_COLS):
        op.drop_column("patient_payment_plans", name)

    for constraint in (
        "fk_ortho_plans_created_office", "fk_ortho_plans_updated_by", "fk_ortho_plans_created_by",
        "fk_ortho_plans_pref_provider", "fk_ortho_plans_initial_procedure_code",
    ):
        op.drop_constraint(constraint, "ortho_plans", type_="foreignkey")
    for name in reversed(_ORTHO_BOOL_COLS):
        op.drop_column("ortho_plans", name)
    for name, _ in reversed(_ORTHO_COLS):
        op.drop_column("ortho_plans", name)
