"""add auxiliary code tables (place_of_service_codes, icd_codes)

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-06-14

Resolves auxiliary code-tables dev-report:
- AUX-3: place_of_service_codes (tenant-scoped CMS POS list + per-office Tax ID).
- AUX-4: icd_codes (global diagnosis catalog + ICD-9/10/SNOMED crosswalk).

(AUX-1 Modifier / AUX-2 Type-of-Service are seeded as ``definitions`` groups —
no schema change.)

New tables created from model metadata to avoid drift.
"""

from __future__ import annotations

from alembic import op

from app.db.base import Base
from app.db.models.aux_codes import IcdCode, PlaceOfServiceCode

revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None

_NEW_TABLES = [
    PlaceOfServiceCode.__table__,
    IcdCode.__table__,
]


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_NEW_TABLES)))
