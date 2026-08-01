"""Imaging, collections, and referral-demographics models.

image_groups · image_details · collection_agencies · referral_demog_headers ·
referral_demog_details

DICOM archive (legacy Apteryx XVWeb migration → GCS + Postgres index):
stored_objects · dicom_studies · dicom_series · dicom_instances. The legacy
``image_groups``/``image_details`` stubs are intentionally left untouched — their
``legacy_id VARCHAR(20)`` cannot hold a 64-char DICOM UID, so the DICOM archive
gets its own first-class tables. See docs/imaging/DICOM_IMAGING_API_CONTRACT.md.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class ImageGroup(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "image_groups"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("imaging_templates.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(255))
    group_type: Mapped[str | None] = mapped_column(String(20))
    ext_id: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(50))
    source2: Mapped[str | None] = mapped_column(String(50))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100))


class ImageDetail(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "image_details"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    image_group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("image_groups.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    tile_id: Mapped[str | None] = mapped_column(String(20))
    filename: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    teeth: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class CollectionAgency(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "collection_agencies"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    address2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(100))


class ReferralDemogHeader(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "referral_demog_headers"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[str | None] = mapped_column(String(100))


class ReferralDemogDetail(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "referral_demog_details"

    referral_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("referrals.id"), index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    demog_header_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("referral_demog_headers.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    data: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(100))


# ── DICOM archive (GCS + Postgres index) ───────────────────────────────────
# The single record of "these bytes live in object storage". Content-addressed:
# ``object_key`` is derived from the file's SHA-256 by the migration uploader, so
# identical files dedupe to one row. Also reusable by the app's other uploads.
class StoredObject(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "stored_objects"

    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    bucket: Mapped[str] = mapped_column(String(200))
    object_key: Mapped[str] = mapped_column(String(500))
    # original | web | thumb | upload
    kind: Mapped[str | None] = mapped_column(String(20))
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    md5_b64: Mapped[str | None] = mapped_column(String(32))
    crc32c: Mapped[str | None] = mapped_column(String(16))
    storage_class: Mapped[str | None] = mapped_column(String(20))
    ref_count: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        UniqueConstraint("bucket", "object_key", name="uq_stored_objects_bucket_object_key"),
    )


class DicomStudy(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "dicom_studies"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    study_instance_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    accession_number: Mapped[str | None] = mapped_column(String(64))
    study_id: Mapped[str | None] = mapped_column(String(64))
    study_date: Mapped[date | None] = mapped_column(Date, index=True)
    study_time: Mapped[str | None] = mapped_column(String(24))
    description: Mapped[str | None] = mapped_column(String(255))
    modalities: Mapped[list | None] = mapped_column(JSON)  # e.g. ["IO", "PX"]
    # The raw legacy PatientID from the DICOM header, kept for audit/re-link.
    source_patient_id_raw: Mapped[str | None] = mapped_column(String(64))
    # Set when PatientID matched but name/DOB disagreed — surfaced, not trusted.
    identity_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_dicom_studies_tenant_patient_date", "tenant_id", "patient_id", "study_date"),
    )


class DicomSeries(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "dicom_series"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    study_id: Mapped[int] = mapped_column(Integer, ForeignKey("dicom_studies.id"), index=True)
    series_instance_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    modality: Mapped[str | None] = mapped_column(String(16))
    series_number: Mapped[str | None] = mapped_column(String(32))
    body_part: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(255))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class DicomInstance(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "dicom_instances"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("dicom_series.id"), index=True)
    sop_instance_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    sop_class_uid: Mapped[str | None] = mapped_column(String(64))
    instance_number: Mapped[str | None] = mapped_column(String(32))
    # pixel geometry (drives the derivative recipe + a future 16-bit viewer)
    rows: Mapped[int | None] = mapped_column(Integer)
    columns: Mapped[int | None] = mapped_column(Integer)
    bits_allocated: Mapped[int | None] = mapped_column(Integer)
    photometric_interpretation: Mapped[str | None] = mapped_column(String(32))
    window_center: Mapped[str | None] = mapped_column(String(64))
    window_width: Mapped[str | None] = mapped_column(String(64))
    applied_window_center: Mapped[str | None] = mapped_column(String(64))
    applied_window_width: Mapped[str | None] = mapped_column(String(64))
    # clinical tagging
    anatomic_codes: Mapped[list | None] = mapped_column(JSON)   # raw SNOMED SNM3 codes
    tooth_numbers: Mapped[list | None] = mapped_column(JSON)    # resolved tooth numbers
    # object-storage links
    original_object_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stored_objects.id"))
    web_object_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stored_objects.id"))
    thumb_object_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stored_objects.id"))
    # pending | thumb_ready | ready | failed
    derivative_status: Mapped[str] = mapped_column(String(20), default="pending")
    derivative_error: Mapped[str | None] = mapped_column(Text)
    # provenance / the XVWeb "CORRECT" re-identification trail
    superseded_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("dicom_instances.id"))
    has_original_attributes: Mapped[bool] = mapped_column(Boolean, default=False)
    original_attributes: Mapped[dict | None] = mapped_column(JSON)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
