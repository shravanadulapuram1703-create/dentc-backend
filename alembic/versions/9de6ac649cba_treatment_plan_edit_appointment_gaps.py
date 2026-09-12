"""Edit Treatment window + Tx Plan -> New Appt gaps

Revision ID: 9de6ac649cba
Revises: aee911131850
Create Date: 2026-09-10

Frontend reports: ``treatment_plan_backend_devreport.md`` (Edit Treatment
re-audit of 2026-09-08, PLAN-9/11/17/18/19/20/24/25/26/27/28/29) and
``tx_plan_new_appointment_backend_devreport.md`` (PLAN-APPT-1..7).

``treatment_plan_items``
    notes (PLAN-17), accepted_date / scheduled_date (PLAN-18), duration_minutes
    (PLAN-19 / PLAN-APPT-7), created_by / updated_by (PLAN-25), referral_id /
    referral_type (PLAN-27), update_end_date_at_posting / re_estimate_at_posting
    (PLAN-28), fee_schedule_id (PLAN-29), counselor_user_id (PLAN-11),
    status_before_scheduled (PLAN-APPT-1 — what to put back when the
    appointment is cancelled).

``treatment_plan_item_icd_codes`` (PLAN-26)
    item <-> ICD-10 link with an ordinal; ON DELETE CASCADE so a hard-deleted
    item can never be blocked by its diagnosis links (the PLAN-13 shape).

``treatment_plan_insurance_details``
    preauth_status / preauth_status_at (PLAN-9).

``appointment_procedures.treatment_plan_item_id`` (PLAN-APPT-2)
    the line books one *item*, not just a plan.

``providers.default_operatory_id`` (PLAN-APPT-4).

No legacy backfill in this revision. ``s27b`` wrote the diagnosing provider into
``diagnosed_by`` as the Denticon PROVIDERID string; resolving it into
``provider_id`` is ``scripts/backfill_treatment_plan_item_providers.py``
(PLAN-APPT-3). The migrated appointment lines and plan items both derive from
``AppointmentDetails.APPTDYD`` but ``appointment_procedures`` kept no legacy id,
so the historical item <-> line link is not reconstructable without a re-import.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "9de6ac649cba"
down_revision = "aee911131850"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── treatment_plan_items ─────────────────────────────────────────────────
    op.add_column("treatment_plan_items", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("treatment_plan_items", sa.Column("accepted_date", sa.Date(), nullable=True))
    op.add_column("treatment_plan_items", sa.Column("scheduled_date", sa.Date(), nullable=True))
    op.add_column("treatment_plan_items", sa.Column("duration_minutes", sa.Integer(), nullable=True))
    op.add_column(
        "treatment_plan_items",
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "treatment_plan_items",
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "treatment_plan_items",
        sa.Column("referral_id", sa.Integer(), sa.ForeignKey("referrals.id"), nullable=True),
    )
    op.add_column("treatment_plan_items", sa.Column("referral_type", sa.String(length=20), nullable=True))
    op.add_column(
        "treatment_plan_items",
        sa.Column("update_end_date_at_posting", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "treatment_plan_items",
        sa.Column("re_estimate_at_posting", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "treatment_plan_items",
        sa.Column("fee_schedule_id", sa.Integer(), sa.ForeignKey("fee_schedules.id"), nullable=True),
    )
    op.add_column(
        "treatment_plan_items",
        sa.Column("counselor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "treatment_plan_items",
        sa.Column("status_before_scheduled", sa.String(length=20), nullable=True),
    )

    # ── treatment_plan_item_icd_codes (PLAN-26) ──────────────────────────────
    op.create_table(
        "treatment_plan_item_icd_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_item_id", sa.String(length=50),
            sa.ForeignKey("treatment_plan_items.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("icd_code_id", sa.Integer(), sa.ForeignKey("icd_codes.id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("plan_item_id", "icd_code_id", name="uq_treatment_plan_item_icd_code"),
    )
    op.create_index(
        "ix_treatment_plan_item_icd_codes_plan_item_id",
        "treatment_plan_item_icd_codes", ["plan_item_id"],
    )
    op.create_index(
        "ix_treatment_plan_item_icd_codes_icd_code_id",
        "treatment_plan_item_icd_codes", ["icd_code_id"],
    )

    # ── treatment_plan_insurance_details (PLAN-9) ────────────────────────────
    op.add_column(
        "treatment_plan_insurance_details",
        sa.Column("preauth_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "treatment_plan_insurance_details",
        sa.Column("preauth_status_at", sa.DateTime(), nullable=True),
    )

    # ── appointment_procedures (PLAN-APPT-2) ─────────────────────────────────
    op.add_column(
        "appointment_procedures",
        sa.Column(
            "treatment_plan_item_id", sa.String(length=50),
            sa.ForeignKey("treatment_plan_items.id"), nullable=True,
        ),
    )
    op.create_index(
        "ix_appointment_procedures_treatment_plan_item_id",
        "appointment_procedures", ["treatment_plan_item_id"],
    )

    # ── providers (PLAN-APPT-4) ──────────────────────────────────────────────
    op.add_column(
        "providers",
        sa.Column(
            "default_operatory_id", sa.String(length=50),
            sa.ForeignKey("operatories.id"), nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("providers", "default_operatory_id")
    op.drop_index("ix_appointment_procedures_treatment_plan_item_id", table_name="appointment_procedures")
    op.drop_column("appointment_procedures", "treatment_plan_item_id")
    op.drop_column("treatment_plan_insurance_details", "preauth_status_at")
    op.drop_column("treatment_plan_insurance_details", "preauth_status")
    op.drop_index("ix_treatment_plan_item_icd_codes_icd_code_id", table_name="treatment_plan_item_icd_codes")
    op.drop_index("ix_treatment_plan_item_icd_codes_plan_item_id", table_name="treatment_plan_item_icd_codes")
    op.drop_table("treatment_plan_item_icd_codes")
    for col in (
        "status_before_scheduled", "counselor_user_id", "fee_schedule_id",
        "re_estimate_at_posting", "update_end_date_at_posting", "referral_type",
        "referral_id", "updated_by", "created_by", "duration_minutes",
        "scheduled_date", "accepted_date", "notes",
    ):
        op.drop_column("treatment_plan_items", col)
