"""Patients-module net-new tables (documents, emergency contacts, adjustments,
claim attachments). Resolves frontend Patients dev-report gaps.

All tenant-scoped; file-backed entities store an internal path + a served URL.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Numeric, String, Text
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientAdjustment(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "patient_adjustments"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    procedure_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("patient_procedures.id"))
    adjustment_date: Mapped[date] = mapped_column()
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    adjustment_type: Mapped[str | None] = mapped_column(String(50))  # code from definitions 'adjustment'
    notes: Mapped[str | None] = mapped_column(Text)
    is_void: Mapped[bool] = mapped_column(Boolean, default=False)
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
