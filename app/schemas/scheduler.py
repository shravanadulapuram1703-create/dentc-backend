"""Scheduler-module DTOs (denormalized appointment read, status change, patient context)."""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.db.models import Patient
from app.schemas.factory import build_schemas

# Reuse the patient field set under a distinct component name for the context aggregate.
SchedulerPatientRead = build_schemas(Patient, "SchedulerPatient")[2]


class AppointmentSchedulerRead(BaseModel):
    """Denormalized appointment row for the calendar — names resolved server-side
    (kills the per-cell N+1 patient lookups)."""

    id: str
    patient_id: int | None = None
    patient_name: str | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    operatory_id: str | None = None
    operatory_name: str | None = None
    office_id: int
    date: date
    start_time: time
    end_time: time
    duration: int
    status: str
    procedure_label: str | None = None
    is_missed: bool = False
    is_cancelled: bool = False
    is_blocked: bool = False
    confirmed_on: datetime | None = None
    checked_in_on: datetime | None = None
    checked_out_on: datetime | None = None


class AppointmentStatusUpdate(BaseModel):
    status: str = Field(..., examples=["confirmed", "in_reception", "checked_out", "cancelled"])


class PatientContextInsurance(BaseModel):
    insurance_type: str
    ins_plan_id: int | None = None
    carrier_name: str | None = None


class PatientContextVisit(BaseModel):
    first_visit: date | None = None
    last_visit: date | None = None
    next_recall: date | None = None


class PatientContext(BaseModel):
    patient: SchedulerPatientRead  # type: ignore[valid-type]
    balance: dict
    insurance: list[PatientContextInsurance]
    visit: PatientContextVisit
