"""
API routes for Treatment Plans.
"""
from fastapi import APIRouter, Depends, Query, status, Path
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.api.v1.auth.dependencies import get_current_user
from app.models.user import User
from app.api.v1.treatment_plans.services import get_treatment_plans
from app.api.v1.scheduler.schemas import TreatmentPlansResponse

router = APIRouter(prefix="/patients", tags=["treatment-plans"])


@router.get("/{patient_id}/treatment-plans", response_model=TreatmentPlansResponse)
def get_patient_treatment_plans(
    patient_id: str = Path(..., description="Patient ID (chart number)"),
    status: Optional[str] = Query(None, description="Filter by status (Active, Completed, Cancelled)"),
    include_completed: bool = Query(False, description="Include completed plans"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all treatment plans for a specific patient.
    
    Path Parameters:
    - patient_id: Patient ID (chart number)
    
    Query Parameters:
    - status: Filter by status ("Active", "Completed", "Cancelled")
    - include_completed: Include completed plans (default: false)
    
    Returns:
    - List of treatment plans with phases and procedures
    """
    plans = get_treatment_plans(
        db=db,
        patient_id=patient_id,
        status_filter=status,
        include_completed=include_completed
    )
    return TreatmentPlansResponse(treatment_plans=plans)
