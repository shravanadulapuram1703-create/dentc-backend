"""
Pydantic schemas for the Scheduler module.
These schemas strictly match the frontend expectations document.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, List
from datetime import date as date_type, time
from enum import Enum
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time,
    ForeignKey, Text, TIMESTAMP, Identity,Numeric
)
from datetime import date
from datetime import datetime


# Type alias to avoid name clash with field name 'date'
DateType = date_type

# Appointment Status Enum (matching frontend)
# AppointmentStatus = Literal[
#     "Scheduled", "Confirmed", "Unconfirmed", "Left Message",
#     "In Reception", "Available", "In Operatory", "Checked Out",
#     "Missed", "Cancelled", "SCHEDULED"
# ]
class AppointmentStatus(str, Enum):
    Scheduled = "Scheduled"
    Confirmed = "Confirmed"
    Unconfirmed = "Unconfirmed"
    LeftMessage = "Left Message"
    InReception = "In Reception"
    Available = "Available"
    InOperatory = "In Operatory"
    CheckedOut = "Checked Out"
    Missed = "Missed"
    Cancelled = "Cancelled"



# ==================================================
# APPOINTMENT SCHEMAS
# ==================================================

class AppointmentTreatmentCreate(BaseModel):
    """Schema for creating appointment treatment"""
    procedure_code: Optional[str] = Field(None, alias="procedureCode", description="Procedure code (e.g., 'D0120'). If not provided, will be set to 'UNKNOWN'")
    status: str = Field(..., description="Treatment status: 'TP' (Treatment Planned), 'C' (Completed), etc.")
    tooth: Optional[str] = Field(None, description="Tooth number/identifier")
    surface: Optional[str] = Field(None, description="Surface identifier")
    description: str = Field(..., description="Procedure description")
    bill_to: Optional[str] = Field(default="Patient", alias="billTo", description="Billing target: 'Patient', 'Insurance', etc.")
    duration: int = Field(..., description="Procedure duration in minutes")
    provider: str = Field(..., description="Provider name")
    provider_units: Optional[int] = Field(default=1, alias="providerUnits", description="Provider units")
    est_patient: Optional[float] = Field(None, alias="estPatient", description="Estimated patient cost")
    est_insurance: Optional[float] = Field(None, alias="estInsurance", description="Estimated insurance cost")
    fee: float = Field(..., description="Procedure fee")
    
    @field_validator('procedure_code', mode='before')
    @classmethod
    def set_default_procedure_code(cls, v):
        """Set default procedure code if not provided"""
        if v is None or v == "":
            return "UNKNOWN"
        return v
    
    class Config:
        populate_by_name = True


class AppointmentBase(BaseModel):
    """Base appointment schema with common fields - supports both Quick Save and Full Save"""
    patient_id: str = Field(..., alias="patientId", description="Patient ID (chart number)")
    date: str = Field(..., description="Appointment date in YYYY-MM-DD format")
    start_time: str = Field(..., alias="startTime", pattern=r'^\d{2}:\d{2}$', description="Start time in HH:MM format")
    duration: int = Field(..., gt=0, le=480, description="Duration in minutes (must be > 0 and <= 480)")
    procedure_type: str = Field(..., alias="procedureType", description="Procedure type name")
    operatory: str = Field(..., description="Operatory ID")
    provider: str = Field(..., description="Provider ID")
    notes: Optional[str] = Field(default="", description="Appointment notes")
    status: AppointmentStatus = Field(default="Scheduled", description="Appointment status")
    
    # Lab information fields (optional - for Full Save)
    lab: Optional[bool] = Field(default=False, description="Whether lab work is required")
    lab_dds: Optional[str] = Field(None, alias="labDds", description="Lab DDS name")
    lab_cost: Optional[float] = Field(None, alias="labCost", description="Lab cost")
    lab_sent_on: Optional[str] = Field(None, alias="labSentOn", description="Date lab work was sent (YYYY-MM-DD)")
    lab_due_on: Optional[str] = Field(None, alias="labDueOn", description="Date lab work is due (YYYY-MM-DD)")
    lab_recvd_on: Optional[str] = Field(None, alias="labRecvdOn", description="Date lab work was received (YYYY-MM-DD)")
    
    # Flag fields (optional - for Full Save)
    missed: Optional[bool] = Field(default=False, description="Whether appointment was missed")
    cancelled: Optional[bool] = Field(default=False, description="Whether appointment was cancelled")
    
    # Additional fields (optional - for Full Save)
    campaign_id: Optional[str] = Field(None, alias="campaignId", description="Campaign identifier")
    
    # Treatment plan linkage (optional - for Full Save)
    treatment_plan_id: Optional[str] = Field(None, alias="treatmentPlanId", description="Linked treatment plan ID")
    treatment_plan_phase_id: Optional[str] = Field(None, alias="treatmentPlanPhaseId", description="Linked treatment plan phase ID")
    
    # Treatments array (optional - for Full Save)
    treatments: Optional[List[AppointmentTreatmentCreate]] = Field(None, description="List of treatments/procedures for this appointment")
    
    class Config:
        populate_by_name = True  # Allow both alias and field name


class AppointmentCreate(AppointmentBase):
    """Schema for creating a new appointment"""
    pass


class AppointmentUpdate(BaseModel):
    """Schema for updating an existing appointment (all fields optional)"""
    patient_id: Optional[str] = Field(None, alias="patientId")
    date: Optional[str] = None
    start_time: Optional[str] = Field(None, alias="startTime", pattern=r'^\d{2}:\d{2}$')
    duration: Optional[int] = Field(None, gt=0, le=480)
    procedure_type: Optional[str] = Field(None, alias="procedureType")
    operatory: Optional[str] = None
    provider: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[AppointmentStatus] = None
    
    # Lab information fields
    lab: Optional[bool] = None
    lab_dds: Optional[str] = Field(None, alias="labDds")
    lab_cost: Optional[float] = Field(None, alias="labCost")
    lab_sent_on: Optional[str] = Field(None, alias="labSentOn")
    lab_due_on: Optional[str] = Field(None, alias="labDueOn")
    lab_recvd_on: Optional[str] = Field(None, alias="labRecvdOn")
    
    # Flag fields
    missed: Optional[bool] = None
    cancelled: Optional[bool] = None
    
    # Additional fields
    campaign_id: Optional[str] = Field(None, alias="campaignId")
    
    # Treatment plan linkage
    treatment_plan_id: Optional[str] = Field(None, alias="treatmentPlanId")
    treatment_plan_phase_id: Optional[str] = Field(None, alias="treatmentPlanPhaseId")
    
    # Treatments array
    treatments: Optional[List[AppointmentTreatmentCreate]] = None
    
    class Config:
        populate_by_name = True


class AppointmentTreatmentResponse(BaseModel):
    """Schema for appointment treatment response"""
    id: str = Field(..., description="Treatment ID")
    appointment_id: str = Field(..., alias="appointmentId")
    procedure_code: str = Field(..., alias="procedureCode")
    status: str
    tooth: Optional[str] = None
    surface: Optional[str] = None
    description: str
    bill_to: str = Field(..., alias="billTo")
    duration: int
    provider: str
    provider_units: int = Field(..., alias="providerUnits")
    est_patient: Optional[float] = Field(None, alias="estPatient")
    est_insurance: Optional[float] = Field(None, alias="estInsurance")
    fee: float
    created_at: str = Field(..., alias="createdAt")
    updated_at: str = Field(..., alias="updatedAt")
    
    class Config:
        populate_by_name = True
        from_attributes = True


class AppointmentResponse(BaseModel):
    """Schema for appointment response (matches frontend expectations exactly)"""
    id: str = Field(..., description="Appointment ID (UUID or unique identifier)")
    patient_id: str = Field(..., alias="patientId")
    patient_name: str = Field(..., alias="patientName", description="Patient name in 'LastName, FirstName' format")
    date: DateType
    start_time: str = Field(..., alias="startTime", pattern=r'^\d{2}:\d{2}$', description="Start time in HH:MM format")
    end_time: str = Field(..., alias="endTime", pattern=r'^\d{2}:\d{2}$', description="End time in HH:MM format (calculated)")
    duration: int
    procedure_type: str = Field(..., alias="procedureType")
    status: AppointmentStatus
    operatory: str
    provider: str
    notes: str
    
    # Lab information fields
    lab: Optional[bool] = None
    lab_dds: Optional[str] = Field(None, alias="labDds")
    lab_cost: Optional[float] = Field(None, alias="labCost")
    lab_sent_on: Optional[str] = Field(None, alias="labSentOn")
    lab_due_on: Optional[str] = Field(None, alias="labDueOn")
    lab_recvd_on: Optional[str] = Field(None, alias="labRecvdOn")
    
    # Flag fields
    missed: Optional[bool] = None
    cancelled: Optional[bool] = None
    
    # Additional fields
    campaign_id: Optional[str] = Field(None, alias="campaignId")
    
    # Treatment plan linkage
    treatment_plan_id: Optional[str] = Field(None, alias="treatmentPlanId")
    treatment_plan_phase_id: Optional[str] = Field(None, alias="treatmentPlanPhaseId")
    
    # Treatments array
    treatments: Optional[List[AppointmentTreatmentResponse]] = None
    
    # Timestamps
    created_at: Optional[str] = Field(None, alias="createdAt")
    updated_at: Optional[str] = Field(None, alias="updatedAt")

    class Config:
        populate_by_name = True  # Allow both alias and field name
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "patient_id": "900097",
                "patient_name": "Miller, Nicolas",
                "date": "2024-12-20",
                "start_time": "09:00",
                "end_time": "10:00",
                "duration": 60,
                "procedure_type": "New Patient",
                "status": "Confirmed",
                "operatory": "OP1",
                "provider": "Dr. Jinna",
                "notes": "First visit"
            }
        }


class AppointmentStatusUpdate(BaseModel):
    """Schema for updating only the appointment status"""
    status: AppointmentStatus = Field(..., description="New appointment status")


class AppointmentsResponse(BaseModel):
    """Response wrapper for list of appointments"""
    appointments: List[AppointmentResponse]


class AppointmentSingleResponse(BaseModel):
    """Response wrapper for single appointment"""
    appointment: AppointmentResponse


# ==================================================
# OPERATORY SCHEMAS
# ==================================================

class OperatoryResponse(BaseModel):
    """Schema for operatory response"""
    id: str = Field(..., description="Operatory ID (e.g., 'OP1')")
    name: Optional[str] = Field(..., description="Operatory name (e.g., 'OP 1 - Hygiene')")
    provider: Optional[str] = Field(..., description="Provider name (e.g., 'Dr. Jinna')")
    office: Optional[str] = Field(..., description="Office name (e.g., 'Moon, PA')")
    display_order: Optional[int] = Field(..., description="Display order (e.g., 1)")
    is_active: Optional[bool] = Field(..., description="Is active (e.g., True)")
    has_future_appointments: Optional[bool] = Field(..., description="Has future appointments (e.g., True)")
    created_at:  Optional[datetime] = Field(..., description="Created at (e.g., '2021-01-01')")
    updated_at:  Optional[datetime] = Field(..., description="Updated at (e.g., '2021-01-01')")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "OP1",
                "name": "OP 1 - Hygiene",
                "provider": "Dr. Jinna",
                "office": "Moon, PA"
            }
        }


class OperatoriesResponse(BaseModel):
    """Response wrapper for list of operatories"""
    operatories: List[OperatoryResponse]


# ==================================================
# PROVIDER SCHEMAS
# ==================================================

class ProviderResponse(BaseModel):
    """Schema for provider response"""
    id: str = Field(..., description="Provider ID (e.g., 'PROV001')")
    name: str = Field(..., description="Provider name (e.g., 'Dr. Jinna')")
    office: Optional[str] = Field(None, description="Office name (optional)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "PROV001",
                "name": "Dr. Jinna",
                "office": "Moon, PA"
            }
        }


class ProvidersResponse(BaseModel):
    """Response wrapper for list of providers"""
    providers: List[ProviderResponse]


# ==================================================
# PROCEDURE TYPE SCHEMAS
# ==================================================

class ProcedureTypeResponse(BaseModel):
    """Schema for procedure type response"""
    id: str = Field(..., description="Procedure type ID (e.g., 'PROC001')")
    name: str = Field(..., description="Procedure type name (e.g., 'Cleaning')")
    color: Optional[str] = Field(None, description="CSS color class or hex code (e.g., 'bg-blue-100')")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "PROC001",
                "name": "Cleaning",
                "color": "bg-blue-100"
            }
        }


class ProcedureTypesResponse(BaseModel):
    """Response wrapper for list of procedure types"""
    procedure_types: List[ProcedureTypeResponse]


# ==================================================
# SCHEDULER CONFIG SCHEMAS
# ==================================================

class SchedulerConfigResponse(BaseModel):
    """Schema for scheduler configuration response"""
    start_hour: int = Field(..., ge=0, le=23, description="Start hour (0-23, e.g., 8 for 8:00 AM)")
    end_hour: int = Field(..., ge=0, le=23, description="End hour (0-23, e.g., 17 for 5:00 PM)")
    slot_interval: int = Field(..., gt=0, description="Slot interval in minutes (e.g., 10 for 10-minute intervals)")

    class Config:
        json_schema_extra = {
            "example": {
                "start_hour": 8,
                "end_hour": 17,
                "slot_interval": 10
            }
        }


class SchedulerConfigWrapper(BaseModel):
    """Response wrapper for scheduler configuration"""
    config: SchedulerConfigResponse


# ==================================================
# ERROR RESPONSE SCHEMAS
# ==================================================

class ErrorResponse(BaseModel):
    """Standard error response schema"""
    detail: str
    status_code: int
    errors: Optional[dict] = None


# ==================================================
# NEW SCHEMAS FOR ADD/EDIT APPOINTMENT PAGE
# ==================================================

class AppointmentStatusResponse(BaseModel):
    """Schema for appointment status response"""
    id: str = Field(..., description="Status ID (e.g., 'STATUS001')")
    name: str = Field(..., description="Status name (e.g., 'Scheduled')")
    displayName: str = Field(..., alias="display_name", description="Display name")
    color: Optional[str] = Field(None, description="CSS color or hex code")
    
    class Config:
        populate_by_name = True
        from_attributes = True


class AppointmentStatusesResponse(BaseModel):
    """Schema for appointment statuses list response"""
    statuses: List[AppointmentStatusResponse]


class AppointmentTypeResponse(BaseModel):
    """Schema for appointment type response"""
    id: str = Field(..., description="Type ID")
    name: str = Field(..., description="Type name")
    description: Optional[str] = Field(None, description="Type description")
    
    class Config:
        from_attributes = True


class AppointmentTypesResponse(BaseModel):
    """Schema for appointment types list response"""
    appointment_types: List[AppointmentTypeResponse] = Field(..., alias="appointmentTypes")
    
    class Config:
        populate_by_name = True


class ProcedureCodeRequirements(BaseModel):
    """Schema for procedure code requirements"""
    tooth: bool = Field(..., description="Requires tooth selection")
    surface: bool = Field(..., description="Requires surface selection")
    quadrant: bool = Field(..., description="Requires quadrant selection")
    materials: bool = Field(..., description="Requires materials selection")
    
    class Config:
        populate_by_name = True


class ProcedureCodeResponse(BaseModel):
    """Schema for procedure code response"""
    code: str = Field(..., description="Procedure code (e.g., 'D0120')")
    userCode: str = Field(..., alias="user_code", description="User code (e.g., 'PROPHY-ADULT')")
    description: str = Field(..., description="Procedure description")
    category: str = Field(..., description="Procedure category")
    requirements: ProcedureCodeRequirements = Field(..., description="Procedure requirements")
    defaultFee: float = Field(..., alias="default_fee", description="Default fee")
    defaultDuration: Optional[int] = Field(None, alias="default_duration", description="Default duration in minutes")
    
    class Config:
        populate_by_name = True
        from_attributes = True


class ProcedureCodesResponse(BaseModel):
    """Schema for procedure codes list response"""
    procedure_codes: List[ProcedureCodeResponse] = Field(..., alias="procedureCodes")
    
    class Config:
        populate_by_name = True


class ProcedureCategoryResponse(BaseModel):
    """Schema for procedure category response"""
    id: str = Field(..., description="Category ID (e.g., 'DIAGNOSTIC')")
    name: str = Field(..., description="Category name")
    displayName: str = Field(..., alias="display_name", description="Display name")
    
    class Config:
        populate_by_name = True
        from_attributes = True


class ProcedureCategoriesResponse(BaseModel):
    """Schema for procedure categories list response"""
    categories: List[ProcedureCategoryResponse]


class TreatmentPlanProcedureResponse(BaseModel):
    """Schema for treatment plan procedure response"""
    id: str = Field(..., description="Procedure ID")
    code: str = Field(..., description="Procedure code")
    description: str = Field(..., description="Procedure description")
    tooth: Optional[str] = Field(None, description="Tooth number")
    surface: Optional[str] = Field(None, description="Surface")
    diagnosedProvider: str = Field(..., alias="diagnosed_provider", description="Diagnosed provider")
    fee: float = Field(..., description="Fee amount")
    insuranceEstimate: float = Field(..., alias="insurance_estimate", description="Insurance estimate")
    status: str = Field(..., description="Status: 'Planned', 'Scheduled', or 'Completed'")
    
    class Config:
        populate_by_name = True
        from_attributes = True


class TreatmentPlanPhaseResponse(BaseModel):
    """Schema for treatment plan phase response"""
    id: str = Field(..., description="Phase ID")
    name: str = Field(..., description="Phase name")
    procedures: List[TreatmentPlanProcedureResponse] = Field(..., description="Procedures in this phase")
    
    class Config:
        from_attributes = True


class TreatmentPlanResponse(BaseModel):
    """Schema for treatment plan response"""
    id: str = Field(..., description="Treatment plan ID")
    name: str = Field(..., description="Treatment plan name")
    patientId: str = Field(..., alias="patient_id", description="Patient ID")
    phases: List[TreatmentPlanPhaseResponse] = Field(..., description="Phases in the treatment plan")
    createdDate: str = Field(..., alias="created_date", description="Creation date (ISO 8601)")
    status: str = Field(..., description="Status: 'Active', 'Completed', or 'Cancelled'")
    
    class Config:
        populate_by_name = True
        from_attributes = True


class TreatmentPlansResponse(BaseModel):
    """Schema for treatment plans list response"""
    treatment_plans: List[TreatmentPlanResponse] = Field(..., alias="treatmentPlans")
    
    class Config:
        populate_by_name = True
