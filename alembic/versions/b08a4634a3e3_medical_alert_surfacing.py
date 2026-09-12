"""medical alerts surfacing (MA-3/4/5) + patient-scoped audit (MH-19)

Revision ID: b08a4634a3e3
Revises: 239077e738d5
Create Date: 2026-09-10

Medical Alerts — surfacing in Prescriptions & Scheduler
(docs/medical-history/medical_alerts_surfacing_backend_devreport.md) and the
Created/Modified + change-log revision of the Medical History report (MH-17..22).

- ``patient_medical_alerts.section`` (MA-3): the catalog group the answer belongs
  to, filled from the MEDALERT definition at write time; client-sent = override.
- ``patient_medical_alerts.is_flash_alert`` / ``blocks_charges`` (MA-4): nullable
  per-answer overrides of the Setup catalog's flags. NULL = derive from the
  catalog (the read reports the effective value either way).
- ``prescriptions.alerts_acknowledged`` / ``acknowledged_alert_ids`` /
  ``alert_warnings`` / ``alerts_acknowledged_at`` / ``alerts_acknowledged_by``
  (MA-5): the prescriber saw the patient's active alerts, and *which* ones.
- ``prescription_library.allergy_keys`` (MA-5): the allergy slugs a library drug
  conflicts with.
- ``audit_logs.patient_id`` (MH-19): the chart a mutation belongs to, indexed, so
  a non-admin patient-scoped read is one filter instead of a JSON scan.

All additive and nullable (``alerts_acknowledged`` defaults false); no data is
rewritten. The MA-3 catalog fix is code (the built-in list is now the frontend
transcription), not data — stored ``alert_code``s were already the frontend's.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b08a4634a3e3"
down_revision = "239077e738d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient_medical_alerts", sa.Column("section", sa.String(100), nullable=True))
    op.add_column("patient_medical_alerts", sa.Column("is_flash_alert", sa.Boolean(), nullable=True))
    op.add_column("patient_medical_alerts", sa.Column("blocks_charges", sa.Boolean(), nullable=True))

    op.add_column(
        "prescriptions",
        sa.Column("alerts_acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("prescriptions", sa.Column("acknowledged_alert_ids", sa.JSON(), nullable=True))
    op.add_column("prescriptions", sa.Column("acknowledged_alerts", sa.JSON(), nullable=True))
    op.add_column("prescriptions", sa.Column("alert_warnings", sa.JSON(), nullable=True))
    op.add_column("prescriptions", sa.Column("alerts_acknowledged_at", sa.DateTime(), nullable=True))
    op.add_column(
        "prescriptions",
        sa.Column("alerts_acknowledged_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )

    op.add_column("prescription_library", sa.Column("allergy_keys", sa.JSON(), nullable=True))

    op.add_column("audit_logs", sa.Column("patient_id", sa.Integer(), nullable=True))
    op.create_index("ix_audit_logs_patient_id", "audit_logs", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_patient_id", table_name="audit_logs")
    op.drop_column("audit_logs", "patient_id")

    op.drop_column("prescription_library", "allergy_keys")

    for col in (
        "alerts_acknowledged_by",
        "alerts_acknowledged_at",
        "alert_warnings",
        "acknowledged_alerts",
        "acknowledged_alert_ids",
        "alerts_acknowledged",
    ):
        op.drop_column("prescriptions", col)

    for col in ("blocks_charges", "is_flash_alert", "section"):
        op.drop_column("patient_medical_alerts", col)
