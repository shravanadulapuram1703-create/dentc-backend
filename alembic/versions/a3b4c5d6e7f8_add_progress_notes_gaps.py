"""add progress notes gaps (PN-1/3/4)

Revision ID: a3b4c5d6e7f8
Revises: f2c3d4e5a6b7
Create Date: 2026-06-23

Addresses the frontend progress-notes dev-report:
- PN-4: ``progress_notes`` gains ``struck_off_at`` / ``struck_off_by`` (set on the
  strike-off transition; cleared on restore) so the client can gate same-day Restore.
- PN-1: ``users`` gains ``signature_len`` / ``signature_device_source`` /
  ``signature_updated_at`` so a provider's signature ("Load My Signature") can
  round-trip independent of any patient (``users.signature_data`` already exists).
- PN-3: new ``progress_note_attachments`` table — files attached to a specific
  note (mirrors the ``claim_attachments`` precedent).

PN-2 (over-the-shoulder sign), PN-5 (resolved names), PN-6 (macro categories) and
PN-7 (server-side lock) are behavioural/derived — no schema change.

Hand-written (scoped to the affected tables only).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "f2c3d4e5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── PN-4: strike-off audit ───────────────────────────────────────────────
    op.add_column("progress_notes", sa.Column("struck_off_at", sa.DateTime(), nullable=True))
    op.add_column("progress_notes", sa.Column("struck_off_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_progress_notes_struck_off_by_users"),
        "progress_notes", "users", ["struck_off_by"], ["id"],
    )

    # ── PN-1: per-user signature metadata ────────────────────────────────────
    op.add_column("users", sa.Column("signature_len", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("signature_device_source", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("signature_updated_at", sa.DateTime(), nullable=True))

    # ── PN-3: per-note attachments ───────────────────────────────────────────
    op.create_table(
        "progress_note_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("progress_note_id", sa.Integer(), nullable=False),
        sa.Column("attachment_type", sa.String(length=50), nullable=True),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_url", sa.String(length=500), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"],
                                name=op.f("fk_progress_note_attachments_created_by_users")),
        sa.ForeignKeyConstraint(["progress_note_id"], ["progress_notes.id"],
                                name=op.f("fk_progress_note_attachments_progress_note_id_progress_notes")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name=op.f("fk_progress_note_attachments_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_progress_note_attachments")),
    )
    op.create_index(
        op.f("ix_progress_note_attachments_tenant_id"),
        "progress_note_attachments", ["tenant_id"], unique=False,
    )
    op.create_index(
        op.f("ix_progress_note_attachments_progress_note_id"),
        "progress_note_attachments", ["progress_note_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_progress_note_attachments_progress_note_id"), table_name="progress_note_attachments")
    op.drop_index(op.f("ix_progress_note_attachments_tenant_id"), table_name="progress_note_attachments")
    op.drop_table("progress_note_attachments")

    op.drop_column("users", "signature_updated_at")
    op.drop_column("users", "signature_device_source")
    op.drop_column("users", "signature_len")

    op.drop_constraint(op.f("fk_progress_notes_struck_off_by_users"), "progress_notes", type_="foreignkey")
    op.drop_column("progress_notes", "struck_off_by")
    op.drop_column("progress_notes", "struck_off_at")
