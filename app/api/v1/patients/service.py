from sqlalchemy.orm import Session
from sqlalchemy import or_, func as sql_func
from fastapi import HTTPException, status
from typing import Optional, List
from datetime import datetime

from app.models.patient import Patient
from app.api.v1.patients.schemas import PatientCreate, PatientUpdate, PatientResponse

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)


def generate_chart_no(db: Session) -> str:
    """
    Generate a unique chart number for a new patient.
    Format: CH + sequential number (e.g., CH001, CH002)
    """
    # Get the highest chart number
    last_patient = (
        db.query(Patient)
        .filter(Patient.chart_no.isnot(None))
        .filter(Patient.chart_no.like('CH%'))
        .order_by(Patient.id.desc())
        .first()
    )
    
    if last_patient and last_patient.chart_no:
        try:
            # Extract number from chart_no (e.g., "CH001" -> 1)
            last_num = int(last_patient.chart_no.replace('CH', ''))
            next_num = last_num + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1
    
    # Format as CH + 3-digit number
    chart_no = f"CH{next_num:03d}"
    
    # Ensure uniqueness (in case of gaps or manual entries)
    while db.query(Patient).filter(Patient.chart_no == chart_no).first():
        next_num += 1
        chart_no = f"CH{next_num:03d}"
    
    return chart_no


def create_patient(
    db: Session, 
    payload: PatientCreate,
    auto_generate_chart_no: bool = True
) -> PatientResponse:
    """
    Create a new patient.
    
    Args:
        db: Database session
        payload: Patient creation data
        auto_generate_chart_no: If True and chart_no is not provided, auto-generate it
    
    Returns:
        Created patient response
    
    Raises:
        HTTPException: If chart_no already exists
    """
    # Check if chart_no is provided and already exists
    if payload.chart_no:
        existing = db.query(Patient).filter(Patient.chart_no == payload.chart_no).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Patient with chart number '{payload.chart_no}' already exists"
            )
    elif auto_generate_chart_no:
        # Auto-generate chart_no if not provided
        payload.chart_no = generate_chart_no(db)
    
    # Create patient
    patient_data = payload.model_dump(exclude_unset=True)
    patient = Patient(**patient_data)
    
    db.add(patient)
    db.commit()
    db.refresh(patient)
    
    return _patient_to_response(patient)


def list_patients(
    db: Session,
    search: Optional[str] = None,
    limit: Optional[int] = 100,
    offset: Optional[int] = 0
) -> tuple[List[PatientResponse], int]:
    """
    List patients with optional search.
    
    Args:
        db: Database session
        search: Search term (searches in first_name, last_name, chart_no, phone, email)
        limit: Maximum number of results
        offset: Number of results to skip
    
    Returns:
        Tuple of (list of patients, total count)
    """
    query = db.query(Patient)
    
    logger.info(f"search   {search}")

    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Patient.first_name.ilike(search_term),
                Patient.last_name.ilike(search_term),
                Patient.chart_no.ilike(search_term),
                Patient.phone.ilike(search_term),
                Patient.email.ilike(search_term)
            )
        )
    
    # Get total count before pagination (use a separate query for count)
    count_query = query
    total = count_query.count()
    
    # Order by most recent first (must be before limit/offset)
    query = query.order_by(Patient.created_at.desc())
    
    # Apply pagination (after ordering)
    if limit:
        query = query.limit(limit)
    if offset:
        query = query.offset(offset)
    
    # Execute query
    patients = query.all()

    logger.info(f"patients===============>>>>   {patients}")

    logger.info(f"total===============>>>>   {total}")
    
    return [_patient_to_response(p) for p in patients], total


def get_patient(db: Session, patient_id: int) -> Optional[PatientResponse]:
    """
    Get a single patient by ID.
    
    Args:
        db: Database session
        patient_id: Patient ID
    
    Returns:
        Patient response or None if not found
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        return None
    return _patient_to_response(patient)


def get_patient_by_chart_no(db: Session, chart_no: str) -> Optional[PatientResponse]:
    """
    Get a patient by chart number.
    
    Args:
        db: Database session
        chart_no: Chart number
    
    Returns:
        Patient response or None if not found
    """
    patient = db.query(Patient).filter(Patient.chart_no == chart_no).first()
    if not patient:
        return None
    return _patient_to_response(patient)


def update_patient(
    db: Session, 
    patient_id: int, 
    payload: PatientUpdate
) -> Optional[PatientResponse]:
    """
    Update an existing patient.
    
    Args:
        db: Database session
        patient_id: Patient ID
        payload: Update data
    
    Returns:
        Updated patient response or None if not found
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        return None
    
    # Update fields
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(patient, field, value)
    
    db.commit()
    db.refresh(patient)
    
    return _patient_to_response(patient)


def delete_patient(db: Session, patient_id: int) -> bool:
    """
    Delete a patient.
    
    Args:
        db: Database session
        patient_id: Patient ID
    
    Returns:
        True if deleted, False if not found
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        return False
    
    db.delete(patient)
    db.commit()
    return True


def _patient_to_response(patient: Patient) -> PatientResponse:
    """
    Convert Patient model to PatientResponse schema.
    
    Args:
        patient: Patient model instance
    
    Returns:
        PatientResponse instance
    """
    return PatientResponse(
        id=patient.id,
        chart_no=patient.chart_no,
        first_name=patient.first_name or "",
        last_name=patient.last_name or "",
        dob=patient.dob,
        gender=patient.gender,
        phone=patient.phone,
        email=patient.email,
        home_office_id=patient.home_office_id,
        created_at=patient.created_at.isoformat() if patient.created_at else None,
        updated_at=patient.updated_at.isoformat() if patient.updated_at else None
    )
