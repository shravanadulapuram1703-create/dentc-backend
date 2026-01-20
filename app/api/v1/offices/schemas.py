from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict
from datetime import datetime, time, date

# ==================================================
# UI / SETUP PAYLOAD MODELS (FLAT RESPONSE)
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
    email: Optional[str] = None


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


class Operatory(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    order: Optional[int] = None
    isActive: bool = True
    hasFutureAppointments: bool = False

from datetime import time

class DaySchedule(BaseModel):
    start: Optional[time] = None
    end: Optional[time] = None
    lunchStart: Optional[time] = None
    lunchEnd: Optional[time] = None
    closed: bool = False


# class Holiday(BaseModel):
#     id: Optional[str] = None
#     name: Optional[str] = None
#     fromDate: Optional[date] = None
#     toDate: Optional[date] = None
#     isActive: bool = True

class Holiday(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    fromDate: Optional[date] = None
    toDate: Optional[date] = None
    isActive: bool = True



class SmartAssistItem(BaseModel):
    enabled: bool = False
    frequency: Optional[str] = None
    includeBal: Optional[bool] = False
    template: Optional[str] = None


class SmartAssist(BaseModel):
    enabled: bool = False
    items: Dict[str, SmartAssistItem] = Field(default_factory=dict)


# class EClaims(BaseModel):
#     vendorType: Optional[str] = None
#     username: Optional[str] = None
#     password: Optional[str] = None


# class Transworld(BaseModel):
#     acceleratorAccount: Optional[str] = None
#     collectionsAccount: Optional[str] = None
#     userId: Optional[str] = None
#     password: Optional[str] = None
#     agingDays: Optional[int] = None


# class ImagingSystem(BaseModel):
#     name: Optional[str] = None
#     linkType: Optional[str] = None
#     mode: Optional[str] = None


# class Imaging(BaseModel):
#     system1: Optional[ImagingSystem] = None
#     system2: Optional[ImagingSystem] = None
#     system3: Optional[ImagingSystem] = None


# class TextMessaging(BaseModel):
#     phoneNumber: Optional[str] = None
#     verified: Optional[bool] = None


# class PatientUrls(BaseModel):
#     formsUrl: Optional[str] = None
#     schedulingUrl: Optional[str] = None
#     financingUrl: Optional[str] = None
#     customUrl1: Optional[str] = None
#     customUrl2: Optional[str] = None


# from typing import Optional, Dict, List
# from pydantic import BaseModel, Field

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
    verified: Optional[bool] = False


class PatientUrls(BaseModel):
    formsUrl: Optional[str] = None
    schedulingUrl: Optional[str] = None
    financingUrl: Optional[str] = None
    customUrl1: Optional[str] = None
    customUrl2: Optional[str] = None


class Integrations(BaseModel):
    eClaims: Optional[EClaims] = Field(default_factory=EClaims)
    transworld: Optional[Transworld] = Field(default_factory=Transworld)
    imaging: Optional[Imaging] = Field(default_factory=Imaging)
    textMessaging: Optional[TextMessaging] = Field(default_factory=TextMessaging)
    patientUrls: Optional[PatientUrls] = Field(default_factory=PatientUrls)
    acceptedCards: List[str] = Field(default_factory=list)




class OfficePayload(BaseModel):
    officeId: int
    officeName: Optional[str] = None
    shortId: Optional[str] = None

    address: Optional[Address] = None
    contact: Optional[Contact] = None
    billing: Optional[Billing] = None
    settings: Optional[Settings] = None

    integrations: Optional[Integrations] = None

    statementMessages: Optional[StatementMessages] = None
    statementSettings: Optional[StatementSettings] = None

    # acceptedCards: Optional[List[str]] = []
    operatories: Optional[List[Operatory]] = []
    schedule: Optional[Dict[str, DaySchedule]] = {}
    holidays: Optional[List[Holiday]] = []

    advanced: Optional[OfficeAdvancedPayload] = None
    smartAssist: Optional[SmartAssist] = None
    
    # Audit fields
    created_by: Optional[str] = None
    created_date: Optional[datetime] = None
    modified_by: Optional[str] = None
    modified_at: Optional[datetime] = None



# app/api/v1/offices/schemas/advanced.py

from pydantic import BaseModel
from datetime import date
from typing import Optional


# class OfficeAdvancedPayload(BaseModel):
#     annualFinanceChargePercent: Optional[float]
#     minimumBalance: Optional[float]
#     minimumFinanceCharge: Optional[float]
#     daysBeforeFinanceCharge: Optional[int]
#     salesTaxPercent: Optional[float]

#     insuranceGroup: Optional[str]
#     schedulerEndDate: Optional[date]
#     eligibilityThresholdDays: Optional[int]
#     sendECard: Optional[bool]

#     defaultPlaceOfService: Optional[str]
#     defaultAppointmentDuration: Optional[int]
#     defaultAreaCode: Optional[str]
#     defaultCity: Optional[str]
#     defaultState: Optional[str]
#     defaultZip: Optional[str]
#     preferredProvider: Optional[str]
#     defaultCoverageType: Optional[str]
#     isOrthoOffice: Optional[bool]

#     hipaaNotice: Optional[bool]
#     consentForm: Optional[bool]
#     additionalConsentForm: Optional[bool]

#     automatedCampaignsEffectiveDate: Optional[date]

class OfficeAdvancedPayload(BaseModel):
    annualFinanceChargePercent: Optional[int] = None
    minimumBalance: Optional[int] = None
    minimumFinanceCharge: Optional[int] = None
    daysBeforeFinanceCharge: Optional[int] = None
    salesTaxPercent: Optional[int] = None
    insuranceGroup: Optional[str] = None
    schedulerEndDate: Optional[date] = None
    eligibilityThresholdDays: Optional[int] = None

    sendECard: Optional[bool] = False
    defaultPlaceOfService: Optional[str] = None

    defaultAppointmentDuration: Optional[int] = None
    defaultAreaCode: Optional[str] = None
    defaultCity: Optional[str] = None
    defaultState: Optional[str] = None
    defaultZip: Optional[str] = None

    preferredProvider: Optional[str] = None
    defaultCoverageType: Optional[str] = None

    isOrthoOffice: Optional[bool] = False
    hipaaNotice: Optional[bool] = False
    consentForm: Optional[bool] = False
    additionalConsentForm: Optional[bool] = False

    automatedCampaignsEffectiveDate: Optional[date] = None


class OfficeAdvancedResponse(OfficeAdvancedPayload):
    pass



# ==================================================
# METADATA SCHEMAS (UI DROPDOWNS)
# ==================================================

# app/api/v1/offices/schemas_metadata.py

from pydantic import BaseModel
from typing import List, Optional


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


class CreateHoliday(BaseModel):
    name: str
    fromDate: Optional[date] = None
    toDate: Optional[date] = None
    isActive: Optional[bool] = True

class CreateOperatory(BaseModel):
    name: str
    order: int
    isActive: Optional[bool] = True
    hasFutureAppointments: Optional[bool] = False

class CreateScheduleDay(BaseModel):
    start: Optional[time] = None
    end: Optional[time] = None
    lunchStart: Optional[time] = None
    lunchEnd: Optional[time] = None
    closed: Optional[bool] = False


class CreateSmartAssistItem(BaseModel):
    enabled: bool
    frequency: Optional[str] = None
    includeBal: Optional[bool] = None
    template: Optional[str] = None




class CreateSmartAssist(BaseModel):
    enabled: bool = False
    items: Dict[str, CreateSmartAssistItem] = {}




# class CreateOfficePayload(BaseModel):
#     officeId: int
#     officeName: str
#     shortId: str

#     address: Optional[Address] = None
#     contact: Optional[Contact] = None
#     billing: Optional[Billing] = None
#     settings: Optional[Settings] = None

#     statementMessages: Optional[StatementMessages] = None
#     statementSettings: Optional[StatementSettings] = None

#     operatories: List[CreateOperatory] = []
#     schedule: Dict[str, CreateScheduleDay] = {}

#     holidays: List[CreateHoliday] = []

#     integrations: Optional[Integrations] = None
#     advanced: Optional[AdvancedSettings] = None
#     smartAssist: Optional[CreateSmartAssist] = None

#     class Config:
#         extra = "ignore"  # 🔥 ignores temp ids, junk fields safely

class CreateOfficePayload(BaseModel):
    officeId: int
    officeName: str
    shortId: str

    address: Optional[Address] = None
    contact: Optional[Contact] = None
    billing: Optional[Billing] = None
    settings: Optional[Settings] = None

    statementMessages: Optional[StatementMessages] = None
    statementSettings: Optional[StatementSettings] = None

    operatories: Optional[list[Operatory]] = None
    schedule: Optional[dict[str, CreateScheduleDay]] = None
    holidays: Optional[list[Holiday]] = None

    integrations: Optional[Integrations] = None
    smartAssist: Optional[SmartAssist] = None

    # THIS MUST MATCH THE CLASS NAME EXACTLY
    advanced: Optional[OfficeAdvancedPayload] = None



# app/api/v1/offices/schemas_billing_provider.py

from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class BillingProviderCreate(BaseModel):
    name: str
    npi: Optional[str] = None
    license: Optional[str] = None


class BillingProviderResponse(BaseModel):
    id: UUID
    name: str

    class Config:
        from_attributes = True


# app/api/v1/offices/schemas_fee_schedule.py

from pydantic import BaseModel
from typing import Literal
from uuid import UUID


class FeeScheduleCreate(BaseModel):
    name: str
    type: Literal["STANDARD", "UCR"]


class FeeScheduleResponse(BaseModel):
    id: UUID
    name: str
    type: str

    class Config:
        from_attributes = True




# REQUIRED FOR PYDANTIC v2
CreateOfficePayload.model_rebuild()
OfficePayload.model_rebuild()

Address.model_rebuild()
Contact.model_rebuild()
Billing.model_rebuild()
Settings.model_rebuild()
StatementMessages.model_rebuild()
StatementSettings.model_rebuild()
SmartAssist.model_rebuild()
OfficeAdvancedPayload.model_rebuild()
Integrations.model_rebuild()
