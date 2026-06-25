"""add perio charting gaps (PERIO-BE-1/2/4/5/6)

Revision ID: f2c3d4e5a6b7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-23

Addresses the frontend periodontal-charting dev-report:
- PERIO-BE-4: ``perio_exam_details`` gains ``cal1..6`` (stored clinical
  attachment level, independent of the PD+FGM derivation).
- PERIO-BE-5: ``perio_exam_details`` gains audit columns ``created_at`` /
  ``updated_at`` / ``created_by`` / ``updated_by``.
- PERIO-BE-2: ``mobility_buccal`` / ``mobility_lingual`` widen INTEGER ->
  NUMERIC(2,1) so half-grades (0.5 / 1.5 / 2.5) persist.
- PERIO-BE-1: UNIQUE ``(exam_id, tooth_no)`` so a chart can't hold two rows for
  the same tooth. Pre-existing duplicates are first collapsed to the most recent
  (highest id) row — matching the "last write wins" upsert semantics.
- PERIO-BE-6: ``perio_exams`` gains ``updated_at`` / ``updated_by``.

Hand-written (scoped to perio tables only; autogenerate also flags unrelated,
pre-existing index-naming drift across the schema — out of scope here).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2c3d4e5a6b7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── PERIO-BE-4: cal1..6 ──────────────────────────────────────────────────
    for i in range(1, 7):
        op.add_column("perio_exam_details", sa.Column(f"cal{i}", sa.Integer(), nullable=True))

    # ── PERIO-BE-5: per-tooth audit columns ──────────────────────────────────
    op.add_column(
        "perio_exam_details",
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("perio_exam_details", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("perio_exam_details", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("perio_exam_details", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_perio_exam_details_created_by_users"),
        "perio_exam_details", "users", ["created_by"], ["id"],
    )
    op.create_foreign_key(
        op.f("fk_perio_exam_details_updated_by_users"),
        "perio_exam_details", "users", ["updated_by"], ["id"],
    )

    # ── PERIO-BE-2: mobility -> NUMERIC(2,1) (half-grades) ────────────────────
    op.alter_column(
        "perio_exam_details", "mobility_buccal",
        existing_type=sa.Integer(), type_=sa.Numeric(2, 1),
        existing_nullable=True, postgresql_using="mobility_buccal::numeric(2,1)",
    )
    op.alter_column(
        "perio_exam_details", "mobility_lingual",
        existing_type=sa.Integer(), type_=sa.Numeric(2, 1),
        existing_nullable=True, postgresql_using="mobility_lingual::numeric(2,1)",
    )

    # ── PERIO-BE-1: collapse duplicates, then enforce one row per tooth ───────
    op.execute(
        """
        DELETE FROM perio_exam_details a
        USING perio_exam_details b
        WHERE a.exam_id = b.exam_id
          AND a.tooth_no = b.tooth_no
          AND a.id < b.id
        """
    )
    op.create_unique_constraint(
        "uq_perio_exam_details_exam_id_tooth_no",
        "perio_exam_details", ["exam_id", "tooth_no"],
    )

    # ── PERIO-BE-6: exam attribution ─────────────────────────────────────────
    op.add_column("perio_exams", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("perio_exams", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_perio_exams_updated_by_users"),
        "perio_exams", "users", ["updated_by"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_perio_exams_updated_by_users"), "perio_exams", type_="foreignkey")
    op.drop_column("perio_exams", "updated_by")
    op.drop_column("perio_exams", "updated_at")

    op.drop_constraint(
        "uq_perio_exam_details_exam_id_tooth_no", "perio_exam_details", type_="unique"
    )
    op.alter_column(
        "perio_exam_details", "mobility_lingual",
        existing_type=sa.Numeric(2, 1), type_=sa.Integer(),
        existing_nullable=True, postgresql_using="mobility_lingual::integer",
    )
    op.alter_column(
        "perio_exam_details", "mobility_buccal",
        existing_type=sa.Numeric(2, 1), type_=sa.Integer(),
        existing_nullable=True, postgresql_using="mobility_buccal::integer",
    )
    op.drop_constraint(
        op.f("fk_perio_exam_details_updated_by_users"), "perio_exam_details", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_perio_exam_details_created_by_users"), "perio_exam_details", type_="foreignkey"
    )
    op.drop_column("perio_exam_details", "updated_by")
    op.drop_column("perio_exam_details", "created_by")
    op.drop_column("perio_exam_details", "updated_at")
    op.drop_column("perio_exam_details", "created_at")
    for i in range(1, 7):
        op.drop_column("perio_exam_details", f"cal{i}")
