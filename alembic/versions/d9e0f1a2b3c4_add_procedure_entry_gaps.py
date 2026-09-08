"""Procedure entry — one path for four screens (PROC-INT-1/2/5/9).

Backs ``docs/procedures/procedure_entry_integration.md``.

- **PROC-INT-1** ``patient_procedures.treatment_plan_item_id`` — the *item* a
  charge fulfilled. ``treatment_plan_id`` is plan-level, so every client was
  pairing a charge with its planned item by code + tooth + surface, and two
  identical open items collapsed to one key. Backfilled where the pairing is
  unambiguous: a live charge with a ``treatment_plan_id`` and exactly one
  matching open item in that plan (same code; item tooth/surface either equal
  or unset). Live data: 3 linked charges, 1 unambiguous match.

- **PROC-INT-2** ``treatment_plan_items.status`` gains ``completed`` (and
  ``scheduled``). The migration had already carried ``'Completed'`` (365 rows)
  and ``'Scheduled'`` (309) in the legacy capitalisation the enum rejected on
  PATCH; they are lower-cased in place, and ``'planned'`` (1 row, not a legacy
  value) folds into ``diagnosed``. Items linked by the backfill above are marked
  ``completed`` with ``end_date`` = the charge's service date.

- **PROC-INT-5** ``treatment_plan_items.quadrant`` / ``material_id`` mirror
  ``patient_procedures`` so a planned quadrant / lab procedure keeps what the
  pop-up captured.

- **PROC-INT-9** ``code_bundle_items.surface`` / ``quadrant`` and
  ``explosion_code_items.quadrant`` so the two template tables carry the same
  three anatomy fields.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-09-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── PROC-INT-1: item FK on the charge ────────────────────────────────────
    op.add_column(
        "patient_procedures",
        sa.Column("treatment_plan_item_id", sa.String(length=50), nullable=True),
    )
    op.create_foreign_key(
        "fk_patient_procedures_treatment_plan_item_id",
        "patient_procedures", "treatment_plan_items",
        ["treatment_plan_item_id"], ["id"],
    )
    op.create_index(
        "ix_patient_procedures_treatment_plan_item_id",
        "patient_procedures", ["treatment_plan_item_id"],
    )

    # ── PROC-INT-5: quadrant + material on the planned item ──────────────────
    op.add_column("treatment_plan_items", sa.Column("quadrant", sa.String(length=10), nullable=True))
    op.add_column("treatment_plan_items", sa.Column("material_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_treatment_plan_items_material_id",
        "treatment_plan_items", "chart_materials", ["material_id"], ["id"],
    )

    # ── PROC-INT-9: align the two template tables ────────────────────────────
    op.add_column("code_bundle_items", sa.Column("surface", sa.String(length=20), nullable=True))
    op.add_column("code_bundle_items", sa.Column("quadrant", sa.String(length=10), nullable=True))
    op.add_column("explosion_code_items", sa.Column("quadrant", sa.String(length=10), nullable=True))

    # ── PROC-INT-2: canonical status casing ──────────────────────────────────
    op.execute("UPDATE treatment_plan_items SET status = 'completed' WHERE status = 'Completed'")
    op.execute("UPDATE treatment_plan_items SET status = 'scheduled' WHERE status = 'Scheduled'")
    op.execute("UPDATE treatment_plan_items SET status = 'diagnosed' WHERE status = 'planned'")

    # ── PROC-INT-1 backfill: link where the pairing is unambiguous ───────────
    # Portable correlated-subquery SQL (runs on Postgres and SQLite alike).
    op.execute(
        """
        UPDATE patient_procedures
           SET treatment_plan_item_id = (
                SELECT i.id FROM treatment_plan_items i
                 WHERE i.plan_id = patient_procedures.treatment_plan_id
                   AND i.procedure_code = patient_procedures.procedure_code
                   AND i.is_archived = FALSE
                   AND (i.tooth IS NULL OR i.tooth = patient_procedures.tooth)
                   AND (i.surface IS NULL OR i.surface = patient_procedures.surface)
           )
         WHERE treatment_plan_id IS NOT NULL
           AND treatment_plan_item_id IS NULL
           AND is_void = FALSE
           AND (
                SELECT COUNT(*) FROM treatment_plan_items i
                 WHERE i.plan_id = patient_procedures.treatment_plan_id
                   AND i.procedure_code = patient_procedures.procedure_code
                   AND i.is_archived = FALSE
                   AND (i.tooth IS NULL OR i.tooth = patient_procedures.tooth)
                   AND (i.surface IS NULL OR i.surface = patient_procedures.surface)
           ) = 1
        """
    )
    op.execute(
        """
        UPDATE treatment_plan_items
           SET status = 'completed',
               end_date = COALESCE(
                   end_date,
                   (SELECT MIN(p.date_of_service) FROM patient_procedures p
                     WHERE p.treatment_plan_item_id = treatment_plan_items.id AND p.is_void = FALSE)
               )
         WHERE EXISTS (
                SELECT 1 FROM patient_procedures p
                 WHERE p.treatment_plan_item_id = treatment_plan_items.id AND p.is_void = FALSE
         )
        """
    )


def downgrade() -> None:
    # Status casing is not restored: the lower-case values are valid on both sides.
    op.drop_column("explosion_code_items", "quadrant")
    op.drop_column("code_bundle_items", "quadrant")
    op.drop_column("code_bundle_items", "surface")
    op.drop_constraint("fk_treatment_plan_items_material_id", "treatment_plan_items", type_="foreignkey")
    op.drop_column("treatment_plan_items", "material_id")
    op.drop_column("treatment_plan_items", "quadrant")
    op.drop_index("ix_patient_procedures_treatment_plan_item_id", table_name="patient_procedures")
    op.drop_constraint(
        "fk_patient_procedures_treatment_plan_item_id", "patient_procedures", type_="foreignkey"
    )
    op.drop_column("patient_procedures", "treatment_plan_item_id")
