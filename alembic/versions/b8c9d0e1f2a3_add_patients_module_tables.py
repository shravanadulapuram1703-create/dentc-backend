"""add Patients-module schema (documents, emergency contacts, adjustments, claim attachments)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-05

Resolves frontend Patients dev-report gaps:
- CREATE patient_documents, patient_emergency_contacts, patient_adjustments, claim_attachments.
- ALTER patients (medicaid_id), patient_notes (updated_by),
  progress_notes (surface, region, signed_by, signed_at, is_struck_off).

Additive; new tables created from model metadata to avoid drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.db.models.patient_extra import (
    ClaimAttachment,
    PatientAdjustment,
    PatientDocument,
    PatientEmergencyContact,
)

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None

_NEW_TABLES = [
    PatientDocument.__table__,
    PatientEmergencyContact.__table__,
    PatientAdjustment.__table__,
    ClaimAttachment.__table__,
]


def upgrade() -> None:
    op.add_column("patients", sa.Column("medicaid_id", sa.String(length=50), nullable=True))
    op.add_column("patient_notes", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_patient_notes_updated_by_users", "patient_notes", "users", ["updated_by"], ["id"])
    op.add_column("progress_notes", sa.Column("surface", sa.String(length=50), nullable=True))
    op.add_column("progress_notes", sa.Column("region", sa.String(length=50), nullable=True))
    op.add_column("progress_notes", sa.Column("signed_by", sa.Integer(), nullable=True))
    op.add_column("progress_notes", sa.Column("signed_at", sa.DateTime(), nullable=True))
    op.add_column("progress_notes", sa.Column("is_struck_off", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_foreign_key("fk_progress_notes_signed_by_users", "progress_notes", "users", ["signed_by"], ["id"])

    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_NEW_TABLES)))
    op.drop_constraint("fk_progress_notes_signed_by_users", "progress_notes", type_="foreignkey")
    for col in ("is_struck_off", "signed_at", "signed_by", "region", "surface"):
        op.drop_column("progress_notes", col)
    op.drop_constraint("fk_patient_notes_updated_by_users", "patient_notes", type_="foreignkey")
    op.drop_column("patient_notes", "updated_by")
    op.drop_column("patients", "medicaid_id")
