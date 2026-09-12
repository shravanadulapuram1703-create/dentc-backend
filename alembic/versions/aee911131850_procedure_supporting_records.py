"""procedure_codes supporting-records flags + patient_documents procedure/claim links

Revision ID: aee911131850
Revises: 3a8f2c41b7d9
Create Date: 2026-09-10

PROC-7 (Setup -> Procedure Codes -> Charting tab, "Supporting Records
Required"). Five per-code on/off rules — attachment, perio chart, photo,
x-ray, missing-tooth info — shaped exactly like ``requires_tooth``: tenant-wide
attributes of the code, NOT NULL, default false. The frontend had been parking
them in browser localStorage because ``PATCH /procedure-codes/{code}`` accepted
and silently dropped them.

No legacy backfill: the Denticon ``Codes.txt`` export the migration reads has
no attachment / x-ray / perio requirement columns (``s10_procedure_codes``
reads TOOTHREQ / SURFREQ / QUADREQ / LABREQ and nothing of that shape), so
every migrated code lands on ``false`` and the practice sets them in Setup.

PROC-7c sub-gap: ``patient_documents`` could only be tied to a *patient*, so
"the crown on #30 has its narrative attached" was not representable and
``requires_attachment`` could never be judged. ``procedure_id`` / ``claim_id``
are nullable FKs the upload route validates (same tenant, same patient).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "aee911131850"
down_revision = "3a8f2c41b7d9"
branch_labels = None
depends_on = None

_FLAGS = (
    "requires_attachment",
    "requires_perio_chart",
    "requires_photo",
    "requires_xray",
    "requires_missing_tooth_info",
)


def upgrade() -> None:
    for flag in _FLAGS:
        op.add_column(
            "procedure_codes",
            sa.Column(flag, sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    op.add_column(
        "patient_documents",
        sa.Column("procedure_id", sa.String(length=50),
                  sa.ForeignKey("patient_procedures.id"), nullable=True),
    )
    op.add_column(
        "patient_documents",
        sa.Column("claim_id", sa.String(length=50),
                  sa.ForeignKey("insurance_claims.id"), nullable=True),
    )
    op.create_index("ix_patient_documents_procedure_id", "patient_documents", ["procedure_id"])
    op.create_index("ix_patient_documents_claim_id", "patient_documents", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_patient_documents_claim_id", table_name="patient_documents")
    op.drop_index("ix_patient_documents_procedure_id", table_name="patient_documents")
    op.drop_column("patient_documents", "claim_id")
    op.drop_column("patient_documents", "procedure_id")
    for flag in reversed(_FLAGS):
        op.drop_column("procedure_codes", flag)
