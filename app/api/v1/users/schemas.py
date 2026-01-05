from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import time, datetime
from decimal import Decimal


# class UserCreate(BaseModel):
#     email: EmailStr
#     password: str
#     tenant: int = 1
#     is_active: bool = True
#     role_ids: List[int] = [11]


# class UserResponse(BaseModel):
#     id: int
#     email: EmailStr
#     tenant_id: int
#     is_active: bool

#     class Config:
#         from_attributes = True

# class RoleUpgradeRequest(BaseModel):
#     role_ids: List[int]




class UserBase(BaseModel):
    username: str
    first_name: Optional[str]
    last_name: Optional[str]
    short_id: Optional[str]
    email: EmailStr
    phone: Optional[str]

    patient_access_level: Optional[str]  # all_offices / home_office
    allowed_days: Optional[List[str]]
    allowed_from: Optional[time]
    allowed_until: Optional[time]
    role_ids : Optional[List[int]]
    tenant_id: Optional[int]



# class UserCreate(UserBase):
#     tenant_id: int


class UserUpdate(BaseModel):
    first_name: Optional[str]
    last_name: Optional[str]
    short_id: Optional[str]
    email: Optional[EmailStr]
    phone: Optional[str]

    is_active: Optional[bool]
    patient_access_level: Optional[str]
    allowed_days: Optional[List[str]]
    allowed_from: Optional[time]
    allowed_until: Optional[time]


class UserResponse(UserBase):
    id: int
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True






# class UserOfficeBase(BaseModel):
#     office_id: int
#     is_home: bool = False
#     can_login: bool = True

# class UserOffice(BaseModel):
#     __tablename__ = "user_offices"

#     id = Column(Integer, primary_key=True)
#     user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
#     office_id = Column(Integer, ForeignKey("offices.id"), nullable=False)

#     is_primary = Column(Boolean, default=False)
#     is_active = Column(Boolean, default=True)

#     user = relationship("User", back_populates="user_offices")

class UserOfficeBase(BaseModel):
    office_id: int
    is_primary: bool = False
    is_active: bool = True 
    

class UserOfficeCreate(UserOfficeBase):
    pass


class UserOfficeResponse(UserOfficeBase):
    id: int

    class Config:
        from_attributes = True


class UserOfficeBulkUpdate(BaseModel):
    home_office_id: int
    office_ids: List[int]






class UserIPRuleBase(BaseModel):
    ip_address: Optional[str]  # CIDR
    is_allowed: bool = True


class UserIPRuleResponse(UserIPRuleBase):
    id: int

    class Config:
        from_attributes = True


class UserIPRuleBulkUpdate(BaseModel):
    allow_all: bool
    ips: Optional[List[str]] = []







class UserTimeClockBase(BaseModel):
    pay_rate: Optional[Decimal]
    overtime_method: Optional[str]  # daily / weekly
    overtime_rate: Optional[Decimal]


class UserTimeClockResponse(UserTimeClockBase):
    id: int

    class Config:
        from_attributes = True




class UserPreferenceBase(BaseModel):
    startup_screen: Optional[str]
    toolbar: Optional[str]

    perio_template: Optional[str]
    default_perio_screen: Optional[str]

    default_navigation_search: Optional[str]
    production_view: Optional[bool]
    print_labels: Optional[bool]
    prompt_entry_date: Optional[bool]

    show_production_colors: Optional[bool]
    hide_provider_time: Optional[bool]

    default_search_by: Optional[str]
    referral_view: Optional[str]
    include_inactive_patients: Optional[bool]

    user_role_type: Optional[str]


class UserPreferenceResponse(UserPreferenceBase):
    id: int

    class Config:
        from_attributes = True



class UserSetupResponse(BaseModel):
    user: UserResponse
    offices: list
    groups: list
    ip_rules: list
    time_clock: Optional[UserTimeClockResponse]
    preferences: Optional[UserPreferenceResponse]





class UserCreate(BaseModel):
    username: str
    password : str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    short_id: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    patient_access_level: Optional[str] = None  # all_offices | home_office
    allowed_days: Optional[List[str]] = None
    allowed_from: Optional[time] = None
    allowed_until: Optional[time] = None
    tenant_id: int
    role_ids: List[int] = []

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    short_id: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    patient_access_level: Optional[str] = None
    allowed_days: Optional[List[str]] = None
    allowed_from: Optional[time] = None
    allowed_until: Optional[time] = None


class UserResponse(BaseModel):
    id: int
    username: str
    password_hash : str
    first_name: Optional[str]
    last_name: Optional[str]
    short_id: Optional[str]
    email: Optional[EmailStr]
    phone: Optional[str]

    is_active: bool
    patient_access_level: Optional[str]
    allowed_days: Optional[List[str]]
    allowed_from: Optional[time]
    allowed_until: Optional[time]

    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    # updated_by: String

    class Config:
        from_attributes = True


class UserDeleteResponse(BaseModel):
    status: str  # "deleted"



# class UserWithOfficeAccessResponse(BaseModel):
#     userid: int
#     pgid: Optional[int]
#     email: str
#     username: str
#     first_name: Optional[str]
#     last_name: Optional[str]
#     role: str
#     security_group: Optional[str]   # role name from roles table
#     is_active: bool
#     is_platform_user: bool
#     is_locked: bool
#     created_at: datetime
#     updated_at: datetime
#     last_login_at: Optional[datetime]
#     created_by: Optional[int]
#     # Practice Group (Tenant)
#     # pgid: Optional[int]             # tenant_id
#     pgid_name: Optional[str]        # tenants.name
#     # Office access
#     home_office_id: Optional[int]
#     home_office_name: Optional[str]
#     assigned_office_ids: List[int]
#     assigned_office_names: List[str]
#     # Optional access constraints
#     patient_access_level: Optional[str]
#     allowed_days: Optional[List[str]]
#     allowed_from: Optional[time]
#     allowed_until: Optional[time]

#     class Config:
#         from_attributes = True


# class UserWithHomeOfficeResponse(BaseModel):
#     user_id: int                     #  match returned key
#     pgid: int
#     email: str
#     username: str
#     first_name: str
#     last_name: str

#     role: Optional[str] = None        #  allow None
#     security_group: Optional[str] = None

#     is_active: bool
#     is_platform_user: bool
#     is_locked: bool

#     created_at: datetime
#     updated_at: datetime
#     last_login_at: Optional[datetime]

#     created_by: Optional[int]

#     pgid_name: Optional[str]

#     home_office_id: Optional[int]
#     home_office_name: Optional[str]

#     assigned_office_ids: List[int]
#     assigned_office_names: List[str]

#     patient_access_level: Optional[str]
#     allowed_days: Optional[List[str]]
#     allowed_from: Optional[time]
#     allowed_until: Optional[time]

#     class Config:
#         from_attributes = True



class UserWithHomeOfficeResponse(BaseModel):
    user_id: int                     #  match returned key
    pgid: int
    email: str
    username: str
    first_name: str
    last_name: str

    role: Optional[str] = None        #  allow None
    security_group: Optional[str] = None

    is_active: bool
    is_platform_user: bool
    is_locked: bool

    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None  # keep simple for now
    last_login_at: Optional[datetime]

    created_by: Optional[int]

    pgid_name: Optional[str]

    home_office_id: Optional[int]
    home_office_name: Optional[str]

    assigned_office_ids: List[int]
    assigned_office_names: List[str]

    patient_access_level: Optional[str]
    allowed_days: Optional[List[str]]
    allowed_from: Optional[time]
    allowed_until: Optional[time]

    class Config:
        from_attributes = True





class UserIPRuleResponse(BaseModel):
    id: int
    ip_id: int
    ip_address: str
    name: str | None
    description: str | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserIPRuleListResponse(BaseModel):
    user_id: int
    total: int
    items: List[UserIPRuleResponse]


class UserIPRuleBulkUpdate(BaseModel):
    ip_ids: list[int]


class UserTimeClockResponse(BaseModel):
    id: int
    pay_rate: Decimal
    overtime_method: str
    overtime_rate: Decimal

    class Config:
        from_attributes = True      

class UserPreferenceResponse(BaseModel):
    id: int
    startup_screen: str | None
    toolbar: str | None
    perio_template: str | None
    default_perio_screen: str | None
    default_navigation_search: str | None
    production_view: bool | None
    print_labels: bool | None
    prompt_entry_date: bool | None
    show_production_colors: bool | None
    hide_provider_time: bool | None
    default_search_by: str | None
    referral_view: str | None
    include_inactive_patients: bool | None
    user_role_type: str | None

    class Config:
        from_attributes = True  



# schemas/access.py

from pydantic import BaseModel
from typing import List, Optional


class OfficeAccessUI(BaseModel):
    id: str
    name: str
    code: str
    address: Optional[str]
    displayName: str
    is_current: bool


class OrganizationAccessUI(BaseModel):
    id: str
    name: str
    code: str
    offices: List[OfficeAccessUI]


class UserAccessResponse(BaseModel):
    current_organization_id: Optional[int]
    current_office_id: Optional[int]

    organizations: List[OrganizationAccess]
    offices: List[OfficeAccess]

    is_super_admin: bool