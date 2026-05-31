"""
API routes for the Scheduler module.
All endpoints follow the frontend expectations document.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from app.core.database import get_db
from app.api.v1.auth.dependencies import get_current_user, get_current_office_id
from app.models.user import User
from app.api.v1.scheduler import schemas
from app.api.v1.scheduler import services

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


# ==================================================
# APPOINTMENT ENDPOINTS
# ==================================================

@router.get("/appointments", response_model=schemas.AppointmentsResponse)
def get_appointments(
    start_date: date = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: Optional[date] = Query(None, description="End date in YYYY-MM-DD format (defaults to start_date)"),
    office_id: Optional[int] = Query(None, description="Filter by office ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_office_id: int = Depends(get_current_office_id)
):
    """
    Fetch appointments for a date range.
    
    - **start_date**: Start date (required)
    - **end_date**: End date (optional, defaults to start_date)
    - **office_id**: Filter by office ID (optional, uses user's primary office if not provided)
    """
    # Use user's primary office_id if not provided
    if office_id is None:
        office_id = user_office_id
    
    appointments = services.get_appointments(
        db=db,
        start_date=start_date,
        end_date=end_date,
        office_id=office_id
    )
    
    return schemas.AppointmentsResponse(appointments=appointments)


@router.get("/appointments/{appointment_id}", response_model=schemas.AppointmentSingleResponse)
def get_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetch a single appointment by ID.
    """
    appointment = services.get_appointment_by_id(db, appointment_id)
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    return schemas.AppointmentSingleResponse(appointment=appointment)


@router.post("/appointments", response_model=schemas.AppointmentSingleResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: schemas.AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    office_id: int = Depends(get_current_office_id)
):
    """
    Create a new appointment.
    
    The backend will:
    - Calculate `end_time` from `start_time` + `duration`
    - Fetch `patient_name` from the patient record
    - Generate a unique `id` for the appointment
    - Validate for appointment overlaps
    """
    try:
        appointment = services.create_appointment(
            db=db,
            payload=payload,
            office_id=office_id
        )
        return schemas.AppointmentSingleResponse(appointment=appointment)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create appointment: {str(e)}"
        )


@router.put("/appointments/{appointment_id}", response_model=schemas.AppointmentSingleResponse)
def update_appointment(
    appointment_id: int,
    payload: schemas.AppointmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing appointment.
    
    All fields are optional. The backend will:
    - Recalculate `end_time` if `start_time` or `duration` changed
    - Validate for appointment overlaps
    """
    try:
        appointment = services.update_appointment(
            db=db,
            appointment_id=appointment_id,
            payload=payload
        )
        
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found"
            )
        
        return schemas.AppointmentSingleResponse(appointment=appointment)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"Failed to update appointment: {str(e)}"
        # Log full traceback for debugging
        print(f"Error updating appointment: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        )


@router.patch("/appointments/{appointment_id}/status", response_model=schemas.AppointmentSingleResponse)
def update_appointment_status(
    appointment_id: int,
    payload: schemas.AppointmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update only the appointment status.
    """
    appointment = services.update_appointment_status(
        db=db,
        appointment_id=appointment_id,
        payload=payload
    )
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    return schemas.AppointmentSingleResponse(appointment=appointment)


@router.delete("/appointments/{appointment_id}", status_code=status.HTTP_200_OK)
def delete_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete an appointment.
    """
    success = services.delete_appointment(db, appointment_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    return {
        "message": "Appointment deleted successfully",
        "status": "success"
    }


# ==================================================
# OPERATORY ENDPOINTS
# ==================================================

@router.get("/operatories", response_model=schemas.OperatoriesResponse)
def get_operatories(
    office_id: Optional[int] = Query(None, description="Filter by office ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_office_id: int = Depends(get_current_office_id)
):
    """
    Fetch all operatories for an office.
    
    - **office_id**: Filter by office ID (optional, uses user's primary office if not provided)
    """
    # Use user's primary office_id if not provided
    if office_id is None:
        office_id = user_office_id
    
    operatories = services.get_operatories(db=db, office_id=office_id)
    return schemas.OperatoriesResponse(operatories=operatories)


# ==================================================
# PROVIDER ENDPOINTS
# ==================================================

@router.get("/providers", response_model=schemas.ProvidersResponse)
def get_providers(
    office_id: Optional[int] = Query(None, description="Filter by office ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_office_id: int = Depends(get_current_office_id)
):
    """
    Fetch all providers.
    
    - **office_id**: Filter by office ID (optional, uses user's primary office if not provided)
    """
    # Use user's primary office_id if not provided
    if office_id is None:
        office_id = user_office_id
    
    providers = services.get_providers(db=db, office_id=office_id)
    return schemas.ProvidersResponse(providers=providers)


# ==================================================
# PROCEDURE TYPE ENDPOINTS
# ==================================================

@router.get("/procedure-types", response_model=schemas.ProcedureTypesResponse)
def get_procedure_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetch all procedure types.
    """
    procedure_types = services.get_procedure_types(db=db)
    return schemas.ProcedureTypesResponse(procedure_types=procedure_types)


# ==================================================
# SCHEDULER CONFIG ENDPOINTS
# ==================================================

@router.get("/config", response_model=schemas.SchedulerConfigWrapper)
def get_scheduler_config(
    office_id: Optional[int] = Query(None, description="Get configuration for a specific office"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_office_id: int = Depends(get_current_office_id)
):
    """
    Fetch scheduler configuration (time slots, working hours, etc.).
    
    Returns default configuration if no office-specific config exists.
    
    - **office_id**: Office ID (optional, uses user's primary office if not provided)
    """
    # Use user's primary office_id if not provided
    if office_id is None:
        office_id = user_office_id
    
    config = services.get_scheduler_config(db=db, office_id=office_id)
    return schemas.SchedulerConfigWrapper(config=config)


@router.get("/appointment-statuses", response_model=schemas.AppointmentStatusesResponse)
def get_appointment_statuses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all available appointment status types for the status dropdown.
    
    Returns:
    - List of appointment statuses with display names and colors
    """
    statuses = services.get_appointment_statuses(db=db)
    return schemas.AppointmentStatusesResponse(statuses=statuses)


@router.get("/appointment-types", response_model=schemas.AppointmentTypesResponse)
def get_appointment_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all appointment types (optional - may reuse procedure types).
    
    Returns:
    - List of appointment types
    """
    types = services.get_appointment_types(db=db)
    return schemas.AppointmentTypesResponse(appointment_types=types)
