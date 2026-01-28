# ==================================================
# COMMON IMPORTS
# ==================================================

from datetime import date, datetime, time
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr
from typing_extensions import Literal


# ==================================================
# CORE SHARED MODELS
# ==================================================

class Address(BaseModel):
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    timeZone: Optional[str] = None


class Contact(BaseModel):
    phone1: Optional[str] = None
    phone1Ext: Optional[str] = None
    phone2: Optional[str] = None
    email: Optional[EmailStr] = None


class Billing(BaseModel):
    billingProviderId: Optional[str] = None
    billingProviderName: Optional[str] = None
    useBillingLicense: Optional[bool] = None
    taxId: Optional[str] = None
    openingDate: Optional[date] = None
    officeGroup: Optional[str] = None
    defaultUCRFeeSchedule: Optional[str] = None
    defaultFeeSchedule: Optional[str] = None


class Settings(BaseModel):
    schedulerTimeInterval: Optional[int] = None
    isActive: Optional[bool] = None


# ==================================================
# STATEMENTS
# ==================================================

class StatementMessages(BaseModel):
    general: Optional[str] = None
    current: Optional[str] = None
    day30: Optional[str] = None
    day60: Optional[str] = None
    day90: Optional[str] = None
    day120: Optional[str] = None


class StatementSettings(BaseModel):
    correspondenceName: Optional[str] = None
    statementName: Optional[str] = None
    statementAddress: Optional[str] = None
    statementPhone: Optional[str] = None
    logoUrl: Optional[str] = None


# ==================================================
# OPERATIONS / SCHEDULING
# ==================================================

class Operatory(BaseModel):
    id: Optional[str] = None
    defaultProviderId: Optional[str] = None
    name: Optional[str] = None
    order: Optional[int] = None
    isActive: bool = True
    hasFutureAppointments: bool = False


class DaySchedule(BaseModel):
    start: Optional[time] = None
    end: Optional[time] = None
    lunchStart: Optional[time] = None
    lunchEnd: Optional[time] = None
    closed: bool = False


class Holiday(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    fromDate: Optional[date] = None
    toDate: Optional[date] = None
    isActive: bool = True


# ==================================================
# SMART ASSIST
# ==================================================

class SmartAssistItem(BaseModel):
    enabled: bool = False
    frequency: Optional[str] = None
    includeBal: Optional[bool] = False
    template: Optional[str] = None


class SmartAssist(BaseModel):
    enabled: bool = False
    items: Dict[str, SmartAssistItem] = Field(default_factory=dict)


# ==================================================
# INTEGRATIONS
# ==================================================

class EClaims(BaseModel):
    vendorType: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class Transworld(BaseModel):
    acceleratorAccount: Optional[str] = None
    collectionsAccount: Optional[str] = None
    userId: Optional[str] = None
    password: Optional[str] = None
    agingDays: Optional[int] = None


class ImagingSystem(BaseModel):
    name: Optional[str] = None
    linkType: Optional[str] = None
    mode: Optional[str] = None


class Imaging(BaseModel):
    system1: Optional[ImagingSystem] = None
    system2: Optional[ImagingSystem] = None
    system3: Optional[ImagingSystem] = None


class TextMessaging(BaseModel):
    phoneNumber: Optional[str] = None
    verified: bool = False


class PatientUrls(BaseModel):
    formsUrl: Optional[str] = None
    schedulingUrl: Optional[str] = None
    financingUrl: Optional[str] = None
    customUrl1: Optional[str] = None
    customUrl2: Optional[str] = None


class Integrations(BaseModel):
    eClaims: EClaims = Field(default_factory=EClaims)
    transworld: Transworld = Field(default_factory=Transworld)
    imaging: Imaging = Field(default_factory=Imaging)
    textMessaging: TextMessaging = Field(default_factory=TextMessaging)
    patientUrls: PatientUrls = Field(default_factory=PatientUrls)
    acceptedCards: List[str] = Field(default_factory=list)


# ==================================================
# ADVANCED OFFICE SETTINGS
# ==================================================

class OfficeAdvancedPayload(BaseModel):
    annualFinanceChargePercent: Optional[int] = None
    minimumBalance: Optional[int] = None
    minimumFinanceCharge: Optional[int] = None
    daysBeforeFinanceCharge: Optional[int] = None
    salesTaxPercent: Optional[int] = None

    insuranceGroup: Optional[str] = None
    schedulerEndDate: Optional[date] = None
    eligibilityThresholdDays: Optional[int] = None

    sendECard: bool = False
    defaultPlaceOfService: Optional[str] = None

    defaultAppointmentDuration: Optional[int] = None
    defaultAreaCode: Optional[str] = None
    defaultCity: Optional[str] = None
    defaultState: Optional[str] = None
    defaultZip: Optional[str] = None

    preferredProvider: Optional[str] = None
    defaultCoverageType: Optional[str] = None

    isOrthoOffice: bool = False
    hipaaNotice: bool = False
    consentForm: bool = False
    additionalConsentForm: bool = False

    automatedCampaignsEffectiveDate: Optional[date] = None


class OfficeAdvancedResponse(OfficeAdvancedPayload):
    pass


# ==================================================
# MAIN OFFICE PAYLOADS
# ==================================================

class OfficePayload(BaseModel):
    # officeId: int
    officeId: Optional[int] = None
    officeName: Optional[str] = None
    shortId: Optional[str] = None

    address: Optional[Address] = None
    contact: Optional[Contact] = None
    billing: Optional[Billing] = None
    settings: Optional[Settings] = None

    integrations: Optional[Integrations] = None
    statementMessages: Optional[StatementMessages] = None
    statementSettings: Optional[StatementSettings] = None

    operatories: List[Operatory] = Field(default_factory=list)
    schedule: Dict[str, DaySchedule] = Field(default_factory=dict)
    holidays: List[Holiday] = Field(default_factory=list)

    advanced: Optional[OfficeAdvancedPayload] = None
    smartAssist: Optional[SmartAssist] = None

    created_by: Optional[str] = None
    created_date: Optional[datetime] = None
    modified_by: Optional[str] = None
    modified_at: Optional[datetime] = None


class CreateOfficePayload(BaseModel):
    officeId: Optional[int] = None
    officeName: Optional[str] = None
    shortId: Optional[str] = None

    address: Optional[Address] = None
    contact: Optional[Contact] = None
    billing: Optional[Billing] = None
    settings: Optional[Settings] = None

    statementMessages: Optional[StatementMessages] = None
    statementSettings: Optional[StatementSettings] = None

    operatories: Optional[List[Operatory]] = None
    schedule: Optional[Dict[str, DaySchedule]] = None
    holidays: Optional[List[Holiday]] = None

    integrations: Optional[Integrations] = None
    smartAssist: Optional[SmartAssist] = None
    advanced: Optional[OfficeAdvancedPayload] = None


# ==================================================
# METADATA / LOOKUPS
# ==================================================

class BillingProviderMeta(BaseModel):
    id: str
    name: str


class FeeScheduleMeta(BaseModel):
    id: str
    name: str
    type: str


class OfficeMetadataResponse(BaseModel):
    time_zones: List[str]
    billing_providers: List[BillingProviderMeta]
    fee_schedules: List[FeeScheduleMeta]


# ==================================================
# BILLING PROVIDER & FEE SCHEDULE
# ==================================================

class BillingProviderCreate(BaseModel):
    name: str
    npi: Optional[str] = None
    license: Optional[str] = None


class BillingProviderResponse(BaseModel):
    id: UUID
    name: str

    class Config:
        from_attributes = True


class FeeScheduleCreate(BaseModel):
    name: str
    type: Literal["STANDARD", "UCR"]


class FeeScheduleResponse(BaseModel):
    id: UUID
    name: str
    type: str

    class Config:
        from_attributes = True


# ==================================================
# PYDANTIC v2 MODEL REBUILD
# ==================================================

OfficePayload.model_rebuild()
CreateOfficePayload.model_rebuild()
Integrations.model_rebuild()
OfficeAdvancedPayload.model_rebuild()
SmartAssist.model_rebuild()
