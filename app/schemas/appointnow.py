"""AppointNow wire models (public booking + staff inbox).

Mirrors the frontend transport contract (`src/features/appointnow/transport/types.ts`):
``PublicOfficeInfo``, ``AppointmentReason``, ``AvailableSlot``, ``SubmitRequestInput``
and ``BookingRequest``. All field names are snake_case; times are ``"HH:MM"`` (24h)
strings and dates ``"YYYY-MM-DD"`` — the service formats them, never a bare
``datetime.time`` (which would serialise as ``"HH:MM:SS"``).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.core.datetimes import UtcDatetime


# ── Public office info (AN-1) ────────────────────────────────────────────────
class PublicProvider(BaseModel):
    id: str
    name: str
    title: str | None = None


class AppointmentReason(BaseModel):
    """A bookable reason (drives chair-time duration). ``id`` is the wire code."""

    id: str
    label: str
    duration_minutes: int
    requires_provider: bool = False


class PublicOfficeInfo(BaseModel):
    office_code: str
    office_id: int
    name: str
    timezone: str
    phone: str | None = None
    address: str | None = None
    providers: list[PublicProvider] = Field(default_factory=list)
    reasons: list[AppointmentReason] = Field(default_factory=list)


# ── Availability (AN-2) ──────────────────────────────────────────────────────
class AvailableSlot(BaseModel):
    date: str
    start_time: str
    end_time: str
    duration_minutes: int
    provider_id: str | None = None
    provider_name: str | None = None


class AvailabilityResponse(BaseModel):
    slots: list[AvailableSlot] = Field(default_factory=list)
    timezone: str  # AN-10: office-local zone the times are expressed in


# ── Request intake (AN-3) ────────────────────────────────────────────────────
class SlotInput(BaseModel):
    date: str
    start_time: str
    end_time: str | None = None
    duration_minutes: int | None = None
    provider_id: str | None = None
    provider_name: str | None = None


class ContactInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    date_of_birth: date | None = None
    is_new_patient: bool = True
    notes: str | None = Field(default=None, max_length=2000)
    # AN-16: persisted as real columns. The two acknowledgements are REQUIRED to
    # be ``true`` at intake (422 ``acknowledgement_required`` otherwise). ``None``
    # means "not sent" — the service then looks for the frontend's interim
    # ``notes`` markers before refusing, so deploy order cannot break booking.
    insurance_info: str | None = Field(default=None, max_length=500)
    disclaimer_accepted: bool | None = None
    consent_accepted: bool | None = None


class SubmitRequestInput(BaseModel):
    reason_id: str
    reason_label: str | None = None
    slot: SlotInput
    contact: ContactInput
    # AN-3 anti-abuse: Cloudflare Turnstile token (enforced only when a secret is set).
    turnstile_token: str | None = None


# ── Booking request read (AN-3 / AN-4 / AN-5) ────────────────────────────────
class SlotOut(BaseModel):
    date: str
    start_time: str
    end_time: str
    duration_minutes: int
    provider_id: str | None = None
    provider_name: str | None = None


class ContactOut(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    date_of_birth: date | None = None
    is_new_patient: bool = True
    notes: str | None = None
    insurance_info: str | None = None
    disclaimer_accepted: bool = False
    consent_accepted: bool = False


class BookingRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    office_code: str | None = None
    office_id: int
    status: str
    reason_id: str | None = None
    reason_label: str | None = None
    slot: SlotOut
    contact: ContactOut
    appointment_id: str | None = None
    patient_id: int | None = None
    decline_reason: str | None = None
    # AN-17: who approved/declined (id + display name resolved from ``users``).
    actioned_by_id: int | None = None
    actioned_by_name: str | None = None
    actioned_at: UtcDatetime | None = None
    # AN-14: the slot the patient first asked for; null until a staff reschedule.
    original_slot: SlotOut | None = None
    reschedule_count: int = 0
    rescheduled_by_id: int | None = None
    rescheduled_by_name: str | None = None
    rescheduled_at: UtcDatetime | None = None
    # AN-21: last outbound notification to the contact (``sms`` | ``email``).
    contact_notified_at: UtcDatetime | None = None
    contact_notified_via: str | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime | None = None


# ── Staff inbox listing (AN-4 / AN-13) ───────────────────────────────────────
class StatusCounts(BaseModel):
    """Unfiltered per-status counts so the tab badges stay accurate (AN-13)."""

    pending: int = 0
    approved: int = 0
    declined: int = 0
    expired: int = 0
    all: int = 0


class RequestListResponse(BaseModel):
    items: list[BookingRequestRead] = Field(default_factory=list)
    counts: StatusCounts
    page: int
    size: int
    total: int  # rows matching the active filter (for pagination)


# ── Approve / decline (AN-5) ─────────────────────────────────────────────────
class ApproveInput(BaseModel):
    # The server books atomically; these only steer that booking.
    appointment_id: str | None = None  # honoured only if the server can't book itself
    patient_id: int | None = None  # link to an existing patient (AN-9 match chosen by staff)
    create_patient: bool = False  # create/match a patient from the contact details (AN-9)
    provider_id: str | None = None  # override the requested provider
    operatory_id: str | None = None  # place into a specific chair


class DeclineInput(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


# ── Reschedule (AN-14) ───────────────────────────────────────────────────────
class RescheduleSlotInput(BaseModel):
    date: str
    start_time: str
    end_time: str | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    # Omitted = keep the request's provider. Any active provider of the office is
    # allowed (staff may place the visit with a provider not offered publicly).
    provider_id: str | None = None


class RescheduleInput(BaseModel):
    slot: RescheduleSlotInput


class SlotConflict(BaseModel):
    """One existing appointment overlapping the requested slot (409
    ``slot_conflict`` → ``details.conflicts[]``, AN-14/AN-15)."""

    appointment_id: str
    patient_name: str | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    operatory_id: str | None = None
    operatory_name: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    procedure_label: str | None = None
    kind: str  # "provider" | "operatory"


# ── Duplicate-patient matching (AN-9) ────────────────────────────────────────
class PatientMatch(BaseModel):
    patient_id: int
    chart_no: str | None = None
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    dob: date | None = None
    match_on: list[str] = Field(default_factory=list)  # e.g. ["phone", "dob"]
