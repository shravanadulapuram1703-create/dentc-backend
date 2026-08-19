"""Patients-module net-new tables (documents, emergency contacts, adjustments,
claim attachments). Resolves frontend Patients dev-report gaps.

All tenant-scoped; file-backed entities store an internal path + a served URL.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class PatientDocument(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "patient_documents"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    document_type: Mapped[str | None] = mapped_column(String(50))
    file_name: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_path: Mapped[str] = mapped_column(String(500))  # internal storage path
    file_url: Mapped[str] = mapped_column(String(500))   # served URL
    description: Mapped[str | None] = mapped_column(String(500))
    # LTR-1 ask #3: where the bytes actually live, so the UI can show provenance
    # and a migration of the pre-GCS rows is auditable. ``storage_path`` is the
    # object key inside ``storage_bucket`` (GCS) or the path under UPLOAD_DIR (local).
    storage_backend: Mapped[str] = mapped_column(String(20), default="local")  # local | gcs
    storage_bucket: Mapped[str | None] = mapped_column(String(255))
    storage_path: Mapped[str | None] = mapped_column(String(500))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientEmergencyContact(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "patient_emergency_contacts"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    relationship: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    # LEG-3: the Medical-Questionnaire "Emergency Contact" block flags a primary.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientAdjustment(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "patient_adjustments"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    procedure_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("patient_procedures.id"), index=True
    )
    adjustment_date: Mapped[date] = mapped_column()
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    adjustment_type: Mapped[str | None] = mapped_column(String(50))  # code from definitions 'adjustment'
    # ADJ-1: an enforced write-off classification (contractual | provider | insurance
    # | courtesy). Distinguishes a contractual/insurance write-off from a courtesy or
    # bad-debt adjustment so the office adjustment-summary can split them (DASH-4).
    write_off_type: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    is_void: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ProgressNoteAttachment(Base, IntPKMixin, CreatedAtMixin):
    """PN-3: a file attached to a *specific* progress note (mirrors the
    claim-attachment precedent). Tenancy via the note's patient; soft-deleted."""

    __tablename__ = "progress_note_attachments"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    progress_note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("progress_notes.id"), index=True
    )
    attachment_type: Mapped[str | None] = mapped_column(String(50))
    file_name: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_path: Mapped[str] = mapped_column(String(500))
    file_url: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(String(500))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientConsent(Base, IntPKMixin, CreatedAtMixin):
    """PLAN-7: a per-patient consent capture — a letter/consent template rendered
    with patient + treatment-plan data, optionally signed and stored. Distinct
    from the tenant-level account ``consents`` (those are the master documents)."""

    __tablename__ = "patient_consents"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("letter_templates.id"))
    plan_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("treatment_plans.id"))
    title: Mapped[str | None] = mapped_column(String(255))
    rendered_html: Mapped[str | None] = mapped_column(Text)
    # LTR-10: the published vocabulary (definitions group ``consent_status``).
    # pending  — created, nothing captured yet
    # printed  — rendered + handed to the patient on paper (no signature yet)
    # signed   — a signature (drawn capture or scanned wet copy) is attached
    # declined — the patient refused
    # voided   — superseded / entered in error
    status: Mapped[str] = mapped_column(String(20), default="pending")
    signature_data: Mapped[str | None] = mapped_column(Text)  # base64 capture (or print/scan)
    document_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patient_documents.id"))
    signed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime)
    # LTR-10: who physically signed (the patient / a guardian) and how, as opposed
    # to ``signed_by`` which is the staff user that captured it.
    signer_name: Mapped[str | None] = mapped_column(String(255))
    signer_relationship: Mapped[str | None] = mapped_column(String(50))
    signature_method: Mapped[str | None] = mapped_column(String(20))  # drawn | scanned | verbal
    declined_reason: Mapped[str | None] = mapped_column(String(500))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ClaimAttachment(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "claim_attachments"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    claim_id: Mapped[str] = mapped_column(String(50), ForeignKey("insurance_claims.id"), index=True)
    attachment_type: Mapped[str | None] = mapped_column(String(50))
    file_name: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_path: Mapped[str] = mapped_column(String(500))
    file_url: Mapped[str] = mapped_column(String(500))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
