from sqlalchemy.orm import Session
from app.models.patient import Patient
from .schemas import PatientCreate, PatientUpdate

def create_patient(db: Session, payload: PatientCreate):
    patient = Patient(**payload.dict())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient

def list_patients(db: Session):
    return db.query(Patient).order_by(Patient.created_at.desc()).all()

def get_patient(db: Session, patient_id: int):
    return db.query(Patient).filter(Patient.id == patient_id).first()

def update_patient(db: Session, patient_id: int, payload: PatientUpdate):
    patient = get_patient(db, patient_id)
    if not patient:
        return None

    for field, value in payload.dict(exclude_unset=True).items():
        setattr(patient, field, value)

    db.commit()
    db.refresh(patient)
    return patient

def delete_patient(db: Session, patient_id: int):
    patient = get_patient(db, patient_id)
    if not patient:
        return False

    db.delete(patient)
    db.commit()
    return True
