"""add treatment plan gaps (PLAN-1/2/5/7/10/14)

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-06-23

Addresses the frontend treatment-plan dev-report:
- PLAN-1 : ``treatment_plan_items.phase_id`` (first-class Phase ID).
- PLAN-2 : ``diagnosed_date`` / ``start_date`` / ``end_date``.
- PLAN-5 : ``provider_id`` (performing provider; FK providers).
- PLAN-10: ``discount``.
- PLAN-14: ``is_archived`` soft-delete (also resolves PLAN-13 — a soft-deleted
  item keeps its FK so insurance-details never block the delete).
- PLAN-7 : new ``patient_consents`` table (per-patient consent capture).

PLAN-3 (re-estimate), PLAN-6 (report) and PLAN-12 (patient items) are endpoints
over existing columns — no schema change.

Hand-written (scoped to the affected tables only).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── treatment_plan_items: new columns ────────────────────────────────────
    op.add_column("treatment_plan_items", sa.Column("phase_id", sa.Integer(), nullable=True))
    op.add_column("treatment_plan_items", sa.Column("discount", sa.Numeric(10, 2), nullable=True))
    op.add_column("treatment_plan_items", sa.Column("provider_id", sa.String(length=50), nullable=True))
    op.add_column("treatment_plan_items", sa.Column("diagnosed_date", sa.Date(), nullable=True))
    op.add_column("treatment_plan_items", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("treatment_plan_items", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column(
        "treatment_plan_items",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_foreign_key(
        op.f("fk_treatment_plan_items_provider_id_providers"),
        "treatment_plan_items", "providers", ["provider_id"], ["id"],
    )

    # ── PLAN-7: patient_consents ─────────────────────────────────────────────
    op.create_table(
        "patient_consents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("plan_id", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("rendered_html", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("signature_data", sa.Text(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("signed_by", sa.Integer(), nullable=True),
        sa.Column("signed_at", sa.DateTime(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"],
                                name=op.f("fk_patient_consents_created_by_users")),
        sa.ForeignKeyConstraint(["document_id"], ["patient_documents.id"],
                                name=op.f("fk_patient_consents_document_id_patient_documents")),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"],
                                name=op.f("fk_patient_consents_patient_id_patients")),
        sa.ForeignKeyConstraint(["plan_id"], ["treatment_plans.id"],
                                name=op.f("fk_patient_consents_plan_id_treatment_plans")),
        sa.ForeignKeyConstraint(["signed_by"], ["users.id"],
                                name=op.f("fk_patient_consents_signed_by_users")),
        sa.ForeignKeyConstraint(["template_id"], ["letter_templates.id"],
                                name=op.f("fk_patient_consents_template_id_letter_templates")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name=op.f("fk_patient_consents_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_consents")),
    )
    op.create_index(op.f("ix_patient_consents_tenant_id"), "patient_consents", ["tenant_id"])
    op.create_index(op.f("ix_patient_consents_patient_id"), "patient_consents", ["patient_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_patient_consents_patient_id"), table_name="patient_consents")
    op.drop_index(op.f("ix_patient_consents_tenant_id"), table_name="patient_consents")
    op.drop_table("patient_consents")

    op.drop_constraint(
        op.f("fk_treatment_plan_items_provider_id_providers"),
        "treatment_plan_items", type_="foreignkey",
    )
    op.drop_column("treatment_plan_items", "is_archived")
    op.drop_column("treatment_plan_items", "end_date")
    op.drop_column("treatment_plan_items", "start_date")
    op.drop_column("treatment_plan_items", "diagnosed_date")
    op.drop_column("treatment_plan_items", "provider_id")
    op.drop_column("treatment_plan_items", "discount")
    op.drop_column("treatment_plan_items", "phase_id")
