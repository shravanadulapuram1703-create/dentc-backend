"""Letters module gaps (LTR-1, LTR-3, LTR-5, LTR-10).

Backs ``docs/letters/letters_backend_devreport.md``:

- LTR-1  ``patient_documents.storage_backend/bucket/path`` — consent PDFs move to
  ``gs://reco-documents/consent-forms/...``; the row records where the bytes
  actually live so the UI can show provenance and the pre-GCS rows stay auditable.
- LTR-3  the merge fields that had no backend source at all: provider letterhead
  (``providers.address_*/city/state/zip/phone/email``), the office corporate/DBA
  name (``offices.corporate_name``) and the ``#MARKET_*#`` practice block
  (``account_settings.marketing_*``).
- LTR-5  ``letter_batch_runs`` / ``letter_batch_items`` — the durable job record
  behind server-side batch letter runs (the CS001..CS009 collection sweeps).
- LTR-10 consent signing: who signed, how, and why they declined.

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── LTR-1: storage provenance on patient documents ───────────────────────
    op.add_column(
        "patient_documents",
        sa.Column("storage_backend", sa.String(length=20), nullable=False, server_default="local"),
    )
    op.add_column("patient_documents", sa.Column("storage_bucket", sa.String(length=255), nullable=True))
    op.add_column("patient_documents", sa.Column("storage_path", sa.String(length=500), nullable=True))
    # Backfill: every existing row is a local upload keyed by file_path.
    op.execute("UPDATE patient_documents SET storage_path = file_path WHERE storage_path IS NULL")
    # The Letters history reads consent forms by type for one patient (LTR-12).
    op.create_index(
        "ix_patient_documents_patient_type",
        "patient_documents", ["patient_id", "document_type"],
    )

    # ── LTR-3: provider letterhead ───────────────────────────────────────────
    for column in ("address_line1", "address_line2"):
        op.add_column("providers", sa.Column(column, sa.String(length=255), nullable=True))
    op.add_column("providers", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("providers", sa.Column("state", sa.String(length=50), nullable=True))
    op.add_column("providers", sa.Column("zip", sa.String(length=20), nullable=True))
    op.add_column("providers", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column("providers", sa.Column("email", sa.String(length=255), nullable=True))

    # ── LTR-3: office corporate / DBA name (#OFFICE_CNAME#) ──────────────────
    op.add_column("offices", sa.Column("corporate_name", sa.String(length=255), nullable=True))

    # ── LTR-3: the #MARKET_*# practice block ─────────────────────────────────
    op.add_column("account_settings", sa.Column("marketing_name", sa.String(length=255), nullable=True))
    op.add_column("account_settings", sa.Column("marketing_address_1", sa.String(length=255), nullable=True))
    op.add_column("account_settings", sa.Column("marketing_address_2", sa.String(length=255), nullable=True))
    op.add_column("account_settings", sa.Column("marketing_city", sa.String(length=100), nullable=True))
    op.add_column("account_settings", sa.Column("marketing_state", sa.String(length=50), nullable=True))
    op.add_column("account_settings", sa.Column("marketing_zip", sa.String(length=20), nullable=True))
    op.add_column("account_settings", sa.Column("marketing_phone", sa.String(length=20), nullable=True))

    # ── LTR-10: consent signing ──────────────────────────────────────────────
    op.add_column("patient_consents", sa.Column("signer_name", sa.String(length=255), nullable=True))
    op.add_column("patient_consents", sa.Column("signer_relationship", sa.String(length=50), nullable=True))
    op.add_column("patient_consents", sa.Column("signature_method", sa.String(length=20), nullable=True))
    op.add_column("patient_consents", sa.Column("declined_reason", sa.String(length=500), nullable=True))

    # ── LTR-5: batch letter runs ─────────────────────────────────────────────
    op.create_table(
        "letter_batch_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("requested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_letter_batch_runs_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], name="fk_letter_batch_runs_office_id_offices"),
        sa.ForeignKeyConstraint(["template_id"], ["letter_templates.id"], name="fk_letter_batch_runs_template_id_letter_templates"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_letter_batch_runs_created_by_users"),
        sa.PrimaryKeyConstraint("id", name="pk_letter_batch_runs"),
    )
    op.create_index("ix_letter_batch_runs_tenant_id", "letter_batch_runs", ["tenant_id"])
    op.create_index("ix_letter_batch_runs_template_id", "letter_batch_runs", ["template_id"])

    op.create_table(
        "letter_batch_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="rendered"),
        sa.Column("unresolved_tokens", sa.JSON(), nullable=True),
        sa.Column("rendered_html", sa.Text(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["letter_batch_runs.id"], name="fk_letter_batch_items_batch_id_letter_batch_runs"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], name="fk_letter_batch_items_patient_id_patients"),
        sa.ForeignKeyConstraint(["document_id"], ["patient_documents.id"], name="fk_letter_batch_items_document_id_patient_documents"),
        sa.PrimaryKeyConstraint("id", name="pk_letter_batch_items"),
    )
    op.create_index("ix_letter_batch_items_batch_id", "letter_batch_items", ["batch_id"])
    op.create_index("ix_letter_batch_items_patient_id", "letter_batch_items", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_letter_batch_items_patient_id", table_name="letter_batch_items")
    op.drop_index("ix_letter_batch_items_batch_id", table_name="letter_batch_items")
    op.drop_table("letter_batch_items")
    op.drop_index("ix_letter_batch_runs_template_id", table_name="letter_batch_runs")
    op.drop_index("ix_letter_batch_runs_tenant_id", table_name="letter_batch_runs")
    op.drop_table("letter_batch_runs")

    for column in ("declined_reason", "signature_method", "signer_relationship", "signer_name"):
        op.drop_column("patient_consents", column)

    for column in (
        "marketing_phone", "marketing_zip", "marketing_state", "marketing_city",
        "marketing_address_2", "marketing_address_1", "marketing_name",
    ):
        op.drop_column("account_settings", column)

    op.drop_column("offices", "corporate_name")

    for column in ("email", "phone", "zip", "state", "city", "address_line2", "address_line1"):
        op.drop_column("providers", column)

    op.drop_index("ix_patient_documents_patient_type", table_name="patient_documents")
    for column in ("storage_path", "storage_bucket", "storage_backend"):
        op.drop_column("patient_documents", column)
