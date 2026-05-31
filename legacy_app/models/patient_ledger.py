"""
Patient Ledger module ORM models (contract-driven).

All tables live in tenant_1 schema.
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Date,
    Time,
    Text,
    TIMESTAMP,
    Numeric,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class PatientLedgerEntry(Base):
    __tablename__ = "patient_ledger_entries"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)
    transaction_id = Column(String(50), nullable=False, index=True)
    posted_date = Column(Date, nullable=False, index=True)

    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_name = Column(String(255), nullable=False)

    office_id = Column(Integer, ForeignKey("public.offices.id", ondelete="RESTRICT"), nullable=False, index=True)
    office_name = Column(String(255), nullable=False)

    apply_to = Column(String(1), nullable=False, default="P")
    code = Column(String(20), nullable=False, index=True)
    tooth = Column(String(10), nullable=True)
    surface = Column(String(20), nullable=True)
    type = Column(String(1), nullable=False, default="P")  # Production/Collection

    has_notes = Column(Boolean, nullable=False, default=False)
    has_eob = Column(Boolean, nullable=False, default=False)
    has_attachments = Column(Boolean, nullable=False, default=False)

    description = Column(Text, nullable=False)
    billing_order = Column(String(10), nullable=True)
    duration_minutes = Column(Integer, nullable=True)

    provider_id = Column(String(50), nullable=True)
    provider_name = Column(String(255), nullable=True)

    est_patient = Column(Numeric(12, 2), nullable=False, default=0)
    est_insurance = Column(Numeric(12, 2), nullable=False, default=0)

    posted_amount = Column(Numeric(12, 2), nullable=False)
    running_balance = Column(Numeric(12, 2), nullable=False)

    created_by = Column(String(100), nullable=False, default="system")
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    transaction_type = Column(String(30), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="", index=True)

    procedure_id = Column(String(50), nullable=True, index=True)
    claim_id = Column(String(50), nullable=True, index=True)
    payment_id = Column(String(50), nullable=True, index=True)
    adjustment_id = Column(String(50), nullable=True, index=True)


class PatientProcedure(Base):
    __tablename__ = "patient_procedures"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)

    procedure_code = Column(String(20), ForeignKey("tenant_1.procedure_codes.code", ondelete="RESTRICT"), nullable=False, index=True)
    date_of_service = Column(Date, nullable=False, index=True)

    provider_id = Column(String(50), nullable=False, index=True)
    provider_name = Column(String(255), nullable=False)

    office_id = Column(Integer, ForeignKey("public.offices.id", ondelete="RESTRICT"), nullable=False, index=True)
    office_name = Column(String(255), nullable=False)

    tooth = Column(String(10), nullable=True)
    surface = Column(String(20), nullable=True)
    quadrant = Column(String(10), nullable=True)
    materials = Column(JSONB, nullable=True)
    duration_minutes = Column(Integer, nullable=True)

    fee = Column(Numeric(12, 2), nullable=False)
    est_patient = Column(Numeric(12, 2), nullable=False, default=0)
    est_insurance = Column(Numeric(12, 2), nullable=False, default=0)

    billing_order = Column(String(10), nullable=True)
    notes = Column(Text, nullable=True)
    apply_to = Column(String(1), nullable=False, default="P")

    status = Column(String(30), nullable=False, default="not_sent", index=True)
    claim_id = Column(String(50), nullable=True, index=True)
    ledger_entry_id = Column(String(50), ForeignKey("tenant_1.patient_ledger_entries.id", ondelete="RESTRICT"), nullable=False, unique=True)

    created_by = Column(String(100), nullable=False, default="system")
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(String(100), nullable=False, default="system")

    ledger_entry = relationship("PatientLedgerEntry")


class PatientClaim(Base):
    __tablename__ = "patient_claims"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)
    claim_number = Column(String(50), nullable=False, unique=True, index=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(30), nullable=False, default="created", index=True)
    claim_type = Column(String(20), nullable=False)
    billing_order = Column(String(20), nullable=False)

    date_of_service_from = Column(Date, nullable=False)
    date_of_service_to = Column(Date, nullable=False)

    total_submitted_fees = Column(Numeric(12, 2), nullable=False, default=0)
    total_fee = Column(Numeric(12, 2), nullable=False, default=0)
    total_est_insurance = Column(Numeric(12, 2), nullable=False, default=0)

    notes = Column(Text, nullable=True)

    created_date = Column(Date, nullable=False, server_default=func.current_date())
    created_time = Column(Time, nullable=False, server_default=func.current_time())
    created_by = Column(String(100), nullable=False, default="system")
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    last_status_update_date = Column(Date, nullable=True)
    claim_sent_date = Column(Date, nullable=True)
    claim_sent_status = Column(String(50), nullable=True)
    claim_close_date = Column(Date, nullable=True)
    claim_closed_by = Column(String(100), nullable=True)
    dxc_attachment_id = Column(String(100), nullable=True)
    icd10_codes = Column(Text, nullable=True)
    send_method = Column(String(20), nullable=True)
    batch_id = Column(String(50), nullable=True, index=True)

    procedures = relationship("PatientClaimProcedure", back_populates="claim", cascade="all, delete-orphan")
    events = relationship("PatientClaimEvent", back_populates="claim", cascade="all, delete-orphan")
    attachments = relationship("PatientClaimAttachment", back_populates="claim", cascade="all, delete-orphan")


class PatientClaimProcedure(Base):
    __tablename__ = "patient_claim_procedures"
    __table_args__ = (
        UniqueConstraint("claim_id", "procedure_id", name="uq_claim_procedure"),
        {"schema": "tenant_1"},
    )

    id = Column(String(50), primary_key=True)
    claim_id = Column(String(50), ForeignKey("tenant_1.patient_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    procedure_id = Column(String(50), ForeignKey("tenant_1.patient_procedures.id", ondelete="RESTRICT"), nullable=False, index=True)

    claim = relationship("PatientClaim", back_populates="procedures")
    procedure = relationship("PatientProcedure")


class PatientClaimEvent(Base):
    __tablename__ = "patient_claim_events"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)
    claim_id = Column(String(50), ForeignKey("tenant_1.patient_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(30), nullable=False, index=True)
    event_date = Column(TIMESTAMP, server_default=func.now(), nullable=False, index=True)
    event_by = Column(String(100), nullable=False, default="system")
    details = Column(JSONB, nullable=True)

    claim = relationship("PatientClaim", back_populates="events")


class PatientClaimAttachment(Base):
    __tablename__ = "patient_claim_attachments"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)
    claim_id = Column(String(50), ForeignKey("tenant_1.patient_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    attachment_type = Column(String(50), nullable=False)
    required = Column(Boolean, nullable=False, default=False)
    provided = Column(Boolean, nullable=False, default=False)
    file_name = Column(String(255), nullable=True)
    uploaded_at = Column(TIMESTAMP, nullable=True)

    claim = relationship("PatientClaim", back_populates="attachments")


class PatientPayment(Base):
    __tablename__ = "patient_payments"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_date = Column(Date, nullable=False, index=True)
    payment_amount = Column(Numeric(12, 2), nullable=False)
    payment_type = Column(String(20), nullable=False)  # patient/insurance
    payment_method = Column(String(50), nullable=False)
    apply_to = Column(String(1), nullable=False)
    provider_id = Column(String(50), nullable=True)
    provider_name = Column(String(255), nullable=True)
    check_number = Column(String(100), nullable=True)
    bank_number = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    ledger_entry_id = Column(String(50), ForeignKey("tenant_1.patient_ledger_entries.id", ondelete="RESTRICT"), nullable=False, unique=True)
    created_by = Column(String(100), nullable=False, default="system")
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    ledger_entry = relationship("PatientLedgerEntry")
    applications = relationship("PatientPaymentApplication", back_populates="payment", cascade="all, delete-orphan")


class PatientPaymentApplication(Base):
    __tablename__ = "patient_payment_applications"
    __table_args__ = (
        UniqueConstraint("payment_id", "procedure_id", name="uq_payment_procedure"),
        {"schema": "tenant_1"},
    )

    id = Column(String(50), primary_key=True)
    payment_id = Column(String(50), ForeignKey("tenant_1.patient_payments.id", ondelete="CASCADE"), nullable=False, index=True)
    procedure_id = Column(String(50), ForeignKey("tenant_1.patient_procedures.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)

    payment = relationship("PatientPayment", back_populates="applications")
    procedure = relationship("PatientProcedure")


class PatientAdjustment(Base):
    __tablename__ = "patient_adjustments"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)
    patient_id = Column(Integer, ForeignKey("tenant_1.patients.id", ondelete="CASCADE"), nullable=False, index=True)
    adjustment_date = Column(Date, nullable=False, index=True)
    adjustment_amount = Column(Numeric(12, 2), nullable=False)  # negative
    adjustment_code = Column(String(50), nullable=False)
    adjustment_reason = Column(Text, nullable=False)
    apply_to = Column(String(1), nullable=False)
    notes = Column(Text, nullable=True)
    ledger_entry_id = Column(String(50), ForeignKey("tenant_1.patient_ledger_entries.id", ondelete="RESTRICT"), nullable=False, unique=True)
    created_by = Column(String(100), nullable=False, default="system")
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    ledger_entry = relationship("PatientLedgerEntry")
    applications = relationship("PatientAdjustmentApplication", back_populates="adjustment", cascade="all, delete-orphan")


class PatientAdjustmentApplication(Base):
    __tablename__ = "patient_adjustment_applications"
    __table_args__ = (
        UniqueConstraint("adjustment_id", "procedure_id", name="uq_adjustment_procedure"),
        {"schema": "tenant_1"},
    )

    id = Column(String(50), primary_key=True)
    adjustment_id = Column(String(50), ForeignKey("tenant_1.patient_adjustments.id", ondelete="CASCADE"), nullable=False, index=True)
    procedure_id = Column(String(50), ForeignKey("tenant_1.patient_procedures.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)

    adjustment = relationship("PatientAdjustment", back_populates="applications")
    procedure = relationship("PatientProcedure")


class PaymentCode(Base):
    __tablename__ = "payment_codes"
    __table_args__ = {"schema": "tenant_1"}

    code = Column(String(50), primary_key=True)
    description = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class AdjustmentCode(Base):
    __tablename__ = "adjustment_codes"
    __table_args__ = {"schema": "tenant_1"}

    code = Column(String(50), primary_key=True)
    description = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class ClaimStatus(Base):
    __tablename__ = "claim_statuses"
    __table_args__ = {"schema": "tenant_1"}

    code = Column(String(30), primary_key=True)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)


class TransactionType(Base):
    __tablename__ = "transaction_types"
    __table_args__ = {"schema": "tenant_1"}

    code = Column(String(30), primary_key=True)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

