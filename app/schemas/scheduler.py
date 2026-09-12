"""Scheduler-module DTOs (denormalized appointment read, status change, patient context)."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.core.datetimes import UtcDatetime
from app.db.models import Patient
from app.schemas.factory import build_schemas
from app.schemas.medical_alerts import MedicalAlertSummary

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
    # SCHED-DEL-1: DELETE soft-archives the row. The feed now excludes archived
    # appointments by default; the flag is exposed so a caller that opts back in
    # with ``?include_archived=true`` can tell the tombstones apart.
    is_archived: bool = False
    posted_on: UtcDatetime | None = None
    confirmed_on: UtcDatetime | None = None
    checked_in_on: UtcDatetime | None = None
    checked_out_on: UtcDatetime | None = None
    # SCHED G1/G2/G4/G5 — denormalized per-block enrichment (no per-cell N+1).
    # MA-1: true when the patient has an active free-text alert OR a Medical
    # History alert answered YES (was free-text only).
    has_alert: bool = False
    # MA-2: one line per section for the block tooltip / popover, no fan-out.
    alert_summary: str | None = None
    alert_count: int = 0
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
    # LAB-3: the lab block, so the calendar can badge a lab case and the Lab
    # Tracking tab can reuse this denormalised feed. ``lab_status`` is the
    # same derivation the ``?lab_status=`` filter evaluates (null unless has_lab).
    has_lab: bool = False
    lab_vendor_id: int | None = None
    lab_vendor_name: str | None = None
    lab_dds: str | None = None
    lab_cost: Decimal | None = None
    lab_short_notice: bool = False
    lab_sent_on: date | None = None
    lab_due_on: date | None = None
    lab_received_on: date | None = None
    lab_status: Literal["not_sent", "sent", "overdue", "received"] | None = None


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
    # AL-12: the ledger title row prints "Prim. Ins" + the plan identity.
    group_number: str | None = None
    plan_type: str | None = None
    legacy_plan_type: str | None = Field(None, description="'D' dental | 'M' medical")
    plan_name: str | None = Field(None, description="Carrier + group number — no plan-name column exists")


class PatientContextResponsibleParty(BaseModel):
    """AL-12: "Responsible: <name>" in the ledger title row."""

    id: int
    legacy_id: str | None = None
    name: str | None = None
    relationship: str | None = None
    home_phone: str | None = None


class PatientContextVisit(BaseModel):
    first_visit: date | None = None
    last_visit: date | None = None
    next_recall: date | None = None


class PatientContext(BaseModel):
    patient: SchedulerPatientRead  # type: ignore[valid-type]
    balance: dict
    # MA-2: the same per-patient alert summary as /patients/{id}/medical-alerts/summary.
    medical_alerts: MedicalAlertSummary | None = None
    insurance: list[PatientContextInsurance]
    # AL-12: header detail the shared patient shell could not previously show.
    primary_insurance: PatientContextInsurance | None = None
    responsible_party: PatientContextResponsibleParty | None = None
    responsible_party_id: str | None = None
    visit: PatientContextVisit
    # PE-3: opening A/R buckets folded in so the Edit form hydrates from one call.
    opening_balance: dict = {}
