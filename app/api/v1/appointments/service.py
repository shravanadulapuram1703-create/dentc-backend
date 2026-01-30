from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.models.appointments import Appointment
from .schemas import AppointmentCreate, AppointmentUpdate

BLOCKING_STATUSES = ("Cancelled", "No-Show")


def has_conflict(
    db: Session,
    provider_id: int,
    operatory_id: int,
    start_time,
    end_time,
    exclude_id: int | None = None
) -> bool:
    query = db.query(Appointment).filter(
        Appointment.status.notin_(BLOCKING_STATUSES),
        or_(
            Appointment.provider_id == provider_id,
            Appointment.operatory_id == operatory_id
        ),
        and_(
            Appointment.start_time < end_time,
            Appointment.end_time > start_time
        )
    )

    if exclude_id:
        query = query.filter(Appointment.id != exclude_id)

    return db.query(query.exists()).scalar()


def create_appointment(db: Session, payload: AppointmentCreate):
    if payload.start_time >= payload.end_time:
        raise ValueError("start_time must be before end_time")

    if has_conflict(
        db,
        payload.provider_id,
        payload.operatory_id,
        payload.start_time,
        payload.end_time
    ):
        raise ValueError("Appointment conflict detected")

    appt = Appointment(**payload.dict())
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


def list_appointments(db: Session, office_id: int, date):
    return (
        db.query(Appointment)
        .filter(
            Appointment.office_id == office_id,
            Appointment.start_time.cast(date) == date
        )
        .order_by(Appointment.start_time)
        .all()
    )


def get_appointment(db: Session, appt_id: int):
    return db.query(Appointment).filter(Appointment.id == appt_id).first()


def update_appointment(
    db: Session,
    appt_id: int,
    payload: AppointmentUpdate
):
    appt = get_appointment(db, appt_id)
    if not appt:
        return None

    data = payload.dict(exclude_unset=True)

    start = data.get("start_time", appt.start_time)
    end = data.get("end_time", appt.end_time)
    provider = data.get("provider_id", appt.provider_id)
    operatory = data.get("operatory_id", appt.operatory_id)

    if start >= end:
        raise ValueError("start_time must be before end_time")

    if has_conflict(
        db,
        provider,
        operatory,
        start,
        end,
        exclude_id=appt.id
    ):
        raise ValueError("Appointment conflict detected")

    for field, value in data.items():
        setattr(appt, field, value)

    db.commit()
    db.refresh(appt)
    return appt


def cancel_appointment(db: Session, appt_id: int):
    appt = get_appointment(db, appt_id)
    if not appt:
        return None

    appt.status = "Cancelled"
    db.commit()
    return appt
