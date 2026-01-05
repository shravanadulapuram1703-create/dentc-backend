from pydantic import BaseModel, Field, EmailStr,validator
from typing import Optional,List
from datetime import datetime,time, date



class OfficeBase(BaseModel):
    office_code: str
    office_name: str
    timezone: Optional[str] = None

    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None

    phone1: Optional[str] = None
    phone2: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[EmailStr] = None


class OfficeCreate(OfficeBase):
    pass


class OfficeUpdate(BaseModel):
    office_name: Optional[str]
    timezone: Optional[str]

    address_line1: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip: Optional[str]

    phone1: Optional[str]
    phone2: Optional[str]
    fax: Optional[str]
    email: Optional[EmailStr]

    is_active: Optional[bool]


class OfficeResponse(OfficeBase):
    id: int
    tenant_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OfficeStatementBase(BaseModel):
    general_message: Optional[str] = None
    current_message: Optional[str] = None
    msg_30_day: Optional[str] = None
    msg_60_day: Optional[str] = None
    msg_90_day: Optional[str] = None
    msg_120_day: Optional[str] = None

    correspondence_name: Optional[str] = None
    statement_address: Optional[str] = None
    statement_city_state_zip: Optional[str] = None
    statement_phone: Optional[str] = None
    logo_url: Optional[str] = None


class OfficeStatementUpdate(OfficeStatementBase):
    """Used for PUT (UI Save button)"""
    pass


class OfficeStatementResponse(OfficeStatementBase):
    office_id: int

    class Config:
        from_attributes = True


class OfficeIntegrationBase(BaseModel):
    eclaim_type: Optional[str] = None

    edi_username: Optional[str] = None
    edi_password: Optional[str] = None

    imaging_system_1: Optional[str] = None
    imaging_mode_1: Optional[str] = None

    imaging_system_2: Optional[str] = None
    imaging_mode_2: Optional[str] = None

    imaging_system_3: Optional[str] = None
    imaging_mode_3: Optional[str] = None

    text_phone_number: Optional[str] = None
    transactional_email: Optional[EmailStr] = None


class OfficeIntegrationCreate(OfficeIntegrationBase):
    """POST payload"""
    pass


class OfficeIntegrationResponse(OfficeIntegrationBase):
    id: int
    office_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class OfficeScheduleDay(BaseModel):
    day_of_week: int = Field(..., ge=1, le=7)
    day_start: Optional[time] = None
    day_end: Optional[time] = None
    lunch_start: Optional[time] = None
    lunch_end: Optional[time] = None

    @validator("day_end")
    def validate_day_range(cls, v, values):
        start = values.get("day_start")
        if start and v and v <= start:
            raise ValueError("day_end must be after day_start")
        return v

    @validator("lunch_end")
    def validate_lunch_range(cls, v, values):
        start = values.get("lunch_start")
        if start and v and v <= start:
            raise ValueError("lunch_end must be after lunch_start")
        return v


class OfficeScheduleUpdate(BaseModel):
    """PUT payload – full week replacement"""
    schedule: List[OfficeScheduleDay]


class OfficeScheduleResponse(OfficeScheduleDay):
    id: int
    office_id: int

    class Config:
        from_attributes = True


class OperatoryCreate(BaseModel):
    name: str
    is_active: Optional[bool] = True


class OperatoryUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class OperatoryResponse(BaseModel):
    id: int
    office_id: int
    name: str
    is_active: bool

    class Config:
        from_attributes = True


class OfficeHolidayCreate(BaseModel):
    holiday_date: date
    description: Optional[str] = None


class OfficeHolidayResponse(BaseModel):
    id: int
    office_id: int
    holiday_date: date
    description: Optional[str]

    class Config:
        from_attributes = True


# class OfficeCreateAllRequest(BaseModel):
#     """
#     Single payload to create Office + all related setup in one request
#     """

#     office: OfficeCreate

#     holidays: Optional[List[OfficeHolidayCreate]] = []
#     operatories: Optional[List[OperatoryCreate]] = []
#     integrations: Optional[List[OfficeIntegrationCreate]] = []

#     schedule: Optional[OfficeScheduleUpdate] = None
#     statement: Optional[OfficeStatementUpdate] = None


class OfficeCreateAllRequest(BaseModel):
    office: OfficeCreate

    holidays: Optional[List[OfficeHolidayCreate]] = None
    operatories: Optional[List[OperatoryCreate]] = None
    integrations: Optional[List[OfficeIntegrationCreate]] = None

    schedule: Optional[OfficeScheduleUpdate] = None
    statement: Optional[OfficeStatementUpdate] = None
