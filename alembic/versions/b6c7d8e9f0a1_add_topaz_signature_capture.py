"""Topaz signature capture — SIG-1/2/3/4/7/8 of
``docs/signature/topaz_signature_backend_devreport.md``.

One shared frontend ``SignatureCapture`` component (Topaz SigPlusExtLite pad +
on-screen fallback) feeds three stores. Until now each kept only the rendered
image; the actual biometric record (the Topaz **SigString**), the pad identity
and the point/stroke counts were captured and dropped.

- **SIG-1** ``sig_string`` (encrypted at rest — SIG-4), ``sig_format``,
  ``sig_compression``, ``sig_encryption`` on ``patient_signatures``,
  ``patient_consents`` and ``users`` (prefixed ``signature_``).
- **SIG-2** ``point_count`` / ``stroke_count`` on the same three.
- **SIG-3** ``device_vendor`` / ``device_model`` / ``device_serial`` on the same
  three (+ ``device_source`` on ``patient_consents``, which never had the
  method column the other two have).
- **SIG-7** document binding: ``patient_signatures.progress_note_id`` /
  ``consent_id`` (the signature's *subject*), ``patient_consents.content_hash``
  and ``progress_notes.content_hash`` (what was signed, so a later edit reads
  as ``stale``).
- **SIG-8** ``captured_user_agent`` on the three stores + the new append-only
  ``signature_audit_events`` table (captured / superseded / voided / declined /
  replaced / sig_string_exported, with ip + user agent + pad identity).

The 3,860 legacy ``patient_signatures`` rows whose ``signature_data`` holds a raw
SigString (the legacy import put SigStrings where images go) are moved into
``sig_string`` by ``scripts/migrate_legacy_sigstrings.py`` — a data step kept out
of this revision so it can be dry-run and reported.

Revision ID: b6c7d8e9f0a1
Revises: e0f1a2b3c4d5
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b6c7d8e9f0a1"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def _capture_block(prefix: str = "") -> list[sa.Column]:
    return [
        sa.Column(f"{prefix}sig_string", sa.Text(), nullable=True),
        sa.Column(f"{prefix}sig_format", sa.String(24), nullable=True),
        sa.Column(f"{prefix}sig_compression", sa.SmallInteger(), nullable=True),
        sa.Column(f"{prefix}sig_encryption", sa.SmallInteger(), nullable=True),
        sa.Column(f"{prefix}point_count", sa.Integer(), nullable=True),
        sa.Column(f"{prefix}stroke_count", sa.Integer(), nullable=True),
        sa.Column(f"{prefix}device_vendor", sa.String(20), nullable=True),
        sa.Column(f"{prefix}device_model", sa.String(40), nullable=True),
        sa.Column(f"{prefix}device_serial", sa.String(40), nullable=True),
        sa.Column(f"{prefix}captured_user_agent", sa.String(255), nullable=True),
    ]


def upgrade() -> None:
    # ── patient_signatures ──
    for col in _capture_block():
        op.add_column("patient_signatures", col)
    op.add_column("patient_signatures", sa.Column("progress_note_id", sa.Integer(), nullable=True))
    op.add_column("patient_signatures", sa.Column("consent_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_patient_signatures_progress_note_id", "patient_signatures", "progress_notes",
        ["progress_note_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_patient_signatures_consent_id", "patient_signatures", "patient_consents",
        ["consent_id"], ["id"],
    )
    op.create_index("ix_patient_signatures_progress_note_id", "patient_signatures", ["progress_note_id"])
    op.create_index("ix_patient_signatures_consent_id", "patient_signatures", ["consent_id"])

    # ── patient_consents ──
    for col in _capture_block():
        op.add_column("patient_consents", col)
    op.add_column("patient_consents", sa.Column("device_source", sa.String(20), nullable=True))
    op.add_column("patient_consents", sa.Column("content_hash", sa.String(64), nullable=True))

    # ── progress_notes ──
    op.add_column("progress_notes", sa.Column("content_hash", sa.String(64), nullable=True))

    # ── users (prefixed) ──
    for col in _capture_block("signature_"):
        op.add_column("users", col)
    op.add_column("users", sa.Column("signature_signed_at", sa.DateTime(), nullable=True))

    # ── signature_audit_events ──
    op.create_table(
        "signature_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("event", sa.String(30), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("device_source", sa.String(20), nullable=True),
        sa.Column("device_vendor", sa.String(20), nullable=True),
        sa.Column("device_model", sa.String(40), nullable=True),
        sa.Column("device_serial", sa.String(40), nullable=True),
        sa.Column("signature_type", sa.String(30), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_signature_audit_events_tenant_id", "signature_audit_events", ["tenant_id"])
    op.create_index("ix_signature_audit_events_patient_id", "signature_audit_events", ["patient_id"])
    op.create_index("ix_signature_audit_events_event", "signature_audit_events", ["event"])
    op.create_index(
        "ix_signature_audit_events_entity", "signature_audit_events", ["entity_type", "entity_id"]
    )


def downgrade() -> None:
    op.drop_table("signature_audit_events")

    op.drop_column("users", "signature_signed_at")
    for col in reversed(_capture_block("signature_")):
        op.drop_column("users", col.name)

    op.drop_column("progress_notes", "content_hash")

    op.drop_column("patient_consents", "content_hash")
    op.drop_column("patient_consents", "device_source")
    for col in reversed(_capture_block()):
        op.drop_column("patient_consents", col.name)

    op.drop_index("ix_patient_signatures_consent_id", table_name="patient_signatures")
    op.drop_index("ix_patient_signatures_progress_note_id", table_name="patient_signatures")
    op.drop_constraint("fk_patient_signatures_consent_id", "patient_signatures", type_="foreignkey")
    op.drop_constraint("fk_patient_signatures_progress_note_id", "patient_signatures", type_="foreignkey")
    op.drop_column("patient_signatures", "consent_id")
    op.drop_column("patient_signatures", "progress_note_id")
    for col in reversed(_capture_block()):
        op.drop_column("patient_signatures", col.name)
