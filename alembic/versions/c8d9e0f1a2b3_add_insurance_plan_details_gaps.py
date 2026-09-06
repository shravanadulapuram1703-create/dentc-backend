"""Insurance Plan Details wizard — PLAN-DTL-1/2/3/5/6/9.

Backs ``docs/patient-insurance/insurance_plan_details_backend_devreport.md``.

- **PLAN-DTL-1** nine PLAN/BENEFITS-tab fields had no column on
  ``insurance_plans`` (``fees_to_print``, ``claim_option``, ``form_to_print``,
  ``reporting_subtype``, ``network_type``, ``noa_only``, ``per_visit_copay``,
  ``lifetime_ortho_benefits``, ``plan_notes``), so the wizard was keeping them
  in browser localStorage per plan id — they did not follow the plan to another
  workstation, and COPY FROM EXISTING only copied them on the same browser.

- **PLAN-DTL-3** the legacy dialog captures the anniversary as Month/Day;
  ``anniversary_month``/``anniversary_day`` are the typed pair, backfilled from
  the full date (which stays — the migrated data carries it).

- **PLAN-DTL-5** ``insurance_coverage_rules.freq_limit`` is converted **in
  place** to INTEGER: every one of the 876,764 live values is a numeric string
  (``'0'`` 580k, ``'12'`` 38k, ``'9'`` 25k, …), so nothing is lost. The age and
  waiting-period limits get typed columns (``age_min``/``age_max``/
  ``wait_months``) and the strings stay as derived mirrors. Backfill rules:
  ``"5-14"`` splits; a lone number on a **migrated** row (``legacy_id`` set) is
  the legacy *maximum* — Denticon's AGELIMIT is a single upper bound, and the
  observed values (19, 16, 13, 14, 18, 26) are exactly the child/dependent
  cut-offs — while on an app-written row it is the wizard's *minimum* (its own
  encoding); ``'0'`` means none. A non-numeric wait period (one row: ``'10
  days'``) keeps its string and gets NULL months rather than a guess.

- **PLAN-DTL-2** new ``insurance_plan_frequency_groups``; the reserved-shape
  ``category='FREQGRP'`` coverage rows the frontend had been writing are moved
  across and removed from the coverage table.

- **PLAN-DTL-6** ``definitions`` was inserted once per migration pass — the
  importer's ``ON CONFLICT DO NOTHING`` had no key to conflict on — leaving
  1,144 exact-duplicate rows (identical on every column including
  ``legacy_id``) across 286 ``(tenant_id, group_code, key1, description)``
  groups. Lowest id survives (no table references ``definitions.id``), and the
  unique constraint stops it recurring.

- **PLAN-DTL-9** ``updated_at``/``updated_by``/``created_by`` on coverage
  rules (plans have had them since ``e4f5a6b7c8d9``).

Revision ID: c8d9e0f1a2b3
Revises: a2b3c4d5e6f7
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


_PLAN_COLUMNS = (
    sa.Column("anniversary_month", sa.Integer(), nullable=True),
    sa.Column("anniversary_day", sa.Integer(), nullable=True),
    sa.Column("fees_to_print", sa.String(20), nullable=True),
    sa.Column("claim_option", sa.String(20), nullable=True),
    sa.Column("form_to_print", sa.String(20), nullable=True),
    sa.Column("reporting_subtype", sa.String(50), nullable=True),
    sa.Column("network_type", sa.String(20), nullable=True),
    sa.Column("noa_only", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("per_visit_copay", sa.Numeric(10, 2), nullable=True),
    sa.Column("lifetime_ortho_benefits", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("plan_notes", sa.Text(), nullable=True),
)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # ── PLAN-DTL-1 / PLAN-DTL-3 ──────────────────────────────────────────────
    for col in _PLAN_COLUMNS:
        op.add_column("insurance_plans", col)
    if is_pg:
        op.execute(
            "UPDATE insurance_plans SET anniversary_month = EXTRACT(MONTH FROM anniversary_date)::int, "
            "anniversary_day = EXTRACT(DAY FROM anniversary_date)::int "
            "WHERE anniversary_date IS NOT NULL"
        )

    # ── PLAN-DTL-9: audit pair on coverage rules ─────────────────────────────
    op.add_column("insurance_coverage_rules", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("insurance_coverage_rules", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("insurance_coverage_rules", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_insurance_coverage_rules_created_by_users",
        "insurance_coverage_rules", "users", ["created_by"], ["id"],
    )
    op.create_foreign_key(
        "fk_insurance_coverage_rules_updated_by_users",
        "insurance_coverage_rules", "users", ["updated_by"], ["id"],
    )

    # ── PLAN-DTL-5: typed limits ─────────────────────────────────────────────
    op.add_column("insurance_coverage_rules", sa.Column("age_min", sa.Integer(), nullable=True))
    op.add_column("insurance_coverage_rules", sa.Column("age_max", sa.Integer(), nullable=True))
    op.add_column("insurance_coverage_rules", sa.Column("wait_months", sa.Integer(), nullable=True))
    if is_pg:
        # freq_limit: every live value is a numeric string; anything else (none
        # today) becomes NULL rather than aborting the migration.
        op.execute(
            "ALTER TABLE insurance_coverage_rules ALTER COLUMN freq_limit TYPE INTEGER "
            "USING (CASE WHEN freq_limit ~ '^\\d+$' THEN freq_limit::integer ELSE NULL END)"
        )
        # "min-max"
        op.execute(
            "UPDATE insurance_coverage_rules SET "
            "age_min = NULLIF(split_part(age_limit, '-', 1), '')::int, "
            "age_max = NULLIF(split_part(age_limit, '-', 2), '')::int "
            "WHERE age_limit ~ '^\\d+\\s*-\\s*\\d+$'"
        )
        op.execute(
            "UPDATE insurance_coverage_rules SET age_min = NULLIF(age_min, 0), age_max = NULLIF(age_max, 0) "
            "WHERE age_min = 0 OR age_max = 0"
        )
        # lone number: legacy maximum on migrated rows, wizard minimum on app rows.
        op.execute(
            "UPDATE insurance_coverage_rules SET age_max = age_limit::int "
            "WHERE legacy_id IS NOT NULL AND age_limit ~ '^\\d+$' AND age_limit <> '0'"
        )
        op.execute(
            "UPDATE insurance_coverage_rules SET age_min = age_limit::int "
            "WHERE legacy_id IS NULL AND age_limit ~ '^\\d+$' AND age_limit <> '0'"
        )
        # Re-derive the mirror so it is canonical ("min-max" / "min" / NULL).
        op.execute(
            "UPDATE insurance_coverage_rules SET age_limit = CASE "
            "WHEN age_min IS NULL AND age_max IS NULL THEN NULL "
            "WHEN age_max IS NULL THEN age_min::text "
            "ELSE COALESCE(age_min, 0)::text || '-' || age_max::text END "
            "WHERE age_limit IS NOT NULL AND category IS DISTINCT FROM 'FREQGRP'"
        )
        op.execute(
            "UPDATE insurance_coverage_rules SET wait_months = NULLIF(wait_period::int, 0) "
            "WHERE wait_period ~ '^\\d+$'"
        )
        op.execute(
            "UPDATE insurance_coverage_rules SET wait_period = wait_months::text "
            "WHERE wait_period ~ '^\\d+$'"
        )
    else:  # SQLite (tests): no data to convert, just retype.
        with op.batch_alter_table("insurance_coverage_rules") as batch:
            batch.alter_column("freq_limit", type_=sa.Integer(), existing_type=sa.String(50))

    # ── PLAN-DTL-2: frequency code groups ────────────────────────────────────
    op.create_table(
        "insurance_plan_frequency_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("ins_plan_id", sa.Integer(), sa.ForeignKey("insurance_plans.id"), nullable=False),
        sa.Column("code_group", sa.String(20), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("freq_limit", sa.Integer(), nullable=True),
        sa.Column("whole_mouth", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("per_day_quantity", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("ins_plan_id", "code_group", name="uq_plan_frequency_groups_plan_code"),
    )
    op.create_index(
        "ix_insurance_plan_frequency_groups_tenant_id",
        "insurance_plan_frequency_groups", ["tenant_id"],
    )
    op.create_index(
        "ix_insurance_plan_frequency_groups_ins_plan_id",
        "insurance_plan_frequency_groups", ["ins_plan_id"],
    )
    op.create_index(
        "ix_plan_frequency_groups_tenant_plan",
        "insurance_plan_frequency_groups", ["tenant_id", "ins_plan_id"],
    )
    if is_pg:
        # Move the FREQGRP-convention rows (start_code "FQ<code>", whole mouth
        # as age_limit "WM", per-day quantity in wait_period) into the table.
        op.execute(
            "INSERT INTO insurance_plan_frequency_groups "
            "(tenant_id, ins_plan_id, code_group, description, freq_limit, whole_mouth, per_day_quantity, created_at) "
            "SELECT DISTINCT ON (r.ins_plan_id, substring(r.start_code from 3)) "
            "p.tenant_id, r.ins_plan_id, substring(r.start_code from 3), r.description, "
            "NULLIF(r.freq_limit, 0), (r.age_limit = 'WM'), "
            "CASE WHEN r.wait_period ~ '^\\d+$' THEN NULLIF(r.wait_period::int, 0) END, r.created_at "
            "FROM insurance_coverage_rules r JOIN insurance_plans p ON p.id = r.ins_plan_id "
            "WHERE (r.category = 'FREQGRP' OR r.start_code ILIKE 'FQ%') "
            "AND substring(r.start_code from 3) <> '' "
            "ORDER BY r.ins_plan_id, substring(r.start_code from 3), r.id"
        )
        op.execute(
            "DELETE FROM insurance_coverage_rules WHERE category = 'FREQGRP' OR start_code ILIKE 'FQ%'"
        )

    # ── PLAN-DTL-6: collapse duplicate definitions, then make it impossible ──
    if is_pg:
        op.execute(
            "DELETE FROM definitions d USING definitions k "
            "WHERE k.tenant_id = d.tenant_id AND k.group_code = d.group_code "
            "AND k.key1 = d.key1 AND k.description = d.description AND k.id < d.id"
        )
    op.create_unique_constraint(
        "uq_definitions_tenant_group_key_description",
        "definitions", ["tenant_id", "group_code", "key1", "description"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_definitions_tenant_group_key_description", "definitions", type_="unique")

    op.drop_index("ix_plan_frequency_groups_tenant_plan", table_name="insurance_plan_frequency_groups")
    op.drop_index("ix_insurance_plan_frequency_groups_ins_plan_id", table_name="insurance_plan_frequency_groups")
    op.drop_index("ix_insurance_plan_frequency_groups_tenant_id", table_name="insurance_plan_frequency_groups")
    op.drop_table("insurance_plan_frequency_groups")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE insurance_coverage_rules ALTER COLUMN freq_limit TYPE VARCHAR(50) USING freq_limit::text")
    op.drop_column("insurance_coverage_rules", "wait_months")
    op.drop_column("insurance_coverage_rules", "age_max")
    op.drop_column("insurance_coverage_rules", "age_min")
    op.drop_constraint("fk_insurance_coverage_rules_updated_by_users", "insurance_coverage_rules", type_="foreignkey")
    op.drop_constraint("fk_insurance_coverage_rules_created_by_users", "insurance_coverage_rules", type_="foreignkey")
    op.drop_column("insurance_coverage_rules", "updated_by")
    op.drop_column("insurance_coverage_rules", "created_by")
    op.drop_column("insurance_coverage_rules", "updated_at")

    for col in reversed(_PLAN_COLUMNS):
        op.drop_column("insurance_plans", col.name)
