"""
Pydantic schemas for Patient Ledger API (contract-driven).
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import List, Optional, Literal, Any, Dict

from pydantic import BaseModel, Field, conint, condecimal


# ==================================================
# Common
# ==================================================

class Pagination(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool


# ==================================================
# Ledger
# ==================================================

class LedgerEntry(BaseModel):
    id: str
    transaction_id: str
    posted_date: date
    patient_id: str
    patient_name: str
    office_id: str
    office_name: str
    apply_to: str
    code: str
    tooth: str = ""
    surface: str = ""
    type: str
    has_notes: bool
    has_eob: bool
    has_attachments: bool
    description: str
    billing_order: str = ""
    duration_minutes: Optional[int] = None
    provider_id: str = ""
    provider_name: str = ""
    est_patient: float
    est_insurance: float
    posted_amount: float
    running_balance: float
    created_by: str
    created_at: datetime
    transaction_type: str
    status: str
    procedure_id: Optional[str] = None
    claim_id: Optional[str] = None
    payment_id: Optional[str] = None
    adjustment_id: Optional[str] = None


class LedgerEntriesResponse(BaseModel):
    ledger_entries: List[LedgerEntry]
    pagination: Pagination


# ==================================================
# Balances
# ==================================================

class Aging(BaseModel):
    current: float
    age_30: float
    age_60: float
    age_90: float
    age_120: float


class LastPayment(BaseModel):
    amount: float
    date: date


class RecentActivity(BaseModel):
    today_charges: float
    last_insurance_payment: Optional[LastPayment] = None
    last_patient_payment: Optional[LastPayment] = None


class BalancesResponse(BaseModel):
    account_balance: float
    patient_balance: float
    insurance_balance: float
    estimated_insurance: float
    estimated_patient: float
    aging: Aging
    recent_activity: RecentActivity


# ==================================================
# Procedures
# ==================================================

class ProcedureCreateRequest(BaseModel):
    procedure_code: str
    date_of_service: date
    provider_id: str
    office_id: str
    tooth: Optional[str] = None
    surface: Optional[str] = None
    quadrant: Optional[str] = None
    materials: Optional[List[str]] = None
    duration_minutes: Optional[int] = None
    fee: float
    est_patient: float
    est_insurance: float
    billing_order: Optional[str] = None
    notes: Optional[str] = None
    apply_to: Optional[str] = "P"


class ProcedureCreateResponse(BaseModel):
    procedure_id: str
    ledger_entry_id: str
    transaction_id: str
    posted_date: date
    running_balance: float
    status: str
    created_at: datetime


class ProcedureDetailsResponse(BaseModel):
    procedure_id: str
    procedure_code: str
    date_of_service: date
    provider_id: str
    provider_name: str
    office_id: str
    office_name: str
    tooth: Optional[str] = None
    surface: Optional[str] = None
    quadrant: Optional[str] = None
    materials: Optional[List[str]] = None
    duration_minutes: Optional[int] = None
    fee: float
    est_patient: float
    est_insurance: float
    billing_order: str = ""
    notes: Optional[str] = None
    status: str
    claim_id: Optional[str] = None
    ledger_entry_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class ProcedureUpdateRequest(BaseModel):
    procedure_code: Optional[str] = None
    date_of_service: Optional[date] = None
    provider_id: Optional[str] = None
    office_id: Optional[str] = None
    tooth: Optional[str] = None
    surface: Optional[str] = None
    quadrant: Optional[str] = None
    materials: Optional[List[str]] = None
    duration_minutes: Optional[int] = None
    fee: Optional[float] = None
    est_patient: Optional[float] = None
    est_insurance: Optional[float] = None
    billing_order: Optional[str] = None
    notes: Optional[str] = None
    apply_to: Optional[str] = None


# ==================================================
# Claims
# ==================================================

class ClaimCreateRequest(BaseModel):
    procedure_ids: List[str]
    claim_type: str
    billing_order: str
    date_of_service_from: Optional[date] = None
    date_of_service_to: Optional[date] = None
    notes: Optional[str] = None


class ClaimProcedureSummary(BaseModel):
    procedure_id: str
    procedure_code: str
    date_of_service: date
    fee: float
    est_insurance: float


class ClaimCreateResponse(BaseModel):
    claim_id: str
    claim_number: str
    status: str
    claim_type: str
    billing_order: str
    date_of_service_from: date
    date_of_service_to: date
    total_submitted_fees: float
    total_fee: float
    total_est_insurance: float
    procedures: List[ClaimProcedureSummary]
    created_by: str
    created_at: datetime


class ClaimPatientInfo(BaseModel):
    patient_id: str
    patient_name: str
    patient_dob: Optional[date] = None
    subscriber_name: str
    subscriber_id: str
    subscriber_dob: Optional[date] = None
    responsible_party_name: str
    responsible_party_id: str
    responsible_party_dob: Optional[date] = None


class ClaimCoverageInfo(BaseModel):
    insurance_carrier: str
    carrier_phone: Optional[str] = None
    group_plan: Optional[str] = None
    benefits_used: Optional[str] = None
    employer_name: Optional[str] = None
    deductibles_used: Optional[str] = None


class ClaimProviderInfo(BaseModel):
    provider_id: str
    provider_name: str


class ClaimAmounts(BaseModel):
    total_submitted_fees: float
    total_fee: float
    total_est_insurance: float
    total_insurance_paid: float
    variance: float


class ClaimPaymentInfo(BaseModel):
    check_number: Optional[str] = None
    bank_number: Optional[str] = None
    eob_number: Optional[str] = None


class ClaimProcedureLine(BaseModel):
    procedure_id: str
    dos: date
    code: str
    tooth: Optional[str] = None
    surface: Optional[str] = None
    description: str
    bref: str
    submitted: float
    fee: float
    est_ins: float
    ins_paid: float
    ins_overpayment: float
    ins_allocated: float
    overpayment_disbursement: float
    write_off_1: float
    write_off_2: float
    write_off_3: float
    other_insurance: float
    reason_code: Optional[str] = None


class ClaimAttachment(BaseModel):
    attachment_id: str
    attachment_type: str
    required: bool
    provided: bool
    file_name: Optional[str] = None
    uploaded_at: Optional[datetime] = None


class ClaimDetailsResponse(BaseModel):
    claim_id: str
    claim_number: str
    status: str
    claim_type: str
    billing_order: str
    date_of_service_from: date
    date_of_service_to: date
    created_date: date
    created_time: str
    created_by: str
    last_status_update_date: Optional[date] = None
    claim_sent_date: Optional[date] = None
    claim_sent_status: Optional[str] = None
    claim_close_date: Optional[date] = None
    claim_closed_by: Optional[str] = None
    dxc_attachment_id: Optional[str] = None
    icd10_codes: Optional[str] = None
    patient_info: ClaimPatientInfo
    coverage_info: ClaimCoverageInfo
    billing_dentist: ClaimProviderInfo
    treating_dentist: ClaimProviderInfo
    amounts: ClaimAmounts
    payment_info: ClaimPaymentInfo
    notes: Optional[str] = None
    attachment_required: bool
    procedures: List[ClaimProcedureLine]
    attachments: List[ClaimAttachment]


class ClaimUpdateRequest(BaseModel):
    notes: Optional[str] = None
    icd10_codes: Optional[str] = None
    payment_info: Optional[ClaimPaymentInfo] = None


class ClaimSendRequest(BaseModel):
    batch_id: Optional[str] = None
    send_method: str


class ClaimSendResponse(BaseModel):
    claim_id: str
    batch_id: str
    status: str
    sent_date: date
    sent_time: str
    sent_by: str
    send_method: str


class ClaimsListItem(BaseModel):
    claim_id: str
    claim_number: str
    status: str
    claim_type: str
    date_of_service_from: date
    date_of_service_to: date
    total_fee: float
    total_est_insurance: float
    created_date: date
    created_by: str


class ClaimsListResponse(BaseModel):
    claims: List[ClaimsListItem]
    pagination: Pagination


# ==================================================
# Payments
# ==================================================

class PaymentCreateRequest(BaseModel):
    payment_date: date
    payment_amount: float
    payment_type: str
    payment_method: str
    apply_to: str
    provider_id: Optional[str] = None
    procedure_ids: Optional[List[str]] = None
    check_number: Optional[str] = None
    bank_number: Optional[str] = None
    notes: Optional[str] = None


class PaymentCreateResponse(BaseModel):
    payment_id: str
    ledger_entry_id: str
    transaction_id: str
    posted_date: date
    running_balance: float
    status: str
    created_at: datetime


class PaymentDetailsResponse(BaseModel):
    payment_id: str
    payment_date: date
    payment_amount: float
    payment_type: str
    payment_method: str
    apply_to: str
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    procedure_ids: List[str] = Field(default_factory=list)
    check_number: Optional[str] = None
    bank_number: Optional[str] = None
    notes: Optional[str] = None
    ledger_entry_id: str
    created_by: str
    created_at: datetime


# ==================================================
# Adjustments
# ==================================================

class AdjustmentCreateRequest(BaseModel):
    adjustment_date: date
    adjustment_amount: float
    adjustment_code: str
    adjustment_reason: str
    apply_to: str
    procedure_ids: Optional[List[str]] = None
    notes: Optional[str] = None


class AdjustmentCreateResponse(BaseModel):
    adjustment_id: str
    ledger_entry_id: str
    transaction_id: str
    posted_date: date
    running_balance: float
    status: str
    created_at: datetime


class AdjustmentDetailsResponse(BaseModel):
    adjustment_id: str
    adjustment_date: date
    adjustment_amount: float
    adjustment_code: str
    adjustment_reason: str
    apply_to: str
    procedure_ids: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    ledger_entry_id: str
    created_by: str
    created_at: datetime


# ==================================================
# Metadata
# ==================================================

class ProcedureCodeRequirement(BaseModel):
    tooth: bool
    surface: bool
    quadrant: bool
    materials: bool


class ProcedureCodeMeta(BaseModel):
    code: str
    user_code: Optional[str] = None
    description: str
    category: str
    default_fee: Optional[int] = None
    default_duration: Optional[int] = None
    requirements: ProcedureCodeRequirement
    is_active: bool


class ProcedureCodesMetaResponse(BaseModel):
    procedure_codes: List[ProcedureCodeMeta]
    categories: List[str]


class PaymentCodeMeta(BaseModel):
    code: str
    description: str
    type: str
    is_active: bool


class PaymentCodesResponse(BaseModel):
    payment_codes: List[PaymentCodeMeta]


class AdjustmentCodeMeta(BaseModel):
    code: str
    description: str
    is_active: bool


class AdjustmentCodesResponse(BaseModel):
    adjustment_codes: List[AdjustmentCodeMeta]


class ClaimStatusMeta(BaseModel):
    code: str
    display_name: str
    description: Optional[str] = None


class ClaimStatusesResponse(BaseModel):
    claim_statuses: List[ClaimStatusMeta]


class TransactionTypeMeta(BaseModel):
    code: str
    display_name: str
    description: Optional[str] = None


class TransactionTypesResponse(BaseModel):
    transaction_types: List[TransactionTypeMeta]


class OfficeProviderMeta(BaseModel):
    provider_id: str
    provider_name: str
    npi: Optional[str] = None
    is_active: bool


class OfficeProvidersResponse(BaseModel):
    providers: List[OfficeProviderMeta]

