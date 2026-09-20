"""Pricing hierarchy R1 — dated fees, one binding model, snapshot provenance.

Phase R1 of ``docs/pricing/pricing_hierarchy_architecture.md``: **additive only**.
It adds the columns and the constraints the new resolver needs, and normalises the
values that would violate them. It deliberately changes no price and deletes no
pricing tier — the resolver still walks the old order until
``PRICING_ENGINE_V2`` is switched on, and the eight legacy "practice-wide"
assignment rows stay until R3, because today they are the only tier that prices
anything at all (no real office has a fee pointer yet).

What it does, and why each piece is here
----------------------------------------
**Dated fees become possible.** ``fee_schedule_entries`` carried a unique on
``(fee_schedule_id, procedure_code)`` from the Denticon ``schema.sql`` — one price
per code per list, *forever*. So a second, later-dated row for the same code was
rejected by the database, which is why "Increase/Decrease" in Setup edits rows in
place (destroying the old price) and why ``effective_date`` was decorative. It is
replaced by ``(fee_schedule_id, procedure_code, effective_date)``, and
``effective_date`` becomes NOT NULL: it is half of the key, Postgres treats NULLs
as distinct, so leaving it nullable would keep exactly the duplicate rows the key
exists to prevent. All 13,493 existing rows already carry a date.

**Per-tenant legacy ids.** ``fee_schedules.legacy_id`` was globally unique, so two
tenants migrating the same Denticon ``FEEID`` collided in the database.
``fee_schedule_assignments`` had no key at all behind ``s51``'s
``ON CONFLICT DO NOTHING``, which is why two source rows are present four times
each. Both become unique per ``(tenant_id, legacy_id)``.

**The cross-tenant hole on entries.** ``fee_schedule_entries`` had no
``tenant_id``, and ``CRUDBase`` only scopes models that carry one, so
``/fee-schedule-entries/{id}`` was readable *and writable* across tenants. The
column is added and backfilled from the owning schedule.

**Snapshot provenance.** ``patient_procedures`` and ``treatment_plan_items`` gain
``fee_source`` / ``fee_effective_date`` / ``fee_override_reason`` / ``coverage_pct``
/ ``coverage_rule_id`` / ``estimated_deductible`` / ``sec_insurance_estimate`` (and
items gain ``ucr_fee``), so a posted line records *how* it was priced and is never
re-priced by a later Setup edit. New ``procedure_fee_provenance`` is the
write-once landing table for Denticon's ``LEDGERINSD`` (1,447,988 rows carrying
``FEEID`` + ``EFFECTIVEDATE``), which the migration discarded; it is kept out of
``ledger_insurance_details`` on purpose, because that table is the live payment
ledger and ``claim.total_paid`` is derived from it by *adding* rows to the migrated
baseline — loading history there would double every migrated claim's paid total.

**Secondary insurance becomes repairable.** ``patient_insurance.legacy_id`` gives
the repair script a deterministic key: ``s19`` read a ``BILLINGORDER`` column that
does not exist in ``PatInsPlans.txt`` (the real discriminator is ``INSTYPE``), made
every slot ``primary``, and let ``ON CONFLICT`` overwrite the 954 secondary rows.
Without a legacy key, re-pointing the wrong row would silently change which plan
is primary — i.e. which coverage rules price the patient.

What is deliberately deferred to R3
-----------------------------------
The ``fee_schedule_assignments`` has-a-target CHECK and a *total* unique index on
the key tuple cannot be created while the legacy all-keys-NULL rows exist, and
those rows may not be removed before the office and patient pointers are
backfilled. So the unique index created here is **partial** — it covers every row
that names a plan, carrier, provider or specialty, and tolerates the legacy ones
until R3 deletes them. ``FeeScheduleAssignmentCRUD`` refuses new targetless rows
from R1, so the exception cannot grow.

Data this revision touches (dev DB, verified before writing)
------------------------------------------------------------
* ``fee_type`` values ``office`` (4), ``provider`` (1) and NULL (1) are folded to
  ``standard``; ``ucr``/``plan``/``carrier`` are already canonical. This only makes
  the data satisfy the vocabulary — deciding *which* of the 13 rows labelled
  ``ucr`` are really UCR lists needs ``Office.FEEID`` from the export and belongs
  to ``scripts/backfill_pricing_hierarchy.py``.
* 6 redundant ``fee_schedule_assignments`` rows (two source rows imported four
  times each) are collapsed to the lowest id per ``(tenant_id, legacy_id)``. This
  does **not** change which schedule wins: the surviving ids are 1 (schedule 4) and
  2 (schedule 26), and the resolver's "newest row wins" tie-break picked schedule
  26 before (id 8) and picks schedule 26 after (id 2). The revision refuses to run
  if any duplicate group is not an exact duplicate.
* 5 entries carry a non-zero ``insurance_fee`` on a list that is not plan- or
  carrier-bound (2 on CP-40, 3 on two test lists). They are **reported, not
  rewritten**: the engine ignores ``insurance_fee`` on a percentage list, the CRUD
  guard only fires on a write to that field, and the pricing-health report lists
  them for the owner. Silently nulling a money column in a migration is worse than
  leaving a value nothing reads.

Revision ID: d4f1a9c7b3e2
Revises: 431b5da5630e
Create Date: 2026-09-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d4f1a9c7b3e2"
down_revision = "431b5da5630e"
branch_labels = None
depends_on = None

# Names of the legacy (Denticon schema.sql) constraints this revision replaces.
# They are Postgres-default names, not ours, so every drop is inspector-guarded.
_LEGACY_SCHEDULE_LEGACY_UNIQUE = "fee_schedules_legacy_id_key"
_LEGACY_ENTRY_CODE_UNIQUE = "fee_schedule_entries_fee_schedule_id_procedure_code_key"

_ENTRY_UNIQUE = "uq_fee_schedule_entries_schedule_code_date"
_SCHEDULE_UNIQUE = "uq_fee_schedules_tenant_legacy"
_ASSIGNMENT_LEGACY_UNIQUE = "uq_fee_schedule_assignments_tenant_legacy"
_ASSIGNMENT_TARGET_UNIQUE = "uq_fee_schedule_assignments_target"
_ENTRY_LOOKUP_INDEX = "ix_fee_schedule_entries_schedule_code_date"
#: ``fk_<table>_coverage_rule_id_insurance_coverage_rules`` would be 65 characters;
#: Postgres caps identifiers at 63, so both are named explicitly (and the models
#: name them the same way).
_COVERAGE_RULE_FK = {
    "patient_procedures": "fk_patient_procedures_coverage_rule",
    "treatment_plan_items": "fk_treatment_plan_items_coverage_rule",
}

#: Mirrors ``fee_vocab.FEE_TYPE_CODES`` / ``PRICING_MODEL_CODES`` /
#: ``UNPRICED_POLICY_CODES``. Duplicated as literals on purpose: models and
#: migrations in this repo never import from ``app.services``. A test asserts the
#: two stay in step.
def _in_list_literal(values: tuple[str, ...]) -> str:
    """``('a', 'b')`` as a SQL IN list. Values are module constants, never input."""
    return ", ".join(f"'{v}'" for v in values)


_FEE_TYPES = ("ucr", "standard", "plan", "carrier")
_PRICING_MODELS = ("percentage", "copay")
_UNPRICED_POLICIES = ("flag", "refuse")
#: ``fee_type`` values the un-validated API and the two frontends actually wrote.
_FEE_TYPE_ALIASES = {"office": "standard", "provider": "standard", "specialty": "standard"}

#: ``(constraint name, condition)`` — declared once so ``upgrade`` and
#: ``downgrade`` can never disagree about a name.
_CHECKS: tuple[tuple[str, str], ...] = (
    ("ck_fee_schedules_fee_type", f"fee_type IN ({_in_list_literal(_FEE_TYPES)})"),
    ("ck_fee_schedules_pricing_model", f"pricing_model IN ({_in_list_literal(_PRICING_MODELS)})"),
    (
        "ck_fee_schedules_pricing_model_needs_payer",
        "pricing_model = 'percentage' OR fee_type IN ('plan', 'carrier')",
    ),
    (
        "ck_offices_unpriced_charge_policy",
        f"unpriced_charge_policy IN ({_in_list_literal(_UNPRICED_POLICIES)})",
    ),
)
_CHECK_TABLES: dict[str, str] = {
    "ck_fee_schedules_fee_type": "fee_schedules",
    "ck_fee_schedules_pricing_model": "fee_schedules",
    "ck_fee_schedules_pricing_model_needs_payer": "fee_schedules",
    "ck_offices_unpriced_charge_policy": "offices",
}

#: The keys that make an assignment apply to a payer or a person. A row setting
#: none of them is a legacy "practice-wide" row (see the module docstring).
_RANK_KEYS = ("ins_plan_id", "carrier_id", "provider_id", "specialty_id")
_HAS_TARGET_SQL = " OR ".join(f"{key} IS NOT NULL" for key in _RANK_KEYS)


def _in_list(values: tuple[str, ...]) -> str:
    return _in_list_literal(values)


def _is_postgres(bind) -> bool:  # noqa: ANN001
    return bind.dialect.name == "postgresql"


def _unique_names(bind, table: str) -> set[str]:  # noqa: ANN001
    insp = sa.inspect(bind)
    names = {uc["name"] for uc in insp.get_unique_constraints(table)}
    names |= {ix["name"] for ix in insp.get_indexes(table) if ix.get("unique")}
    return {n for n in names if n}


def _columns(bind, table: str) -> set[str]:  # noqa: ANN001
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


# ── pre-flight ───────────────────────────────────────────────────────────────


def _preflight(bind) -> None:  # noqa: ANN001
    """Refuse to run rather than silently destroy or corrupt pricing data.

    Every check here was green on the dev DB when the revision was written; they
    exist so a different environment fails loudly instead of losing a price.
    """
    dup_entries = bind.execute(
        sa.text(
            "SELECT count(*) FROM (SELECT fee_schedule_id, procedure_code, effective_date "
            "FROM fee_schedule_entries GROUP BY 1, 2, 3 HAVING count(*) > 1) d"
        )
    ).scalar_one()
    if dup_entries:
        raise RuntimeError(
            f"{dup_entries} (fee_schedule_id, procedure_code, effective_date) groups are "
            "duplicated in fee_schedule_entries. Deduplicate them deliberately (keeping the "
            "price you mean to keep, with an audit record) before adding the unique key — "
            "this revision will not delete a fee for you."
        )

    # A duplicate legacy assignment is only safe to collapse when the rows are
    # genuinely identical. If two rows share a legacy id but bind different
    # schedules or different targets, one of them means something.
    key_tuple = ", ".join(
        ["fee_schedule_id"] + [f"COALESCE(CAST({k} AS TEXT), '')" for k in _RANK_KEYS]
        + ["COALESCE(CAST(office_id AS TEXT), '')", "COALESCE(CAST(office_group_id AS TEXT), '')"]
    )
    divergent = bind.execute(
        sa.text(
            "SELECT count(*) FROM (SELECT tenant_id, legacy_id "
            "FROM fee_schedule_assignments WHERE legacy_id IS NOT NULL "
            f"GROUP BY 1, 2 HAVING count(DISTINCT ({key_tuple})) > 1) d"
        )
    ).scalar_one()
    if divergent:
        raise RuntimeError(
            f"{divergent} (tenant_id, legacy_id) groups in fee_schedule_assignments hold rows "
            "that bind different schedules or targets. Resolve them by hand before this "
            "revision collapses duplicates."
        )


# ── upgrade ──────────────────────────────────────────────────────────────────


def upgrade() -> None:
    bind = op.get_bind()
    _preflight(bind)

    # ── 1. new columns (all nullable or defaulted: no table rewrite, no lock) ─
    op.add_column(
        "fee_schedules",
        sa.Column(
            "pricing_model", sa.String(length=12),
            server_default="percentage", nullable=False,
        ),
    )

    op.add_column("fee_schedule_entries", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_fee_schedule_entries_tenant_id_tenants",
        "fee_schedule_entries", "tenants", ["tenant_id"], ["id"],
    )
    op.create_index("ix_fee_schedule_entries_tenant_id", "fee_schedule_entries", ["tenant_id"])
    op.add_column(
        "fee_schedule_entries",
        sa.Column("is_no_charge", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("fee_schedule_entries", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("fee_schedule_entries", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("fee_schedule_entries", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_fee_schedule_entries_created_by_users",
        "fee_schedule_entries", "users", ["created_by"], ["id"],
    )
    op.create_foreign_key(
        "fk_fee_schedule_entries_updated_by_users",
        "fee_schedule_entries", "users", ["updated_by"], ["id"],
    )
    op.create_index(
        "ix_fee_schedule_entries_procedure_code", "fee_schedule_entries", ["procedure_code"]
    )

    op.add_column("fee_schedule_assignments", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("fee_schedule_assignments", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_fee_schedule_assignments_updated_by_users",
        "fee_schedule_assignments", "users", ["updated_by"], ["id"],
    )
    op.create_index(
        "ix_fee_schedule_assignments_carrier_id", "fee_schedule_assignments", ["carrier_id"]
    )

    op.add_column(
        "offices",
        sa.Column(
            "unpriced_charge_policy", sa.String(length=10),
            server_default="flag", nullable=False,
        ),
    )

    op.add_column("patient_insurance", sa.Column("legacy_id", sa.String(length=50), nullable=True))
    op.create_index("ix_patient_insurance_legacy_id", "patient_insurance", ["legacy_id"])

    op.add_column(
        "insurance_plans",
        sa.Column("is_non_dup_benefits", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "insurance_plans", sa.Column("legacy_prepaid_code", sa.String(length=5), nullable=True)
    )

    # Provenance + split snapshot on both priced rows.
    for table, money in (("patient_procedures", 12), ("treatment_plan_items", 10)):
        op.add_column(table, sa.Column("fee_source", sa.String(length=24), nullable=True))
        op.add_column(table, sa.Column("fee_effective_date", sa.Date(), nullable=True))
        op.add_column(table, sa.Column("fee_override_reason", sa.String(length=255), nullable=True))
        op.add_column(table, sa.Column("coverage_pct", sa.Numeric(5, 2), nullable=True))
        op.add_column(table, sa.Column("coverage_rule_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("estimated_deductible", sa.Numeric(money, 2), nullable=True))
        op.add_column(table, sa.Column("sec_insurance_estimate", sa.Numeric(money, 2), nullable=True))
        # Short, explicit name: the repo's convention would generate 65
        # characters here and Postgres caps identifiers at 63.
        op.create_foreign_key(
            _COVERAGE_RULE_FK[table],
            table, "insurance_coverage_rules", ["coverage_rule_id"], ["id"],
        )
    # A plan item had no UCR figure at all, so a charge posted from a plan could
    # never produce a contractual write-off.
    op.add_column("treatment_plan_items", sa.Column("ucr_fee", sa.Numeric(10, 2), nullable=True))

    op.create_table(
        "procedure_fee_provenance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("procedure_id", sa.String(length=50), nullable=False),
        sa.Column("fee_schedule_id", sa.Integer(), nullable=True),
        sa.Column("fee_schedule_legacy_id", sa.String(length=20), nullable=True),
        sa.Column("fee_effective_date", sa.Date(), nullable=True),
        sa.Column("legacy_ledger_id", sa.String(length=50), nullable=True),
        sa.Column("contracted_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("prim_ins_plan_legacy_id", sa.String(length=20), nullable=True),
        sa.Column("prim_estimated", sa.Numeric(12, 2), nullable=True),
        sa.Column("prim_deductible", sa.Numeric(12, 2), nullable=True),
        sa.Column("prim_max_consumed", sa.Numeric(12, 2), nullable=True),
        sa.Column("sec_estimated", sa.Numeric(12, 2), nullable=True),
        sa.Column("sec_deductible", sa.Numeric(12, 2), nullable=True),
        sa.Column("ter_estimated", sa.Numeric(12, 2), nullable=True),
        sa.Column("ter_deductible", sa.Numeric(12, 2), nullable=True),
        sa.Column("quad_estimated", sa.Numeric(12, 2), nullable=True),
        sa.Column("quad_deductible", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fee_schedule_id"], ["fee_schedules.id"],
            name="fk_procedure_fee_provenance_fee_schedule_id_fee_schedules",
        ),
        sa.ForeignKeyConstraint(
            ["procedure_id"], ["patient_procedures.id"],
            name="fk_procedure_fee_provenance_procedure_id_patient_procedures",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_procedure_fee_provenance"),
        sa.UniqueConstraint("procedure_id", name="uq_procedure_fee_provenance_procedure"),
    )
    op.create_index(
        "ix_procedure_fee_provenance_procedure_id",
        "procedure_fee_provenance", ["procedure_id"],
    )
    op.create_index(
        "ix_procedure_fee_provenance_legacy_ledger_id",
        "procedure_fee_provenance", ["legacy_ledger_id"],
    )
    op.create_index(
        "ix_procedure_fee_provenance_schedule",
        "procedure_fee_provenance", ["fee_schedule_id"],
    )

    # ── 2. normalise the values that would violate the new constraints ───────
    # ``fee_type`` onto the vocabulary. Keyed on the *value*, never on legacy_id,
    # so no tenant predicate is needed (and none of these UPDATEs can reach
    # another tenant's rows).
    op.execute(sa.text("UPDATE fee_schedules SET fee_type = lower(trim(fee_type)) WHERE fee_type IS NOT NULL"))
    for alias, canonical in _FEE_TYPE_ALIASES.items():
        op.execute(
            sa.text(f"UPDATE fee_schedules SET fee_type = '{canonical}' WHERE fee_type = '{alias}'")
        )
    op.execute(
        sa.text(
            "UPDATE fee_schedules SET fee_type = 'standard' "
            f"WHERE fee_type IS NULL OR fee_type = '' OR fee_type NOT IN ({_in_list(_FEE_TYPES)})"
        )
    )

    # Entries inherit the owning schedule's tenant (one statement; 13,493 rows).
    op.execute(
        sa.text(
            "UPDATE fee_schedule_entries e SET tenant_id = fs.tenant_id "
            "FROM fee_schedules fs WHERE fs.id = e.fee_schedule_id AND e.tenant_id IS NULL"
        )
        if _is_postgres(bind)
        else sa.text(
            "UPDATE fee_schedule_entries SET tenant_id = ("
            "SELECT fs.tenant_id FROM fee_schedules fs WHERE fs.id = fee_schedule_id"
            ") WHERE tenant_id IS NULL"
        )
    )

    # ``effective_date`` becomes NOT NULL. Nothing is NULL today; the defensive
    # fallback is an open-ended past date so such a row would price every date of
    # service rather than none.
    op.execute(
        sa.text(
            "UPDATE fee_schedule_entries SET effective_date = "
            "COALESCE((SELECT fs.effective_date FROM fee_schedules fs WHERE fs.id = fee_schedule_id), "
            "DATE '1900-01-01') WHERE effective_date IS NULL"
        )
    )

    # ── 3. collapse the duplicated legacy assignment rows ────────────────────
    # Two source rows imported four times each (``s51``'s ON CONFLICT had no key
    # to conflict on). Keeping the lowest id per legacy id leaves one row per
    # source row and does not change which schedule the resolver picks.
    op.execute(
        sa.text(
            "DELETE FROM fee_schedule_assignments WHERE legacy_id IS NOT NULL AND id NOT IN ("
            "SELECT min(id) FROM fee_schedule_assignments WHERE legacy_id IS NOT NULL "
            "GROUP BY tenant_id, legacy_id)"
        )
    )

    # ── 4. constraints ───────────────────────────────────────────────────────
    existing_schedule = _unique_names(bind, "fee_schedules")
    if _LEGACY_SCHEDULE_LEGACY_UNIQUE in existing_schedule:
        op.drop_constraint(_LEGACY_SCHEDULE_LEGACY_UNIQUE, "fee_schedules", type_="unique")
    if _SCHEDULE_UNIQUE not in existing_schedule:
        op.create_unique_constraint(_SCHEDULE_UNIQUE, "fee_schedules", ["tenant_id", "legacy_id"])

    existing_entry = _unique_names(bind, "fee_schedule_entries")
    if _LEGACY_ENTRY_CODE_UNIQUE in existing_entry:
        # This is what made a dated price list impossible.
        op.drop_constraint(_LEGACY_ENTRY_CODE_UNIQUE, "fee_schedule_entries", type_="unique")
    op.alter_column(
        "fee_schedule_entries", "effective_date",
        existing_type=sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE"),
    )
    if _ENTRY_UNIQUE not in existing_entry:
        op.create_unique_constraint(
            _ENTRY_UNIQUE, "fee_schedule_entries",
            ["fee_schedule_id", "procedure_code", "effective_date"],
        )
    # The resolver's hot path: newest fee on or before a date of service.
    op.create_index(
        _ENTRY_LOOKUP_INDEX, "fee_schedule_entries",
        ["fee_schedule_id", "procedure_code", sa.text("effective_date DESC")],
    )

    if _ASSIGNMENT_LEGACY_UNIQUE not in _unique_names(bind, "fee_schedule_assignments"):
        op.create_unique_constraint(
            _ASSIGNMENT_LEGACY_UNIQUE, "fee_schedule_assignments", ["tenant_id", "legacy_id"]
        )

    if _is_postgres(bind):
        # One binding per target tuple. **Partial**: the legacy targetless rows are
        # excluded so they can survive until R3 (they are the only tier pricing
        # anything today), while every row a user can now author is covered.
        op.execute(
            sa.text(
                f"CREATE UNIQUE INDEX {_ASSIGNMENT_TARGET_UNIQUE} ON fee_schedule_assignments ("
                "tenant_id, COALESCE(ins_plan_id, 0), COALESCE(carrier_id, 0), "
                "COALESCE(provider_id, ''), COALESCE(specialty_id, ''), "
                "COALESCE(office_id, 0), COALESCE(office_group_id, 0)"
                f") WHERE {_HAS_TARGET_SQL}"
            )
        )
        # Vocabulary CHECKs. ``pricing_model='copay'`` is only reachable through a
        # payer tier, so it is restricted to plan-/carrier-bound lists.
        #
        # Emitted as explicit DDL rather than ``op.create_check_constraint``: that
        # helper applies ``Base.metadata``'s naming convention only when the
        # migration context was configured with ``target_metadata``, so the same
        # call produces ``ck_fee_schedules_fee_type`` under ``alembic upgrade`` and
        # a bare ``fee_type`` under a bare context — and then ``downgrade`` cannot
        # find what ``upgrade`` created. Naming them here is unambiguous.
        for constraint, condition in _CHECKS:
            table = _CHECK_TABLES[constraint]
            op.execute(
                sa.text(f"ALTER TABLE {table} ADD CONSTRAINT {constraint} CHECK ({condition})")
            )
        # NOTE: the ``fee_schedule_assignments`` has-a-target CHECK is deliberately
        # NOT added here — the legacy targetless rows would fail it. R3 deletes
        # those (once office and patient pointers exist) and adds the CHECK.
        # ``FeeScheduleAssignmentCRUD`` refuses new ones from R1.


# ── downgrade ────────────────────────────────────────────────────────────────


def downgrade() -> None:
    bind = op.get_bind()

    if _is_postgres(bind):
        for constraint, _ in reversed(_CHECKS):
            op.execute(
                sa.text(
                    f"ALTER TABLE {_CHECK_TABLES[constraint]} "
                    f"DROP CONSTRAINT IF EXISTS {constraint}"
                )
            )
        op.execute(sa.text(f"DROP INDEX IF EXISTS {_ASSIGNMENT_TARGET_UNIQUE}"))

    existing = _unique_names(bind, "fee_schedule_assignments")
    if _ASSIGNMENT_LEGACY_UNIQUE in existing:
        op.drop_constraint(_ASSIGNMENT_LEGACY_UNIQUE, "fee_schedule_assignments", type_="unique")

    op.drop_index(_ENTRY_LOOKUP_INDEX, table_name="fee_schedule_entries")
    existing = _unique_names(bind, "fee_schedule_entries")
    if _ENTRY_UNIQUE in existing:
        op.drop_constraint(_ENTRY_UNIQUE, "fee_schedule_entries", type_="unique")
    op.alter_column(
        "fee_schedule_entries", "effective_date",
        existing_type=sa.Date(), nullable=True, server_default=None,
    )
    # Restore the legacy shape only if it can hold: dated rows added since this
    # revision would make one price per (list, code) impossible, and that is the
    # whole point of the change, so a failure here is informative.
    if _LEGACY_ENTRY_CODE_UNIQUE not in existing:
        op.create_unique_constraint(
            _LEGACY_ENTRY_CODE_UNIQUE, "fee_schedule_entries",
            ["fee_schedule_id", "procedure_code"],
        )

    existing = _unique_names(bind, "fee_schedules")
    if _SCHEDULE_UNIQUE in existing:
        op.drop_constraint(_SCHEDULE_UNIQUE, "fee_schedules", type_="unique")
    if _LEGACY_SCHEDULE_LEGACY_UNIQUE not in existing:
        op.create_unique_constraint(
            _LEGACY_SCHEDULE_LEGACY_UNIQUE, "fee_schedules", ["legacy_id"]
        )

    op.drop_index("ix_procedure_fee_provenance_schedule", table_name="procedure_fee_provenance")
    op.drop_index(
        "ix_procedure_fee_provenance_legacy_ledger_id",
        table_name="procedure_fee_provenance",
    )
    op.drop_index(
        "ix_procedure_fee_provenance_procedure_id",
        table_name="procedure_fee_provenance",
    )
    op.drop_table("procedure_fee_provenance")

    op.drop_column("treatment_plan_items", "ucr_fee")
    for table in ("treatment_plan_items", "patient_procedures"):
        op.drop_constraint(_COVERAGE_RULE_FK[table], table, type_="foreignkey")
        for column in (
            "sec_insurance_estimate", "estimated_deductible", "coverage_rule_id",
            "coverage_pct", "fee_override_reason", "fee_effective_date", "fee_source",
        ):
            op.drop_column(table, column)

    op.drop_column("insurance_plans", "legacy_prepaid_code")
    op.drop_column("insurance_plans", "is_non_dup_benefits")

    op.drop_index("ix_patient_insurance_legacy_id", table_name="patient_insurance")
    op.drop_column("patient_insurance", "legacy_id")

    op.drop_column("offices", "unpriced_charge_policy")

    op.drop_index("ix_fee_schedule_assignments_carrier_id", table_name="fee_schedule_assignments")
    op.drop_constraint(
        "fk_fee_schedule_assignments_updated_by_users", "fee_schedule_assignments", type_="foreignkey"
    )
    op.drop_column("fee_schedule_assignments", "updated_by")
    op.drop_column("fee_schedule_assignments", "updated_at")

    op.drop_index("ix_fee_schedule_entries_procedure_code", table_name="fee_schedule_entries")
    op.drop_constraint(
        "fk_fee_schedule_entries_updated_by_users", "fee_schedule_entries", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_fee_schedule_entries_created_by_users", "fee_schedule_entries", type_="foreignkey"
    )
    op.drop_column("fee_schedule_entries", "updated_by")
    op.drop_column("fee_schedule_entries", "created_by")
    op.drop_column("fee_schedule_entries", "updated_at")
    op.drop_column("fee_schedule_entries", "is_no_charge")
    op.drop_index("ix_fee_schedule_entries_tenant_id", table_name="fee_schedule_entries")
    op.drop_constraint(
        "fk_fee_schedule_entries_tenant_id_tenants", "fee_schedule_entries", type_="foreignkey"
    )
    op.drop_column("fee_schedule_entries", "tenant_id")

    op.drop_column("fee_schedules", "pricing_model")
