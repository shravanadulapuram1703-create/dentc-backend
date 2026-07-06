"""Scheduler-module DTOs (denormalized appointment read, status change, patient context)."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

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
    is_posted: bool = False
    posted_on: datetime | None = None
    confirmed_on: datetime | None = None
    checked_in_on: datetime | None = None
    checked_out_on: datetime | None = None
    # SCHED G1/G2/G4/G5 — denormalized per-block enrichment (no per-cell N+1).
    has_alert: bool = False
    patient_age: int | None = None
    patient_gender: str | None = None
    responsible_party_id: str | None = None
    service_summary: str | None = None
    insurance_eligibility: Literal["eligible", "ineligible", "unknown"] | None = None
    account_balance: Decimal | None = None
    created_by: int | None = None
    created_by_name: str | None = None
    updated_by: int | None = None
    updated_by_name: str | None = None
    cancellation_note: str | None = None
    cancellation_reason: str | None = None
    add_to_call_list: bool = False


class AppointmentStatusUpdate(BaseModel):
    status: str = Field(..., examples=["confirmed", "in_reception", "checked_out", "cancelled"])
    # SCHED G3: optional cancellation metadata persisted with the transition.
    cancellation_note: str | None = None
    cancellation_reason: str | None = None
    add_to_call_list: bool | None = None


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
