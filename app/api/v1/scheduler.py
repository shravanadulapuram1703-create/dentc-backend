"""Scheduler-module supplemental routes.

- GET  /appointments/scheduler           denormalized calendar feed (gap #7, #9)
- PATCH /appointments/{id}/status         server-stamped status transition (gap #5)
- GET  /patients/{id}/context             demographics+insurance+balance+visits (gap #6)

Mounted before the generic CRUD so the literal `/appointments/scheduler` wins over
`/appointments/{item_id}`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.scheduler import (
    AppointmentSchedulerRead,
    AppointmentStatusUpdate,
    PatientContext,
)
from app.services import scheduler_service as svc

appt_router = APIRouter(
    prefix="/appointments",
    tags=["Appointments"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@appt_router.get("/scheduler", response_model=list[AppointmentSchedulerRead],
                 operation_id="list_scheduler_appointments",
                 summary="Denormalized appointment feed (names resolved) for the calendar")
def list_scheduler_appointments(
    db: DbSession,
    tenant_id: TenantId,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    office_id: Annotated[int | None, Query()] = None,
    provider_id: Annotated[str | None, Query(description="Scope to one provider (MP-7 / G8)")] = None,
    status: Annotated[str | None, Query(description="Scope to one appointment status")] = None,
    include_archived: Annotated[bool, Query(
        description="SCHED-DEL-1: include soft-deleted (archived) appointments. "
                    "Off by default — the calendar wants live appointments only.",
    )] = False,
):
    return svc.list_scheduler_appointments(
        db, tenant_id, date_from=date_from, date_to=date_to, office_id=office_id,
        provider_id=provider_id, status=status, include_archived=include_archived,
    )


@appt_router.patch("/{appointment_id}/status", response_model=AppointmentSchedulerRead,
                   operation_id="update_appointment_status",
                   summary="Change appointment status; the server stamps the transition time")
def update_appointment_status(
    db: DbSession, tenant_id: TenantId, current: CurrentUser,
    appointment_id: Annotated[str, Path()],
    body: AppointmentStatusUpdate,
):
    appt = svc.update_status(
        db, tenant_id, appointment_id, body.status,
        cancellation_note=body.cancellation_note, cancellation_reason=body.cancellation_reason,
        add_to_call_list=body.add_to_call_list, actor_id=current.id,
    )
    # Reuse the denormalized shape (single-row) for a consistent response.
    # include_archived: the row being transitioned is the one we must find, even if
    # it is archived — the feed's default filter would otherwise hide it from itself.
    rows = svc.list_scheduler_appointments(
        db, tenant_id, office_id=appt.office_id, include_archived=True,
    )
    match = next((r for r in rows if r["id"] == appt.id), None)
    return match or {
        "id": appt.id, "office_id": appt.office_id, "date": appt.date,
        "start_time": appt.start_time, "end_time": appt.end_time, "duration": appt.duration,
        "status": appt.status, "is_missed": appt.is_missed, "is_cancelled": appt.is_cancelled,
        "is_blocked": appt.is_blocked, "is_archived": appt.is_archived,
        "confirmed_on": appt.confirmed_on,
        "checked_in_on": appt.checked_in_on, "checked_out_on": appt.checked_out_on,
    }


@appt_router.post("/{appointment_id}/restore", response_model=AppointmentSchedulerRead,
                  operation_id="restore_appointment",
                  summary="Un-archive a soft-deleted appointment (SCHED-DEL-2)")
def restore_appointment(
    db: DbSession, tenant_id: TenantId, current: CurrentUser,
    appointment_id: Annotated[str, Path()],
):
    """SCHED-DEL-2: soft delete is intentional (HIPAA-adjacent history — an
    appointment that existed is a fact about the patient's record), so DELETE stays
    soft. This is the missing other half: the archived rows are listable via
    ``GET /appointments?is_archived=true`` and this puts one back on the calendar.
    """
    appt = svc.restore_appointment(db, tenant_id, appointment_id, actor_id=current.id)
    rows = svc.list_scheduler_appointments(db, tenant_id, office_id=appt.office_id)
    match = next((r for r in rows if r["id"] == appt.id), None)
    return match or {
        "id": appt.id, "office_id": appt.office_id, "date": appt.date,
        "start_time": appt.start_time, "end_time": appt.end_time, "duration": appt.duration,
        "status": appt.status, "is_missed": appt.is_missed, "is_cancelled": appt.is_cancelled,
        "is_blocked": appt.is_blocked, "is_archived": appt.is_archived,
        "confirmed_on": appt.confirmed_on,
        "checked_in_on": appt.checked_in_on, "checked_out_on": appt.checked_out_on,
    }


patient_ctx_router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@patient_ctx_router.get("/{patient_id}/context", response_model=PatientContext,
                        operation_id="get_patient_context",
                        summary="Aggregated patient context for cross-module navigation")
def get_patient_context(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    return svc.get_patient_context(db, patient_id, tenant_id)
