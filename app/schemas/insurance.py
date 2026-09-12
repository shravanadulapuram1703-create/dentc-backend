"""Insurance Setup DTOs (insurance dev-report INS-2, patient-insurance INS-PT-*).

The carrier ``Read`` schema adds a typed ``is_dental`` discriminator derived from
the brittle legacy ``carrier_type`` string (``"True"``/``"False"``), so the
frontend has a stable boolean to branch on instead of guessing.

INS-PT-12 makes that boolean **writable** as well: send ``is_dental`` and the
server stores the canonical ``carrier_type``. Both fields stay accepted (the form
binds to ``carrier_type`` 1:1 today), and the vocabulary that decides which is
which lives once, in ``app.services.insurance_service``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, create_model

from app.db.models import (
    Employer,
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    InsurancePlanFrequencyGroup,
    InsuranceSubscriber,
)
from app.schemas.common import PageMeta
from app.schemas.factory import build_schemas
from app.services.insurance_service import carrier_is_dental
from app.core.datetimes import UtcDatetime

_CarrierCreate, _CarrierUpdate, _CarrierReadBase = build_schemas(
    InsuranceCarrier, "InsuranceCarrier"
)


class _CarrierWriteMixin(BaseModel):
    # INS-PT-12: the typed alternative to ``carrier_type``. When present it wins,
    # because it is the field that cannot have been mistyped.
    is_dental: bool | None = None
    # INS-PT-13: quick-add creates a second carrier under an existing name only
    # when the caller says so; otherwise the create is a 409 the dialog can act on.
    allow_duplicate_name: bool = False


class InsuranceCarrierCreate(_CarrierCreate, _CarrierWriteMixin):  # type: ignore[valid-type, misc]
    pass


class InsuranceCarrierUpdate(_CarrierUpdate, _CarrierWriteMixin):  # type: ignore[valid-type, misc]
    pass


class InsuranceCarrierRead(_CarrierReadBase):  # type: ignore[valid-type, misc]
    @computed_field(  # type: ignore[prop-decorator]
        description="Typed discriminator derived from carrier_type (True/dental → true)."
    )
    @property
    def is_dental(self) -> bool | None:
        return carrier_is_dental(self.carrier_type)


# ── Employers (INS-PT-13) ────────────────────────────────────────────────────
_EmployerCreate, _EmployerUpdate, EmployerRead = build_schemas(Employer, "Employer")


class EmployerCreate(_EmployerCreate):  # type: ignore[valid-type, misc]
    allow_duplicate_name: bool = False


class EmployerUpdate(_EmployerUpdate):  # type: ignore[valid-type, misc]
    allow_duplicate_name: bool = False


# ── Plans (INS-PT-8/9/12/18/19) ──────────────────────────────────────────────
# EDIT-PLAN-5: ``locked_at`` / ``locked_by`` are server-stamped when ``is_locked``
# flips, never client-written.
_PlanCreate, _PlanUpdate, _PlanReadBase = build_schemas(
    InsurancePlan, "InsurancePlanBase",
    create_exclude=("locked_at", "locked_by"),
    update_exclude=("locked_at", "locked_by"),
)


class InsurancePlanCreate(_PlanCreate):  # type: ignore[valid-type, misc]
    """INS-PT-19: an active plan on the same carrier + group number is a 409.

    ``allow_duplicate_group`` is the API half of the dialog's "override" button —
    two offices can legitimately hold separate plans on one group, so the server
    refuses the *accidental* duplicate rather than the duplicate.

    EDIT-PLAN-8: unknown keys are **422**, not silently dropped — a stale field
    name in a client would otherwise fail without a trace.
    """

    model_config = ConfigDict(extra="forbid")

    allow_duplicate_group: bool = False


class InsurancePlanUpdate(_PlanUpdate):  # type: ignore[valid-type, misc]
    """EDIT-PLAN-1: ``expected_updated_at`` is the ``updated_at`` the client read
    when it opened the wizard. Send it and the save is refused (412) if the row
    moved since; send an explicit ``null`` to assert the row has never been
    updated; leave it out for no precondition. ``If-Match`` / ``If-Unmodified-
    Since`` headers are the equivalent transport-level form."""

    model_config = ConfigDict(extra="forbid")

    allow_duplicate_group: bool = False
    expected_updated_at: UtcDatetime | None = None


class GroupNumberCascade(BaseModel):
    """EDIT-PLAN-4: what a plan group-number change did to the subscribers on
    the plan (returned on the PATCH that moved it)."""

    previous_group_number: str | None = None
    new_group_number: str | None = None
    #: Subscribers whose stored group number still equalled the plan's previous
    #: value (or was blank) — moved to the new value.
    subscribers_updated: int = 0
    #: Subscribers holding a different value — left alone (a per-card override).
    subscribers_kept: int = 0
    kept_subscriber_ids: list[int] = []


# INS-PT-9/18: a plan list returns carrier_id/employer_id only, so a 20-row grid
# page cost up to 40 single-id GETs (each with a preflight) just to render two
# name columns. INS-PT-8 adds the Created/Modified actors the grid renders as
# "date + user". ``is_dental`` rides along because the plan form re-derives the
# Dental/Medical selector from the carrier every time a plan is opened or copied.
InsurancePlanRead = create_model(
    "InsurancePlanRead", __base__=_PlanReadBase,
    carrier_name=(Optional[str], None),
    payer_id=(Optional[str], None),
    employer_name=(Optional[str], None),
    is_dental=(Optional[bool], None),
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
    # EDIT-PLAN-5
    locked_by_name=(Optional[str], None),
    # EDIT-PLAN-1: the version string ``If-Match`` accepts (also sent as the
    # ETag header); derived from updated_at (created_at when never updated).
    version=(Optional[str], None),
    # EDIT-PLAN-4: present only on the PATCH response that changed group_number.
    group_number_cascade=(Optional[GroupNumberCascade], None),
)


# ── Subscribers (EDIT-PLAN-4) ────────────────────────────────────────────────
InsuranceSubscriberCreate, InsuranceSubscriberUpdate, _SubscriberReadBase = build_schemas(
    InsuranceSubscriber, "InsuranceSubscriber"
)
# The subscriber's ``group_number`` is the value on the member's card — a
# per-enrolment snapshot that legitimately differs from the plan master on
# 22,335 migrated rows (``000003`` vs ``000003-pa``). The read says what the
# plan holds and whether the two agree, so a screen can show the divergence
# instead of guessing which is right.
InsuranceSubscriberRead = create_model(
    "InsuranceSubscriberRead", __base__=_SubscriberReadBase,
    plan_group_number=(Optional[str], None),
    group_number_matches_plan=(Optional[bool], None),
)


# ── INS-PT-5: eligibility "Update Status" stamp ──────────────────────────────
class EligibilityVerifyRequest(BaseModel):
    elig_status: str | None = None  # defaults to "verified" server-side
    notes: str | None = None


class EligibilityVerifyResult(BaseModel):
    subscriber_id: int
    elig_status: str | None = None
    elig_verified_on: UtcDatetime | None = None
    elig_verified_by: str | None = None
    realtime_supported: bool | None = None
    method: str  # "realtime" | "manual"


# ── INS-PT-20/21: "is this group taken?" ─────────────────────────────────────
class PlanMatch(BaseModel):
    id: int
    group_number: str | None = None
    carrier_id: int | None = None
    carrier_name: str | None = None
    payer_id: str | None = None
    employer_id: int | None = None
    employer_name: str | None = None
    plan_type: str | None = None
    coverage_type: str | None = None
    is_active: bool = True


class GroupAvailabilityResult(BaseModel):
    group_number: str
    carrier_id: int | None = None
    #: True when an **active** plan on the same carrier already holds this group.
    taken: bool
    matches: list[PlanMatch] = []
    #: INS-PT-21 — soft-deleted plans holding the number. Never blocking.
    inactive_matches: list[PlanMatch] = []
    #: Same group number under a different carrier. Never blocking.
    other_carrier_matches: list[PlanMatch] = []


# ── INS-PT-13: "is this carrier/employer name taken?" ────────────────────────
class NameMatch(BaseModel):
    id: int
    name: str
    is_active: bool = True


class NameAvailabilityResult(BaseModel):
    name: str
    taken: bool
    matches: list[NameMatch] = []
    inactive_matches: list[NameMatch] = []


# ── PLAN-DTL-2/5/9: coverage rules + frequency groups ────────────────────────
# Built here (not in the registry) so the generic CRUD routes and the
# plan-details endpoints share one named component each.
InsuranceCoverageRuleCreate, InsuranceCoverageRuleUpdate, InsuranceCoverageRuleRead = build_schemas(
    InsuranceCoverageRule, "InsuranceCoverageRule"
)
(
    InsurancePlanFrequencyGroupCreate,
    InsurancePlanFrequencyGroupUpdate,
    InsurancePlanFrequencyGroupRead,
) = build_schemas(InsurancePlanFrequencyGroup, "InsurancePlanFrequencyGroup")


class CoverageRuleItem(BaseModel):
    """One row of ``PUT /insurance-plans/{id}/coverage-rules``. ``id`` keeps an
    existing row (updated in place); omit it to insert. ``end_code`` defaults
    to ``start_code``. Typed limits win over the legacy string mirrors."""

    id: int | None = None
    start_code: str
    end_code: str | None = None
    category: str | None = None
    description: str | None = None
    coverage_pct: Decimal | None = None
    ded_waived: bool = False
    freq_limit: int | None = Field(None, ge=0, description="Frequency ordinal; 0/null = No Limitation")
    age_min: int | None = Field(None, ge=0)
    age_max: int | None = Field(None, ge=0)
    wait_months: int | None = Field(None, ge=0)
    # Legacy mirrors — accepted from older clients, parsed into the typed fields.
    age_limit: str | None = None
    wait_period: str | None = None


class FrequencyGroupItem(BaseModel):
    id: int | None = None
    code_group: str
    description: str | None = None
    freq_limit: int | None = Field(None, ge=0)
    whole_mouth: bool = False
    per_day_quantity: int | None = Field(None, ge=0)


class PlanCoverageReplaceRequest(BaseModel):
    """A section left ``null`` is untouched; a section sent as a list replaces
    the plan's rows of that kind (see the endpoint docstring).

    EDIT-PLAN-1: ``expected_updated_at`` is the **plan's** ``updated_at`` the
    client read — the plan row is the version of the whole document (every
    rule / frequency-group write moves it), so one value guards all four tabs.
    """

    rules: list[CoverageRuleItem] | None = None
    frequency_groups: list[FrequencyGroupItem] | None = None
    expected_updated_at: UtcDatetime | None = None


class SectionSummary(BaseModel):
    created: int = 0
    updated: int = 0
    deleted: int = 0


class PlanCoverageSummary(BaseModel):
    rules: SectionSummary | None = None
    frequency_groups: SectionSummary | None = None


class PlanCoverageResponse(BaseModel):
    plan_id: int
    rules: list[InsuranceCoverageRuleRead]  # type: ignore[valid-type]
    frequency_groups: list[InsurancePlanFrequencyGroupRead]  # type: ignore[valid-type]
    summary: PlanCoverageSummary | None = None
    copied_from_plan_id: int | None = None
    copied_plan_fields: list[str] = []
    # EDIT-PLAN-1: the plan's version after the write — what the next save asserts.
    plan_updated_at: UtcDatetime | None = None
    version: str | None = None


# ── EDIT-PLAN-2: usage / impact of a shared plan ─────────────────────────────
class PlanUsage(BaseModel):
    plan_id: int
    #: Distinct patients with an **active** slot on the plan.
    patients: int
    #: Active ``patient_insurance`` rows — a patient holding the plan in two
    #: slots counts twice here and once in ``patients``.
    patient_links: int
    #: Active ``insurance_subscribers`` rows on the plan.
    subscribers: int
    claims_total: int
    #: Claims not yet closed / paid / denied / voided (see ``OPEN_CLAIM_STATUSES``).
    claims_open: int
    claims_by_status: dict[str, int] = {}
    #: Claims naming this plan as the *other* coverage (ADA Items 4–11).
    claims_as_other_coverage: int = 0
    #: Distinct treatment plans that would be touched by a re-estimate
    #: (``GET …/affected-treatment-plans``).
    treatment_plans: int
    #: Open (not completed, not archived) items on those plans.
    treatment_plan_items_pending: int
    #: ``patient_payment_plans`` + ``ortho_plans`` referencing the plan.
    payment_plans: int = 0
    fee_schedules: int = 0
    #: Latest of: a slot linked, a subscriber enrolled, a claim created.
    last_used_at: UtcDatetime | None = None
    is_locked: bool = False
    #: True when more than one patient is linked — the UI's "update for all N".
    shared: bool = False


# ── EDIT-PLAN-6: per-plan change history ─────────────────────────────────────
class PlanHistoryChange(BaseModel):
    """One row-level change inside a bulk write (the coverage PUT / copy)."""

    resource_type: str
    row_id: int | str | None = None
    action: str
    label: str | None = None
    before: dict | None = None
    after: dict | None = None


class PlanHistoryEntry(BaseModel):
    id: int
    at: UtcDatetime
    user_id: int | None = None
    user_name: str | None = None
    #: HTTP method of the audited request (POST / PATCH / PUT / DELETE).
    action: str
    #: ``plan`` | ``coverage_rule`` | ``frequency_group`` | ``coverage_bulk`` | ``copy``
    source: str
    resource_type: str | None = None
    resource_id: str | None = None
    path: str
    before: dict | None = None
    after: dict | None = None
    changes: list[PlanHistoryChange] = []
    summary: str


class PlanHistoryResponse(BaseModel):
    plan_id: int
    items: list[PlanHistoryEntry]
    meta: PageMeta
    # The "Modified by / on" strip.
    created_at: UtcDatetime | None = None
    created_by_name: str | None = None
    updated_at: UtcDatetime | None = None
    updated_by_name: str | None = None
    version: str | None = None


# ── EDIT-PLAN-3: the re-estimate cascade ─────────────────────────────────────
class AffectedTreatmentPlan(BaseModel):
    id: str
    patient_id: int
    patient_name: str | None = None
    name: str | None = None
    status: str | None = None
    office_id: int | None = None
    pending_items: int
    #: ``active_slot`` — the patient's active coverage is this plan (what a
    #: re-estimate reads); ``estimated_against`` — an open item's insurance
    #: detail names this plan but the patient's active slot no longer does.
    coverage_source: str
    #: Latest ``updated_at`` across the plan's open items.
    last_updated_at: UtcDatetime | None = None


class AffectedTreatmentPlansResponse(BaseModel):
    plan_id: int
    items: list[AffectedTreatmentPlan]
    meta: PageMeta


class PlanReEstimateRequest(BaseModel):
    #: Count and list what would run; write nothing.
    dry_run: bool = False
    #: Legacy "Use New Fees" on every line (PLAN-29) before re-estimating.
    use_new_fees: bool = False
    #: Restrict to these treatment plans (must be in the affected set).
    treatment_plan_ids: list[str] | None = None
    #: Safety cap — the call runs inline in the request.
    max_plans: int = Field(500, ge=1, le=5000)
    #: Also re-sum the plan's open (unsubmitted) claims from their lines.
    recalculate_claims: bool = True


class PlanReEstimateLine(BaseModel):
    treatment_plan_id: str
    patient_id: int
    #: ``re_estimated`` | ``unchanged`` | ``failed`` | ``planned`` (dry run)
    status: str
    items: int = 0
    insurance_estimate_before: Decimal | None = None
    insurance_estimate_after: Decimal | None = None
    error: str | None = None


class PlanReEstimateResult(BaseModel):
    plan_id: int
    dry_run: bool
    use_new_fees: bool = False
    affected: int
    re_estimated: int = 0
    unchanged: int = 0
    failed: int = 0
    #: ``affected`` exceeded ``max_plans`` (or the explicit id list) — run again.
    truncated: bool = False
    claims_open: int = 0
    claims_recalculated: int = 0
    treatment_plans: list[PlanReEstimateLine] = []
    started_at: UtcDatetime
    finished_at: UtcDatetime


class PlanCopyRequest(BaseModel):
    include_rules: bool = True
    include_frequency_groups: bool = True
    #: Also copy the BENEFITS + PLAN-tab fields (never carrier/employer/group).
    include_plan_fields: bool = False


# ── PLAN-DTL-1/4: the wizard's catalogues ────────────────────────────────────
class FrequencyLimitation(BaseModel):
    code: int
    label: str
    key1: str | None = None
    key2: str | None = None
    definition_id: int | None = None
    legacy_id: str | None = None


class DefaultCoverageRule(BaseModel):
    start_code: str
    end_code: str
    category: str
    description: str
    coverage_pct: int
    ded_waived: bool
    freq_limit: int
    age_min: int | None = None
    age_max: int | None = None
    wait_months: int | None = None
    source: str


class CodeGroup(BaseModel):
    code: str
    label: str
    definition_id: int | None = None


class PlanFieldOption(BaseModel):
    code: str
    label: str


class InsurancePlanMetadata(BaseModel):
    frequency_limitations: list[FrequencyLimitation]
    default_coverage_rules: list[DefaultCoverageRule]
    code_groups: list[CodeGroup]
    plan_field_options: dict[str, list[PlanFieldOption]]
    #: EDIT-PLAN-9: the value a blank / omitted coded field stores and means.
    plan_field_defaults: dict[str, Any] = {}
    #: EDIT-PLAN-5: the right codes the plan write paths enforce.
    permissions: dict[str, Any] = {}
    #: EDIT-PLAN-1: how to assert "unchanged since I read it".
    concurrency: dict[str, Any] = {}
    catalog_sources: dict[str, str]
    conventions: dict[str, str]


__all__ = [
    "AffectedTreatmentPlan",
    "AffectedTreatmentPlansResponse",
    "GroupNumberCascade",
    "InsuranceSubscriberCreate",
    "InsuranceSubscriberRead",
    "InsuranceSubscriberUpdate",
    "PlanHistoryChange",
    "PlanHistoryEntry",
    "PlanHistoryResponse",
    "PlanReEstimateLine",
    "PlanReEstimateRequest",
    "PlanReEstimateResult",
    "PlanUsage",
    "CodeGroup",
    "CoverageRuleItem",
    "DefaultCoverageRule",
    "FrequencyGroupItem",
    "FrequencyLimitation",
    "InsuranceCoverageRuleCreate",
    "InsuranceCoverageRuleRead",
    "InsuranceCoverageRuleUpdate",
    "InsurancePlanFrequencyGroupCreate",
    "InsurancePlanFrequencyGroupRead",
    "InsurancePlanFrequencyGroupUpdate",
    "InsurancePlanMetadata",
    "PlanCopyRequest",
    "PlanCoverageReplaceRequest",
    "PlanCoverageResponse",
    "PlanCoverageSummary",
    "PlanFieldOption",
    "SectionSummary",
    "EligibilityVerifyRequest",
    "EligibilityVerifyResult",
    "EmployerCreate",
    "EmployerRead",
    "EmployerUpdate",
    "GroupAvailabilityResult",
    "InsuranceCarrierCreate",
    "InsuranceCarrierRead",
    "InsuranceCarrierUpdate",
    "InsurancePlanCreate",
    "InsurancePlanRead",
    "InsurancePlanUpdate",
    "NameAvailabilityResult",
    "NameMatch",
    "PlanMatch",
]
