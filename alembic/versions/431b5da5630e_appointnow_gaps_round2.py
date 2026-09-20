"""AppointNow round 2 — reschedule, intake acknowledgements, provider opt-in.

Answers docs/appointnow/appointnow_backend_devreport.md (2026-09-12):

- **AN-16** ``booking_requests.insurance_info`` / ``disclaimer_accepted`` /
  ``consent_accepted`` — the two legal acknowledgements the public page requires
  were being dropped by ``ContactInput`` and folded into ``notes`` as a
  workaround. Existing rows are backfilled from those ``notes`` markers so the
  audit trail the frontend improvised survives the cut-over.
- **AN-14** ``original_slot_*`` + ``reschedule_count`` / ``rescheduled_by`` /
  ``rescheduled_at`` — a staff reschedule replaces ``slot_*`` and keeps what the
  patient first asked for.
- **AN-21** ``contact_notified_at`` / ``contact_notified_via`` — the last
  outbound approve/decline/reschedule notification to the contact.
- **AN-18** ``providers.visible_in_appointnow`` becomes **opt-in** (server
  default false) and every existing row is set to false explicitly: with the
  old default every active provider of an office — test rows, placeholders,
  duplicates — was offered on the public page, and "any provider" requests were
  booked against the first one alphabetically. Practices curate the list from
  Provider Setup (or ``scripts/appointnow_visible_providers.py``).

Revision ID: 431b5da5630e
Revises: 7c862ec97e84
Create Date: 2026-09-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "431b5da5630e"
down_revision = "7c862ec97e84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── AN-16 intake acknowledgements ────────────────────────────────────────
    op.add_column("booking_requests", sa.Column("insurance_info", sa.String(length=500), nullable=True))
    op.add_column(
        "booking_requests",
        sa.Column("disclaimer_accepted", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "booking_requests",
        sa.Column("consent_accepted", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    # Backfill from the frontend's interim ``notes`` markers (see
    # ``appointnow_service.split_contact_extras``): the acknowledgement was
    # given, it was just stored in the wrong column.
    op.execute(
        sa.text(
            "UPDATE booking_requests SET disclaimer_accepted = TRUE "
            "WHERE notes LIKE '%Disclaimer accepted: Yes%'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE booking_requests SET consent_accepted = TRUE "
            "WHERE notes LIKE '%Contact consent (calls/texts): Yes%'"
        )
    )

    # ── AN-14 reschedule ─────────────────────────────────────────────────────
    op.add_column("booking_requests", sa.Column("original_slot_date", sa.Date(), nullable=True))
    op.add_column("booking_requests", sa.Column("original_start_time", sa.Time(), nullable=True))
    op.add_column("booking_requests", sa.Column("original_end_time", sa.Time(), nullable=True))
    op.add_column("booking_requests", sa.Column("original_duration_minutes", sa.Integer(), nullable=True))
    op.add_column("booking_requests", sa.Column("original_provider_id", sa.String(length=50), nullable=True))
    op.add_column("booking_requests", sa.Column("original_provider_name", sa.String(length=255), nullable=True))
    op.add_column(
        "booking_requests",
        sa.Column("reschedule_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("booking_requests", sa.Column("rescheduled_by", sa.Integer(), nullable=True))
    op.add_column("booking_requests", sa.Column("rescheduled_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_booking_requests_rescheduled_by_users",
        "booking_requests",
        "users",
        ["rescheduled_by"],
        ["id"],
    )

    # ── AN-21 contact notifications ──────────────────────────────────────────
    op.add_column("booking_requests", sa.Column("contact_notified_at", sa.DateTime(), nullable=True))
    op.add_column("booking_requests", sa.Column("contact_notified_via", sa.String(length=10), nullable=True))

    # ── AN-18 provider opt-in ────────────────────────────────────────────────
    op.alter_column(
        "providers",
        "visible_in_appointnow",
        existing_type=sa.Boolean(),
        server_default=sa.false(),
        existing_nullable=False,
    )
    op.execute(sa.text("UPDATE providers SET visible_in_appointnow = FALSE"))


def downgrade() -> None:
    op.alter_column(
        "providers",
        "visible_in_appointnow",
        existing_type=sa.Boolean(),
        server_default=sa.true(),
        existing_nullable=False,
    )
    op.drop_column("booking_requests", "contact_notified_via")
    op.drop_column("booking_requests", "contact_notified_at")
    op.drop_constraint("fk_booking_requests_rescheduled_by_users", "booking_requests", type_="foreignkey")
    op.drop_column("booking_requests", "rescheduled_at")
    op.drop_column("booking_requests", "rescheduled_by")
    op.drop_column("booking_requests", "reschedule_count")
    op.drop_column("booking_requests", "original_provider_name")
    op.drop_column("booking_requests", "original_provider_id")
    op.drop_column("booking_requests", "original_duration_minutes")
    op.drop_column("booking_requests", "original_end_time")
    op.drop_column("booking_requests", "original_start_time")
    op.drop_column("booking_requests", "original_slot_date")
    op.drop_column("booking_requests", "consent_accepted")
    op.drop_column("booking_requests", "disclaimer_accepted")
    op.drop_column("booking_requests", "insurance_info")
