"""add setup-screen gaps (PICK / NM / RX / MED / TB audit + filter columns)

Revision ID: f1a2b3c4d5e6
Revises: e945c28dd602
Create Date: 2026-06-17

Backs the frontend "Setup screens — backend dev report" (pick_list / notes-macros /
medical / prescriptions / custom-toolbar). Schema-side gaps only; pure registry
filters (NM-1 category, MED-1/TB-1 group_type, PICK-3 is_custom) need no migration.

- NM-4  : note_macros gains updated_at ("Modified On") + updated_by (FK users).
- RX-1  : prescription_library gains updated_by ("Modified By"; updated_at already
          present via TimestampMixin).
- PICK-3: questionnaire_headers gains is_custom (splits Manage vs Custom pick lists).
- PICK-1: questionnaire_options.questionnaire_id FK gains ON DELETE CASCADE so a
          hard header delete can't orphan items (the cascade endpoint soft-deletes
          the header but removes items; this keeps the DB consistent regardless).
- MED-3 : definitions gains input_type (typed questionnaire control).
- TB-3 / MED modified-by: definitions + definition_groups gain updated_at +
          updated_by; definition_groups.group_type widened 10 -> 20 to fit the
          feature markers (MEDALERT/MEDQUEST/DENTQUEST/TOOLBAR…).

Hand-written (autogenerate also picks up unrelated pre-existing index-naming drift
across the whole schema — out of scope here).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e945c28dd602"
branch_labels = None
depends_on = None

# The baseline schema was created from raw SQL, so this FK carries Postgres'
# default name (not the SQLAlchemy naming-convention name). Keep the same name on
# recreate so the constraint identity is stable across up/down.
_FK_QOPT = "questionnaire_options_questionnaire_id_fkey"


def upgrade() -> None:
    # NM-4 — note_macros audit columns.
    op.add_column("note_macros", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("note_macros", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_note_macros_updated_by_users"),
        "note_macros", "users", ["updated_by"], ["id"],
    )

    # RX-1 — prescription_library "Modified By".
    op.add_column("prescription_library", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_prescription_library_updated_by_users"),
        "prescription_library", "users", ["updated_by"], ["id"],
    )

    # PICK-3 — questionnaire_headers.is_custom (Manage vs Custom pick lists).
    op.add_column(
        "questionnaire_headers",
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # PICK-1 — questionnaire_options FK -> ON DELETE CASCADE (same name preserved).
    op.drop_constraint(_FK_QOPT, "questionnaire_options", type_="foreignkey")
    op.create_foreign_key(
        _FK_QOPT,
        "questionnaire_options", "questionnaire_headers",
        ["questionnaire_id"], ["id"], ondelete="CASCADE",
    )

    # MED-3 + TB-3 / MED modified-by — definitions.
    op.add_column("definitions", sa.Column("input_type", sa.String(length=20), nullable=True))
    op.add_column("definitions", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("definitions", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_definitions_updated_by_users"),
        "definitions", "users", ["updated_by"], ["id"],
    )

    # TB-3 — definition_groups audit + wider group_type.
    op.add_column("definition_groups", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("definition_groups", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_definition_groups_updated_by_users"),
        "definition_groups", "users", ["updated_by"], ["id"],
    )
    op.alter_column(
        "definition_groups", "group_type",
        existing_type=sa.String(length=10), type_=sa.String(length=20), existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "definition_groups", "group_type",
        existing_type=sa.String(length=20), type_=sa.String(length=10), existing_nullable=True,
    )
    op.drop_constraint(op.f("fk_definition_groups_updated_by_users"), "definition_groups", type_="foreignkey")
    op.drop_column("definition_groups", "updated_by")
    op.drop_column("definition_groups", "updated_at")

    op.drop_constraint(op.f("fk_definitions_updated_by_users"), "definitions", type_="foreignkey")
    op.drop_column("definitions", "updated_by")
    op.drop_column("definitions", "updated_at")
    op.drop_column("definitions", "input_type")

    op.drop_constraint(_FK_QOPT, "questionnaire_options", type_="foreignkey")
    op.create_foreign_key(
        _FK_QOPT,
        "questionnaire_options", "questionnaire_headers",
        ["questionnaire_id"], ["id"],
    )

    op.drop_column("questionnaire_headers", "is_custom")

    op.drop_constraint(op.f("fk_prescription_library_updated_by_users"), "prescription_library", type_="foreignkey")
    op.drop_column("prescription_library", "updated_by")

    op.drop_constraint(op.f("fk_note_macros_updated_by_users"), "note_macros", type_="foreignkey")
    op.drop_column("note_macros", "updated_at")
    op.drop_column("note_macros", "updated_by")
