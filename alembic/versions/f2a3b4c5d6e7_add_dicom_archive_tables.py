"""add DICOM archive tables (stored_objects, dicom_studies/series/instances)

First-class home for the migrated legacy imaging archive (Apteryx XVWeb → GCS +
Postgres index). The legacy image_groups/image_details stubs are left untouched
(their legacy_id VARCHAR(20) cannot hold a 64-char DICOM UID). Backs
GET /patients/{id}/imaging and the token-authorised /dicom-instances/* serving.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-29

Additive.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stored_objects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("bucket", sa.String(200), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(20)),
        sa.Column("content_type", sa.String(100)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("md5_b64", sa.String(32)),
        sa.Column("crc32c", sa.String(16)),
        sa.Column("storage_class", sa.String(20)),
        sa.Column("ref_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("bucket", "object_key", name="uq_stored_objects_bucket_object_key"),
    )
    op.create_index("ix_stored_objects_tenant_id", "stored_objects", ["tenant_id"])
    op.create_index("ix_stored_objects_sha256", "stored_objects", ["sha256"])

    op.create_table(
        "dicom_studies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("study_instance_uid", sa.String(64), nullable=False),
        sa.Column("accession_number", sa.String(64)),
        sa.Column("study_id", sa.String(64)),
        sa.Column("study_date", sa.Date()),
        sa.Column("study_time", sa.String(24)),
        sa.Column("description", sa.String(255)),
        sa.Column("modalities", sa.JSON()),
        sa.Column("source_patient_id_raw", sa.String(64)),
        sa.Column("identity_review_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint("study_instance_uid", name="uq_dicom_studies_study_instance_uid"),
    )
    op.create_index("ix_dicom_studies_tenant_id", "dicom_studies", ["tenant_id"])
    op.create_index("ix_dicom_studies_patient_id", "dicom_studies", ["patient_id"])
    op.create_index("ix_dicom_studies_study_date", "dicom_studies", ["study_date"])
    op.create_index("ix_dicom_studies_tenant_patient_date", "dicom_studies",
                    ["tenant_id", "patient_id", "study_date"])

    op.create_table(
        "dicom_series",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("study_id", sa.Integer(), sa.ForeignKey("dicom_studies.id"), nullable=False),
        sa.Column("series_instance_uid", sa.String(64), nullable=False),
        sa.Column("modality", sa.String(16)),
        sa.Column("series_number", sa.String(32)),
        sa.Column("body_part", sa.String(64)),
        sa.Column("description", sa.String(255)),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("series_instance_uid", name="uq_dicom_series_series_instance_uid"),
    )
    op.create_index("ix_dicom_series_tenant_id", "dicom_series", ["tenant_id"])
    op.create_index("ix_dicom_series_study_id", "dicom_series", ["study_id"])

    op.create_table(
        "dicom_instances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("dicom_series.id"), nullable=False),
        sa.Column("sop_instance_uid", sa.String(64), nullable=False),
        sa.Column("sop_class_uid", sa.String(64)),
        sa.Column("instance_number", sa.String(32)),
        sa.Column("rows", sa.Integer()),
        sa.Column("columns", sa.Integer()),
        sa.Column("bits_allocated", sa.Integer()),
        sa.Column("photometric_interpretation", sa.String(32)),
        sa.Column("window_center", sa.String(64)),
        sa.Column("window_width", sa.String(64)),
        sa.Column("applied_window_center", sa.String(64)),
        sa.Column("applied_window_width", sa.String(64)),
        sa.Column("anatomic_codes", sa.JSON()),
        sa.Column("tooth_numbers", sa.JSON()),
        sa.Column("original_object_id", sa.Integer(), sa.ForeignKey("stored_objects.id")),
        sa.Column("web_object_id", sa.Integer(), sa.ForeignKey("stored_objects.id")),
        sa.Column("thumb_object_id", sa.Integer(), sa.ForeignKey("stored_objects.id")),
        sa.Column("derivative_status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("derivative_error", sa.Text()),
        sa.Column("superseded_by", sa.Integer(), sa.ForeignKey("dicom_instances.id")),
        sa.Column("has_original_attributes", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("original_attributes", sa.JSON()),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("sop_instance_uid", name="uq_dicom_instances_sop_instance_uid"),
    )
    op.create_index("ix_dicom_instances_tenant_id", "dicom_instances", ["tenant_id"])
    op.create_index("ix_dicom_instances_series_id", "dicom_instances", ["series_id"])


def downgrade() -> None:
    op.drop_table("dicom_instances")
    op.drop_table("dicom_series")
    op.drop_table("dicom_studies")
    op.drop_table("stored_objects")
