"""add Office Assignment module schema (Setup -> Offices -> Office Assignment)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-01

Resolves backend dev-report gaps #24, #25, #26, #28, #29, #30, #31:
- ALTER providers: first_name, last_name, created_by (#28).
- CREATE production_types catalog (#26).
- CREATE 7 M:N office-assignment link tables (procedure_codes #24, code_bundles
  #25, production_types #26, providers #28, note_macros #29, prescription_library
  #30, letter_templates #31).

Additive; new tables created from model metadata to avoid drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.db.models.office_assignment import (
    OfficeCodeBundle,
    OfficeLetterTemplate,
    OfficeNoteMacro,
    OfficePrescriptionLibrary,
    OfficeProcedureCode,
    OfficeProductionType,
    ProductionType,
    ProviderOffice,
)

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

# ProductionType first (the link table references it).
_NEW_TABLES = [
    ProductionType.__table__,
    OfficeProcedureCode.__table__,
    OfficeCodeBundle.__table__,
    OfficeProductionType.__table__,
    ProviderOffice.__table__,
    OfficeNoteMacro.__table__,
    OfficePrescriptionLibrary.__table__,
    OfficeLetterTemplate.__table__,
]


def upgrade() -> None:
    op.add_column("providers", sa.Column("first_name", sa.String(length=100), nullable=True))
    op.add_column("providers", sa.Column("last_name", sa.String(length=100), nullable=True))
    op.add_column("providers", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_providers_created_by_users", "providers", "users", ["created_by"], ["id"])

    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_NEW_TABLES)))

    op.drop_constraint("fk_providers_created_by_users", "providers", type_="foreignkey")
    op.drop_column("providers", "created_by")
    op.drop_column("providers", "last_name")
    op.drop_column("providers", "first_name")
