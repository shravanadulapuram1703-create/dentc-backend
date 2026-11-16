"""Family accounts & guarantor schemas (RP-1 … RP-16)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.datetimes import UtcDatetime
from app.schemas.patient_intake import ResponsiblePartyPersonIn

from app.schemas.guarantor import Guarantor, GuarantorKind, GuarantorSummary  # noqa: E402,F401


class PrimaryGuarantor(BaseModel):
    kind: Literal["patient", "responsible_party", "unresolved"]
    patient_id: Optional[int] = None
    responsible_party_id: Optional[int] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    email: Optional[str] = None
    cell_phone: Optional[str] = None
    legacy_id: Optional[str] = None


class AccountPartyRead(BaseModel):
    id: Optional[int] = None
    account_id: int
    role: str
    kind: str
    patient_id: Optional[int] = None
    responsible_party_id: Optional[int] = None
    name: Optional[str] = None
    responsibility_pct: Optional[Decimal] = None
    receives_statements: bool = False
    sort_order: int = 0
    is_active: bool = True
    created_at: Optional[UtcDatetime] = None
    updated_at: Optional[UtcDatetime] = None


class AccountMember(BaseModel):
    model_config = ConfigDict(extra="allow")

    patient_id: int
    chart_no: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[dt.date] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    is_active: Optional[bool] = None
    relationship: Optional[str] = None
    guarantor_kind: Optional[str] = None
    is_guarantor: bool = False
    balance: float = 0.0
    next_visit: Optional[dt.date] = None
    last_visit: Optional[dt.date] = None
    next_recall: Optional[dt.date] = None
    scheduled_recall: Optional[dt.date] = None
    estimated_patient: float = 0.0
    estimated_insurance: float = 0.0
    aging: dict[str, Any] = Field(default_factory=dict)


class AccountRead(BaseModel):
    id: int
    tenant_id: int
    account_no: Optional[str] = None
    legacy_key: Optional[str] = None
    primary_guarantor_patient_id: Optional[int] = None
    primary_guarantor_party_id: Optional[int] = None
    primary_guarantor: PrimaryGuarantor
    home_office_id: Optional[int] = None
    send_statements: bool = True
    no_email_statement: bool = False
    send_collections: bool = False
    collection_agency_id: Optional[int] = None
    is_finance_charge: bool = False
    statement_message: Optional[str] = None
    financial_notes: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True
    merged_into_account_id: Optional[int] = None
    merged_at: Optional[UtcDatetime] = None
    created_at: Optional[UtcDatetime] = None
    updated_at: Optional[UtcDatetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    parties: list[AccountPartyRead] = Field(default_factory=list)
    member_count: int = 0
    members: Optional[list[AccountMember]] = None
    balance: Optional[float] = None
    # Only on GET /patients/{id}/account.
    patient_id: Optional[int] = None
    guarantor: Optional[Guarantor] = None


class AccountPage(BaseModel):
    items: list[AccountRead]
    total: int
    page: int
    size: int
    pages: int


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_no: Optional[str] = Field(None, max_length=30)
    home_office_id: Optional[int] = None
    send_statements: Optional[bool] = None
    no_email_statement: Optional[bool] = None
    send_collections: Optional[bool] = None
    collection_agency_id: Optional[int] = None
    is_finance_charge: Optional[bool] = None
    statement_message: Optional[str] = None
    financial_notes: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class ChangeGuarantorRequest(BaseModel):
    """RP-6. Precedence ``is_self > guarantor_patient_id > account_id > person >
    responsible_party_id`` (the first one present wins)."""

    model_config = ConfigDict(extra="forbid")

    is_self: bool = False
    guarantor_patient_id: Optional[int] = None
    account_id: Optional[int] = None
    person: Optional[ResponsiblePartyPersonIn] = None
    responsible_party_id: Optional[str] = Field(None, max_length=50)
    relationship: Optional[str] = Field(None, max_length=50)
    move_open_balance: bool = Field(
        True, description="false = leave the open balance with the old account (a "
        "balance-transfer adjustment pair onto a remaining member)")
    include_dependents: bool = Field(
        False, description="also move members whose guarantor is this patient")
    new_account: bool = Field(
        False, description="with is_self: always open a new account, even if the patient "
        "already heads their current one")
    effective_date: Optional[dt.date] = None


class AccountSummaryShort(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    account_no: Optional[str] = None
    is_active: bool = True
    member_count: int = 0


class ChangeGuarantorResponse(BaseModel):
    patient_id: int
    event_id: Optional[int] = None
    old_account_id: Optional[int] = None
    new_account_id: Optional[int] = None
    old_guarantor: Guarantor
    guarantor: Guarantor
    moved_patient_ids: list[int]
    moved_balance: float
    balance_left_with_old_account: bool
    transfer_payment_ids: list[str]
    old_account_retired: bool
    old_account: Optional[AccountSummaryShort] = None
    new_account: AccountSummaryShort


class MergeAccountsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_account_id: int


class MergeAccountsResponse(BaseModel):
    account: AccountRead
    merged_account_id: int
    moved_patient_ids: list[int]
    parties_added: int


class AccountPartyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: Optional[int] = None
    responsible_party_id: Optional[int] = None
    person: Optional[ResponsiblePartyPersonIn] = None
    role: str = "secondary"
    responsibility_pct: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    receives_statements: bool = False
    sort_order: Optional[int] = None


class AccountPartyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Optional[str] = None
    responsibility_pct: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    receives_statements: Optional[bool] = None
    sort_order: Optional[int] = None


class AccountPaymentAllocation(BaseModel):
    patient_id: int
    amount: Decimal = Field(..., max_digits=12, decimal_places=2)


class AccountPaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(..., max_digits=12, decimal_places=2)
    tender: Optional[str] = Field(None, max_length=50, description="payment_method code")
    payment_type: Optional[str] = Field("patient", max_length=20)
    distribute: Literal["oldest_first", "by_member"] = "oldest_first"
    allocations: Optional[list[AccountPaymentAllocation]] = None
    payment_date: Optional[dt.date] = None
    check_number: Optional[str] = Field(None, max_length=100)
    bank_number: Optional[str] = Field(None, max_length=100)
    office_id: Optional[int] = None
    provider_id: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class AccountPaymentLine(BaseModel):
    id: str
    patient_id: int
    amount: float


class AccountPaymentResponse(BaseModel):
    account_id: int
    account_payment_id: str
    amount: float
    distribute: str
    payment_date: dt.date
    payments: list[AccountPaymentLine]


class AccountStatementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    office_id: Optional[int] = None
    statement_date: Optional[dt.date] = None
    date_from: Optional[dt.date] = None
    date_to: Optional[dt.date] = None
    message: Optional[str] = Field(None, max_length=500)


class AccountInsuranceMember(BaseModel):
    patient_id: int
    patient_name: Optional[str] = None
    insurance_type: Optional[str] = None
    relationship: Optional[str] = None
    is_active: Optional[bool] = None


class AccountInsurancePlan(BaseModel):
    ins_plan_id: Optional[int] = None
    subscriber_id: Optional[int] = None
    carrier_id: Optional[int] = None
    carrier_name: Optional[str] = None
    group_number: Optional[str] = None
    plan_type: Optional[str] = None
    legacy_plan_type: Optional[str] = None
    subscriber_name: Optional[str] = None
    subscriber_patient_id: Optional[int] = None
    subscriber_is_account_member: bool = False
    members: list[AccountInsuranceMember]


class AccountChangeEventRead(BaseModel):
    id: int
    patient_id: Optional[int] = None
    action: str
    old_account_id: Optional[int] = None
    new_account_id: Optional[int] = None
    old_guarantor: Optional[dict] = None
    new_guarantor: Optional[dict] = None
    move_open_balance: Optional[bool] = None
    moved_balance: Optional[float] = None
    effective_date: Optional[dt.date] = None
    details: Optional[dict] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    at: Optional[UtcDatetime] = None


class AccountRules(BaseModel):
    model_config = ConfigDict(extra="allow")

    guarantor_kinds: list[str]
    spec_precedence: list[str]
    relationships: list[dict]
    relationship_definition_group: str
    self_relationship: str
    max_account_parties: int
    additional_party_roles: list[str]
    distribute_modes: list[str]
    responsible_party_id_alias: str
