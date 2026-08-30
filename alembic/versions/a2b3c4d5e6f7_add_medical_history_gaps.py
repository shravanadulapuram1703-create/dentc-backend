"""Patient Medical History — MH-4/5/6/7/8/13/14/16.

Backs ``docs/medical-history/medical_history_backend_devreport.md``.

- **MH-6 is the load-bearing one.** ``patient_signatures`` recorded only *that*
  someone signed — no reference at all to the medical-history content that was
  signed. A patient could sign, staff could then change any answer, and nothing
  in the data recorded that the signature predated the change; for a legal
  clinical record that is the gap that matters. The fix reuses the tables the
  migration already created: ``medical_history_records`` (the Denticon
  ``PatMedicalHistoryH`` header, which already pointed at a signature) becomes
  the **version** row and ``medical_history_details`` holds its frozen answers,
  with ``content_hash`` the SHA-256 fingerprint shared by both sides. The
  signature also gains ``signature_type`` (a medical-history, consent and
  financial-policy signature were indistinguishable rows on one patient),
  ``signed_at`` and ``signed_by_user_id`` (who is attesting, vs ``created_by``,
  who operated the pad).

- **MH-7** signatures were append-only, so a *cleared* signature could not be
  represented at all. ``is_active``/``superseded_by_id``/``voided_at``/
  ``voided_by`` + ``updated_at`` follow the soft-delete pattern used elsewhere.

- **MH-8** ``patient_medical_alerts`` and ``patient_questionnaire_responses``
  exposed ``created_by`` but no ``updated_by``, so the legacy screen's "Modified
  By" had to render blank. Both gain it (``CRUDBase.update`` stamps it), plus
  the new append-only ``patient_medical_history_events`` change log —
  ``audit_logs`` records one row per request, which for the composite write is a
  single entry for a whole document and cannot answer "who changed *this
  answer*".

- **MH-13/MH-16** new ``patient_medical_history`` header, one row per patient.
  The Additional Comments box was being stored as an alert row with the reserved
  code ``ADDITIONAL_COMMENTS`` — a convention shared by two modules with nothing
  enforcing it, polluting the alert list for every other consumer. The same row
  carries the per-questionnaire ``*_completed_at``/``*_completed_by`` pair: a
  row's ``updated_at`` is not "the patient reviewed and confirmed this on
  DD/MM/YYYY", because editing one answer does not mean the form was reviewed.

- **MH-14** a patient answering "yes" to a catalog item flagged
  ``is_flash_alert``/``blocks_charges`` in Setup produced a row no scheduler
  popover or charge gate could act on. ``patient_alerts`` gains ``is_flash_alert``
  and ``source_medical_alert_id`` so the propagated banner alert is reconcilable
  — un-answering deactivates exactly the row it created, never a hand-typed one.

- **MH-4** ``medical_history_records.source_patient_id``/``copied_at`` (and the
  header's ``copied_from_patient_id``) record that chart B's history came from
  chart A. Copying medical answers between charts is exactly the kind of
  operation that has to be attributable.

``medical_history_records`` also gains ``tenant_id`` so the version rows are
scoped like every other root table; migrated rows are backfilled from
``patients``.

Revision ID: a2b3c4d5e6f7
Revises: a6b7c8d9e0f1
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── MH-8: "Modified By" + MH-16 answered_at on the two answer tables ──────
    for table in ("patient_medical_alerts", "patient_questionnaire_responses"):
        op.add_column(table, sa.Column("updated_by", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("answered_at", sa.DateTime(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_updated_by_users", table, "users", ["updated_by"], ["id"]
        )

    # ── MH-6 / MH-7: the signature knows what it signed, and can be superseded ─
    op.add_column("patient_signatures", sa.Column("signature_type", sa.String(30), nullable=True))
    op.add_column("patient_signatures", sa.Column("signed_at", sa.DateTime(), nullable=True))
    op.add_column("patient_signatures", sa.Column("signed_by_user_id", sa.Integer(), nullable=True))
    op.add_column("patient_signatures", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column(
        "patient_signatures",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("patient_signatures", sa.Column("superseded_by_id", sa.Integer(), nullable=True))
    op.add_column("patient_signatures", sa.Column("voided_at", sa.DateTime(), nullable=True))
    op.add_column("patient_signatures", sa.Column("voided_by", sa.Integer(), nullable=True))
    op.add_column("patient_signatures", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("patient_signatures", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_index(
        "ix_patient_signatures_signature_type", "patient_signatures", ["signature_type"]
    )
    for column, target in (
        ("signed_by_user_id", "users"),
        ("voided_by", "users"),
        ("updated_by", "users"),
        ("superseded_by_id", "patient_signatures"),
    ):
        op.create_foreign_key(
            f"fk_patient_signatures_{column}_{target}",
            "patient_signatures", target, [column], ["id"],
        )

    # ── MH-6: medical_history_records is the version row ─────────────────────
    op.add_column("medical_history_records", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("medical_history_records", sa.Column("scope", sa.String(20), nullable=True))
    op.add_column("medical_history_records", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("medical_history_records", sa.Column("item_count", sa.Integer(), nullable=True))
    op.add_column("medical_history_records", sa.Column("comments", sa.Text(), nullable=True))
    op.add_column("medical_history_records", sa.Column("completed_at", sa.DateTime(), nullable=True))
    op.add_column("medical_history_records", sa.Column("completed_by", sa.Integer(), nullable=True))
    op.add_column(
        "medical_history_records", sa.Column("source_patient_id", sa.Integer(), nullable=True)
    )
    op.add_column("medical_history_records", sa.Column("copied_at", sa.DateTime(), nullable=True))
    op.add_column("medical_history_records", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("medical_history_records", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_index("ix_medical_history_records_tenant_id", "medical_history_records", ["tenant_id"])
    op.create_index(
        "ix_medical_history_records_content_hash", "medical_history_records", ["content_hash"]
    )
    for column, target in (
        ("tenant_id", "tenants"),
        ("completed_by", "users"),
        ("updated_by", "users"),
        ("source_patient_id", "patients"),
    ):
        op.create_foreign_key(
            f"fk_medical_history_records_{column}_{target}",
            "medical_history_records", target, [column], ["id"],
        )
    # Migrated header rows predate the column; derive the tenant from the patient
    # so the scoped list endpoint does not silently hide them.
    op.execute(
        "UPDATE medical_history_records AS r SET tenant_id = p.tenant_id "
        "FROM patients AS p WHERE p.id = r.patient_id AND r.tenant_id IS NULL"
    )

    # ── MH-6: which tab a frozen answer came from ────────────────────────────
    op.add_column("medical_history_details", sa.Column("answer_type", sa.String(20), nullable=True))
    op.add_column("medical_history_details", sa.Column("section", sa.String(100), nullable=True))
    op.create_index(
        "ix_medical_history_details_answer_type", "medical_history_details", ["answer_type"]
    )

    # ── MH-14: a Yes answer can raise a real banner alert ────────────────────
    op.add_column(
        "patient_alerts",
        sa.Column("is_flash_alert", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "patient_alerts", sa.Column("source_medical_alert_id", sa.Integer(), nullable=True)
    )
    op.create_index(
        "ix_patient_alerts_source_medical_alert_id",
        "patient_alerts", ["source_medical_alert_id"],
    )
    op.create_foreign_key(
        "fk_patient_alerts_source_medical_alert_id_patient_medical_alerts",
        "patient_alerts", "patient_medical_alerts", ["source_medical_alert_id"], ["id"],
    )

    # ── MH-13 / MH-16: the per-patient medical-history header ────────────────
    op.create_table(
        "patient_medical_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False, unique=True
        ),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("alerts_completed_at", sa.DateTime(), nullable=True),
        sa.Column("alerts_completed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("dental_completed_at", sa.DateTime(), nullable=True),
        sa.Column("dental_completed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("medical_completed_at", sa.DateTime(), nullable=True),
        sa.Column("medical_completed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "last_signature_id",
            sa.Integer(), sa.ForeignKey("patient_signatures.id"), nullable=True,
        ),
        sa.Column(
            "last_version_id",
            sa.Integer(), sa.ForeignKey("medical_history_records.id"), nullable=True,
        ),
        sa.Column(
            "copied_from_patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=True
        ),
        sa.Column("copied_at", sa.DateTime(), nullable=True),
        sa.Column("copied_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_patient_medical_history_tenant_id", "patient_medical_history", ["tenant_id"])
    op.create_index(
        "ix_patient_medical_history_patient_id", "patient_medical_history", ["patient_id"]
    )

    # ── MH-8: the append-only field-level change log ─────────────────────────
    op.create_table(
        "patient_medical_history_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("source_patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_patient_medical_history_events_tenant_id",
        "patient_medical_history_events", ["tenant_id"],
    )
    op.create_index(
        "ix_patient_medical_history_events_patient_id",
        "patient_medical_history_events", ["patient_id"],
    )
    op.create_index(
        "ix_patient_medical_history_events_entity_type",
        "patient_medical_history_events", ["entity_type"],
    )


def downgrade() -> None:
    op.drop_table("patient_medical_history_events")
    op.drop_table("patient_medical_history")

    op.drop_constraint(
        "fk_patient_alerts_source_medical_alert_id_patient_medical_alerts",
        "patient_alerts", type_="foreignkey",
    )
    op.drop_index("ix_patient_alerts_source_medical_alert_id", table_name="patient_alerts")
    op.drop_column("patient_alerts", "source_medical_alert_id")
    op.drop_column("patient_alerts", "is_flash_alert")

    op.drop_index("ix_medical_history_details_answer_type", table_name="medical_history_details")
    op.drop_column("medical_history_details", "section")
    op.drop_column("medical_history_details", "answer_type")

    for column, target in (
        ("tenant_id", "tenants"),
        ("completed_by", "users"),
        ("updated_by", "users"),
        ("source_patient_id", "patients"),
    ):
        op.drop_constraint(
            f"fk_medical_history_records_{column}_{target}",
            "medical_history_records", type_="foreignkey",
        )
    op.drop_index("ix_medical_history_records_content_hash", table_name="medical_history_records")
    op.drop_index("ix_medical_history_records_tenant_id", table_name="medical_history_records")
    for column in (
        "updated_by", "updated_at", "copied_at", "source_patient_id", "completed_by",
        "completed_at", "comments", "item_count", "content_hash", "scope", "tenant_id",
    ):
        op.drop_column("medical_history_records", column)

    for column, target in (
        ("signed_by_user_id", "users"),
        ("voided_by", "users"),
        ("updated_by", "users"),
        ("superseded_by_id", "patient_signatures"),
    ):
        op.drop_constraint(
            f"fk_patient_signatures_{column}_{target}", "patient_signatures", type_="foreignkey"
        )
    op.drop_index("ix_patient_signatures_signature_type", table_name="patient_signatures")
    for column in (
        "updated_by", "updated_at", "voided_by", "voided_at", "superseded_by_id",
        "is_active", "content_hash", "signed_by_user_id", "signed_at", "signature_type",
    ):
        op.drop_column("patient_signatures", column)

    for table in ("patient_questionnaire_responses", "patient_medical_alerts"):
        op.drop_constraint(f"fk_{table}_updated_by_users", table, type_="foreignkey")
        op.drop_column(table, "answered_at")
        op.drop_column(table, "updated_by")
