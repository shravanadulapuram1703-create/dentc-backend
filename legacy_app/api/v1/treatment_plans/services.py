"""
Service layer for Treatment Plans.
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import HTTPException, status
from datetime import datetime

from app.api.v1.scheduler.models import (
    TreatmentPlan,
    TreatmentPlanPhase,
    TreatmentPlanProcedure
)
from app.api.v1.scheduler.schemas import (
    TreatmentPlanResponse,
    TreatmentPlanPhaseResponse,
    TreatmentPlanProcedureResponse
)


def get_treatment_plans(
    db: Session,
    patient_id: str,
    status_filter: Optional[str] = None,
    include_completed: bool = False
) -> List[TreatmentPlanResponse]:
    """
    Get treatment plans for a patient.
    
    Args:
        db: Database session
        patient_id: Patient ID (chart number)
        status_filter: Filter by status ("Active", "Completed", "Cancelled")
        include_completed: Include completed plans (default: False)
    
    Returns:
        List of treatment plans with phases and procedures
    """
    query = db.query(TreatmentPlan).filter(TreatmentPlan.patient_id == patient_id)
    
    # Apply status filter
    if status_filter:
        query = query.filter(TreatmentPlan.status == status_filter)
    elif not include_completed:
        # By default, exclude completed and cancelled
        query = query.filter(TreatmentPlan.status == "Active")
    
    # Order by creation date (newest first)
    plans = query.order_by(TreatmentPlan.created_date.desc()).all()
    
    result = []
    for plan in plans:
        # Get phases for this plan
        phases = db.query(TreatmentPlanPhase).filter(
            TreatmentPlanPhase.treatment_plan_id == plan.id
        ).order_by(TreatmentPlanPhase.phase_order).all()
        
        phase_responses = []
        for phase in phases:
            # Get procedures for this phase
            procedures = db.query(TreatmentPlanProcedure).filter(
                TreatmentPlanProcedure.phase_id == phase.id
            ).order_by(TreatmentPlanProcedure.created_at).all()
            
            procedure_responses = [
                TreatmentPlanProcedureResponse(
                    id=proc.id,
                    code=proc.procedure_code,
                    description=proc.description,
                    tooth=proc.tooth or "",
                    surface=proc.surface or "",
                    diagnosedProvider=proc.diagnosed_provider,
                    fee=float(proc.fee),
                    insuranceEstimate=float(proc.insurance_estimate),
                    status=proc.status
                )
                for proc in procedures
            ]
            
            phase_responses.append(TreatmentPlanPhaseResponse(
                id=phase.id,
                name=phase.name,
                procedures=procedure_responses
            ))
        
        # Format created_date as ISO 8601
        created_date_str = plan.created_date.isoformat() + "Z" if plan.created_date else datetime.now().isoformat() + "Z"
        
        result.append(TreatmentPlanResponse(
            id=plan.id,
            name=plan.name,
            patientId=plan.patient_id,
            phases=phase_responses,
            createdDate=created_date_str,
            status=plan.status
        ))
    
    return result
