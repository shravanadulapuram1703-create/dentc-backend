"""Schemas for the Add-Patient intake extras: opening balances (GAP-AP-12) and
the composite register transaction (GAP-AP-13/15/18)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.patient import PatientCreate


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
    """LEG-10: a full non-self guarantor to create inline during registration."""

    title: str | None = None
    preferred_name: str | None = None
    last_name: str | None = None
    first_name: str | None = None
    middle_initial: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    email: str | None = None
    dob: date | None = None
    marital_status: str | None = None
    sex: str | None = None
    ssn: str | None = None
    driver_license: str | None = None
    home_phone: str | None = None
    cell_phone: str | None = None
    work_phone: str | None = None
    employer: str | None = None
    resp_party_type: str | None = None
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

    relationship: str | None = None  # self|spouse|parent|guardian|child|other
    is_self: bool = False
    responsible_party_id: str | None = None
    person: ResponsiblePartyPersonIn | None = None


class MedicalAlertIn(BaseModel):
    alert_code: str
    alert_label: str | None = None
    response: str | None = None  # yes|no
    comments: str | None = None


class QuestionnaireResponseIn(BaseModel):
    questionnaire_type: str  # dental|medical
    question_code: str
    question_text: str | None = None
    answer: str | None = None


class RecallIn(BaseModel):
    recall_type: str | None = None
    procedure_code: str | None = None
    due_date: date | None = None
    interval_months: int | None = None
    office_id: int | None = None
    notes: str | None = None


class RegisterRequest(BaseModel):
    """One atomic registration: the patient plus any of the wizard's later steps.
    Every sub-section is optional so the same endpoint serves Quick-Save and the
    full wizard Finish."""

    patient: PatientCreate
    responsible_party: ResponsiblePartyIn | None = None
    medical_alerts: list[MedicalAlertIn] = Field(default_factory=list)
    questionnaire_responses: list[QuestionnaireResponseIn] = Field(default_factory=list)
    recalls: list[RecallIn] = Field(default_factory=list)
    opening_balance: OpeningBalanceIn | None = None
    # KAN-108: registration refuses with 409 when an existing patient is almost
    # certainly the same person. Set once the user has reviewed the returned
    # matches and confirmed this really is a new patient.
    force_create: bool = Field(
        False,
        description="Create even if a strong duplicate match exists (user confirmed).",
    )


class RegisterResponse(BaseModel):
    patient_id: int
    chart_no: str | None = None
    responsible_party_id: str | None = None
    medical_alert_ids: list[int] = Field(default_factory=list)
    questionnaire_response_ids: list[int] = Field(default_factory=list)
    recall_ids: list[int] = Field(default_factory=list)
    opening_balance_seeded: bool = False


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
