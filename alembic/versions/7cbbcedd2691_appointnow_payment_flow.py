"""AppointNow payment acknowledgement + payment-required flow (AN-26 / AN-27)

AN-26: ``booking_requests.payment_terms_accepted`` (NULL on existing rows —
"asked before the question existed", never ``false``), the per-acknowledgement
wording hashes + version + server timestamp, and ``booking_acknowledgement_texts``
holding each distinct wording once.

AN-27: office + per-reason payment config, and the payment block on
``booking_requests`` (status ``awaiting_payment`` is just a new value of the
existing ``status`` varchar). Existing rows get ``requires_payment=false`` /
``payment_status='not_required'`` via server defaults.

Revision ID: 7cbbcedd2691
Revises: e4b31c406999
Create Date: 2026-10-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7cbbcedd2691"
down_revision: Union[str, None] = "e4b31c406999"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BR_COLUMNS = [
    # AN-26
    sa.Column("payment_terms_accepted", sa.Boolean(), nullable=True),
    sa.Column("acknowledgement_hashes", sa.JSON(), nullable=True),
    sa.Column("acknowledgement_version", sa.String(50), nullable=True),
    sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
    # AN-27.6
    sa.Column("status_token_hash", sa.String(64), nullable=True),
    # AN-27
    sa.Column("requires_payment", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("payment_status", sa.String(20), nullable=False, server_default="not_required"),
    sa.Column("payment_amount", sa.Numeric(10, 2), nullable=True),
    sa.Column("payment_currency", sa.String(3), nullable=True),
    sa.Column("payment_provider", sa.String(20), nullable=True),
    sa.Column("payment_link_id", sa.String(255), nullable=True),
    sa.Column("payment_link_url", sa.Text(), nullable=True),
    sa.Column("payment_link_sent_at", sa.DateTime(), nullable=True),
    sa.Column("payment_link_sent_via", sa.String(10), nullable=True),
    sa.Column("payment_link_expires_at", sa.DateTime(), nullable=True),
    sa.Column("payment_note", sa.Text(), nullable=True),
    sa.Column("payment_requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("payment_booking", sa.JSON(), nullable=True),
    sa.Column("paid_at", sa.DateTime(), nullable=True),
    sa.Column("paid_amount", sa.Numeric(10, 2), nullable=True),
    sa.Column("payment_reference", sa.String(255), nullable=True),
    sa.Column("payment_method", sa.String(50), nullable=True),
    sa.Column("ledger_payment_id", sa.String(50), sa.ForeignKey("patient_payments.id"), nullable=True),
    sa.Column("booking_error", sa.String(500), nullable=True),
    sa.Column("refunded_at", sa.DateTime(), nullable=True),
    sa.Column("refund_amount", sa.Numeric(10, 2), nullable=True),
    sa.Column("refund_reference", sa.String(255), nullable=True),
    sa.Column("refund_reason", sa.Text(), nullable=True),
    sa.Column("refunded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
]


def upgrade() -> None:
    op.create_table(
        "booking_acknowledgement_texts",
        sa.Column("text_hash", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("version", sa.String(50), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
    )
    for col in _BR_COLUMNS:
        op.add_column("booking_requests", col)
    op.create_index("ix_booking_requests_payment_link_id", "booking_requests", ["payment_link_id"])

    op.add_column("appointnow_reasons", sa.Column("requires_payment", sa.Boolean(), nullable=True))
    op.add_column("appointnow_reasons", sa.Column("payment_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "offices",
        sa.Column("appointnow_requires_payment", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("offices", sa.Column("appointnow_payment_amount", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("offices", "appointnow_payment_amount")
    op.drop_column("offices", "appointnow_requires_payment")
    op.drop_column("appointnow_reasons", "payment_amount")
    op.drop_column("appointnow_reasons", "requires_payment")
    op.drop_index("ix_booking_requests_payment_link_id", table_name="booking_requests")
    for col in reversed(_BR_COLUMNS):
        op.drop_column("booking_requests", col.name)
    op.drop_table("booking_acknowledgement_texts")
