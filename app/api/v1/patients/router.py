"""
Patient Management API Routes
Implements all endpoints per API contract
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status, Path
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.core.database import get_db
from app.api.v1.auth.dependencies import get_current_user, get_current_office_id
from app.models.user import User
from app.core.logging import setup_logging

logger = setup_logging()
logger = logging.getLogger(__name__)
from app.api.v1.patients.schemas import (
    # Legacy schemas
    PatientCreate, PatientCreateWithAliases, PatientResponse, 
    PatientListResponse, PatientUpdate,
    # New comprehensive schemas
    PatientSearchListResponse, PatientDetailsResponse,
    PatientCreateRequest, PatientUpdateRequest,
    FeeSchedulesResponse, PatientTypesResponse, ReferralTypesResponse,
    RelationshipsResponse, ContactPreferencesResponse,
    TitlesResponse, PronounsResponse, StatesResponse,
    MaritalStatusesResponse, GendersResponse,
    PatientMetadataResponse,
    DuplicateCheckRequest, DuplicateCheckResponse
)
from app.api.v1.patients import service

router = APIRouter(prefix="/patients", tags=["Patients"])


# ==================================================
# STATIC ROUTES (must be before dynamic routes)
# ==================================================

@router.get("/search", response_model=PatientSearchListResponse)
def search_patients(
    search_by: str = Query(..., description="Field to search in"),
    search_value: str = Query(..., description="Search term/value"),
    search_for: str = Query("patient", description="'patient' or 'responsible'"),
    patient_type: Optional[str] = Query(None, description="'general' or 'ortho'"),
    search_scope: str = Query("all", description="'current', 'all', or 'group'"),
    include_inactive: bool = Query(False, description="Include inactive patients"),
    office_id: Optional[int] = Query(None, description="Office ID (required if search_scope is 'current')"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_office_id: int = Depends(get_current_office_id)
):
    """
    Advanced patient search with field-specific search criteria.
    
    - **search_by**: Field to search in (lastName, firstName, chartNumber, etc.)
    - **search_value**: The search term/value
    - **search_for**: "patient" or "responsible" (default: "patient")
    - **patient_type**: "general" or "ortho" (optional)
    - **search_scope**: "current", "all", or "group" (default: "all")
    - **include_inactive**: Include inactive patients (default: false)
    - **office_id**: Office ID (required if search_scope is "current")
    - **limit**: Maximum results (1-1000, default: 100)
    - **offset**: Pagination offset (default: 0)
    """
    # Use current_office_id if office_id not provided and search_scope is "current"
    if search_scope == "current" and not office_id:
        office_id = current_office_id
    
    patients, total = service.search_patients(
        db=db,
        search_by=search_by,
        search_value=search_value,
        search_for=search_for,
        patient_type=patient_type,
        search_scope=search_scope,
        include_inactive=include_inactive,
        office_id=office_id,
        limit=limit,
        offset=offset
    )
    
    return PatientSearchListResponse(
        patients=patients,
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/check-duplicate", response_model=DuplicateCheckResponse)
def check_duplicate_patient(
    payload: DuplicateCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if a patient with similar information already exists.
    Used before creating a new patient.
    """
    return service.check_duplicate_patient(db, payload)


@router.get("/metadata/fee-schedules", response_model=FeeSchedulesResponse)
def get_fee_schedules(
    office_id: Optional[int] = Query(None, description="Filter by office ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get fee schedules metadata."""
    return service.get_fee_schedules(db, office_id)


@router.get("/metadata/patient-types", response_model=PatientTypesResponse)
def get_patient_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get patient types metadata."""
    return service.get_patient_types(db)


@router.get("/metadata/referral-types", response_model=ReferralTypesResponse)
def get_referral_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get referral types metadata."""
    return service.get_referral_types(db)


@router.get("/metadata/responsible-party-relationships", response_model=RelationshipsResponse)
def get_responsible_party_relationships(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get responsible party relationships metadata."""
    return service.get_responsible_party_relationships(db)


@router.get("/metadata/contact-preferences", response_model=ContactPreferencesResponse)
def get_contact_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get contact preferences metadata."""
    return service.get_contact_preferences(db)


# ==================================================
# ADDITIONAL METADATA ENDPOINTS
# ==================================================

@router.get("/metadata", response_model=PatientMetadataResponse)
def get_all_patient_metadata(
    office_id: Optional[int] = Query(None, description="Filter fee schedules by office ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all patient metadata in a single call (recommended for form initialization)."""
    return service.get_all_patient_metadata(db, office_id)


@router.get("/metadata/titles", response_model=TitlesResponse)
def get_titles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get titles metadata."""
    return service.get_titles(db)


@router.get("/metadata/pronouns", response_model=PronounsResponse)
def get_pronouns(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get pronouns metadata."""
    return service.get_pronouns(db)


@router.get("/metadata/states", response_model=StatesResponse)
def get_states(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get US states metadata."""
    return service.get_states(db)


@router.get("/metadata/marital-statuses", response_model=MaritalStatusesResponse)
def get_marital_statuses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get marital statuses metadata."""
    return service.get_marital_statuses(db)


@router.get("/metadata/genders", response_model=GendersResponse)
def get_genders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get genders metadata."""
    return service.get_genders(db)


# ==================================================
# PATIENT DETAILS API
# ==================================================

@router.get("/{patientId}", response_model=PatientDetailsResponse)
def get_patient_details(
    patientId: str = Path(..., description="Patient ID or chart number"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get complete patient details including demographics, contact info, 
    insurance, responsible party, appointments, recalls, and balances.
    
    - **patientId**: Patient chart number or ID
    """
    patient = service.get_patient_details(db, patientId)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    return patient


# ==================================================
# PATIENT CREATE API
# ==================================================

@router.post("/", response_model=PatientDetailsResponse, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_office_id: int = Depends(get_current_office_id)
):
    """
    Create a new patient with complete information.
    
    All fields in the request body are optional except:
    - identity.first_name (required)
    - identity.last_name (required)
    - identity.dob (required)
    - office.home_office_id (required)
    """
    # Use current office if not provided
    if not payload.office.home_office_id:
        payload.office.home_office_id = current_office_id
    
    try:
        return service.create_patient_full(db, payload,current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating patient: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create patient: {str(e)}"
        )


# ==================================================
# PATIENT UPDATE API
# ==================================================

@router.put("/{patientId}", response_model=PatientDetailsResponse)
def update_patient(
    patientId: str = Path(..., description="Patient ID or chart number"),
    payload: PatientUpdateRequest = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing patient's information.
    
    - **patientId**: Patient chart number or ID
    - All fields in payload are optional (only include fields to update)
    """
    patient = service.update_patient_full(db, patientId, payload,current_user)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    return patient




# ==================================================
# LEGACY ENDPOINTS (for backward compatibility)
# ==================================================

@router.post("/legacy", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient_legacy(
    payload: PatientCreateWithAliases,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    office_id: int = Depends(get_current_office_id)
):
    """Legacy endpoint for creating a patient (backward compatibility)."""
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
    """Legacy endpoint for listing patients (backward compatibility)."""
    patients, total = service.list_patients(
        db=db,
        search=search,
        limit=limit,
        offset=offset
    )
    
    return PatientListResponse(patients=patients, total=total)


@router.get("/by-id/{patient_id}", response_model=PatientResponse)
def get_patient_by_id(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Legacy endpoint for getting a patient by ID (backward compatibility)."""
    patient = service.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    return patient



@router.get("/{patientId}", response_model=PatientDetailsResponse)
def get_patient_details(
    patientId: str = Path(..., description="Patient ID or chart number"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get complete patient details including demographics, contact info, 
    insurance, responsible party, appointments, recalls, and balances.
    
    - **patientId**: Patient chart number or ID
    """
    patient = service.get_patient_details(db, patientId)
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
    """Legacy endpoint for getting a patient by chart number (backward compatibility)."""
    patient = service.get_patient_by_chart_no(db, chart_no)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with chart number '{chart_no}' not found"
        )
    return patient


@router.put("/by-id/{patient_id}", response_model=PatientResponse)
def update_patient_legacy(
    patient_id: int,
    payload: PatientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Legacy endpoint for updating a patient (backward compatibility)."""
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
    """Delete a patient."""
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
