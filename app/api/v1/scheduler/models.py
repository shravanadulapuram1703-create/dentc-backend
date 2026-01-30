"""
SQLAlchemy models for the Scheduler module.
These models are specific to the scheduler functionality and may differ from
the existing appointments model in app/models/appointments.py
"""
from sqlalchemy import (
    Column, Integer, String, Date, Time, Text, ForeignKey, TIMESTAMP,
    Enum as SQLEnum, Boolean, Numeric, DECIMAL
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class AppointmentStatusEnum(str, enum.Enum):
    """Appointment status enumeration matching frontend expectations"""
    SCHEDULED = "Scheduled"
    CONFIRMED = "Confirmed"
    UNCONFIRMED = "Unconfirmed"
    LEFT_MESSAGE = "Left Message"
    IN_RECEPTION = "In Reception"
    AVAILABLE = "Available"
    IN_OPERATORY = "In Operatory"
    CHECKED_OUT = "Checked Out"
    MISSED = "Missed"
    CANCELLED = "Cancelled"


class SchedulerAppointment(Base):
    """
    Scheduler-specific appointment model.
    This model is designed specifically for the scheduler module and follows
    the frontend expectations document.
    """
    __tablename__ = "scheduler_appointments"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    
    # Patient reference - using patient_id as string to match frontend (chart_no)
    patient_id = Column(String, nullable=False, index=True)
    
    # Date and time fields
    date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)  # HH:MM format
    end_time = Column(Time, nullable=False)    # Calculated from start_time + duration
    duration = Column(Integer, nullable=False)  # Duration in minutes
    
    # Procedure and location
    procedure_type = Column(String, nullable=False)
    operatory_id = Column(String, nullable=False, index=True)  # References scheduler_operatories.id
    provider_id = Column(String, nullable=False, index=True)   # References scheduler_providers.id
    
    # Status
    # Note: Enum type is created via SQL script in tenant_1 schema
    # Using schema-qualified name to ensure correct reference
    status = Column(
        SQLEnum(
            AppointmentStatusEnum, 
            name="appointment_status_enum",
            schema="tenant_1",
            create_type=False  # Enum is created via SQL script
        ),
        nullable=False,
        default=AppointmentStatusEnum.SCHEDULED,
        index=True
    )
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Lab fields
    lab = Column(Boolean, default=False, nullable=False)
    lab_dds = Column(String(200), nullable=True)
    lab_cost = Column(DECIMAL(10, 2), nullable=True)
    lab_sent_on = Column(Date, nullable=True)
    lab_due_on = Column(Date, nullable=True)
    lab_recvd_on = Column(Date, nullable=True)
    
    # Flags
    missed = Column(Boolean, default=False, nullable=False)
    cancelled = Column(Boolean, default=False, nullable=False)
    
    # Additional fields
    campaign_id = Column(String(100), nullable=True)
    
    # Treatment plan linkage
    treatment_plan_id = Column(String(50), nullable=True)
    treatment_plan_phase_id = Column(String(50), nullable=True)
    
    # Office reference for multi-tenant support
    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Timestamps
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    office = relationship("Office", backref="scheduler_appointments")

    treatments = relationship(
        "AppointmentTreatment",
        back_populates="appointment",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


class SchedulerOperatory(Base):
    """
    Operatory model for scheduler.
    Represents a dental operatory/room.
    """
    __tablename__ = "scheduler_operatories"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String, primary_key=True)  # e.g., "OP1", "OP2"
    name = Column(String, nullable=False)  # e.g., "OP 1 - Hygiene"
    provider_id = Column(String, nullable=False)  # References scheduler_providers.id
    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    office = relationship("Office", backref="scheduler_operatories")


class SchedulerProvider(Base):
    """
    Provider model for scheduler.
    Represents a dental provider (doctor, hygienist, etc.)
    """
    __tablename__ = "scheduler_providers"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String, primary_key=True)  # e.g., "PROV001", "PROV002"
    name = Column(String, nullable=False)  # e.g., "Dr. Jinna"
    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=True,  # Can be null for providers that work across offices
        index=True
    )
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    office = relationship("Office", backref="scheduler_providers")


class SchedulerProcedureType(Base):
    """
    Procedure type model for scheduler.
    Represents different types of procedures (Cleaning, New Patient, Crown, etc.)
    """
    __tablename__ = "scheduler_procedure_types"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String, primary_key=True)  # e.g., "PROC001", "PROC002"
    name = Column(String, nullable=False, unique=True)  # e.g., "Cleaning", "New Patient"
    color = Column(String, nullable=True)  # CSS color class or hex code, e.g., "bg-blue-100"
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class SchedulerConfig(Base):
    """
    Scheduler configuration model.
    Stores office-specific scheduler settings (working hours, slot intervals, etc.)
    """
    __tablename__ = "scheduler_config"
    __table_args__ = {"schema": "tenant_1"}

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        primary_key=True
    )
    
    start_hour = Column(Integer, nullable=False, default=8)  # 0-23, e.g., 8 for 8:00 AM
    end_hour = Column(Integer, nullable=False, default=17)    # 0-23, e.g., 17 for 5:00 PM
    slot_interval = Column(Integer, nullable=False, default=10)  # Minutes, e.g., 10 for 10-minute intervals
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    office = relationship("Office", backref="scheduler_config", uselist=False)


# ==================================================
# NEW MODELS FOR ADD/EDIT APPOINTMENT PAGE
# ==================================================

class AppointmentStatus(Base):
    """
    Appointment status model for status dropdown.
    Stores status types with display names and colors.
    """
    __tablename__ = "appointment_statuses"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)  # e.g., "STATUS001"
    name = Column(String(100), nullable=False, unique=True)  # e.g., "Scheduled"
    display_name = Column(String(100), nullable=False)  # e.g., "Scheduled"
    color = Column(String(20), nullable=True)  # CSS color or hex, e.g., "#3A6EA5"
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class AppointmentType(Base):
    """
    Appointment type model (optional - may reuse procedure types).
    """
    __tablename__ = "appointment_types"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)  # e.g., "TYPE001"
    name = Column(String(100), nullable=False, unique=True)  # e.g., "New Patient"
    description = Column(Text, nullable=True)
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)


class ProcedureCode(Base):
    """
    Procedure code model for Quick Add procedure browser.
    """
    __tablename__ = "procedure_codes"
    __table_args__ = {"schema": "tenant_1"}

    code = Column(String(20), primary_key=True)  # e.g., "D0120"
    user_code = Column(String(50), nullable=True)  # e.g., "PROPHY-ADULT"
    description = Column(String(500), nullable=False)
    category = Column(String(100), nullable=False, index=True)  # e.g., "DIAGNOSTIC"
    
    # Requirements
    requires_tooth = Column(Boolean, default=False, nullable=False)
    requires_surface = Column(Boolean, default=False, nullable=False)
    requires_quadrant = Column(Boolean, default=False, nullable=False)
    requires_materials = Column(Boolean, default=False, nullable=False)
    
    # Defaults
    default_fee = Column(DECIMAL(10, 2), nullable=False)
    default_duration = Column(Integer, nullable=True)  # minutes
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class ProcedureCategory(Base):
    """
    Procedure category model for filtering procedure codes.
    """
    __tablename__ = "procedure_categories"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)  # e.g., "DIAGNOSTIC"
    name = Column(String(100), nullable=False, unique=True)  # e.g., "DIAGNOSTIC"
    display_name = Column(String(100), nullable=False)  # e.g., "Diagnostic"
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)


class TreatmentPlan(Base):
    """
    Treatment plan model for patients.
    """
    __tablename__ = "treatment_plans"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)  # e.g., "TXP-001"
    name = Column(String(200), nullable=False)  # e.g., "Plan 1"
    patient_id = Column(String(50), nullable=False, index=True)  # References patients.chart_no
    status = Column(
        String(20),
        nullable=False,
        default="Active"
    )  # "Active", "Completed", "Cancelled"
    
    created_date = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class TreatmentPlanPhase(Base):
    """
    Treatment plan phase model.
    """
    __tablename__ = "treatment_plan_phases"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)  # e.g., "PHASE-001"
    treatment_plan_id = Column(
        String(50),
        ForeignKey("tenant_1.treatment_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name = Column(String(200), nullable=False)  # e.g., "Phase 1"
    phase_order = Column(Integer, nullable=False)  # Order within treatment plan
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    
    # Relationships
    treatment_plan = relationship("TreatmentPlan", backref="phases")


class TreatmentPlanProcedure(Base):
    """
    Treatment plan procedure model.
    """
    __tablename__ = "treatment_plan_procedures"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)  # e.g., "PROC-001"
    phase_id = Column(
        String(50),
        ForeignKey("tenant_1.treatment_plan_phases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    procedure_code = Column(
        String(20),
        ForeignKey("tenant_1.procedure_codes.code"),
        nullable=False
    )
    description = Column(String(500), nullable=False)
    tooth = Column(String(10), nullable=True)
    surface = Column(String(50), nullable=True)
    diagnosed_provider = Column(String(200), nullable=False)
    fee = Column(DECIMAL(10, 2), nullable=False)
    insurance_estimate = Column(DECIMAL(10, 2), default=0.00, nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default="Planned"
    )  # "Planned", "Scheduled", "Completed"
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    phase = relationship("TreatmentPlanPhase", backref="procedures")
    procedure = relationship("ProcedureCode", backref="treatment_plan_procedures")


class AppointmentTreatment(Base):
    """
    Appointment treatment/procedure model.
    Links procedures to appointments.
    """
    __tablename__ = "appointment_treatments"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(String(50), primary_key=True)  # e.g., "TREAT-001"
    appointment_id = Column(
        Integer,
        ForeignKey("tenant_1.scheduler_appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    procedure_code = Column(
        String(20),
        ForeignKey("tenant_1.procedure_codes.code"),
        nullable=False
    )
    status = Column(String(20), nullable=False)  # e.g., "TP" (Treatment Planned), "C" (Completed)
    tooth = Column(String(10), nullable=True)
    surface = Column(String(50), nullable=True)
    description = Column(String(500), nullable=True)
    bill_to = Column(String(50), default="Patient", nullable=False)  # "Patient", "Insurance", etc.
    duration = Column(Integer, nullable=False)  # minutes
    provider = Column(String(200), nullable=False)
    provider_units = Column(Integer, default=1, nullable=False)
    est_patient = Column(DECIMAL(10, 2), nullable=True)
    est_insurance = Column(DECIMAL(10, 2), nullable=True)
    fee = Column(DECIMAL(10, 2), nullable=False)
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    appointment = relationship("SchedulerAppointment", back_populates="treatments")
    procedure = relationship("ProcedureCode", backref="appointment_treatments")
