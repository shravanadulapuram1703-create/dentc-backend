from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.api.v1.auth.dependencies import get_current_user, get_current_office_id
from app.models.user import User
from app.api.v1.patients.schemas import (
    PatientCreate, 
    PatientCreateWithAliases,
    PatientResponse, 
    PatientListResponse,
    PatientUpdate
)
from app.api.v1.patients import service

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreateWithAliases,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    office_id: int = Depends(get_current_office_id)
):
    """
    Create a new patient.
    
    - **firstName**: Patient first name (required)
    - **lastName**: Patient last name (required)
    - **chartNo**: Chart number (optional, auto-generated if not provided)
    - **dob**: Date of birth (optional)
    - **gender**: Gender (M/F/O) (optional)
    - **phone**: Phone number (optional)
    - **email**: Email address (optional)
    - **homeOfficeId**: Home office ID (optional)
    
    Returns the created patient with auto-generated chart number if not provided.
    """
    # Convert camelCase payload to snake_case PatientCreate
    patient_create = PatientCreate(
        chart_no=payload.chartNo,
        first_name=payload.firstName,
        last_name=payload.lastName,
        dob=payload.dob,
        gender=payload.gender,
        phone=payload.phone,
        email=payload.email,
        home_office_id=payload.homeOfficeId if payload.homeOfficeId else office_id
    )
    
    try:
        return service.create_patient(db, patient_create)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create patient: {str(e)}"
        )


@router.get("/", response_model=PatientListResponse)
def list_patients(
    search: Optional[str] = Query(None, description="Search term (searches in name, chart_no, phone, email)"),
    limit: Optional[int] = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: Optional[int] = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a list of patients with optional search and pagination.
    
    - **search**: Search term to filter patients (searches in first_name, last_name, chart_no, phone, email)
    - **limit**: Maximum number of results (default: 100, max: 1000)
    - **offset**: Number of results to skip for pagination (default: 0)
    
    Returns a list of patients matching the search criteria.
    """
    patients, total = service.list_patients(
        db=db,
        search=search,
        limit=limit,
        offset=offset
    )
    
    return PatientListResponse(patients=patients, total=total)


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a single patient by ID.
    
    - **patient_id**: Patient ID
    """
    patient = service.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    return patient


@router.get("/chart/{chart_no}", response_model=PatientResponse)
def get_patient_by_chart_no(
    chart_no: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a patient by chart number.
    
    - **chart_no**: Patient chart number
    """
    patient = service.get_patient_by_chart_no(db, chart_no)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with chart number '{chart_no}' not found"
        )
    return patient


@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing patient.
    
    - **patient_id**: Patient ID
    - All fields in payload are optional
    """
    patient = service.update_patient(db, patient_id, payload)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_200_OK)
def delete_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a patient.
    
    - **patient_id**: Patient ID
    """
    success = service.delete_patient(db, patient_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    return {
        "message": "Patient deleted successfully",
        "status": "success"
    }
