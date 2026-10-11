"""AppointNow operatory pick + emergency requests (AN-28 / AN-29)

AN-28: ``booking_requests.operatory_id`` - the chair the patient picked on the
public page (null = any chair / emergency). Availability is computed per chair
and approve books into it unless staff override.

AN-29: ``booking_requests.is_emergency`` - emergency requests may ask for any
time; the slot is a preference and is not re-checked at intake.

Revision ID: a28e9c1d0b7f
Revises: 7cbbcedd2691
Create Date: 2026-10-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a28e9c1d0b7f"
down_revision: Union[str, None] = "7cbbcedd2691"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "booking_requests",
        sa.Column("operatory_id", sa.String(length=50), sa.ForeignKey("operatories.id"), nullable=True),
    )
    op.add_column(
        "booking_requests",
        sa.Column("is_emergency", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("booking_requests", "is_emergency")
    op.drop_column("booking_requests", "operatory_id")
