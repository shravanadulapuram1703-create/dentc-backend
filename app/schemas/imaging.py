"""Imaging (DICOM archive) response schemas.

The frontend imaging tab consumes ``GET /patients/{id}/imaging`` (a
study→series→instance tree) and renders each instance's ``assets`` URLs directly
in ``<img>`` / download links. URLs are stable, self-authorising, and require no
bearer header — see docs/imaging/DICOM_IMAGING_API_CONTRACT.md.

All field names are snake_case (frontend binds to them directly).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InstanceAssets(BaseModel):
    """Ready-to-use, browser-facing URLs for one image instance."""

    # ready | pending | failed  — whether the web/thumbnail derivatives exist yet
    status: str = Field(examples=["ready", "pending", "failed"])
    thumbnail_url: str | None = Field(None, description="Small preview JPEG for the gallery grid")
    web_url: str | None = Field(None, description="Full-resolution web JPEG for the viewer")
    original_url: str | None = Field(None, description="Original .dcm download (not renderable)")


class DicomInstanceOut(BaseModel):
    id: int
    sop_instance_uid: str
    sop_class_uid: str | None = None
    instance_number: str | None = None
    modality: str | None = None
    rows: int | None = None
    columns: int | None = None
    bits_allocated: int | None = None
    photometric_interpretation: str | None = None
    window_center: str | None = None
    window_width: str | None = None
    tooth_numbers: list[int] | None = None
    anatomic_codes: list[str] | None = None
    derivative_status: str
    has_original_attributes: bool = False
    assets: InstanceAssets


class DicomSeriesOut(BaseModel):
    id: int
    series_instance_uid: str
    modality: str | None = None
    series_number: str | None = None
    body_part: str | None = None
    description: str | None = None
    instances: list[DicomInstanceOut] = []


class DicomStudyOut(BaseModel):
    id: int
    study_instance_uid: str
    study_date: str | None = None
    study_time: str | None = None
    description: str | None = None
    accession_number: str | None = None
    modalities: list[str] | None = None
    identity_review_required: bool = False
    image_count: int = 0
    series: list[DicomSeriesOut] = []


class PatientImagingResponse(BaseModel):
    patient_id: int
    study_count: int
    image_count: int
    latest_study_date: str | None = None
    studies: list[DicomStudyOut] = []


class PatientImagingSummary(BaseModel):
    """Lightweight counts for the imaging tab badge / patient overview."""

    patient_id: int
    study_count: int
    image_count: int
    latest_study_date: str | None = None
    modalities: list[str] = []
    pending_derivatives: int = 0
