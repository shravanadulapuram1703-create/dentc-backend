"""Treatment-plan schemas (service summary + the dev-report customisations).

Custom item Create/Update/Read (single source, imported by the registry) add the
new fields (PLAN-1 ``phase_id``, PLAN-2 dates, PLAN-5 ``provider_id``, PLAN-10
``discount``, PLAN-14 ``is_archived``, the Edit Treatment window's PLAN-17/18/19/
25/26/27/28/29 + PLAN-11 columns) and a server-side status enum. Plus the
re-estimate (PLAN-3), report (PLAN-6) and book-from-plan (PLAN-APPT-5) shapes.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.core.datetimes import UtcDatetime

# Canonical item statuses (legacy D/A/U/H/Alt/RO). Server-side enum (report §LOW).
# PROC-INT-2: ``completed`` is a real value — set by the server when a charge
# references the item (``patient_procedures.treatment_plan_item_id``) and
# released when that charge is voided; a client may only *write* it when such a
# charge exists. ``scheduled`` is the legacy "on an appointment" state: set by
# the server when an appointment line books the item (PLAN-APPT-1), reverted
# when that appointment is cancelled / deleted, and still writable by hand.
# PLAN-20: ``internal_referral`` / ``external_referral`` are the two remaining
# STATUS-panel boxes (a referral routed to a provider in the practice vs. out).
ItemStatus = Literal[
    "diagnosed", "accepted", "unaccepted", "hold", "alternative", "referred_out",
    "scheduled", "completed", "internal_referral", "external_referral",
]
COMPLETED_STATUS = "completed"
SCHEDULED_STATUS = "scheduled"
ACCEPTED_STATUS = "accepted"

# PLAN-27: the Edit Treatment "Referral Type" radio. Same vocabulary as
# ``referrals.referral_type`` ("in" = referred in by, "out" = referred out to).
ReferralType = Literal["in", "out"]

# PLAN-9: the PRE AUTH STATUS radios.
PreauthStatus = Literal["sent", "closed"]


class TreatmentPlanSummary(BaseModel):
    plan_id: str
    name: str
    status: str
    item_count: int
    total_fee: Decimal
    total_insurance_estimate: Decimal
    total_patient_estimate: Decimal


# ── Treatment-plan item (custom over the factory) ────────────────────────────
class TreatmentPlanItemCreate(BaseModel):
    id: str
    plan_id: str
    procedure_code: str
    # PLAN-29 / FEE-3: optional — an omitted fee is priced server-side through the
    # same resolver a charge uses, and the schedule that priced it is recorded.
    fee: Optional[Decimal] = None
    description: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    quadrant: Optional[str] = None  # PROC-INT-5
    material_id: Optional[int] = None  # PROC-INT-5
    priority: Optional[int] = None
    phase_id: Optional[int] = None  # PLAN-1
    insurance_estimate: Optional[Decimal] = None
    discount: Optional[Decimal] = None  # PLAN-10
    billing_order: Optional[str] = None
    status: Optional[ItemStatus] = None
    diagnosed_by: Optional[str] = None
    provider_id: Optional[str] = None  # PLAN-5
    diagnosed_date: Optional[date] = None  # PLAN-2
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # ── Edit Treatment window ──
    notes: Optional[str] = None  # PLAN-17
    accepted_date: Optional[date] = None  # PLAN-18
    scheduled_date: Optional[date] = None
    duration_minutes: Optional[int] = Field(default=None, ge=0)  # PLAN-19
    referral_id: Optional[int] = None  # PLAN-27
    referral_type: Optional[str] = None  # normalised + validated server-side (in|out)
    update_end_date_at_posting: Optional[bool] = None  # PLAN-28
    re_estimate_at_posting: Optional[bool] = None
    fee_schedule_id: Optional[int] = None  # PLAN-29
    counselor_user_id: Optional[int] = None  # PLAN-11
    # PLAN-26: the full ICD-10 set for the line (ordered). Omit to leave alone.
    icd_code_ids: Optional[list[int]] = None


class TreatmentPlanItemUpdate(BaseModel):
    plan_id: Optional[str] = None  # re-parent (Change IDs → Tx Plan)
    procedure_code: Optional[str] = None
    fee: Optional[Decimal] = None
    description: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    quadrant: Optional[str] = None
    material_id: Optional[int] = None
    priority: Optional[int] = None
    phase_id: Optional[int] = None
    insurance_estimate: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    billing_order: Optional[str] = None
    status: Optional[ItemStatus] = None
    diagnosed_by: Optional[str] = None
    provider_id: Optional[str] = None
    diagnosed_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_archived: Optional[bool] = None
    # ── Edit Treatment window ──
    notes: Optional[str] = None
    accepted_date: Optional[date] = None
    scheduled_date: Optional[date] = None
    duration_minutes: Optional[int] = Field(default=None, ge=0)
    referral_id: Optional[int] = None
    referral_type: Optional[str] = None  # normalised + validated server-side (in|out)
    update_end_date_at_posting: Optional[bool] = None
    re_estimate_at_posting: Optional[bool] = None
    fee_schedule_id: Optional[int] = None
    counselor_user_id: Optional[int] = None
    # PLAN-26: replaces the set; ``[]`` is "clear all".
    icd_code_ids: Optional[list[int]] = None


class ItemIcdCodeRead(BaseModel):
    """PLAN-26: one linked diagnosis, denormalised so the list box needs no lookup."""

    id: int
    code: Optional[str] = None
    icd10: Optional[str] = None
    description: Optional[str] = None
    ordinal: int = 1


class TreatmentPlanItemRead(ORMModel):
    id: str
    plan_id: str
    procedure_code: str
    description: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    quadrant: Optional[str] = None
    material_id: Optional[int] = None
    priority: int
    phase_id: Optional[int] = None
    fee: Decimal
    insurance_estimate: Decimal
    discount: Optional[Decimal] = None
    billing_order: Optional[str] = None
    status: str
    diagnosed_by: Optional[str] = None
    provider_id: Optional[str] = None
    diagnosed_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_archived: bool
    created_at: UtcDatetime
    updated_at: Optional[UtcDatetime] = None
    # PROC-INT-1: the live (non-void) charge that fulfilled this item, resolved
    # from ``patient_procedures.treatment_plan_item_id`` by the read enrich hook.
    # Derived on purpose — the FK lives on the charge so there is one source of truth.
    procedure_id: Optional[str] = None
    # ── Edit Treatment window ──
    notes: Optional[str] = None  # PLAN-17
    accepted_date: Optional[date] = None  # PLAN-18
    scheduled_date: Optional[date] = None
    duration_minutes: Optional[int] = None  # PLAN-19
    # PLAN-25: actor ids + names (names resolved by the enrich hook, batched).
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    referral_id: Optional[int] = None  # PLAN-27
    referral_type: Optional[str] = None
    referral_name: Optional[str] = None
    update_end_date_at_posting: bool = False  # PLAN-28
    re_estimate_at_posting: bool = False
    fee_schedule_id: Optional[int] = None  # PLAN-29
    fee_schedule_name: Optional[str] = None
    counselor_user_id: Optional[int] = None  # PLAN-11
    counselor_name: Optional[str] = None
    # PLAN-26: ordered diagnosis links (enriched, one query per page).
    icd_code_ids: list[int] = Field(default_factory=list)
    icd_codes: list[ItemIcdCodeRead] = Field(default_factory=list)
    # PLAN-APPT-2: the live appointment(s) this item is booked on, derived from
    # ``appointment_procedures.treatment_plan_item_id`` (archived lines and
    # cancelled / deleted appointments excluded). ``appointment_id`` is the
    # soonest; ``appointment_ids`` lists every live booking.
    appointment_id: Optional[str] = None
    appointment_ids: list[str] = Field(default_factory=list)
    status_before_scheduled: Optional[str] = None


class PostPlanItemRequest(BaseModel):
    """Body for ``POST /treatment-plan-items/{id}/post`` (Post to Ledger).

    Every field is optional: the charge inherits the item (code, tooth, surface,
    quadrant, material, fee, provider, duration) and the plan/patient (office).
    Anything given here overrides the inherited value. PLAN-28: the item's
    ``update_end_date_at_posting`` / ``re_estimate_at_posting`` flags are honoured
    unless overridden per call.
    """

    date_of_service: Optional[date] = None
    provider_id: Optional[str] = None
    hygienist_id: Optional[str] = None
    office_id: Optional[int] = None
    fee: Optional[Decimal] = None
    insurance_estimate: Optional[Decimal] = None
    patient_estimate: Optional[Decimal] = None
    apply_to: Optional[str] = None
    billing_order: Optional[str] = None
    appointment_id: Optional[str] = None
    notes: Optional[str] = None
    procedure_id: Optional[str] = None  # client-chosen charge id (else generated)
    # PLAN-28 per-call overrides of the item's stored posting flags.
    update_end_date_at_posting: Optional[bool] = None
    re_estimate_at_posting: Optional[bool] = None


# ── PLAN-3: insurance re-estimate ────────────────────────────────────────────
class ReEstimateLine(BaseModel):
    item_id: str
    procedure_code: str
    fee: Decimal
    coverage_pct: Decimal
    deductible_applied: Decimal
    insurance_estimate: Decimal
    patient_estimate: Decimal
    # FEE-1: which band priced the line — an ADA range or a coverage category.
    coverage_category: Optional[str] = None
    rule_start_code: Optional[str] = None
    # PLAN-29: set when ``use_new_fees`` re-priced the line.
    fee_schedule_id: Optional[int] = None
    fee_source: Optional[str] = None


class ReEstimateResult(BaseModel):
    plan_id: str
    insured: bool
    ins_plan_id: Optional[int] = None
    phase_id: Optional[int] = None
    use_new_fees: bool = False
    deductible_remaining_after: Optional[Decimal] = None
    annual_max_remaining_after: Optional[Decimal] = None
    total_fee: Decimal
    total_insurance_estimate: Decimal
    total_patient_estimate: Decimal
    lines: list[ReEstimateLine]


# ── PLAN-6: server-side report payload ───────────────────────────────────────
class PlanReportPatient(BaseModel):
    id: int
    chart_no: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[date] = None


class PlanReportItem(BaseModel):
    id: str
    procedure_code: str
    description: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    priority: int
    phase_id: Optional[int] = None
    status: str
    fee: Decimal
    discount: Optional[Decimal] = None
    insurance_estimate: Decimal
    patient_estimate: Decimal
    diagnosed_by: Optional[str] = None
    provider_id: Optional[str] = None
    diagnosed_date: Optional[date] = None
    # PLAN-21: the tilde marker needs the deductible applied per line; it comes
    # from the item's live insurance-detail row (written by re-estimate).
    deductible_applied: Optional[Decimal] = None


class TreatmentPlanReport(BaseModel):
    plan_id: str
    name: str
    status: str
    patient: PlanReportPatient
    item_count: int
    total_fee: Decimal
    total_discount: Decimal
    total_insurance_estimate: Decimal
    total_patient_estimate: Decimal
    items: list[PlanReportItem]


# ── PLAN-APPT-5: atomic book-from-plan ───────────────────────────────────────
class BookFromPlanRequest(BaseModel):
    """Body for ``POST /treatment-plans/{plan_id}/book``.

    ``item_ids`` are the selected grid rows. Everything else defaults: provider =
    the first item's provider (PLAN-APPT-3), operatory = the provider's default
    chair, else the office chair whose column provider matches (PLAN-APPT-4),
    office = the plan's office, else the patient's home office, duration = the sum
    of the items' ``duration_minutes`` (code default, else 30 each).
    """

    item_ids: list[str] = Field(..., min_length=1)
    date: date
    start_time: time
    duration: Optional[int] = Field(default=None, gt=0, description="Minutes; default = sum of items")
    provider_id: Optional[str] = None
    operatory_id: Optional[str] = None
    office_id: Optional[int] = None
    appointment_id: Optional[str] = Field(default=None, description="Client-chosen id (else generated)")
    notes: Optional[str] = None
    status: Optional[str] = Field(default=None, description="Appointment status (default 'Scheduled')")


class BookedProcedureRead(BaseModel):
    id: int
    appointment_id: str
    treatment_plan_id: Optional[str] = None
    treatment_plan_item_id: Optional[str] = None
    procedure_code: str
    provider_id: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    description: Optional[str] = None
    fee: Decimal
    insurance_estimate: Decimal
    est_patient: Optional[Decimal] = None
    duration_minutes: Optional[int] = None
    status: str


class BookFromPlanResult(BaseModel):
    appointment_id: str
    patient_id: int
    office_id: int
    provider_id: str
    operatory_id: Optional[str] = None
    date: date
    start_time: time
    end_time: time
    duration: int
    status: str
    # How the defaults were resolved, so the form can say so.
    provider_source: Literal["request", "item", "plan_items", "operatory", "patient_preferred"]
    operatory_source: Literal["request", "provider_default", "provider_column", "none"]
    procedures: list[BookedProcedureRead]
    items: list[TreatmentPlanItemRead]


# ── PLAN-16: provider ↔ procedure-code eligibility, batched ──────────────────
class EligibleProviderRead(BaseModel):
    id: str
    name: str
    short_id: Optional[str] = None
    role: Optional[str] = None
    is_active: bool = True


class CodeEligibility(BaseModel):
    procedure_code: str
    # PLAN-16 semantics, confirmed: a code nobody is assigned to is *unrestricted*
    # (every provider may perform it). ``restricted`` is False in that case and
    # ``provider_ids`` is empty.
    restricted: bool
    provider_ids: list[str] = Field(default_factory=list)


class ProcedureEligibilityResult(BaseModel):
    codes: list[CodeEligibility]
    # The provider set that can perform *every* requested code — the Change
    # Provider dropdown for a multi-row selection. ``None`` when nothing is
    # restricted (offer everyone).
    eligible_for_all: Optional[list[str]] = None
    restricted_provider_ids: list[str] = Field(
        default_factory=list,
        description="Providers that hold at least one assignment in this tenant",
    )
