"""add Add-Patient legacy-parity gaps (LEG-1..14)

New ``responsible_parties`` guarantor/billing entity (LEG-10/11/12/13) + additive
columns: emergency-contact ``is_primary`` (LEG-3), definition ``section`` (LEG-4),
``patient_insurance`` Dentical Share of Cost (LEG-6), plan ``anniversary_expiry_date``
(LEG-7), recall ``interval_unit``/``scheduled_date``/``scheduled_time`` (LEG-8).

Catalog seeding (LEG-1) + the RESP_PARTY_TYPE group are handled by
``scripts/seed_legacy_parity.py`` (data, not schema).

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-25

Additive; the new table is created from model metadata to avoid drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.db.models.patients import ResponsibleParty

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None

_NEW_TABLES = [ResponsibleParty.__table__]


def upgrade() -> None:
    op.add_column(
        "patient_emergency_contacts",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("definitions", sa.Column("section", sa.String(length=100), nullable=True))
    op.add_column("insurance_plans", sa.Column("anniversary_expiry_date", sa.Date(), nullable=True))
    op.add_column("patient_insurance", sa.Column("dentical_share_month", sa.Integer(), nullable=True))
    op.add_column("patient_insurance", sa.Column("dentical_share_year", sa.Integer(), nullable=True))
    op.add_column("patient_insurance", sa.Column("dentical_share_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("patient_insurance", sa.Column("dentical_unused", sa.Numeric(10, 2), nullable=True))
    op.add_column("patient_recalls", sa.Column("interval_unit", sa.String(length=10), nullable=True))
    op.add_column("patient_recalls", sa.Column("scheduled_date", sa.Date(), nullable=True))
    op.add_column("patient_recalls", sa.Column("scheduled_time", sa.String(length=10), nullable=True))

    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=_NEW_TABLES)
    for col in ("scheduled_time", "scheduled_date", "interval_unit"):
        op.drop_column("patient_recalls", col)
    for col in ("dentical_unused", "dentical_share_amount", "dentical_share_year", "dentical_share_month"):
        op.drop_column("patient_insurance", col)
    op.drop_column("insurance_plans", "anniversary_expiry_date")
    op.drop_column("definitions", "section")
    op.drop_column("patient_emergency_contacts", "is_primary")
