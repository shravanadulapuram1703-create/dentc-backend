"""
Service layer for the Scheduler module.
Contains all business logic for appointments, operatories, providers, etc.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func as sql_func, literal, cast, text
from sqlalchemy.types import String
from datetime import date, time, datetime, timedelta
from typing import List, Optional
from fastapi import HTTPException, status

from app.models.offices import OfficeOperatory, OfficeProvider

from app.api.v1.scheduler.models import (
    SchedulerAppointment,
    SchedulerOperatory,

    SchedulerProvider,
    SchedulerProcedureType,
    SchedulerConfig,
    AppointmentStatusEnum,
    AppointmentTreatment
)
from app.api.v1.scheduler.schemas import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentResponse,
    AppointmentStatusUpdate,
    OperatoryResponse,
    ProviderResponse,
    ProcedureTypeResponse,
    SchedulerConfigResponse
)
from app.models.patient import Patient
from app.models.offices import Office

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)
# ==================================================
# UTILITY FUNCTIONS
# ==================================================

def normalize_status_to_enum(status_value: str) -> AppointmentStatusEnum:
    """
    Normalize status string to AppointmentStatusEnum.
    Handles case variations and finds the matching enum value.
    
    Args:
        status_value: Status string (can be any case)
    
    Returns:
        AppointmentStatusEnum instance
    
    Raises:
        HTTPException: If status value is invalid
    """
    # Try direct conversion first
    try:
        return AppointmentStatusEnum(status_value)
    except ValueError:
        pass
    
    # Try case-insensitive matching
    status_lower = status_value.lower().strip()
    for enum_member in AppointmentStatusEnum:
        if enum_member.value.lower() == status_lower:
            return enum_member
    
    # If still not found, raise error
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Invalid appointment status: {status_value}. Valid values are: {[e.value for e in AppointmentStatusEnum]}"
    )


def calculate_end_time(start_time_str: str, duration_minutes: int) -> str:
    """
    Calculate end_time from start_time and duration.
    
    Args:
        start_time_str: Start time in "HH:MM" format
        duration_minutes: Duration in minutes
    
    Returns:
        End time in "HH:MM" format
    """
    # Parse start_time
    hour, minute = map(int, start_time_str.split(':'))
    start_dt = datetime.combine(date.today(), time(hour, minute))
    
    # Add duration
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    
    # Format as HH:MM
    return end_dt.strftime("%H:%M")


def get_patient_name(db: Session, patient_id: str) -> str:
    """
    Fetch patient name from patient record.
    Returns name in "LastName, FirstName" format.
    
    Args:
        db: Database session
        patient_id: Patient ID (chart_no or id as string)
    
    Returns:
        Patient name in "LastName, FirstName" format
    
    Raises:
        HTTPException: If patient not found
    """
    # Try to find by chart_no first (string match)
    patient = db.query(Patient).filter(Patient.chart_no == patient_id).first()
    
    # If not found, try by ID
    if not patient:
        try:
            patient_id_int = int(patient_id)
            patient = db.query(Patient).filter(Patient.id == patient_id_int).first()
        except ValueError:
            pass
    
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID '{patient_id}' not found"
        )
    
    # Format as "LastName, FirstName"
    last_name = patient.last_name or ""
    first_name = patient.first_name or ""
    
    if not last_name and not first_name:
        return patient_id  # Fallback to ID if no name available
    
    return f"{last_name}, {first_name}".strip(", ")


def check_appointment_overlap(
    db: Session,
    operatory_id: str,
    appointment_date: date,
    start_time_str: str,
    end_time_str: str,
    exclude_appointment_id: Optional[int] = None
) -> bool:
    """
    Check if an appointment overlaps with existing appointments for the same operatory.
    
    Args:
        db: Database session
        operatory_id: Operatory ID
        appointment_date: Appointment date
        start_time_str: Start time in "HH:MM" format
        end_time_str: End time in "HH:MM" format
        exclude_appointment_id: Appointment ID to exclude from check (for updates)
    
    Returns:
        True if overlap exists, False otherwise
    """
    # Parse times
    start_hour, start_minute = map(int, start_time_str.split(':'))
    end_hour, end_minute = map(int, end_time_str.split(':'))
    
    start_time_obj = time(start_hour, start_minute)
    end_time_obj = time(end_hour, end_minute)

    # Query for overlapping appointments
    # Exclude cancelled/missed appointments from overlap check
    # Use string literals that match the database enum values exactly
    query = db.query(SchedulerAppointment).filter(
        SchedulerAppointment.operatory_id == operatory_id,
        SchedulerAppointment.date == appointment_date,
        SchedulerAppointment.status.notin_([
            'Cancelled',  # Database enum value
            'Missed'      # Database enum value
        ]),
        # Overlap condition: new_start < existing_end AND new_end > existing_start
        and_(
            start_time_obj < SchedulerAppointment.end_time,
            end_time_obj > SchedulerAppointment.start_time
        )
    )
    
    if exclude_appointment_id:
        query = query.filter(SchedulerAppointment.id != exclude_appointment_id)
    
    return query.first() is not None


# ==================================================
# APPOINTMENT SERVICES
# ==================================================

def build_appointment_response(
    db: Session,
    appointment: SchedulerAppointment
) -> AppointmentResponse:
    """
    Helper function to build AppointmentResponse from SchedulerAppointment model.
    
    Args:
        db: Database session
        appointment: SchedulerAppointment model instance
    
    Returns:
        AppointmentResponse with all fields including treatments
    """
    # Get patient name
    try:
        patient_name = get_patient_name(db, appointment.patient_id)
    except HTTPException:
        patient_name = appointment.patient_id  # Fallback
    
    # Get treatments for this appointment
    treatments = db.query(AppointmentTreatment).filter(
        AppointmentTreatment.appointment_id == appointment.id
    ).all()
    
    treatment_responses = []
    from app.api.v1.scheduler.schemas import AppointmentTreatmentResponse
    for treatment in treatments:
        treatment_responses.append(AppointmentTreatmentResponse(
            id=treatment.id,
            appointment_id=str(appointment.id),
            procedure_code=treatment.procedure_code,
            status=treatment.status,
            tooth=treatment.tooth,
            surface=treatment.surface,
            description=treatment.description,
            bill_to=treatment.bill_to,
            duration=treatment.duration,
            provider=treatment.provider,
            provider_units=treatment.provider_units,
            est_patient=float(treatment.est_patient) if treatment.est_patient else None,
            est_insurance=float(treatment.est_insurance) if treatment.est_insurance else None,
            fee=float(treatment.fee),
            created_at=treatment.created_at.isoformat() if treatment.created_at else "",
            updated_at=treatment.updated_at.isoformat() if treatment.updated_at else ""
        ))
    
    return AppointmentResponse(
        id=str(appointment.id),
        patient_id=appointment.patient_id,
        patient_name=patient_name,
        date=appointment.date,
        start_time=appointment.start_time.strftime("%H:%M"),
        end_time=appointment.end_time.strftime("%H:%M"),
        duration=appointment.duration,
        procedure_type=appointment.procedure_type,
        status=appointment.status.value,
        operatory=appointment.operatory_id,
        provider=appointment.provider_id,
        notes=appointment.notes or "",
        # Lab fields
        lab=appointment.lab,
        lab_dds=appointment.lab_dds,
        lab_cost=float(appointment.lab_cost) if appointment.lab_cost else None,
        lab_sent_on=appointment.lab_sent_on.isoformat() if appointment.lab_sent_on else None,
        lab_due_on=appointment.lab_due_on.isoformat() if appointment.lab_due_on else None,
        lab_recvd_on=appointment.lab_recvd_on.isoformat() if appointment.lab_recvd_on else None,
        # Flag fields
        missed=appointment.missed,
        cancelled=appointment.cancelled,
        # Additional fields
        campaign_id=appointment.campaign_id,
        # Treatment plan linkage
        treatment_plan_id=appointment.treatment_plan_id,
        treatment_plan_phase_id=appointment.treatment_plan_phase_id,
        # Treatments
        treatments=treatment_responses if treatment_responses else None,
        # Timestamps
        created_at=appointment.created_at.isoformat() if appointment.created_at else None,
        updated_at=appointment.updated_at.isoformat() if appointment.updated_at else None
    )


def create_appointment(
    db: Session,
    payload: AppointmentCreate,
    office_id: int
) -> AppointmentResponse:
    """
    Create a new appointment.
    
    Args:
        db: Database session
        payload: Appointment creation data
        office_id: Office ID (from context)
    
    Returns:
        Created appointment response
    
    Raises:
        HTTPException: If validation fails or overlap detected
    """
    # Calculate end_time
    end_time_str = calculate_end_time(payload.start_time, payload.duration)
    
    # Check for overlap
    # if check_appointment_overlap(
    #     db,
    #     payload.operatory,
    #     payload.date,
    #     payload.startTime,
    #     end_time_str
    # ):
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail="Appointment overlaps with existing appointment for this operatory"
    #     )
    # if payload.patient_id == 'NEW':
    #     patient_name = 'TEST Hardcoded'
    # else:
    # # Get patient name
    try:
        patient_name = get_patient_name(db, payload.patient_id)
    except HTTPException:
        raise
    
    # Parse date string to date object
    if isinstance(payload.date, str):
        appointment_date = datetime.strptime(payload.date, "%Y-%m-%d").date()
    else:
        appointment_date = payload.date
    
    # Parse start_time and end_time for database storage
    start_hour, start_minute = map(int, payload.start_time.split(':'))
    end_hour, end_minute = map(int, end_time_str.split(':'))
    
    # Parse lab dates if provided
    lab_sent_on_date = None
    lab_due_on_date = None
    lab_recvd_on_date = None
    
    if payload.lab_sent_on:
        lab_sent_on_date = datetime.strptime(payload.lab_sent_on, "%Y-%m-%d").date()
    if payload.lab_due_on:
        lab_due_on_date = datetime.strptime(payload.lab_due_on, "%Y-%m-%d").date()
    if payload.lab_recvd_on:
        lab_recvd_on_date = datetime.strptime(payload.lab_recvd_on, "%Y-%m-%d").date()
    
    # Create appointment with all fields
    appointment = SchedulerAppointment(
        patient_id=payload.patient_id,
        date=appointment_date,
        start_time=time(start_hour, start_minute),
        end_time=time(end_hour, end_minute),
        duration=payload.duration,
        procedure_type=payload.procedure_type,
        operatory_id=payload.operatory,
        provider_id=payload.provider,
        status=normalize_status_to_enum(payload.status),
        notes=payload.notes or "",
        office_id=office_id,
        # Lab fields
        lab=payload.lab if payload.lab is not None else False,
        lab_dds=payload.lab_dds,
        lab_cost=payload.lab_cost,
        lab_sent_on=lab_sent_on_date,
        lab_due_on=lab_due_on_date,
        lab_recvd_on=lab_recvd_on_date,
        # Flag fields
        missed=payload.missed if payload.missed is not None else False,
        cancelled=payload.cancelled if payload.cancelled is not None else False,
        # Additional fields
        campaign_id=payload.campaign_id,
        # Treatment plan linkage
        treatment_plan_id=payload.treatment_plan_id,
        treatment_plan_phase_id=payload.treatment_plan_phase_id
    )
    
    db.add(appointment)
    db.flush()  # Flush to get appointment.id before creating treatments
    
    # Create treatments if provided
    treatment_responses = []
    if payload.treatments:
        import uuid
        for treatment_data in payload.treatments:
            # Use procedure_code from treatment_data, or default to "UNKNOWN"
            procedure_code = treatment_data.procedure_code or "UNKNOWN"
            
            treatment = AppointmentTreatment(
                id=f"TREAT-{uuid.uuid4().hex[:8].upper()}",
                appointment_id=appointment.id,
                procedure_code=procedure_code,
                status=treatment_data.status,
                tooth=treatment_data.tooth,
                surface=treatment_data.surface,
                description=treatment_data.description,
                bill_to=treatment_data.bill_to or "Patient",
                duration=treatment_data.duration,
                provider=treatment_data.provider,
                provider_units=treatment_data.provider_units or 1,
                est_patient=treatment_data.est_patient,
                est_insurance=treatment_data.est_insurance,
                fee=treatment_data.fee
            )
            db.add(treatment)
            db.flush()
            
            # Build treatment response
            from app.api.v1.scheduler.schemas import AppointmentTreatmentResponse
            treatment_responses.append(AppointmentTreatmentResponse(
                id=treatment.id,
                appointment_id=str(appointment.id),
                procedure_code=treatment.procedure_code,
                status=treatment.status,
                tooth=treatment.tooth,
                surface=treatment.surface,
                description=treatment.description,
                bill_to=treatment.bill_to,
                duration=treatment.duration,
                provider=treatment.provider,
                provider_units=treatment.provider_units,
                est_patient=float(treatment.est_patient) if treatment.est_patient else None,
                est_insurance=float(treatment.est_insurance) if treatment.est_insurance else None,
                fee=float(treatment.fee),
                created_at=treatment.created_at.isoformat() if treatment.created_at else "",
                updated_at=treatment.updated_at.isoformat() if treatment.updated_at else ""
            ))
    
    db.commit()
    db.refresh(appointment)
    
    # Build response with all fields using helper function
    return build_appointment_response(db, appointment)


def get_appointments(
    db: Session,
    start_date: date,
    end_date: Optional[date] = None,
    office_id: Optional[int] = None
) -> List[AppointmentResponse]:
    """
    Fetch appointments for a date range.
    
    Args:
        db: Database session
        start_date: Start date
        end_date: End date (defaults to start_date if not provided)
        office_id: Office ID filter (optional)
    
    Returns:
        List of appointment responses
    """
    if end_date is None:
        end_date = start_date
    
    query = db.query(SchedulerAppointment).filter(
        SchedulerAppointment.date >= start_date,
        SchedulerAppointment.date <= end_date
    )
    
    if office_id:
        query = query.filter(SchedulerAppointment.office_id == office_id)
    
    appointments = query.order_by(
        SchedulerAppointment.date,
        SchedulerAppointment.start_time
    ).all()
    
    result = []
    for appt in appointments:
        # Get patient name
        try:
            patient_name = get_patient_name(db, appt.patient_id)
        except HTTPException:
            patient_name = appt.patient_id  # Fallback
        
        result.append(build_appointment_response(db, appt))
    
    return result


def get_appointment_by_id(
    db: Session,
    appointment_id: int
) -> Optional[AppointmentResponse]:
    """
    Get a single appointment by ID.
    
    Args:
        db: Database session
        appointment_id: Appointment ID
    
    Returns:
        Appointment response or None if not found
    """
    appointment = db.query(SchedulerAppointment).filter(
        SchedulerAppointment.id == appointment_id
    ).first()
    
    if not appointment:
        return None
    
    return build_appointment_response(db, appointment)


def update_appointment(
    db: Session,
    appointment_id: int,
    payload: AppointmentUpdate
) -> Optional[AppointmentResponse]:
    """
    Update an existing appointment.
    
    Args:
        db: Database session
        appointment_id: Appointment ID
        payload: Update data
    
    Returns:
        Updated appointment response or None if not found
    
    Raises:
        HTTPException: If validation fails or overlap detected
    """
    appointment = db.query(SchedulerAppointment).filter(
        SchedulerAppointment.id == appointment_id
    ).first()
    
    if not appointment:
        return None
    
    # Update fields
    update_data = payload.model_dump(exclude_unset=True)
    
    # Handle date, start_time, duration changes
    # Parse date if it's a string
    if "date" in update_data and isinstance(update_data["date"], str):
        new_date = datetime.strptime(update_data["date"], "%Y-%m-%d").date()
    else:
        new_date = update_data.get("date", appointment.date)
    
    new_start_time_str = update_data.get("start_time", appointment.start_time.strftime("%H:%M"))
    new_duration = update_data.get("duration", appointment.duration)
    
    # Calculate new end_time
    new_end_time_str = calculate_end_time(new_start_time_str, new_duration)
    
    # Check for overlap only if operatory, date, or time actually changed
    # Compare current values with new values to determine if overlap check is needed
    operatory_changed = "operatory" in update_data and update_data.get("operatory") != appointment.operatory_id
    date_changed = "date" in update_data and new_date != appointment.date
    time_changed = ("start_time" in update_data or "duration" in update_data) and (
        new_start_time_str != appointment.start_time.strftime("%H:%M") or 
        new_duration != appointment.duration
    )
    
    if operatory_changed or date_changed or time_changed:
        operatory_id = update_data.get("operatory", appointment.operatory_id)
        
        if check_appointment_overlap(
            db,
            operatory_id,
            new_date,
            new_start_time_str,
            new_end_time_str,
            exclude_appointment_id=appointment_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Appointment overlaps with existing appointment for this operatory"
            )
    
    # Update patient_id if changed
    if "patient_id" in update_data:
        appointment.patient_id = update_data["patient_id"]
    
    # Update date (use parsed new_date from above)
    if "date" in update_data:
        appointment.date = new_date
    
    # Update time fields
    if "start_time" in update_data or "duration" in update_data:
        start_hour, start_minute = map(int, new_start_time_str.split(':'))
        end_hour, end_minute = map(int, new_end_time_str.split(':'))
        appointment.start_time = time(start_hour, start_minute)
        appointment.end_time = time(end_hour, end_minute)
        appointment.duration = new_duration
    
    # Update other fields
    if "procedure_type" in update_data:
        appointment.procedure_type = update_data["procedure_type"]
    if "operatory" in update_data:
        appointment.operatory_id = update_data["operatory"]
    if "provider" in update_data:
        appointment.provider_id = update_data["provider"]
    if "status" in update_data:
        appointment.status = normalize_status_to_enum(update_data["status"])
    if "notes" in update_data:
        appointment.notes = update_data["notes"]
    
    # Update lab fields
    if "lab" in update_data:
        appointment.lab = update_data["lab"]
    if "lab_dds" in update_data:
        appointment.lab_dds = update_data["lab_dds"]
    if "lab_cost" in update_data:
        appointment.lab_cost = update_data["lab_cost"]
    if "lab_sent_on" in update_data:
        if update_data["lab_sent_on"]:
            appointment.lab_sent_on = datetime.strptime(update_data["lab_sent_on"], "%Y-%m-%d").date()
        else:
            appointment.lab_sent_on = None
    if "lab_due_on" in update_data:
        if update_data["lab_due_on"]:
            appointment.lab_due_on = datetime.strptime(update_data["lab_due_on"], "%Y-%m-%d").date()
        else:
            appointment.lab_due_on = None
    if "lab_recvd_on" in update_data:
        if update_data["lab_recvd_on"]:
            appointment.lab_recvd_on = datetime.strptime(update_data["lab_recvd_on"], "%Y-%m-%d").date()
        else:
            appointment.lab_recvd_on = None
    
    # Update flag fields
    if "missed" in update_data:
        appointment.missed = update_data["missed"]
    if "cancelled" in update_data:
        appointment.cancelled = update_data["cancelled"]
    
    # Update additional fields
    if "campaign_id" in update_data:
        appointment.campaign_id = update_data["campaign_id"]
    
    # Update treatment plan linkage
    if "treatment_plan_id" in update_data:
        appointment.treatment_plan_id = update_data["treatment_plan_id"]
    if "treatment_plan_phase_id" in update_data:
        appointment.treatment_plan_phase_id = update_data["treatment_plan_phase_id"]
    
    # Handle treatments update (replace all existing treatments)
    if payload.treatments is not None:
        # CRITICAL: Delete ALL existing treatments for this appointment FIRST
        # Use raw SQL delete to bypass any SQLAlchemy session caching issues
        db.execute(
            text("DELETE FROM tenant_1.appointment_treatments WHERE appointment_id = :appointment_id"),
            {"appointment_id": appointment_id}
        )
        db.flush()
        
        # Also clear any treatments that might be in SQLAlchemy session
        # Query and expunge any treatments that might be cached
        existing_treatments = db.query(AppointmentTreatment).filter(
            AppointmentTreatment.appointment_id == appointment_id
        ).all()
        for treatment in existing_treatments:
            db.expunge(treatment)
        
        # Clear relationship cache on appointment object
        if hasattr(appointment, 'treatments'):
            # Force reload by clearing the relationship
            from sqlalchemy.orm.attributes import set_committed_value
            set_committed_value(appointment, 'treatments', [])
        
        # Verify appointment.id is not None (shouldn't be, but safety check)
        if appointment.id is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Appointment ID is None - cannot create treatments"
            )
        
        # Create new treatments - ensure they're completely new objects
        import uuid
        for treatment_data in payload.treatments:
            # Use procedure_code from treatment_data, or default to "UNKNOWN"
            procedure_code = treatment_data.procedure_code or "UNKNOWN"
            
            # Ensure UNKNOWN exists in procedure_codes table (for foreign key constraint)
            if procedure_code == "UNKNOWN":
                from app.api.v1.scheduler.models import ProcedureCode
                unknown_code = db.query(ProcedureCode).filter(
                    ProcedureCode.code == "UNKNOWN"
                ).first()
                if not unknown_code:
                    # Create UNKNOWN procedure code if it doesn't exist
                    unknown_code = ProcedureCode(
                        code="UNKNOWN",
                        user_code="UNKNOWN",
                        description="Unknown Procedure",
                        category="ALL",
                        requires_tooth=False,
                        requires_surface=False,
                        requires_quadrant=False,
                        requires_materials=False,
                        default_fee=0.00,
                        default_duration=None
                    )
                    db.add(unknown_code)
                    db.flush()
            
            # Generate unique treatment ID - check if it exists ANYWHERE in the database
            max_attempts = 10
            treatment_id = None
            for attempt in range(max_attempts):
                candidate_id = f"TREAT-{uuid.uuid4().hex[:8].upper()}"
                # Check if this ID exists anywhere (not just for this appointment)
                existing = db.query(AppointmentTreatment).filter(
                    AppointmentTreatment.id == candidate_id
                ).first()
                if not existing:
                    treatment_id = candidate_id
                    break
            
            if not treatment_id:
                # Fallback: use timestamp-based ID if UUID collision (extremely rare)
                treatment_id = f"TREAT-{int(datetime.utcnow().timestamp() * 1000)}"
            
            # Double-check the ID doesn't exist and delete if it does (safety check)
            # Use raw SQL to avoid loading into session
            existing_check = db.execute(
                text("SELECT id FROM tenant_1.appointment_treatments WHERE id = :treatment_id"),
                {"treatment_id": treatment_id}
            ).first()
            if existing_check:
                # Delete it using raw SQL to avoid session issues
                db.execute(
                    text("DELETE FROM tenant_1.appointment_treatments WHERE id = :treatment_id"),
                    {"treatment_id": treatment_id}
                )
                db.flush()
            
            # Verify appointment.id is set
            if appointment.id is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Cannot create treatment: appointment ID is None"
                )
            
            # Use raw SQL INSERT to bypass SQLAlchemy's object tracking
            # This ensures we're doing an INSERT, not an UPDATE
            db.execute(
                text("""
                    INSERT INTO tenant_1.appointment_treatments 
                    (id, appointment_id, procedure_code, status, tooth, surface, description, 
                     bill_to, duration, provider, provider_units, est_patient, est_insurance, fee, 
                     created_at, updated_at)
                    VALUES 
                    (:id, :appointment_id, :procedure_code, :status, :tooth, :surface, :description,
                     :bill_to, :duration, :provider, :provider_units, :est_patient, :est_insurance, :fee,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """),
                {
                    "id": treatment_id,
                    "appointment_id": appointment.id,  # CRITICAL: Must be set
                    "procedure_code": procedure_code,
                    "status": treatment_data.status,
                    "tooth": treatment_data.tooth,
                    "surface": treatment_data.surface,
                    "description": treatment_data.description,
                    "bill_to": treatment_data.bill_to or "Patient",
                    "duration": treatment_data.duration,
                    "provider": treatment_data.provider,
                    "provider_units": treatment_data.provider_units or 1,
                    "est_patient": treatment_data.est_patient,
                    "est_insurance": treatment_data.est_insurance,
                    "fee": treatment_data.fee
                }
            )
            # Flush immediately to ensure it's inserted before next iteration
            db.flush()
    
    db.commit()
    db.refresh(appointment)
    
    # Get patient name
    try:
        patient_name = get_patient_name(db, appointment.patient_id)
    except HTTPException:
        patient_name = appointment.patient_id  # Fallback
    
    # Get treatments for this appointment
    treatments = db.query(AppointmentTreatment).filter(
        AppointmentTreatment.appointment_id == appointment.id
    ).all()
    
    treatment_responses = []
    from app.api.v1.scheduler.schemas import AppointmentTreatmentResponse
    for treatment in treatments:
        treatment_responses.append(AppointmentTreatmentResponse(
            id=treatment.id,
            appointment_id=str(appointment.id),
            procedure_code=treatment.procedure_code,
            status=treatment.status,
            tooth=treatment.tooth,
            surface=treatment.surface,
            description=treatment.description,
            bill_to=treatment.bill_to,
            duration=treatment.duration,
            provider=treatment.provider,
            provider_units=treatment.provider_units,
            est_patient=float(treatment.est_patient) if treatment.est_patient else None,
            est_insurance=float(treatment.est_insurance) if treatment.est_insurance else None,
            fee=float(treatment.fee),
            created_at=treatment.created_at.isoformat() if treatment.created_at else "",
            updated_at=treatment.updated_at.isoformat() if treatment.updated_at else ""
        ))
    
    return AppointmentResponse(
        id=str(appointment.id),
        patient_id=appointment.patient_id,
        patient_name=patient_name,
        date=appointment.date,
        start_time=appointment.start_time.strftime("%H:%M"),
        end_time=appointment.end_time.strftime("%H:%M"),
        duration=appointment.duration,
        procedure_type=appointment.procedure_type,
        status=appointment.status.value,
        operatory=appointment.operatory_id,
        provider=appointment.provider_id,
        notes=appointment.notes or "",
        # Lab fields
        lab=appointment.lab,
        lab_dds=appointment.lab_dds,
        lab_cost=float(appointment.lab_cost) if appointment.lab_cost else None,
        lab_sent_on=appointment.lab_sent_on.isoformat() if appointment.lab_sent_on else None,
        lab_due_on=appointment.lab_due_on.isoformat() if appointment.lab_due_on else None,
        lab_recvd_on=appointment.lab_recvd_on.isoformat() if appointment.lab_recvd_on else None,
        # Flag fields
        missed=appointment.missed,
        cancelled=appointment.cancelled,
        # Additional fields
        campaign_id=appointment.campaign_id,
        # Treatment plan linkage
        treatment_plan_id=appointment.treatment_plan_id,
        treatment_plan_phase_id=appointment.treatment_plan_phase_id,
        # Treatments
        treatments=treatment_responses if treatment_responses else None,
        # Timestamps
        created_at=appointment.created_at.isoformat() if appointment.created_at else None,
        updated_at=appointment.updated_at.isoformat() if appointment.updated_at else None
    )


def update_appointment_status(
    db: Session,
    appointment_id: int,
    payload: AppointmentStatusUpdate
) -> Optional[AppointmentResponse]:
    """
    Update only the appointment status.
    
    Args:
        db: Database session
        appointment_id: Appointment ID
        payload: Status update data
    
    Returns:
        Updated appointment response or None if not found
    """
    appointment = db.query(SchedulerAppointment).filter(
        SchedulerAppointment.id == appointment_id
    ).first()
    
    if not appointment:
        return None
    
    # Convert status string to enum (handles case variations)
    appointment.status = normalize_status_to_enum(payload.status)
    
    db.commit()
    db.refresh(appointment)
    
    return build_appointment_response(db, appointment)


def delete_appointment(
    db: Session,
    appointment_id: int
) -> bool:
    """
    Delete an appointment.
    
    Args:
        db: Database session
        appointment_id: Appointment ID
    
    Returns:
        True if deleted, False if not found
    """
    appointment = db.query(SchedulerAppointment).filter(
        SchedulerAppointment.id == appointment_id
    ).first()
    
    if not appointment:
        return False
    
    db.delete(appointment)
    db.commit()
    return True


# ==================================================
# OPERATORY SERVICES
# ==================================================

def get_operatories(
    db: Session,
    office_id: Optional[int] = None
) -> List[OperatoryResponse]:
    """
    Fetch all operatories for an office.
    
    Args:
        db: Database session
        office_id: Office ID filter (optional)
    
    Returns:
        List of operatory responses
    """
    query = db.query(OfficeOperatory).filter(
        OfficeOperatory.is_active == True
    )
    logger.info(f"office_id: {office_id}")
    logger.info(f"query: {query}")
    
    if office_id:
        query = query.filter(OfficeOperatory.office_id == office_id)
    
    operatories = query.order_by(OfficeOperatory.id).all()
    
    result = []
    for op in operatories:
        logger.info(f"Operatory: {op}")
        # logger.info(f"Provider ID: {op.provider_id}")
        logger.info(f"Office ID: {op.office_id}")
        # logger.info(f"Provider: {op.provider}")
        # logger.info(f"Office: {op.office}")
        logger.info(f"Name: {op.name}")
        logger.info(f"ID: {op.id}")
        logger.info(f"Is Active: {op.is_active}")
        logger.info(f"Created At: {op.created_at}")
        # logger.info(f"Updated At: {op.updated_at}")
        # Get provider name
        provider = db.query(OfficeProvider).filter(
            OfficeProvider.id == op.provider_id
        ).first()
        provider_name = provider.name if provider else op.provider_id
        
        # Get office name
        office = db.query(Office).filter(Office.id == op.office_id).first()
        office_name = office.office_name if office else ""
        
        result.append(OperatoryResponse(
            id=op.id,
            name=op.name,
            provider=provider_name,
            office=office_name,
            display_order=op.display_order,
            is_active=op.is_active,
            has_future_appointments=op.has_future_appointments,
            created_at=op.created_at,
            updated_at=op.updated_at
        ))
    
    return result


# ==================================================
# PROVIDER SERVICES
# ==================================================

def get_providers(
    db: Session,
    office_id: Optional[int] = None
) -> List[ProviderResponse]:
    """
    Fetch all providers.
    
    Args:
        db: Database session
        office_id: Office ID filter (optional)
    
    Returns:
        List of provider responses
    """
    query = db.query(OfficeProvider).filter(
        OfficeProvider.is_active == True
    )
    
    if office_id:
        query = query.filter(OfficeProvider.office_id == office_id)
    
    providers = query.order_by(OfficeProvider.id).all()
    
    result = []
    for prov in providers:
        # Get office name if office_id is set
        office_name = None
        if prov.office_id:
            office = db.query(Office).filter(Office.id == prov.office_id).first()
            office_name = office.office_name if office else None
        
        result.append(ProviderResponse(
            id=prov.id,
            name=prov.name,
            office=office_name
        ))
    
    return result


# ==================================================
# PROCEDURE TYPE SERVICES
# ==================================================

def get_procedure_types(db: Session) -> List[ProcedureTypeResponse]:
    """
    Fetch all procedure types.
    
    Args:
        db: Database session
    
    Returns:
        List of procedure type responses
    """
    procedure_types = db.query(SchedulerProcedureType).filter(
        SchedulerProcedureType.is_active == True
    ).order_by(SchedulerProcedureType.name).all()
    
    return [
        ProcedureTypeResponse(
            id=pt.id,
            name=pt.name,
            color=pt.color
        )
        for pt in procedure_types
    ]


# ==================================================
# APPOINTMENT STATUS SERVICES
# ==================================================

def get_appointment_statuses(db: Session) -> List:
    """
    Get all appointment statuses.
    
    Args:
        db: Database session
    
    Returns:
        List of appointment statuses
    """
    from app.api.v1.scheduler.models import AppointmentStatus
    from app.api.v1.scheduler.schemas import AppointmentStatusResponse
    
    statuses = db.query(AppointmentStatus).order_by(AppointmentStatus.id).all()
    
    return [
        AppointmentStatusResponse(
            id=status.id,
            name=status.name,
            displayName=status.display_name,
            color=status.color
        )
        for status in statuses
    ]


def get_appointment_types(db: Session) -> List:
    """
    Get all appointment types.
    
    Args:
        db: Database session
    
    Returns:
        List of appointment types
    """
    from app.api.v1.scheduler.models import AppointmentType
    from app.api.v1.scheduler.schemas import AppointmentTypeResponse
    
    types = db.query(AppointmentType).order_by(AppointmentType.id).all()
    
    return [
        AppointmentTypeResponse(
            id=apt_type.id,
            name=apt_type.name,
            description=apt_type.description
        )
        for apt_type in types
    ]


# ==================================================
# SCHEDULER CONFIG SERVICES
# ==================================================

def get_scheduler_config(
    db: Session,
    office_id: Optional[int] = None
) -> SchedulerConfigResponse:
    """
    Fetch scheduler configuration for an office.
    Returns default values if no config exists.
    
    Args:
        db: Database session
        office_id: Office ID (optional)
    
    Returns:
        Scheduler configuration response
    """
    if office_id:
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.office_id == office_id
        ).first()
        
        if config:
            return SchedulerConfigResponse(
                start_hour=config.start_hour,
                end_hour=config.end_hour,
                slot_interval=config.slot_interval
            )
    
    # Return default configuration
    return SchedulerConfigResponse(
        start_hour=8,
        end_hour=17,
        slot_interval=10
    )
