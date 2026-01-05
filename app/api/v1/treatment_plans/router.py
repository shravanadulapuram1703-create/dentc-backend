from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db as get_tenant_db
from app.api.v1.treatment_plans.service import (
    create_plan,
    add_plan_procedure,
    accept_plan,
)

router = APIRouter(
    prefix="/treatment-plans",
    tags=["Treatment Plans"]
)


@router.post("/")
def create_treatment_plan(
    payload: dict,
    db: Session = Depends(get_tenant_db),
):
    """
    Create a new treatment plan (Draft)
    """
    try:
        return create_plan(
            db=db,
            patient_id=payload["patient_id"],
            office_id=payload["office_id"],
            user_id=payload["created_by"],
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing field: {e}")


@router.post("/{plan_id}/procedures")
def add_procedure_to_plan(
    plan_id: int,
    payload: dict,
    db: Session = Depends(get_tenant_db),
):
    """
    Add a procedure to a treatment plan
    """
    try:
        return add_plan_procedure(
            db=db,
            plan_id=plan_id,
            code=payload["procedure_code"],
            fee=payload["fee"],
            provider_id=payload.get("provider_id"),
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing field: {e}")


@router.post("/{plan_id}/accept")
def accept_treatment_plan(
    plan_id: int,
    db: Session = Depends(get_tenant_db),
):
    """
    Accept a treatment plan and approve all procedures
    """
    try:
        return accept_plan(db, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
