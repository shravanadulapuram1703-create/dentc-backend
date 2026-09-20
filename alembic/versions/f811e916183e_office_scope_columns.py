"""Office scope columns (OFF-SCOPE-3/11/17).

Additive only. Three columns the server-side office scoping needs:

* ``users.current_office_id`` — the caller's remembered working office (the
  switcher's last selection), restored across devices (OFF-SCOPE-3). Not a
  fence; validated against ``user_offices`` on write.
* ``audit_logs.office_id`` (indexed) — the office a mutation was made in, for
  the HIPAA access-by-location trail (``GET /audit-logs?office_id=``, OFF-SCOPE-17).
* ``patient_payments.created_office_id`` — the *posting* office of a payment,
  distinct from ``office_id`` (which office the money was applied at), stamped
  from ``X-Office-ID`` (OFF-SCOPE-11).

All three are nullable with ``ON DELETE SET NULL`` where they FK to ``offices``,
so a removed office never strands a row. No data backfill — these describe new
writes; existing rows keep NULL.

Revision ID: f811e916183e
Revises: d4f1a9c7b3e2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f811e916183e"
down_revision = "d4f1a9c7b3e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("current_office_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_current_office",
        "users",
        "offices",
        ["current_office_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("audit_logs", sa.Column("office_id", sa.Integer(), nullable=True))
    op.create_index("ix_audit_logs_office_id", "audit_logs", ["office_id"])

    op.add_column(
        "patient_payments", sa.Column("created_office_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_patient_payments_created_office",
        "patient_payments",
        "offices",
        ["created_office_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_patient_payments_created_office", "patient_payments", type_="foreignkey"
    )
    op.drop_column("patient_payments", "created_office_id")

    op.drop_index("ix_audit_logs_office_id", table_name="audit_logs")
    op.drop_column("audit_logs", "office_id")

    op.drop_constraint("fk_users_current_office", "users", type_="foreignkey")
    op.drop_column("users", "current_office_id")
