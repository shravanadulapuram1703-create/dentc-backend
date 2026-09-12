"""Edit Insurance Plan from the patient screen — EDIT-PLAN-2/5/6/7/9.

Backs ``docs/patient-insurance/edit_insurance_plan_backend_devreport.md``.

- **EDIT-PLAN-5** ``insurance_plans.is_locked`` / ``locked_at`` / ``locked_by``.
  The rights catalog has carried ``setup_insurance_plans_screen_edit_locked_plan``
  since the Groups module, with no column for it to guard.

- **EDIT-PLAN-9** 31,334 of 31,335 migrated plans held NULL in the four coded
  PLAN-tab columns, so the wizard rendered the legacy defaults and the first
  FINISH persisted them — four audited "changes" the user never made. The
  columns are backfilled with exactly those defaults (``office_ucr`` /
  ``submit`` / ``ADA2024`` / ``unknown``), which is what every consumer was
  already treating NULL as. ``lifetime_ortho_benefits`` is **not** rewritten:
  the legacy dialog defaults it to true, but the Denticon export carries no
  such column, and flipping 31k rows would assert a benefit structure nobody
  confirmed — the model default changes for *new* rows only.

- **EDIT-PLAN-2/7** the usage counts behind the shared-plan banner were
  sequential scans: ``insurance_claims`` (96k rows) and ``patient_insurance``
  (55k) had no index on ``ins_plan_id``, nor did
  ``treatment_plan_insurance_details``. The requested
  ``insurance_plans (tenant_id, group_number)`` index has existed since
  ``e4f5a6b7c8d9``. ``insurance_claims`` carries no ``tenant_id`` (tenancy is
  through the patient), so the claim index is on ``ins_plan_id`` alone.

- **EDIT-PLAN-6** ``audit_logs (resource_type, resource_id)`` — the per-record
  history read (AUD-1, and now the per-plan history) filtered on both with an
  index on ``resource_type`` only.

Revision ID: 7f483f6833a7
Revises: 3cf1360c0100
Create Date: 2026-09-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "7f483f6833a7"
down_revision = "3cf1360c0100"
branch_labels = None
depends_on = None


#: EDIT-PLAN-9 — the legacy dialog defaults (``insurance_plan_service.PLAN_FIELD_DEFAULTS``).
_PLAN_FIELD_DEFAULTS = {
    "fees_to_print": "office_ucr",
    "claim_option": "submit",
    "form_to_print": "ADA2024",
    "network_type": "unknown",
}

_INDEXES = (
    ("ix_insurance_claims_ins_plan_id", "insurance_claims", ["ins_plan_id"]),
    ("ix_patient_insurance_ins_plan_id", "patient_insurance", ["ins_plan_id"]),
    ("ix_tp_insurance_details_ins_plan_id", "treatment_plan_insurance_details", ["ins_plan_id"]),
    ("ix_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"]),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── EDIT-PLAN-5: the lock ────────────────────────────────────────────────
    plan_cols = {c["name"] for c in inspector.get_columns("insurance_plans")}
    if "is_locked" not in plan_cols:
        op.add_column(
            "insurance_plans",
            sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "locked_at" not in plan_cols:
        op.add_column("insurance_plans", sa.Column("locked_at", sa.DateTime(), nullable=True))
    if "locked_by" not in plan_cols:
        op.add_column(
            "insurance_plans",
            sa.Column("locked_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )

    # ── EDIT-PLAN-9: NULL → legacy default on the four coded fields ──────────
    plans = sa.table(
        "insurance_plans",
        *[sa.column(name, sa.String()) for name in _PLAN_FIELD_DEFAULTS],
    )
    for name, value in _PLAN_FIELD_DEFAULTS.items():
        col = getattr(plans.c, name)
        op.execute(plans.update().where(col.is_(None)).values({name: value}))

    # ── EDIT-PLAN-2/6/7: the indexes ─────────────────────────────────────────
    for index_name, table, columns in _INDEXES:
        existing = {ix["name"] for ix in inspector.get_indexes(table)}
        if index_name not in existing:
            op.create_index(index_name, table, columns, unique=False)


def downgrade() -> None:
    for index_name, table, _ in reversed(_INDEXES):
        op.drop_index(index_name, table_name=table)
    # The backfilled defaults are left in place: NULL and the default were
    # already read identically, and un-writing them would re-create the
    # phantom-diff problem this revision closes.
    with op.batch_alter_table("insurance_plans") as batch:
        batch.drop_column("locked_by")
        batch.drop_column("locked_at")
        batch.drop_column("is_locked")
