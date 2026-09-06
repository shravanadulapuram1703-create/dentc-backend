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
from typing import Optional

from pydantic import BaseModel, Field, computed_field, create_model

from app.db.models import (
    Employer,
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    InsurancePlanFrequencyGroup,
)
from app.schemas.factory import build_schemas
from app.services.insurance_service import carrier_is_dental

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
_PlanCreate, _PlanUpdate, _PlanReadBase = build_schemas(InsurancePlan, "InsurancePlanBase")


class InsurancePlanCreate(_PlanCreate):  # type: ignore[valid-type, misc]
    """INS-PT-19: an active plan on the same carrier + group number is a 409.

    ``allow_duplicate_group`` is the API half of the dialog's "override" button —
    two offices can legitimately hold separate plans on one group, so the server
    refuses the *accidental* duplicate rather than the duplicate.
    """

    allow_duplicate_group: bool = False


class InsurancePlanUpdate(_PlanUpdate):  # type: ignore[valid-type, misc]
    allow_duplicate_group: bool = False


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
)


# ── INS-PT-5: eligibility "Update Status" stamp ──────────────────────────────
class EligibilityVerifyRequest(BaseModel):
    elig_status: str | None = None  # defaults to "verified" server-side
    notes: str | None = None


class EligibilityVerifyResult(BaseModel):
    subscriber_id: int
    elig_status: str | None = None
    elig_verified_on: datetime | None = None
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
    the plan's rows of that kind (see the endpoint docstring)."""

    rules: list[CoverageRuleItem] | None = None
    frequency_groups: list[FrequencyGroupItem] | None = None


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
    catalog_sources: dict[str, str]
    conventions: dict[str, str]


__all__ = [
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
