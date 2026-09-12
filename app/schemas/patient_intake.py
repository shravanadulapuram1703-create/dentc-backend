"""Schemas for the Add-Patient intake extras: opening balances (GAP-AP-12) and
the composite register transaction (GAP-AP-13/15/18)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, create_model, field_validator, model_validator

from app.db.models import InsuranceSubscriber, PatientInsurance
from app.schemas.common import ORMModel
from app.schemas.factory import build_schemas
from app.schemas.patient import PatientCreate
from app.schemas.patient_catalog import (
    ALERT_LABEL_MAX_LENGTH,
    CATALOG_CODE_MAX_LENGTH,
    QUESTIONNAIRE_TYPE_MAX_LENGTH,
    SECTION_MAX_LENGTH,
)


# ── Opening balance (GAP-AP-12) ───────────────────────────────────────────────
class OpeningBalanceIn(BaseModel):
    as_of_date: date | None = None
    current: float = 0.0
    over_30: float = 0.0
    over_60: float = 0.0
    over_90: float = 0.0
    over_120: float = 0.0
    notes: str | None = None


class OpeningBalanceRead(ORMModel):
    patient_id: int
    as_of_date: date | None = None
    current: float = 0.0
    over_30: float = 0.0
    over_60: float = 0.0
    over_90: float = 0.0
    over_120: float = 0.0
    total: float = 0.0
    notes: str | None = None


# ── Composite register (GAP-AP-13/15/18) ──────────────────────────────────────
class ResponsiblePartyPersonIn(BaseModel):
    """LEG-10: a full non-self guarantor to create inline during registration.

    GAP-AP-19/20/26: every bounded string carries the column's ``max_length``
    so an over-long value is a 422 naming the field, not a 500 that rolls the
    whole registration back."""

    title: str | None = Field(None, max_length=20)
    preferred_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    first_name: str | None = Field(None, max_length=100)
    middle_initial: str | None = Field(None, max_length=10)
    middle_name: str | None = Field(None, max_length=50)  # GAP-AP-19
    address_line1: str | None = Field(None, max_length=255)
    address_line2: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=50)
    zip: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=255)
    dob: date | None = None
    marital_status: str | None = Field(None, max_length=20)
    sex: str | None = Field(None, max_length=20)
    ssn: str | None = Field(None, max_length=20)
    driver_license: str | None = Field(None, max_length=50)
    home_phone: str | None = Field(None, max_length=20)
    cell_phone: str | None = Field(None, max_length=20)
    work_phone: str | None = Field(None, max_length=20)
    employer: str | None = Field(None, max_length=255)
    resp_party_type: str | None = Field(None, max_length=20)
    collection_agency_id: int | None = None
    send_statements: bool | None = None
    no_email_statement: bool | None = None
    send_collections: bool | None = None
    is_finance_charge: bool | None = None
    statement_message: str | None = None
    statement_message_print_count: int | None = None
    financial_notes: str | None = None
    responsible_party_notes: str | None = None


class ResponsiblePartyIn(BaseModel):
    """Relationship of the patient to their responsible party (GAP-AP-7/15).
    ``is_self`` self-links the patient as their own guarantor; ``responsible_party_id``
    links an already-existing party; ``person`` creates a new guarantor inline
    (LEG-10) and links it — the three are mutually exclusive, resolved in that order
    of precedence (is_self > person > responsible_party_id)."""

    # GAP-AP-25: the resp_party_rel *code* (S/SP/P/G/C/D/O); a lowercase key or
    # a label is accepted and folded to the code.
    relationship: str | None = Field(None, max_length=50)
    is_self: bool = False
    responsible_party_id: str | None = Field(None, max_length=50)
    person: ResponsiblePartyPersonIn | None = None


_ALERT_RESPONSES = ("yes", "no", "unknown")


class MedicalAlertIn(BaseModel):
    """One alert answer on the composite. Same vocabulary as the generic
    resource (``yes|no|unknown``, MH-5) — case-folded rather than a strict
    ``Literal`` so a ``"Yes"`` from a form does not 422 the whole registration."""

    alert_code: str = Field(..., max_length=CATALOG_CODE_MAX_LENGTH)
    alert_label: str | None = Field(None, max_length=ALERT_LABEL_MAX_LENGTH)
    section: str | None = Field(None, max_length=SECTION_MAX_LENGTH)
    response: str | None = None  # yes|no|unknown
    comments: str | None = None
    is_flash_alert: bool | None = None
    blocks_charges: bool | None = None

    @field_validator("response", mode="before")
    @classmethod
    def _fold_response(cls, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip().lower()
        if not text:
            return None
        if text not in _ALERT_RESPONSES:
            raise ValueError(f"response must be one of {', '.join(_ALERT_RESPONSES)}")
        return text


class QuestionnaireResponseIn(BaseModel):
    questionnaire_type: str = Field(..., max_length=QUESTIONNAIRE_TYPE_MAX_LENGTH)  # dental|medical
    question_code: str = Field(..., max_length=CATALOG_CODE_MAX_LENGTH)
    question_text: str | None = None
    answer: str | None = None

    @field_validator("questionnaire_type", mode="before")
    @classmethod
    def _fold_type(cls, value: Any) -> Any:
        text = str(value or "").strip().lower()
        if text not in ("dental", "medical"):
            raise ValueError("questionnaire_type must be 'dental' or 'medical'")
        return text


class RecallIn(BaseModel):
    recall_type: str | None = Field(None, max_length=50)
    procedure_code: str | None = Field(None, max_length=20)
    due_date: date | None = None
    interval_months: int | None = None
    # GAP-AP-23 / LEG-17: the three LEG-8 columns, so a recall can ride the
    # atomic register instead of a follow-up POST that can fail on its own.
    interval_unit: str | None = Field(None, max_length=10)  # month|year
    scheduled_date: date | None = None
    scheduled_time: str | None = Field(None, max_length=10)  # HH:MM (24h)
    office_id: int | None = None
    notes: str | None = None


# ── Insurance on the composite (GAP-AP-24) ────────────────────────────────────
# The two halves of one coverage slot, derived from the same columns the
# stand-alone resources accept (so a field added to the model reaches both),
# minus the ids the transaction supplies itself.
_subscriber_base = build_schemas(
    InsuranceSubscriber, "RegisterSubscriberBase",
    create_exclude=("subscriber_patient_id",),
)[0]
RegisterSubscriberIn = create_model("RegisterSubscriberIn", __base__=_subscriber_base)
RegisterSubscriberIn.__doc__ = (
    "InsuranceSubscriberCreate minus ``subscriber_patient_id`` (set from "
    "``subscriber_is_patient``). ``ins_plan_id`` is required."
)

_link_base = build_schemas(
    PatientInsurance, "RegisterInsuranceLinkBase",
    create_exclude=("patient_id", "subscriber_id"),
)[0]
RegisterInsuranceLinkIn = create_model("RegisterInsuranceLinkIn", __base__=_link_base)
RegisterInsuranceLinkIn.__doc__ = (
    "PatientInsuranceCreate minus ``patient_id`` / ``subscriber_id`` (both supplied "
    "by the transaction). ``ins_plan_id`` defaults to the subscriber's plan."
)


class InsuranceIn(BaseModel):
    """One coverage slot: a subscriber (new, or an existing id — e.g. a dependent
    on the guarantor's plan from *Account Plans*) plus the ``patient_insurance``
    link. Exactly one of ``subscriber`` / ``subscriber_id``."""

    subscriber: RegisterSubscriberIn | None = None  # type: ignore[valid-type]
    subscriber_id: int | None = None
    #: The subscriber *is* the patient being registered (a self-subscriber):
    #: ``subscriber_patient_id`` is set to the new patient's id.
    subscriber_is_patient: bool = False
    link: RegisterInsuranceLinkIn  # type: ignore[valid-type]

    @model_validator(mode="after")
    def _one_subscriber(self) -> "InsuranceIn":
        if (self.subscriber is None) == (self.subscriber_id is None):
            raise ValueError("provide exactly one of 'subscriber' or 'subscriber_id'")
        if self.subscriber_id is not None and self.subscriber_is_patient:
            raise ValueError("subscriber_is_patient applies to an inline 'subscriber' only")
        return self


class RegisterRequest(BaseModel):
    """One atomic registration: the patient plus any of the wizard's later steps.
    Every sub-section is optional so the same endpoint serves Quick-Save and the
    full wizard Finish."""

    patient: PatientCreate
    responsible_party: ResponsiblePartyIn | None = None
    medical_alerts: list[MedicalAlertIn] = Field(default_factory=list)
    questionnaire_responses: list[QuestionnaireResponseIn] = Field(default_factory=list)
    recalls: list[RecallIn] = Field(default_factory=list)
    # GAP-AP-24: coverage slots created inside the same transaction.
    insurance: list[InsuranceIn] = Field(default_factory=list)
    opening_balance: OpeningBalanceIn | None = None
    # KAN-108: registration refuses with 409 when an existing patient is almost
    # certainly the same person. Set once the user has reviewed the returned
    # matches and confirmed this really is a new patient.
    force_create: bool = Field(
        False,
        description="Create even if a strong duplicate match exists (user confirmed).",
    )
    #: MH-12: the alert answers are judged by the same contradiction rules as
    #: the generic resource; set to store a contradiction deliberately.
    allow_contradictions: bool = False


class RegisteredInsuranceRead(BaseModel):
    subscriber_id: int
    patient_insurance_id: int
    ins_plan_id: int | None = None
    legacy_plan_type: str | None = None
    insurance_type: str | None = None


class RegisterResponse(BaseModel):
    patient_id: int
    chart_no: str | None = None
    responsible_party_id: str | None = None
    medical_alert_ids: list[int] = Field(default_factory=list)
    questionnaire_response_ids: list[int] = Field(default_factory=list)
    recall_ids: list[int] = Field(default_factory=list)
    insurance: list[RegisteredInsuranceRead] = Field(default_factory=list)
    opening_balance_seeded: bool = False
    #: MH-12 contradictions stored because ``allow_contradictions`` was set.
    contradictions: list[dict] = Field(default_factory=list)


# ── Add/Edit Patient checkbox rules ──────────────────────────────────────────
class PatientTypeExclusion(BaseModel):
    codes: list[str]
    labels: list[str]
    reason: str


class PatientStatusImplication(BaseModel):
    when: dict[str, bool]
    then: dict[str, bool]
    reason: str


class PatientTypeRules(BaseModel):
    field: str = "patient_types"
    exclusions: list[PatientTypeExclusion] = Field(default_factory=list)


class PatientStatusRules(BaseModel):
    implications: list[PatientStatusImplication] = Field(default_factory=list)


class CoverageSlotRef(BaseModel):
    legacy_plan_type: str
    insurance_type: str


class CoverageTypeRules(BaseModel):
    no_coverage_is_derived: bool = True
    no_coverage_excludes: list[CoverageSlotRef] = Field(default_factory=list)
    ranks: list[str] = Field(default_factory=list)
    requires_lower_rank: bool = True


class RespPartyRelCode(BaseModel):
    code: str
    label: str


class RespPartyRelRules(BaseModel):
    """GAP-AP-25: which ``resp_party_rel`` value the patient column holds."""

    field: str = "responsible_party_relationship"
    canonical: str = "key1"
    definition_group: str = "resp_party_rel"
    self_code: str = "S"
    codes: list[RespPartyRelCode] = Field(default_factory=list)


class PatientFlagRules(BaseModel):
    """The Add/Edit Patient checkbox-integrity rules, served as data so the form
    drives its own tick/untick behaviour from the same table the API enforces."""

    patient_type: PatientTypeRules
    patient_status: PatientStatusRules
    coverage_type: CoverageTypeRules
    responsible_party_relationship: RespPartyRelRules | None = None


# ── Account plans (LEG-5) ─────────────────────────────────────────────────────
class AccountPlanRead(ORMModel):
    """A plan already attached to a patient's account — the legacy *Account Plans*
    search scope, so a dependent can reuse the guarantor's existing plan."""

    id: int
    carrier_id: int
    carrier_name: str | None = None
    employer_id: int | None = None
    group_number: str | None = None
    plan_type: str | None = None
    coverage_type: str | None = None
    individual_max: float | None = None
    individual_deductible: float | None = None


# ── Responsible-party roster (LEG-14 / PO-3) ──────────────────────────────────
class RosterPatientRead(BaseModel):
    patient_id: int
    chart_no: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    age: int | None = None
    sex: str | None = None
    is_active: bool = True
    balance: float = 0.0
    recall_date: date | None = None  # back-compat alias of scheduled_recall
    # PO-3: the columns the legacy ACCOUNT MEMBERS + BALANCES grids need, so the FE
    # stops fanning out 3 extra requests per member.
    next_visit: date | None = None
    last_visit: date | None = None
    scheduled_recall: date | None = None
    estimated_patient: float = 0.0
    estimated_insurance: float = 0.0
    aging: dict[str, float] = Field(default_factory=dict)
