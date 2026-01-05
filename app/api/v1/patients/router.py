from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
# from app.core.dependencies import get_tenant_db
# from app.api.v1.auth.dependencies import require_permission, get_current_user, require_superuser
from app.core.database import get_db as get_tenant_db
from .schemas import PatientCreate, PatientOut, PatientUpdate
from .service import *

router = APIRouter(prefix="/patients", tags=["Patients"])

@router.post("/", response_model=PatientOut)
def create(payload: PatientCreate, db: Session = Depends(get_tenant_db)):
    return create_patient(db, payload)

@router.get("/", response_model=list[PatientOut])
def list_all(db: Session = Depends(get_tenant_db)):
    return list_patients(db)

@router.get("/{patient_id}", response_model=PatientOut)
def get(patient_id: int, db: Session = Depends(get_tenant_db)):
    patient = get_patient(db, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    return patient

@router.put("/{patient_id}", response_model=PatientOut)
def update(patient_id: int, payload: PatientUpdate, db: Session = Depends(get_tenant_db)):
    patient = update_patient(db, patient_id, payload)
    if not patient:
        raise HTTPException(404, "Patient not found")
    return patient

@router.delete("/{patient_id}")
def delete(patient_id: int, db: Session = Depends(get_tenant_db)):
    if not delete_patient(db, patient_id):
        raise HTTPException(404, "Patient not found")
    return {"success": True}
