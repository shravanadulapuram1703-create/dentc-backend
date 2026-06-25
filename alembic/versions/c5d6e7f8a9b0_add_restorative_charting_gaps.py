"""add restorative charting gaps (REST-1/2/3/4/7/8/9/10)

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-06-23

Addresses the frontend restorative-charting dev-report / capability assessment:
- REST-1/7/9: ``chart_conditions`` first-class qualifier columns (group_id, grade,
  segment, root_segment, tooth_status, root_scope, rct_fill, watch_dir, watch_x,
  watch_y, status) + audit (updated_at/updated_by) + query indexes. ``region`` is
  widened and kept writable for backward-compatible backfill.
- REST-8: ``procedure_codes`` alternate-benefit metadata (amb_code/is_downgrade/
  alternate_of).
- REST-10: ``progress_notes`` first-class drawing (drawing_strokes/drawing_doc_id).
- REST (lineage): ``patient_procedures.treatment_plan_id``.
- REST-2/3/4: new ``chart_status_templates`` / ``chart_settings`` /
  ``chart_tooth_notes`` tables.

REST-5 (seed colors/materials/finding codes) ships as ``scripts/seed_restorative``.
REST-6 (FHIR export) is deferred.

Hand-written (scoped to the affected tables only).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── REST-1/7/9: chart_conditions qualifiers + audit + indexes ────────────
    op.alter_column("chart_conditions", "region",
                    existing_type=sa.String(length=20), type_=sa.String(length=100),
                    existing_nullable=True)
    for col, type_ in [
        ("group_id", sa.String(length=64)),
        ("grade", sa.String(length=20)),
        ("segment", sa.String(length=20)),
        ("root_segment", sa.String(length=50)),
        ("tooth_status", sa.String(length=30)),
        ("root_scope", sa.String(length=10)),
        ("rct_fill", sa.String(length=20)),
        ("watch_dir", sa.String(length=5)),
        ("watch_x", sa.Integer()),
        ("watch_y", sa.Integer()),
        ("status", sa.String(length=20)),
        ("updated_at", sa.DateTime()),
        ("updated_by", sa.Integer()),
    ]:
        op.add_column("chart_conditions", sa.Column(col, type_, nullable=True))
    op.create_foreign_key(
        op.f("fk_chart_conditions_updated_by_users"),
        "chart_conditions", "users", ["updated_by"], ["id"],
    )
    op.create_index("ix_chart_conditions_group_id", "chart_conditions", ["group_id"])
    op.create_index("ix_chart_conditions_patient_is_inactive", "chart_conditions",
                    ["patient_id", "is_inactive"])
    op.create_index("ix_chart_conditions_patient_procedure_code", "chart_conditions",
                    ["patient_id", "procedure_code"])

    # ── REST-8: procedure_codes alternate-benefit metadata ───────────────────
    op.add_column("procedure_codes", sa.Column("amb_code", sa.String(length=20), nullable=True))
    op.add_column("procedure_codes",
                  sa.Column("is_downgrade", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("procedure_codes", sa.Column("alternate_of", sa.String(length=20), nullable=True))

    # ── REST-10: progress_notes first-class drawing ──────────────────────────
    op.add_column("progress_notes", sa.Column("drawing_strokes", sa.JSON(), nullable=True))
    op.add_column("progress_notes", sa.Column("drawing_doc_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_progress_notes_drawing_doc_id_patient_documents"),
        "progress_notes", "patient_documents", ["drawing_doc_id"], ["id"],
    )

    # ── REST lineage: patient_procedures.treatment_plan_id ───────────────────
    op.add_column("patient_procedures",
                  sa.Column("treatment_plan_id", sa.String(length=50), nullable=True))
    op.create_foreign_key(
        op.f("fk_patient_procedures_treatment_plan_id_treatment_plans"),
        "patient_procedures", "treatment_plans", ["treatment_plan_id"], ["id"],
    )

    # ── REST-2: chart_status_templates ───────────────────────────────────────
    op.create_table(
        "chart_status_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("legacy_id", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("label_key", sa.String(length=100), nullable=True),
        sa.Column("template_type", sa.String(length=50), nullable=False),
        sa.Column("arch", sa.String(length=10), nullable=True),
        sa.Column("material", sa.String(length=50), nullable=True),
        sa.Column("teeth", sa.JSON(), nullable=True),
        sa.Column("implants", sa.JSON(), nullable=True),
        sa.Column("missing", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"],
                                name=op.f("fk_chart_status_templates_created_by_users")),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"],
                                name=op.f("fk_chart_status_templates_updated_by_users")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name=op.f("fk_chart_status_templates_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chart_status_templates")),
        sa.UniqueConstraint("tenant_id", "legacy_id", name="uq_chart_status_templates_tenant_legacy"),
    )
    op.create_index(op.f("ix_chart_status_templates_tenant_id"), "chart_status_templates", ["tenant_id"])

    # ── REST-3: chart_settings (1:1 per patient) ─────────────────────────────
    op.create_table(
        "chart_settings",
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("numbering_system", sa.String(length=20), nullable=False, server_default="UNIVERSAL"),
        sa.Column("wisdom_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("occlusal_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("show_base", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("show_healthy_pulp", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("edentulous", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("arch_mode", sa.String(length=10), nullable=False, server_default="both"),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"],
                                name=op.f("fk_chart_settings_patient_id_patients")),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"],
                                name=op.f("fk_chart_settings_updated_by_users")),
        sa.PrimaryKeyConstraint("patient_id", name=op.f("pk_chart_settings")),
    )

    # ── REST-4: chart_tooth_notes (one per patient+tooth) ────────────────────
    op.create_table(
        "chart_tooth_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("tooth", sa.String(length=10), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"],
                                name=op.f("fk_chart_tooth_notes_patient_id_patients")),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"],
                                name=op.f("fk_chart_tooth_notes_updated_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chart_tooth_notes")),
        sa.UniqueConstraint("patient_id", "tooth", name="uq_chart_tooth_notes_patient_id_tooth"),
    )
    op.create_index(op.f("ix_chart_tooth_notes_patient_id"), "chart_tooth_notes", ["patient_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_chart_tooth_notes_patient_id"), table_name="chart_tooth_notes")
    op.drop_table("chart_tooth_notes")
    op.drop_table("chart_settings")
    op.drop_index(op.f("ix_chart_status_templates_tenant_id"), table_name="chart_status_templates")
    op.drop_table("chart_status_templates")

    op.drop_constraint(op.f("fk_patient_procedures_treatment_plan_id_treatment_plans"),
                       "patient_procedures", type_="foreignkey")
    op.drop_column("patient_procedures", "treatment_plan_id")

    op.drop_constraint(op.f("fk_progress_notes_drawing_doc_id_patient_documents"),
                       "progress_notes", type_="foreignkey")
    op.drop_column("progress_notes", "drawing_doc_id")
    op.drop_column("progress_notes", "drawing_strokes")

    op.drop_column("procedure_codes", "alternate_of")
    op.drop_column("procedure_codes", "is_downgrade")
    op.drop_column("procedure_codes", "amb_code")

    op.drop_index("ix_chart_conditions_patient_procedure_code", table_name="chart_conditions")
    op.drop_index("ix_chart_conditions_patient_is_inactive", table_name="chart_conditions")
    op.drop_index("ix_chart_conditions_group_id", table_name="chart_conditions")
    op.drop_constraint(op.f("fk_chart_conditions_updated_by_users"),
                       "chart_conditions", type_="foreignkey")
    for col in ("updated_by", "updated_at", "status", "watch_y", "watch_x", "watch_dir",
                "rct_fill", "root_scope", "tooth_status", "root_segment", "segment",
                "grade", "group_id"):
        op.drop_column("chart_conditions", col)
    op.alter_column("chart_conditions", "region",
                    existing_type=sa.String(length=100), type_=sa.String(length=20),
                    existing_nullable=True)
