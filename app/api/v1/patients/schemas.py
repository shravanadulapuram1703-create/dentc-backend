"""
Comprehensive Pydantic schemas for Patient Management API.
All schemas match the API contracts provided.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, EmailStr, validator
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal


# ==================================================
# PATIENT SEARCH API SCHEMAS
# ==================================================

class PatientSearchResponse(BaseModel):
    """Response schema for patient search - matches frontend expectations"""
    id: int
    patientId: Optional[str] = Field(None, alias="patient_id")
    name: str = Field(..., alias="name")
    firstName: str = Field(..., alias="firstName")
    lastName: str = Field(..., alias="lastName")
    dob: Optional[str] = Field(None, alias="dob")
    phone: str = Field("", alias="phone")
    email: str = Field("", alias="email")
    address: str = Field("", alias="address")
    city: str = Field("", alias="city")
    state: str = Field("", alias="state")
    zip: str = Field("", alias="zip")
    insurance: str = Field("", alias="insurance")
    lastVisit: str = Field("", alias="lastVisit")
    nextAppointment: str = Field("", alias="nextAppointment")
    balance: str = Field("", alias="balance")
    officeId: str = Field("", alias="officeId")
    officeName: str = Field("", alias="officeName")
    chartNumber: Optional[str] = Field(None, alias="chartNumber")
    ssn: str = Field("***-**-****", alias="ssn")
    emergencyContact: str = Field("", alias="emergencyContact")
    emergencyPhone: str = Field("", alias="emergencyPhone")

    class Config:
        populate_by_name = True
        from_attributes = True


class PatientSearchListResponse(BaseModel):
    """Response for patient search endpoint"""
    patients: List[PatientSearchResponse]
    total: int
    limit: int
    offset: int


# ==================================================
# PATIENT DETAILS API SCHEMAS
# ==================================================

class AddressSchema(BaseModel):
    """Address information"""
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = "USA"

    class Config:
        from_attributes = True


class ContactSchema(BaseModel):
    """Contact information"""
    home_phone: Optional[str] = None
    cell_phone: Optional[str] = None
    work_phone: Optional[str] = None
    email: Optional[str] = None
    preferred_contact: Optional[str] = None

    class Config:
        from_attributes = True


class OfficeSchema(BaseModel):
    """Office information"""
    home_office_id: Optional[int] = None
    home_office_name: Optional[str] = None
    home_office_code: Optional[str] = None

    class Config:
        from_attributes = True


class ProviderSchema(BaseModel):
    """Provider information"""
    preferred_provider_id: Optional[str] = None
    preferred_provider_name: Optional[str] = None
    preferred_hygienist_id: Optional[str] = None
    preferred_hygienist_name: Optional[str] = None

    class Config:
        from_attributes = True


class FeeScheduleSchema(BaseModel):
    """Fee schedule information"""
    fee_schedule_id: Optional[str] = None
    fee_schedule_name: Optional[str] = None

    class Config:
        from_attributes = True


class PatientFlagsSchema(BaseModel):
    """Patient flags"""
    is_active: bool = True
    is_ortho: bool = False
    is_child: bool = False
    is_collection_problem: bool = False
    is_employee_family: bool = False
    is_short_notice: bool = False
    is_senior: bool = False
    is_spanish_speaking: bool = False
    assign_benefits: bool = True
    hipaa_agreement: bool = False
    no_correspondence: bool = False
    no_auto_email: bool = False
    no_auto_sms: bool = False
    add_to_quickfill: bool = False

    class Config:
        from_attributes = True


class ResponsiblePartySchema(BaseModel):
    """Responsible party information"""
    id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    _relationship: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    home_office: Optional[str] = None

    class Config:
        from_attributes = True


class InsuranceInfoSchema(BaseModel):
    """Insurance information"""
    carrier_name: Optional[str] = None
    plan_name: Optional[str] = None
    group_number: Optional[str] = None
    subscriber_id: Optional[str] = None
    subscriber_name: Optional[str] = None
    _relationship: Optional[str] = None
    carrier_phone: Optional[str] = None
    individual_max_remaining: Optional[Decimal] = None
    individual_deductible_remaining: Optional[Decimal] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class InsuranceSchema(BaseModel):
    """Insurance container"""
    primary_dental: Optional[InsuranceInfoSchema] = None
    secondary_dental: Optional[InsuranceInfoSchema] = None
    primary_medical: Optional[InsuranceInfoSchema] = None
    secondary_medical: Optional[InsuranceInfoSchema] = None


class AccountMemberSchema(BaseModel):
    """Account member information"""
    id: int
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    next_visit: Optional[date] = None
    recall: Optional[str] = None
    last_visit: Optional[date] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class AppointmentSchema(BaseModel):
    """Appointment information"""
    id: str
    date: date
    time: str
    office: str
    operatory: str
    procedure: str
    provider: str
    duration: int
    status: str
    last_updated: date
    member: str

    class Config:
        from_attributes = True


class RecallSchema(BaseModel):
    """Recall information"""
    code: str
    age_range: str
    next_date: date
    frequency: str

    class Config:
        from_attributes = True


class AgingSchema(BaseModel):
    """Aging balance information"""
    current: Decimal = Decimal("0.00")
    over_30: Decimal = Decimal("0.00")
    over_60: Decimal = Decimal("0.00")
    over_90: Decimal = Decimal("0.00")
    over_120: Decimal = Decimal("0.00")

    class Config:
        from_attributes = True


class BalancesSchema(BaseModel):
    """Balance information"""
    account_balance: Decimal = Decimal("0.00")
    today_charges: Decimal = Decimal("0.00")
    today_est_insurance: Decimal = Decimal("0.00")
    today_est_patient: Decimal = Decimal("0.00")
    last_insurance_payment: Optional[Decimal] = None
    last_insurance_payment_date: Optional[date] = None
    last_patient_payment: Optional[Decimal] = None
    last_patient_payment_date: Optional[date] = None
    aging: AgingSchema = Field(default_factory=AgingSchema)

    class Config:
        from_attributes = True


class MedicalAlertSchema(BaseModel):
    """Medical alert information"""
    alert: str
    date: datetime
    entered_by: str

    class Config:
        from_attributes = True


class ClinicalSchema(BaseModel):
    """Clinical information"""
    first_visit: Optional[date] = None
    last_visit: Optional[date] = None
    next_visit: Optional[date] = None
    next_recall: Optional[date] = None
    last_pano_chart: Optional[date] = None
    medical_alerts: List[MedicalAlertSchema] = Field(default_factory=list)

    class Config:
        from_attributes = True


class NotesSchema(BaseModel):
    """Notes information"""
    patient_notes: Optional[str] = None
    hipaa_sharing: Optional[str] = None

    class Config:
        from_attributes = True


class ReferralSchema(BaseModel):
    """Referral information"""
    referral_type: Optional[str] = None
    referred_by: Optional[str] = None
    referred_to: Optional[str] = None
    referral_to_date: Optional[date] = None

    class Config:
        from_attributes = True


class PreferencesSchema(BaseModel):
    """Preferences information"""
    preferred_language: Optional[str] = None
    contact_preference: Optional[str] = None

    class Config:
        from_attributes = True


class PatientDetailsResponse(BaseModel):
    """Complete patient details response"""
    id: int
    chart_no: Optional[str] = None
    first_name: str
    last_name: str
    preferred_name: Optional[str] = None
    dob: Optional[date] = None
    gender: Optional[str] = None
    title: Optional[str] = None
    pronouns: Optional[str] = None
    marital_status: Optional[str] = None
    
    address: AddressSchema = Field(default_factory=AddressSchema)
    contact: ContactSchema = Field(default_factory=ContactSchema)
    office: OfficeSchema = Field(default_factory=OfficeSchema)
    provider: ProviderSchema = Field(default_factory=ProviderSchema)
    fee_schedule: FeeScheduleSchema = Field(default_factory=FeeScheduleSchema)
    
    patient_type: str = "General"
    patient_flags: PatientFlagsSchema = Field(default_factory=PatientFlagsSchema)
    
    responsible_party: ResponsiblePartySchema = Field(default_factory=ResponsiblePartySchema)
    insurance: InsuranceSchema = Field(default_factory=InsuranceSchema)
    
    account_members: List[AccountMemberSchema] = Field(default_factory=list)
    appointments: List[AppointmentSchema] = Field(default_factory=list)
    recalls: List[RecallSchema] = Field(default_factory=list)
    balances: BalancesSchema = Field(default_factory=BalancesSchema)
    clinical: ClinicalSchema = Field(default_factory=ClinicalSchema)
    notes: NotesSchema = Field(default_factory=NotesSchema)
    referral: ReferralSchema = Field(default_factory=ReferralSchema)
    preferences: PreferencesSchema = Field(default_factory=PreferencesSchema)
    guardian_name:Optional[str] = None,
    guardian_phone:Optional[str] = None,
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: str = "system"
    updated_by: Optional[str] ="system"

    class Config:
        from_attributes = True


# ==================================================
# PATIENT CREATE/UPDATE API SCHEMAS
# ==================================================

class IdentitySchema(BaseModel):
    """Identity information for create/update"""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    preferred_name: Optional[str] = Field(None, max_length=100)
    dob: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=10)
    title: Optional[str] = Field(None, max_length=10)
    pronouns: Optional[str] = Field(None, max_length=20)
    marital_status: Optional[str] = Field(None, max_length=50)
    ssn: Optional[int] #= Field(None, max_length=20)
    medi_id: Optional[int] #= Field(None, max_length=20)

class AddressCreateSchema(BaseModel):
    """Address for create/update"""
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = "USA"


class ContactCreateSchema(BaseModel):
    """Contact for create/update"""
    home_phone: Optional[str] = None
    cell_phone: Optional[str] = None
    work_phone: Optional[str] = None
    email: Optional[EmailStr] = None
    preferred_contact: Optional[str] = None


class OfficeCreateSchema(BaseModel):
    """Office for create/update"""
    home_office_id: int


class ProviderCreateSchema(BaseModel):
    """Provider for create/update"""
    preferred_provider_id: Optional[str] = None
    preferred_hygienist_id: Optional[str] = None


class FeeScheduleCreateSchema(BaseModel):
    """Fee schedule for create/update"""
    fee_schedule_id: Optional[str] = None


class PatientFlagsCreateSchema(BaseModel):
    """Patient flags for create/update"""
    is_ortho: bool = False
    is_child: bool = False
    is_collection_problem: bool = False
    is_employee_family: bool = False
    is_short_notice: bool = False
    is_senior: bool = False
    is_spanish_speaking: bool = False
    assign_benefits: bool = True
    hipaa_agreement: bool = False
    no_correspondence: bool = False
    no_auto_email: bool = False
    no_auto_sms: bool = False
    add_to_quickfill: bool = False


class ResponsiblePartyCreateSchema(BaseModel):
    """Responsible party for create/update"""
    _relationship: Optional[str] = None
    responsible_party_id: Optional[str] = None


class CoverageSchema(BaseModel):
    """Coverage information"""
    no_coverage: bool = False
    primary_dental: bool = False
    secondary_dental: bool = False
    primary_medical: bool = False
    secondary_medical: bool = False


class ReferralCreateSchema(BaseModel):
    """Referral for create/update"""
    referral_type: Optional[str] = None
    referred_by: Optional[str] = None
    referred_to: Optional[str] = None
    referral_to_date: Optional[date] = None


class GuardianSchema(BaseModel):
    """Guardian information"""
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None


class NotesCreateSchema(BaseModel):
    """Notes for create/update"""
    patient_notes: Optional[str] = None
    hipaa_sharing: Optional[str] = None


class StartingBalancesSchema(BaseModel):
    """Starting balances"""
    current: Decimal = Decimal("0.00")
    over_30: Decimal = Decimal("0.00")
    over_60: Decimal = Decimal("0.00")
    over_90: Decimal = Decimal("0.00")
    over_120: Decimal = Decimal("0.00")


class PatientCreateRequest(BaseModel):
    """Request schema for creating a patient"""
    identity: IdentitySchema
    address: Optional[AddressCreateSchema] = None
    contact: Optional[ContactCreateSchema] = None
    office: OfficeCreateSchema
    provider: Optional[ProviderCreateSchema] = None
    fee_schedule: Optional[FeeScheduleCreateSchema] = None
    patient_type: str = "General"
    patient_flags: Optional[PatientFlagsCreateSchema] = None
    responsible_party: Optional[ResponsiblePartyCreateSchema] = None
    coverage: Optional[CoverageSchema] = None
    referral: Optional[ReferralCreateSchema] = None
    guardian: Optional[GuardianSchema] = None
    notes: Optional[NotesCreateSchema] = None
    starting_balances: Optional[StartingBalancesSchema] = None


class PatientUpdateRequest(BaseModel):
    """Request schema for updating a patient - all fields optional"""
    identity: Optional[IdentitySchema] = None
    address: Optional[AddressCreateSchema] = None
    contact: Optional[ContactCreateSchema] = None
    office: Optional[OfficeCreateSchema] = None
    provider: Optional[ProviderCreateSchema] = None
    fee_schedule: Optional[FeeScheduleCreateSchema] = None
    patient_type: Optional[str] = None
    patient_flags: Optional[PatientFlagsCreateSchema] = None
    responsible_party: Optional[ResponsiblePartyCreateSchema] = None
    coverage: Optional[CoverageSchema] = None
    referral: Optional[ReferralCreateSchema] = None
    guardian: Optional[GuardianSchema] = None
    notes: Optional[NotesCreateSchema] = None
    starting_balances: Optional[StartingBalancesSchema] = None


# ==================================================
# METADATA API SCHEMAS
# ==================================================

class FeeScheduleMetadata(BaseModel):
    """Fee schedule metadata"""
    fee_schedule_id: str
    fee_schedule_name: str
    description: Optional[str] = None
    office_id: Optional[int] = None
    office_name: Optional[str] = None

    class Config:
        from_attributes = True


class FeeSchedulesResponse(BaseModel):
    """Response for fee schedules metadata"""
    fee_schedules: List[FeeScheduleMetadata]


class PatientTypeMetadata(BaseModel):
    """Patient type metadata"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class PatientTypesResponse(BaseModel):
    """Response for patient types metadata"""
    patient_types: List[PatientTypeMetadata]


class ReferralTypeMetadata(BaseModel):
    """Referral type metadata"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class ReferralTypesResponse(BaseModel):
    """Response for referral types metadata"""
    referral_types: List[ReferralTypeMetadata]


class RelationshipMetadata(BaseModel):
    """Responsible party _relationship metadata"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RelationshipsResponse(BaseModel):
    """Response for relationships metadata"""
    relationships: List[RelationshipMetadata]


class ContactPreferenceMetadata(BaseModel):
    """Contact preference metadata"""
    code: str
    name: str

    class Config:
        from_attributes = True


class ContactPreferencesResponse(BaseModel):
    """Response for contact preferences metadata"""
    contact_preferences: List[ContactPreferenceMetadata]


# ==================================================
# METADATA API SCHEMAS (Additional)
# ==================================================

class TitleMetadata(BaseModel):
    """Title metadata"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class TitlesResponse(BaseModel):
    """Response for titles metadata"""
    titles: List[TitleMetadata]


class PronounMetadata(BaseModel):
    """Pronoun metadata"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class PronounsResponse(BaseModel):
    """Response for pronouns metadata"""
    pronouns: List[PronounMetadata]


class StateMetadata(BaseModel):
    """State metadata"""
    code: str
    name: str

    class Config:
        from_attributes = True


class StatesResponse(BaseModel):
    """Response for states metadata"""
    states: List[StateMetadata]


class MaritalStatusMetadata(BaseModel):
    """Marital status metadata"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class MaritalStatusesResponse(BaseModel):
    """Response for marital statuses metadata"""
    marital_statuses: List[MaritalStatusMetadata]


class GenderMetadata(BaseModel):
    """Gender metadata"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class GendersResponse(BaseModel):
    """Response for genders metadata"""
    genders: List[GenderMetadata]


# Unified metadata response
class PatientMetadataResponse(BaseModel):
    """Unified response for all patient metadata"""
    titles: List[TitleMetadata] = Field(default_factory=list)
    pronouns: List[PronounMetadata] = Field(default_factory=list)
    states: List[StateMetadata] = Field(default_factory=list)
    marital_statuses: List[MaritalStatusMetadata] = Field(default_factory=list)
    genders: List[GenderMetadata] = Field(default_factory=list)
    responsible_party_relationships: List[RelationshipMetadata] = Field(default_factory=list)
    contact_preferences: List[ContactPreferenceMetadata] = Field(default_factory=list)
    referral_types: List[ReferralTypeMetadata] = Field(default_factory=list)
    patient_types: List[PatientTypeMetadata] = Field(default_factory=list)
    fee_schedules: List[FeeScheduleMetadata] = Field(default_factory=list)


# ==================================================
# DUPLICATE CHECK API SCHEMAS
# ==================================================

class DuplicateCheckRequest(BaseModel):
    """Request for duplicate check"""
    firstName: str
    lastName: str
    office: Optional[str] = None
    birthdate: Optional[date] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class DuplicateMatchSchema(BaseModel):
    """Duplicate match information"""
    id: int
    chart_no: Optional[str] = None
    name: str
    dob: Optional[date] = None
    phone: Optional[str] = None
    match_score: float
    match_reasons: List[str]


class DuplicateCheckResponse(BaseModel):
    """Response for duplicate check"""
    has_duplicates: bool
    duplicates: List[DuplicateMatchSchema] = Field(default_factory=list)


# ==================================================
# LEGACY SCHEMAS (for backward compatibility)
# ==================================================

class PatientCreate(BaseModel):
    """Legacy schema for creating a new patient"""
    chart_no: Optional[str] = Field(None, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    dob: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=20)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    home_office_id: Optional[int] = None


class PatientCreateWithAliases(BaseModel):
    """Legacy schema with camelCase aliases"""
    chartNo: Optional[str] = Field(None, alias="chart_no", max_length=50)
    firstName: str = Field(..., alias="first_name", min_length=1, max_length=100)
    lastName: str = Field(..., alias="last_name", min_length=1, max_length=100)
    dob: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=20)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    homeOfficeId: Optional[int] = Field(None, alias="home_office_id")
    
    class Config:
        populate_by_name = True


class PatientUpdate(BaseModel):
    """Legacy schema for updating a patient"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    dob: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=1)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    home_office_id: Optional[int] = None


class PatientResponse(BaseModel):
    """Legacy schema for patient response"""
    id: int
    chart_no: Optional[str] = Field(None, alias="chartNo")
    first_name: str = Field(..., alias="firstName")
    last_name: str = Field(..., alias="lastName")
    dob: Optional[date] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    home_office_id: Optional[int] = Field(None, alias="homeOfficeId")
    created_at: Optional[str] = Field(None, alias="createdAt")
    updated_at: Optional[str] = Field(None, alias="updatedAt")
    
    class Config:
        populate_by_name = True
        from_attributes = True


class PatientListResponse(BaseModel):
    """Legacy schema for patient list response"""
    patients: list[PatientResponse]
    total: int


# Legacy alias
PatientOut = PatientResponse
