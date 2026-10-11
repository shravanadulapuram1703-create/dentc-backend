"""AppointNow wire models (public booking + staff inbox).

Mirrors the frontend transport contract (`src/features/appointnow/transport/types.ts`):
``PublicOfficeInfo``, ``AppointmentReason``, ``AvailableSlot``, ``SubmitRequestInput``
and ``BookingRequest``. All field names are snake_case; times are ``"HH:MM"`` (24h)
strings and dates ``"YYYY-MM-DD"`` — the service formats them, never a bare
``datetime.time`` (which would serialise as ``"HH:MM:SS"``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.datetimes import UtcDatetime


# ── Public office info (AN-1) ────────────────────────────────────────────────
class PublicProvider(BaseModel):
    id: str
    name: str
    title: str | None = None


class PublicOperatory(BaseModel):
    """AN-28: a chair the patient may book into on the public page. Every active
    operatory of the office is offered; the page always adds its own synthetic
    "Emergency" choice on top (never a row here)."""

    id: str
    name: str
    provider_id: str | None = None
    provider_name: str | None = None


class AppointmentReason(BaseModel):
    """A bookable reason (drives chair-time duration). ``id`` is the wire code."""

    id: str
    label: str
    duration_minutes: int
    requires_provider: bool = False
    # AN-27: effective requirement for this reason (reason override → office).
    requires_payment: bool = False
    payment_amount: Decimal | None = None


class PublicPaymentInfo(BaseModel):
    """AN-27.1: lets the public page say up front whether a visit needs payment
    and how much, instead of only "if payment is required"."""

    requires_payment: bool = False  # office default (a reason may override)
    amount: Decimal | None = None
    currency: str = "usd"
    # True when the office can send a hosted card link; False = the office
    # collects by phone / at the desk before confirming.
    online_payment_available: bool = False


class PublicOfficeInfo(BaseModel):
    office_code: str
    office_id: int
    name: str
    timezone: str
    phone: str | None = None
    address: str | None = None
    providers: list[PublicProvider] = Field(default_factory=list)
    operatories: list[PublicOperatory] = Field(default_factory=list)  # AN-28
    reasons: list[AppointmentReason] = Field(default_factory=list)
    payment: PublicPaymentInfo = Field(default_factory=PublicPaymentInfo)


# ── Availability (AN-2) ──────────────────────────────────────────────────────
class AvailableSlot(BaseModel):
    date: str
    start_time: str
    end_time: str
    duration_minutes: int
    provider_id: str | None = None
    provider_name: str | None = None
    # AN-28: set when the query was scoped to one operatory.
    operatory_id: str | None = None
    operatory_name: str | None = None


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
    operatory_id: str | None = None  # AN-28


class AcknowledgementTexts(BaseModel):
    disclaimer: str | None = Field(default=None, max_length=10000)
    consent: str | None = Field(default=None, max_length=10000)
    payment: str | None = Field(default=None, max_length=10000)


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
    # AN-26: the Payment acknowledgement — required ``true`` like the other two.
    payment_terms_accepted: bool | None = None
    # AN-26: the exact wording shown for each acknowledgement, so the server can
    # record which text was agreed to (hashed onto the row, text kept once).
    acknowledgement_texts: AcknowledgementTexts | None = None
    acknowledgement_version: str | None = Field(default=None, max_length=50)


class SubmitRequestInput(BaseModel):
    reason_id: str
    reason_label: str | None = None
    slot: SlotInput
    contact: ContactInput
    # AN-29: an emergency request may ask for ANY time — the slot is a preference,
    # not re-checked against availability (staff triage it on approve).
    is_emergency: bool = False
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
    operatory_id: str | None = None  # AN-28
    operatory_name: str | None = None


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
    # AN-26: null = the request predates the Payment question (not a refusal).
    payment_terms_accepted: bool | None = None
    acknowledgement_hashes: dict[str, str] | None = None
    acknowledgement_version: str | None = None
    acknowledged_at: UtcDatetime | None = None


class PaymentOut(BaseModel):
    """AN-27.2: the payment block on a request."""

    requires_payment: bool = False
    # not_required | required | link_sent | paid | expired | refunded
    status: str = "not_required"
    amount: Decimal | None = None
    currency: str | None = None
    provider: str | None = None  # stripe | manual
    link_url: str | None = None
    link_sent_at: UtcDatetime | None = None
    link_sent_via: str | None = None  # sms | email
    link_expires_at: UtcDatetime | None = None
    note: str | None = None
    requested_by_id: int | None = None
    requested_by_name: str | None = None
    paid_at: UtcDatetime | None = None
    paid_amount: Decimal | None = None
    reference: str | None = None
    method: str | None = None
    # The ledger credit; null while paid = unapplied (no PMS patient yet).
    ledger_payment_id: str | None = None
    posted_to_ledger: bool = False
    booking_error: str | None = None
    refunded_at: UtcDatetime | None = None
    refund_amount: Decimal | None = None
    refund_reference: str | None = None
    refund_reason: str | None = None


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
    is_emergency: bool = False  # AN-29
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
    payment: PaymentOut = Field(default_factory=PaymentOut)
    # AN-27.6: returned ONCE, on the public submit response only — the patient's
    # key to ``GET /appointnow/requests/{id}/status``. Never stored in clear.
    status_token: str | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime | None = None


# ── Staff inbox listing (AN-4 / AN-13) ───────────────────────────────────────
class StatusCounts(BaseModel):
    """Unfiltered per-status counts so the tab badges stay accurate (AN-13)."""

    pending: int = 0
    awaiting_payment: int = 0
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
    # AN-27: approve a payment-required request with no recorded payment
    # (collected outside DentC, or waived). Recorded in the appointment note.
    waive_payment: bool = False


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
    # AN-28: omitted = keep the request's operatory.
    operatory_id: str | None = None


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


# ── Payment flow (AN-27) ─────────────────────────────────────────────────────
class PaymentBookingInput(BaseModel):
    """What to book once the payment lands (the ApproveInput steering fields)."""

    patient_id: int | None = None
    create_patient: bool = False
    provider_id: str | None = None
    operatory_id: str | None = None


class RequestPaymentInput(BaseModel):
    # Omitted = the amount snapshotted from the reason / office config.
    amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    note: str | None = Field(default=None, max_length=1000)
    # Link life (and slot hold). Stripe Checkout accepts 30 min .. 24 h.
    expires_in_minutes: int | None = Field(default=None, ge=30, le=1440)
    booking: PaymentBookingInput | None = None


class MarkPaidInput(BaseModel):
    """Staff record a payment taken outside the link (phone / terminal / cash)."""

    amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    reference: str | None = Field(default=None, max_length=255)
    method: str | None = Field(default="credit_card", max_length=50)
    # Book immediately (default) through the same atomic path as approve.
    book: bool = True
    booking: PaymentBookingInput | None = None


class RefundInput(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    reason: str | None = Field(default=None, max_length=1000)


class PublicRequestStatus(BaseModel):
    """AN-27.6: what the patient may see about their own request. No contact
    details — the token proves possession of the confirmation, not identity."""

    id: str
    office_name: str | None = None
    office_phone: str | None = None
    status: str
    confirmed: bool = False
    slot: SlotOut
    reason_label: str | None = None
    payment_required: bool = False
    payment_status: str = "not_required"
    payment_amount: Decimal | None = None
    payment_currency: str | None = None
    payment_link_url: str | None = None  # only while a link is open
    payment_link_expires_at: UtcDatetime | None = None
    paid_at: UtcDatetime | None = None


class PaymentWebhookAck(BaseModel):
    received: bool = True
    handled: bool = False
    request_id: str | None = None
    detail: str | None = None
