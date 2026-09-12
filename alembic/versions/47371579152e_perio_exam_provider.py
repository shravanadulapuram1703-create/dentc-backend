"""Perio exam provider (PERIO-BE-14)

Revision ID: 47371579152e
Revises: 587baa6a0ba7
Create Date: 2026-09-11

Frontend report: ``docs/Perio Chart/perio_charting_backend_devreport.md``
(PERIO-BE-14, second pass).

``perio_exams.provider_id`` (FK -> providers, nullable, indexed)
    the rendering provider the printed perio chart credits. The exam only ever
    carried ``created_by`` — the charting *user* — and the frontend was parking
    the provider per exam in ``localStorage``, so a reprint from another
    workstation credited whoever the inferred default happened to be, on a
    sheet that is attached to insurance claims.

No backfill: the Denticon ``PerioExam`` export has no provider column and
``created_by`` is a user, not a provider, so nothing can be recovered.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "47371579152e"
down_revision = "587baa6a0ba7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "perio_exams",
        sa.Column("provider_id", sa.String(length=50), sa.ForeignKey("providers.id"), nullable=True),
    )
    op.create_index("ix_perio_exams_provider_id", "perio_exams", ["provider_id"])


def downgrade() -> None:
    op.drop_index("ix_perio_exams_provider_id", table_name="perio_exams")
    op.drop_column("perio_exams", "provider_id")
