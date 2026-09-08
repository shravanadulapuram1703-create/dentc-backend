"""Patient SMS (Twilio) + e-mail log — SMS-3/5/7/8/9/10, EMAIL-1.

Backs ``docs/sms/SMS_BACKEND_DEVREPORT.md``.

- **SMS-3** ``sms_messages`` gains the Twilio correlation / delivery columns
  (``twilio_sid``, ``reply_twilio_sid``, ``from_phone``, ``direction``,
  ``sent_at``, ``error_code``/``error_message``, ``segments``, ``client_id``,
  ``template_id``) plus ``reply_intent`` / ``needs_attention`` /
  ``candidate_patient_ids`` (SMS-2 step 1/3), ``reminder_lead_hours`` (SMS-9
  dedupe), the two webhook payload hashes (SMS-10) and ``updated_at``.
  Backfill on the 5,425 migrated rows: ``direction`` from which text column is
  set, ``sent_at`` = ``delivered_on`` (the real send time — ``created_at`` is
  the migration date), legacy ``send_status='Success'`` → ``delivered``, and
  ``message_type`` inferred from the text with the same heuristic the frontend
  applied client-side (``sms_service.infer_message_type``).
- **SMS-5** new ``sms_templates``.
- **SMS-7** ``account_communications.messaging_service_sid`` / ``sms_from_phone``
  and ``office_phone_assignments.messaging_service_sid`` — the From selector
  per tenant/office. The Auth Token is never stored in the DB.
- **SMS-8** ``patients.sms_opt_out_at`` / ``sms_opt_in_at`` (STOP/START audit
  trail behind ``no_auto_sms``); quiet-hours window on ``account_communications``.
- **SMS-9** reminder settings on ``account_communications`` + a partial unique
  index enforcing one reminder per ``(appointment_id, message_type, lead)``.
- **EMAIL-1** new ``email_messages``.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-09-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── SMS-5: sms_templates (first — sms_messages/account_communications FK it) ──
    op.create_table(
        "sms_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("office_id", sa.Integer(), sa.ForeignKey("offices.id"), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sms_templates_tenant_id", "sms_templates", ["tenant_id"])
    op.create_index("ix_sms_templates_office_id", "sms_templates", ["office_id"])

    # ── SMS-3: sms_messages columns ──────────────────────────────────────────
    for col in (
        sa.Column("twilio_sid", sa.String(length=34), nullable=True),
        sa.Column("reply_twilio_sid", sa.String(length=34), nullable=True),
        sa.Column("from_phone", sa.String(length=20), nullable=True),
        sa.Column("direction", sa.String(length=10), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("segments", sa.SmallInteger(), nullable=True),
        sa.Column("client_id", sa.String(length=40), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("reply_intent", sa.String(length=20), nullable=True),
        sa.Column("needs_attention", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("candidate_patient_ids", sa.JSON(), nullable=True),
        sa.Column("reminder_lead_hours", sa.SmallInteger(), nullable=True),
        sa.Column("inbound_payload_hash", sa.String(length=64), nullable=True),
        sa.Column("status_payload_hash", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ):
        op.add_column("sms_messages", col)
    op.create_foreign_key("fk_sms_messages_template_id", "sms_messages", "sms_templates",
                          ["template_id"], ["id"])
    op.create_unique_constraint("uq_sms_messages_twilio_sid", "sms_messages", ["twilio_sid"])
    op.create_unique_constraint("uq_sms_messages_reply_twilio_sid", "sms_messages", ["reply_twilio_sid"])
    op.create_unique_constraint("uq_sms_messages_tenant_client_id", "sms_messages",
                                ["tenant_id", "client_id"])
    op.create_index("ix_sms_messages_office_sent_at", "sms_messages", ["office_id", "sent_at"])
    op.create_index("ix_sms_messages_sent_phone", "sms_messages", ["sent_phone"])
    op.create_index("ix_sms_messages_from_phone", "sms_messages", ["from_phone"])
    # SMS-9: one automated reminder per appointment × lead bucket.
    op.create_index(
        "uq_sms_messages_reminder_dedupe", "sms_messages",
        ["appointment_id", "message_type", "reminder_lead_hours"],
        unique=True,
        postgresql_where=sa.text("reminder_lead_hours IS NOT NULL"),
        sqlite_where=sa.text("reminder_lead_hours IS NOT NULL"),
    )

    # ── SMS-3 backfill on migrated rows (portable SQL) ───────────────────────
    op.execute(
        "UPDATE sms_messages SET direction = CASE "
        "WHEN sent_text IS NOT NULL AND sent_text <> '' THEN 'outbound' "
        "WHEN reply_text IS NOT NULL AND reply_text <> '' THEN 'inbound' "
        "ELSE direction END WHERE direction IS NULL"
    )
    op.execute(
        "UPDATE sms_messages SET sent_at = COALESCE(delivered_on, created_at) "
        "WHERE sent_at IS NULL AND sent_text IS NOT NULL"
    )
    op.execute(
        "UPDATE sms_messages SET send_status = 'delivered' "
        "WHERE LOWER(send_status) = 'success'"
    )
    op.execute(
        "UPDATE sms_messages SET send_status = 'received' "
        "WHERE send_status IS NULL AND sent_text IS NULL AND reply_text IS NOT NULL"
    )
    # Same heuristic as sms_service.infer_message_type (order matters).
    op.execute(
        "UPDATE sms_messages SET message_type = CASE "
        "WHEN sent_text IS NULL OR sent_text = '' THEN "
        "  CASE WHEN reply_text IS NOT NULL AND reply_text <> '' THEN 'inbound_reply' ELSE 'other' END "
        "WHEN LOWER(sent_text) LIKE '%confirm%' THEN 'appointment_confirmation' "
        "WHEN LOWER(sent_text) LIKE '%reminder%' OR LOWER(sent_text) LIKE '%appointment%' "
        "  OR LOWER(sent_text) LIKE '%appt%' THEN 'appointment_reminder' "
        "WHEN LOWER(sent_text) LIKE '%recall%' OR LOWER(sent_text) LIKE '%due for%' "
        "  OR LOWER(sent_text) LIKE '%cleaning%' OR LOWER(sent_text) LIKE '%check-up%' "
        "  OR LOWER(sent_text) LIKE '%checkup%' THEN 'recall' "
        "WHEN LOWER(sent_text) LIKE '%balance%' OR LOWER(sent_text) LIKE '%payment%' "
        "  OR LOWER(sent_text) LIKE '%statement%' OR LOWER(sent_text) LIKE '%past due%' THEN 'balance' "
        "ELSE 'manual' END "
        "WHERE message_type IS NULL OR message_type = ''"
    )

    # ── SMS-7/8/9: tenant + office sender / compliance / reminder settings ────
    op.add_column("account_communications", sa.Column("messaging_service_sid", sa.String(length=40), nullable=True))
    op.add_column("account_communications", sa.Column("sms_from_phone", sa.String(length=20), nullable=True))
    op.add_column("account_communications", sa.Column("sms_quiet_hours_start", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("account_communications", sa.Column("sms_quiet_hours_end", sa.Integer(), nullable=False, server_default="21"))
    op.add_column("account_communications", sa.Column("sms_reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("account_communications", sa.Column("sms_reminder_lead_hours", sa.JSON(), nullable=True))
    op.add_column("account_communications", sa.Column("sms_reminder_template_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_account_communications_sms_reminder_template_id",
                          "account_communications", "sms_templates",
                          ["sms_reminder_template_id"], ["id"])
    op.add_column("office_phone_assignments", sa.Column("messaging_service_sid", sa.String(length=40), nullable=True))
    op.create_index("ix_office_phone_assignments_phone_number", "office_phone_assignments", ["phone_number"])

    op.add_column("patients", sa.Column("sms_opt_out_at", sa.DateTime(), nullable=True))
    op.add_column("patients", sa.Column("sms_opt_in_at", sa.DateTime(), nullable=True))

    # ── EMAIL-1: email_messages ──────────────────────────────────────────────
    op.create_table(
        "email_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("office_id", sa.Integer(), sa.ForeignKey("offices.id"), nullable=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("appointment_id", sa.String(length=50), sa.ForeignKey("appointments.id"), nullable=True),
        sa.Column("to_email", sa.String(length=255), nullable=False),
        sa.Column("from_email", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("provider_message_id", sa.String(length=120), nullable=True),
        sa.Column("send_status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("message_type", sa.String(length=50), nullable=True),
        sa.Column("client_id", sa.String(length=40), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status_payload_hash", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "client_id", name="uq_email_messages_tenant_client_id"),
    )
    op.create_index("ix_email_messages_tenant_id", "email_messages", ["tenant_id"])
    op.create_index("ix_email_messages_patient_id", "email_messages", ["patient_id"])
    op.create_index("ix_email_messages_provider_message_id", "email_messages", ["provider_message_id"])


def downgrade() -> None:
    op.drop_index("ix_email_messages_provider_message_id", table_name="email_messages")
    op.drop_index("ix_email_messages_patient_id", table_name="email_messages")
    op.drop_index("ix_email_messages_tenant_id", table_name="email_messages")
    op.drop_table("email_messages")

    op.drop_column("patients", "sms_opt_in_at")
    op.drop_column("patients", "sms_opt_out_at")

    op.drop_index("ix_office_phone_assignments_phone_number", table_name="office_phone_assignments")
    op.drop_column("office_phone_assignments", "messaging_service_sid")
    op.drop_constraint("fk_account_communications_sms_reminder_template_id",
                       "account_communications", type_="foreignkey")
    for name in ("sms_reminder_template_id", "sms_reminder_lead_hours", "sms_reminders_enabled",
                 "sms_quiet_hours_end", "sms_quiet_hours_start", "sms_from_phone",
                 "messaging_service_sid"):
        op.drop_column("account_communications", name)

    op.drop_index("uq_sms_messages_reminder_dedupe", table_name="sms_messages")
    op.drop_index("ix_sms_messages_from_phone", table_name="sms_messages")
    op.drop_index("ix_sms_messages_sent_phone", table_name="sms_messages")
    op.drop_index("ix_sms_messages_office_sent_at", table_name="sms_messages")
    op.drop_constraint("uq_sms_messages_tenant_client_id", "sms_messages", type_="unique")
    op.drop_constraint("uq_sms_messages_reply_twilio_sid", "sms_messages", type_="unique")
    op.drop_constraint("uq_sms_messages_twilio_sid", "sms_messages", type_="unique")
    op.drop_constraint("fk_sms_messages_template_id", "sms_messages", type_="foreignkey")
    for name in ("updated_at", "status_payload_hash", "inbound_payload_hash", "reminder_lead_hours",
                 "candidate_patient_ids", "needs_attention", "reply_intent", "template_id",
                 "client_id", "segments", "error_message", "error_code", "sent_at", "direction",
                 "from_phone", "reply_twilio_sid", "twilio_sid"):
        op.drop_column("sms_messages", name)

    op.drop_index("ix_sms_templates_office_id", table_name="sms_templates")
    op.drop_index("ix_sms_templates_tenant_id", table_name="sms_templates")
    op.drop_table("sms_templates")
