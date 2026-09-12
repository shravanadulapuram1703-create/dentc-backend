"""Patients-module net-new tables (documents, emergency contacts, adjustments,
claim attachments). Resolves frontend Patients dev-report gaps.

All tenant-scoped; file-backed entities store an internal path + a served URL.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text
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
    # PROC-7c: which posted charge / claim this document supports. Before this
    # a document could only be tied to the *patient*, so "the crown on #30 has a
    # narrative attached" was not representable and ``requires_attachment``
    # could never be judged. Both optional; validated same-tenant + same-patient.
    procedure_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("patient_procedures.id"), index=True
    )
    claim_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("insurance_claims.id"), index=True
    )
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
    # SIG-5: drawn | scanned | verbal | topaz (published by signature_service.SIGNATURE_METHODS)
    signature_method: Mapped[str | None] = mapped_column(String(20))
    declined_reason: Mapped[str | None] = mapped_column(String(500))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # ── Topaz signature capture (SIG-1/2/3/4/7/8) - mirrors patient_signatures ──
    sig_string: Mapped[str | None] = mapped_column(Text)  # encrypted at rest
    sig_format: Mapped[str | None] = mapped_column(String(24))
    sig_compression: Mapped[int | None] = mapped_column(SmallInteger)
    sig_encryption: Mapped[int | None] = mapped_column(SmallInteger)
    point_count: Mapped[int | None] = mapped_column(Integer)
    stroke_count: Mapped[int | None] = mapped_column(Integer)
    device_source: Mapped[str | None] = mapped_column(String(20))
    device_vendor: Mapped[str | None] = mapped_column(String(20))
    device_model: Mapped[str | None] = mapped_column(String(40))
    device_serial: Mapped[str | None] = mapped_column(String(40))
    captured_user_agent: Mapped[str | None] = mapped_column(String(255))
    # SIG-7: SHA-256 over the rendered consent as it stood when signed, so an
    # edit to ``rendered_html`` afterwards reads as ``signature_status="stale"``.
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # ── Sign-in-viewer (docs/letters/consent_inline_signing_backend_devreport.md) ──
    # CS-1: the *signed* PDF rendition (signature stamped on the lines), kept
    # beside ``document_id`` (the printed / scanned copy) instead of replacing it.
    signed_document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("patient_documents.id")
    )
    # CS-3: the workstation capture time as sent; ``signed_at`` honours it when
    # it is within tolerance of the server clock (``signed_at_source``).
    captured_at: Mapped[datetime | None] = mapped_column(DateTime)
    signed_at_source: Mapped[str | None] = mapped_column(String(10))  # client | server
    # CS-4: the immutable "as signed" HTML — ``rendered_html`` stays editable
    # (and ``content_hash`` flags the edit); this is what was on the sheet.
    signed_rendered_html: Mapped[str | None] = mapped_column(Text)


class ConsentSignature(Base, IntPKMixin, CreatedAtMixin):
    """CS-2: a countersignature on a consent (Dentist / Hygienist / Assistant /
    Office Manager line). The consent row keeps the patient/guardian signature;
    every other line is one of these. Same capture block, SigString encrypted."""

    __tablename__ = "consent_signatures"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    consent_id: Mapped[int] = mapped_column(Integer, ForeignKey("patient_consents.id"), index=True)
    role: Mapped[str] = mapped_column(String(30))  # dentist | hygienist | assistant | office_manager | other
    signer_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    signer_provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    signer_name: Mapped[str | None] = mapped_column(String(120))
    signature_data: Mapped[str | None] = mapped_column(Text)
    signature_len: Mapped[int | None] = mapped_column(Integer)
    device_source: Mapped[str | None] = mapped_column(String(20))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime)
    sig_string: Mapped[str | None] = mapped_column(Text)
    sig_format: Mapped[str | None] = mapped_column(String(24))
    sig_compression: Mapped[int | None] = mapped_column(SmallInteger)
    sig_encryption: Mapped[int | None] = mapped_column(SmallInteger)
    point_count: Mapped[int | None] = mapped_column(Integer)
    stroke_count: Mapped[int | None] = mapped_column(Integer)
    device_vendor: Mapped[str | None] = mapped_column(String(20))
    device_model: Mapped[str | None] = mapped_column(String(40))
    device_serial: Mapped[str | None] = mapped_column(String(40))
    captured_user_agent: Mapped[str | None] = mapped_column(String(255))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    voided_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
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
