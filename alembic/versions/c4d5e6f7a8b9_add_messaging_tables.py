"""add direct messaging tables (MSG-1)

conversations · conversation_participants · messages · message_receipts
message_recipient_states · message_attachments · message_reactions · user_presence

Revision ID: c4d5e6f7a8b9
Revises: b0c1d2e3f4a5
Create Date: 2026-07-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("dedupe_key", sa.String(length=100), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("last_message_id", sa.Uuid(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_conversations_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_conversations_created_by_users"),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        # 1:1 dedupe — this is what makes POST /conversations idempotent per pair.
        sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_conversations_tenant_dedupe_key"),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index(
        "ix_conversations_tenant_last_message_at",
        "conversations",
        ["tenant_id", "last_message_at"],
    )

    op.create_table(
        "conversation_participants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=True),
        sa.Column("is_muted", sa.Boolean(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), nullable=True),
        sa.Column("last_read_message_id", sa.Uuid(), nullable=True),
        sa.Column("last_read_at", sa.DateTime(), nullable=True),
        sa.Column("unread_count", sa.Integer(), nullable=True),
        sa.Column("joined_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("left_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_cp_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], name="fk_cp_conversation_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_cp_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_participants"),
        sa.UniqueConstraint(
            "conversation_id", "user_id", name="uq_conversation_participants_conversation_user"
        ),
    )
    op.create_index("ix_conversation_participants_tenant_id", "conversation_participants", ["tenant_id"])
    op.create_index("ix_conversation_participants_conversation_id", "conversation_participants", ["conversation_id"])
    op.create_index("ix_conversation_participants_user_id", "conversation_participants", ["user_id"])
    op.create_index(
        "ix_conversation_participants_tenant_user",
        "conversation_participants",
        ["tenant_id", "user_id"],
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("reply_to_id", sa.Uuid(), nullable=True),
        sa.Column("forwarded_from", sa.String(length=255), nullable=True),
        sa.Column("client_id", sa.String(length=64), nullable=True),
        sa.Column("is_edited", sa.Boolean(), nullable=True),
        sa.Column("edited_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_for_everyone", sa.Boolean(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_messages_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], name="fk_messages_conversation_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], name="fk_messages_sender_id_users"),
        # SET NULL, not CASCADE: deleting a quoted message must not delete the reply.
        sa.ForeignKeyConstraint(
            ["reply_to_id"], ["messages.id"], name="fk_messages_reply_to_id", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        # Idempotent sends: a retried POST with the same client_id collides here.
        sa.UniqueConstraint("conversation_id", "client_id", name="uq_messages_conversation_client_id"),
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
    # Keyset history scan: (conversation_id, id DESC) serves ORDER BY id DESC LIMIT n.
    op.create_index("ix_messages_conversation_id_desc", "messages", ["conversation_id", "id"])

    op.create_table(
        "message_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_mr_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_mr_message_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_mr_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_message_receipts"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_receipts_message_user"),
    )
    op.create_index("ix_message_receipts_tenant_id", "message_receipts", ["tenant_id"])
    op.create_index("ix_message_receipts_message_id", "message_receipts", ["message_id"])
    op.create_index("ix_message_receipts_user_id", "message_receipts", ["user_id"])
    # Serves the reconnect backlog flush (undelivered rows for one user).
    op.create_index(
        "ix_message_receipts_user_delivered", "message_receipts", ["user_id", "delivered_at"]
    )

    op.create_table(
        "message_recipient_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_mrs_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_mrs_message_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_mrs_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_message_recipient_states"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_recipient_states_message_user"),
    )
    op.create_index("ix_message_recipient_states_tenant_id", "message_recipient_states", ["tenant_id"])
    op.create_index("ix_message_recipient_states_message_id", "message_recipient_states", ["message_id"])
    op.create_index("ix_message_recipient_states_user_id", "message_recipient_states", ["user_id"])

    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("uploader_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_ma_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_ma_message_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"], name="fk_ma_uploader_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_message_attachments"),
    )
    op.create_index("ix_message_attachments_tenant_id", "message_attachments", ["tenant_id"])
    op.create_index("ix_message_attachments_message", "message_attachments", ["message_id"])

    op.create_table(
        "message_reactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("emoji", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_mrx_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_mrx_message_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_mrx_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_message_reactions"),
        sa.UniqueConstraint(
            "message_id", "user_id", "emoji", name="uq_message_reactions_message_user_emoji"
        ),
    )
    op.create_index("ix_message_reactions_tenant_id", "message_reactions", ["tenant_id"])
    op.create_index("ix_message_reactions_message", "message_reactions", ["message_id"])

    op.create_table(
        "user_presence",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_up_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_up_user_id_users"),
        sa.PrimaryKeyConstraint("tenant_id", "user_id", name="pk_user_presence"),
    )
    op.create_index("ix_user_presence_tenant_status", "user_presence", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_table("user_presence")
    op.drop_table("message_reactions")
    op.drop_table("message_attachments")
    op.drop_table("message_recipient_states")
    op.drop_table("message_receipts")
    op.drop_table("messages")
    op.drop_table("conversation_participants")
    op.drop_table("conversations")
