"""ADA claim-form signatures — SIG-11/13/14/15 of
``docs/signature/topaz_signature_backend_devreport (2).md`` §5.

- **SIG-11** ``patient_signatures.claim_id`` (FK ``insurance_claims.id``, which is a
  ``VARCHAR(50)`` — not a UUID column — so the FK matches the real type) — the
  claim a signature was captured for. A pinned row beats the patient's latest
  "signature on file" at print time.
- **SIG-13** ``patient_signatures.signer_name`` / ``signer_relationship`` (+ the
  same two on ``signature_audit_events``) so a guardian signing Item 36 for a
  minor is named on the form and on the trail.
- **SIG-15** ``patient_signatures.signer_provider_id`` — the *provider* attesting
  Item 53, distinct from ``created_by`` (pad operator) and ``signed_by_user_id``
  (an attesting *user*); most migrated providers have no user account.
- **SIG-14** new ``provider_signatures`` (1:1 with provider) — the same block as
  ``users.signature_*`` keyed on the provider.

Revision ID: 6f5fd1cb5b52
Revises: 7f483f6833a7
Create Date: 2026-09-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "6f5fd1cb5b52"
down_revision = "7f483f6833a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient_signatures", sa.Column("claim_id", sa.String(50), nullable=True))
    op.add_column("patient_signatures", sa.Column("signer_name", sa.String(120), nullable=True))
    op.add_column("patient_signatures", sa.Column("signer_relationship", sa.String(40), nullable=True))
    op.add_column("patient_signatures", sa.Column("signer_provider_id", sa.String(50), nullable=True))
    op.create_foreign_key(
        "fk_patient_signatures_claim_id", "patient_signatures", "insurance_claims",
        ["claim_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_patient_signatures_signer_provider_id", "patient_signatures", "providers",
        ["signer_provider_id"], ["id"],
    )
    op.create_index("ix_patient_signatures_claim_id", "patient_signatures", ["claim_id"])
    op.create_index("ix_patient_signatures_signer_provider_id", "patient_signatures",
                    ["signer_provider_id"])

    op.add_column("signature_audit_events", sa.Column("signer_name", sa.String(120), nullable=True))
    op.add_column("signature_audit_events",
                  sa.Column("signer_relationship", sa.String(40), nullable=True))

    op.create_table(
        "provider_signatures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider_id", sa.String(50), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("signature_data", sa.Text(), nullable=True),
        sa.Column("signature_len", sa.Integer(), nullable=True),
        sa.Column("device_source", sa.String(20), nullable=True),
        sa.Column("signed_at", sa.DateTime(), nullable=True),
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
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("provider_id", name="uq_provider_signatures_provider"),
    )
    op.create_index("ix_provider_signatures_tenant_id", "provider_signatures", ["tenant_id"])
    op.create_index("ix_provider_signatures_provider_id", "provider_signatures", ["provider_id"])


def downgrade() -> None:
    op.drop_table("provider_signatures")
    op.drop_column("signature_audit_events", "signer_relationship")
    op.drop_column("signature_audit_events", "signer_name")
    op.drop_index("ix_patient_signatures_signer_provider_id", table_name="patient_signatures")
    op.drop_index("ix_patient_signatures_claim_id", table_name="patient_signatures")
    op.drop_constraint("fk_patient_signatures_signer_provider_id", "patient_signatures",
                       type_="foreignkey")
    op.drop_constraint("fk_patient_signatures_claim_id", "patient_signatures", type_="foreignkey")
    op.drop_column("patient_signatures", "signer_provider_id")
    op.drop_column("patient_signatures", "signer_relationship")
    op.drop_column("patient_signatures", "signer_name")
    op.drop_column("patient_signatures", "claim_id")
