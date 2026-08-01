"""add Add-Patient module gaps

New patient demographic/office/status columns (GAP-AP-1..11) + per-patient
medical-alert and questionnaire response tables (GAP-AP-16/17) + opening-balance
table (GAP-AP-12). Chart-no auto-generation (GAP-AP-14) and the composite
register endpoint (GAP-AP-13/15/18) are code-only.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-24

Additive; new tables created from model metadata to avoid drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.db.models.patients import (
    PatientMedicalAlert,
    PatientOpeningBalance,
    PatientQuestionnaireResponse,
)

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None

_NEW_TABLES = [
    PatientMedicalAlert.__table__,
    PatientQuestionnaireResponse.__table__,
    PatientOpeningBalance.__table__,
]

_STRING_COLS = {
    "pronouns": 20,
    "driver_license": 50,
    "student_status": 20,
    "school_name": 255,
    "preferred_hygienist_id": 50,
    "referred_to": 255,
    "responsible_party_relationship": 50,
}
_BOOL_COLS = ("assign_benefits", "add_to_quickfill", "no_correspondence")


def upgrade() -> None:
    for name, length in _STRING_COLS.items():
        op.add_column("patients", sa.Column(name, sa.String(length=length), nullable=True))
    op.add_column("patients", sa.Column("referral_to_date", sa.Date(), nullable=True))
    op.add_column("patients", sa.Column("hipaa_sharing_notes", sa.Text(), nullable=True))
    op.add_column("patients", sa.Column("patient_types", sa.JSON(), nullable=True))
    op.add_column("patients", sa.Column("fee_schedule_id", sa.Integer(), nullable=True))
    for name in _BOOL_COLS:
        op.add_column(
            "patients",
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    op.create_foreign_key(
        "fk_patients_preferred_hygienist_id_providers",
        "patients", "providers", ["preferred_hygienist_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_patients_fee_schedule_id_fee_schedules",
        "patients", "fee_schedules", ["fee_schedule_id"], ["id"],
    )

    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_NEW_TABLES)))
    op.drop_constraint("fk_patients_fee_schedule_id_fee_schedules", "patients", type_="foreignkey")
    op.drop_constraint("fk_patients_preferred_hygienist_id_providers", "patients", type_="foreignkey")
    for name in _BOOL_COLS:
        op.drop_column("patients", name)
    for name in ("fee_schedule_id", "patient_types", "hipaa_sharing_notes",
                 "referral_to_date", *_STRING_COLS):
        op.drop_column("patients", name)
