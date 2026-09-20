"""AppointNow routes — external online booking.

Two routers under ``/appointnow``:

- ``public_router`` — **unauthenticated** (AN-1..3). Reachable anonymously from a
  third-party website; the tenant is resolved from ``office_code``. These never
  return 401 (AN-12) — only 200/403/404/409/422/429 — so the frontend's shared
  axios 401→/login redirect can never fire on a public visitor.
- ``staff_router`` — authenticated inbox + approve/decline (AN-4..5, AN-9).

Deliberately hand-written (not in the CRUD registry): the public surface is
anonymous + tenant-from-code, and approval is a bespoke atomic booking. The reason
*catalog* is a plain CRUD entity (see the registry) for staff to manage.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import (
    CurrentUser,
    DbSession,
    TenantId,
    get_current_user,
    require_permission,
    require_roles,
)
from app.schemas.appointnow import (
    ApproveInput,
    AvailabilityResponse,
    BookingRequestRead,
    DeclineInput,
    PatientMatch,
    PublicOfficeInfo,
    RequestListResponse,
    RescheduleInput,
    SubmitRequestInput,
)
from app.schemas.common import ErrorResponse
from app.services import appointnow_service as svc

public_router = APIRouter(
    prefix="/appointnow",
    tags=["Appointments"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)

staff_router = APIRouter(
    prefix="/appointnow",
    tags=["Appointments"],
    dependencies=[Depends(get_current_user)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP for the public rate-limit (behind Cloud Run's proxy)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


# ── Public (UNAUTH) ──────────────────────────────────────────────────────────
@public_router.get(
    "/offices/{office_code}",
    response_model=PublicOfficeInfo,
    operation_id="appointnow_public_office_info",
)
def public_office_info(office_code: str, db: DbSession) -> PublicOfficeInfo:
    """AN-1: public-safe office branding + bookable providers + reason catalog."""
    return PublicOfficeInfo(**svc.get_public_office_info(db, office_code))


@public_router.get(
    "/offices/{office_code}/availability",
    response_model=AvailabilityResponse,
    operation_id="appointnow_public_availability",
)
def public_availability(
    office_code: str,
    db: DbSession,
    date: str = Query(description="Day to check, YYYY-MM-DD"),
    provider_id: str | None = Query(default=None),
    duration_minutes: int | None = Query(default=None, ge=5, le=480),
) -> AvailabilityResponse:
    """AN-2: open, bookable start times for the day (office-local, AN-10)."""
    return AvailabilityResponse(
        **svc.get_availability(
            db,
            office_code,
            date_str=date,
            provider_id=provider_id,
            duration_minutes=duration_minutes,
        )
    )


@public_router.post(
    "/offices/{office_code}/requests",
    response_model=BookingRequestRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="appointnow_public_submit_request",
    responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
def public_submit_request(
    office_code: str, body: SubmitRequestInput, db: DbSession, request: Request
) -> BookingRequestRead:
    """AN-3: create a booking request (rate-limited, CAPTCHA-gated, slot re-checked,
    slot soft-held). Does NOT create a patient or appointment — that happens on
    staff approval."""
    req = svc.submit_request(db, office_code, body, source_ip=_client_ip(request))
    return BookingRequestRead(**svc.read_one(db, req))


# ── Staff (AUTH) ─────────────────────────────────────────────────────────────
@staff_router.get(
    "/requests",
    response_model=RequestListResponse,
    operation_id="appointnow_list_requests",
)
def list_requests(
    db: DbSession,
    tenant_id: TenantId,
    status: str | None = Query(default=None, description="pending|approved|declined|expired"),
    office_id: int | None = Query(default=None),
    office_ids: list[int] | None = Query(default=None, description="OFF-SCOPE-15: My-offices inbox (repeatable)"),
    q: str | None = Query(default=None, description="name/phone/email/reason/code"),
    reason_id: str | None = Query(default=None),
    reason_label: str | None = Query(default=None),
    is_new_patient: bool | None = Query(default=None),
    date_from: date | None = Query(default=None, description="over requested slot date"),
    date_to: date | None = Query(default=None),
    sort: str = Query(default="created_desc", description="created_desc|created_asc|slot_asc|slot_desc"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> RequestListResponse:
    """AN-4 / AN-13: the inbox — server-side filter/search/sort/paging + an
    unfiltered per-status count summary for the tab badges."""
    result = svc.list_requests(
        db,
        tenant_id,
        status=status,
        office_id=office_id,
        office_ids=office_ids,
        q=q,
        reason_id=reason_id,
        reason_label=reason_label,
        is_new_patient=is_new_patient,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        page=page,
        size=size,
    )
    return RequestListResponse(
        items=[BookingRequestRead(**d) for d in svc.read_many(db, result["items"])],
        counts=result["counts"],
        page=result["page"],
        size=result["size"],
        total=result["total"],
    )


@staff_router.get(
    "/requests/{request_id}",
    response_model=BookingRequestRead,
    operation_id="appointnow_get_request",
)
def get_request(request_id: str, db: DbSession, tenant_id: TenantId) -> BookingRequestRead:
    req = svc.get_request(db, tenant_id, request_id)
    return BookingRequestRead(**svc.read_one(db, req))


@staff_router.get(
    "/requests/{request_id}/patient-matches",
    response_model=list[PatientMatch],
    operation_id="appointnow_request_patient_matches",
)
def request_patient_matches(
    request_id: str, db: DbSession, tenant_id: TenantId
) -> list[PatientMatch]:
    """AN-9: possible existing-patient matches (phone/email/DOB) to surface before
    a new patient is created on approve."""
    req = svc.get_request(db, tenant_id, request_id)
    return [PatientMatch(**m) for m in svc.find_patient_matches(db, tenant_id, req)]


@staff_router.post(
    "/requests/{request_id}/approve",
    response_model=BookingRequestRead,
    operation_id="appointnow_approve_request",
    responses={409: {"model": ErrorResponse}},
    # ACCESS-RIGHTS C1: approving books a real appointment — gate it.
    dependencies=[Depends(require_permission(
        "appointnow_approve_booking", action="approve an online booking"))],
)
def approve_request(
    request_id: str,
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    body: ApproveInput | None = None,
) -> BookingRequestRead:
    """AN-5: atomically re-check the slot, book the appointment, link it, mark
    approved. Optionally matches/creates a patient (AN-9)."""
    req = svc.approve_request(
        db, tenant_id, request_id, body or ApproveInput(), actor_id=current.id
    )
    return BookingRequestRead(**svc.read_one(db, req))


@staff_router.post(
    "/requests/{request_id}/decline",
    response_model=BookingRequestRead,
    operation_id="appointnow_decline_request",
    responses={409: {"model": ErrorResponse}},
    # ACCESS-RIGHTS C1: declining actions a booking request — gate it.
    dependencies=[Depends(require_permission(
        "appointnow_decline_booking", action="decline an online booking"))],
)
def decline_request(
    request_id: str,
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    body: DeclineInput | None = None,
) -> BookingRequestRead:
    """AN-5: mark the request declined (stores the reason + actor)."""
    reason = body.reason if body else None
    req = svc.decline_request(db, tenant_id, request_id, reason, actor_id=current.id)
    return BookingRequestRead(**svc.read_one(db, req))


@staff_router.post(
    "/requests/{request_id}/reschedule",
    response_model=BookingRequestRead,
    operation_id="appointnow_reschedule_request",
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def reschedule_request(
    request_id: str,
    body: RescheduleInput,
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
) -> BookingRequestRead:
    """AN-14: move a *pending* request to a staff-chosen slot. Keeps the contact,
    preserves the patient's first-requested slot in ``original_slot``, re-takes
    the soft-hold, records the actor. 409 ``request_not_pending`` once settled;
    409 ``slot_conflict`` with ``details.conflicts[]`` on an overlapping
    appointment for the provider."""
    req = svc.reschedule_request(db, tenant_id, request_id, body, actor_id=current.id)
    return BookingRequestRead(**svc.read_one(db, req))


@staff_router.delete(
    "/requests/{request_id}",
    operation_id="appointnow_purge_request",
    dependencies=[Depends(require_roles("admin"))],
    responses={409: {"model": ErrorResponse}},
)
def purge_request(
    request_id: str,
    db: DbSession,
    tenant_id: TenantId,
    force: bool = Query(default=False, description="Also purge an approved request"),
) -> dict:
    """AN-24 (admin): hard-delete a spam/test request. An approved request is
    refused (409 ``request_approved``) without ``force=true``; the booked
    appointment is never touched."""
    return svc.purge_request(db, tenant_id, request_id, force=force)
