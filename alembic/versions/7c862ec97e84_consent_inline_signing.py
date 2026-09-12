"""Consent forms signed in the Report Viewer — CS-1/2/3/4 of
``docs/letters/consent_inline_signing_backend_devreport.md``.

- **CS-1** ``patient_consents.signed_document_id`` — the signed PDF rendition,
  kept beside ``document_id`` (printed / scanned copy).
- **CS-2** new ``consent_signatures`` — countersignatures (dentist / hygienist /
  assistant / office manager) with the full capture block.
- **CS-3** ``patient_consents.captured_at`` + ``signed_at_source``.
- **CS-4** ``patient_consents.signed_rendered_html`` — the immutable as-signed HTML.

Revision ID: 7c862ec97e84
Revises: 6f5fd1cb5b52
Create Date: 2026-09-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "7c862ec97e84"
down_revision = "6f5fd1cb5b52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient_consents", sa.Column("signed_document_id", sa.Integer(), nullable=True))
    op.add_column("patient_consents", sa.Column("captured_at", sa.DateTime(), nullable=True))
    op.add_column("patient_consents", sa.Column("signed_at_source", sa.String(10), nullable=True))
    op.add_column("patient_consents", sa.Column("signed_rendered_html", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_patient_consents_signed_document_id", "patient_consents", "patient_documents",
        ["signed_document_id"], ["id"],
    )
    op.create_table(
        "consent_signatures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("consent_id", sa.Integer(), sa.ForeignKey("patient_consents.id"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("signer_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("signer_provider_id", sa.String(50), sa.ForeignKey("providers.id"), nullable=True),
        sa.Column("signer_name", sa.String(120), nullable=True),
        sa.Column("signature_data", sa.Text(), nullable=True),
        sa.Column("signature_len", sa.Integer(), nullable=True),
        sa.Column("device_source", sa.String(20), nullable=True),
        sa.Column("signed_at", sa.DateTime(), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=True),
        sa.Column("sig_string", sa.Text(), nullable=True),
        sa.Column("sig_format", sa.String(24), nullable=True),
        sa.Column("sig_compression", sa.SmallInteger(), nullable=True),
        sa.Column("sig_encryption", sa.SmallInteger(), nullable=True),
        sa.Column("point_count", sa.Integer(), nullable=True),
        sa.Column("stroke_count", sa.Integer(), nullable=True),
        sa.Column("device_vendor", sa.String(20), nullable=True),
        sa.Column("device_model", sa.String(40), nullable=True),
        sa.Column("device_serial", sa.String(40), nullable=True),
        sa.Column("captured_user_agent", sa.String(255), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("voided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_consent_signatures_tenant_id", "consent_signatures", ["tenant_id"])
    op.create_index("ix_consent_signatures_consent_id", "consent_signatures", ["consent_id"])


def downgrade() -> None:
    op.drop_table("consent_signatures")
    op.drop_constraint("fk_patient_consents_signed_document_id", "patient_consents", type_="foreignkey")
    op.drop_column("patient_consents", "signed_rendered_html")
    op.drop_column("patient_consents", "signed_at_source")
    op.drop_column("patient_consents", "captured_at")
    op.drop_column("patient_consents", "signed_document_id")
