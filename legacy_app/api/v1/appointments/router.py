from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date
from app.core.database import get_db as get_tenant_db
from .schemas import *
from .service import *

router = APIRouter(prefix="/appointments", tags=["Appointments"])


@router.post("/", response_model=AppointmentOut)
def create(payload: AppointmentCreate, db: Session = Depends(get_tenant_db)):
    try:
        return create_appointment(db, payload)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/", response_model=list[AppointmentOut])
def list_day(
    office_id: int,
    appt_date: date = Query(...),
    db: Session = Depends(get_tenant_db)
):
    return list_appointments(db, office_id, appt_date)


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_one(appointment_id: int, db: Session = Depends(get_tenant_db)):
    appt = get_appointment(db, appointment_id)
    if not appt:
        raise HTTPException(404, "Appointment not found")
    return appt


@router.put("/{appointment_id}", response_model=AppointmentOut)
def update(
    appointment_id: int,
    payload: AppointmentUpdate,
    db: Session = Depends(get_tenant_db)
):
    try:
        appt = update_appointment(db, appointment_id, payload)
    except ValueError as e:
        raise HTTPException(409, str(e))

    if not appt:
        raise HTTPException(404, "Appointment not found")

    return appt


@router.post("/{appointment_id}/cancel")
def cancel(appointment_id: int, db: Session = Depends(get_tenant_db)):
    appt = cancel_appointment(db, appointment_id)
    if not appt:
        raise HTTPException(404, "Appointment not found")
    return {"success": True}
