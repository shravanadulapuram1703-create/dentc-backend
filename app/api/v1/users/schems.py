

# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    patient_access_level: Optional[str] = "all"  # "all" or "assigned"
    login_restrictions: Optional["UserLoginRestrictions"] = None
    time_clock: Optional["UserTimeClockConfig"] = None
    preferences: Optional["UserPreferencesConfig"] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

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


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

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


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

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


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

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


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# USER DETAILS API SCHEMAS (View User Modal)
# ==================================================

class UserDetailResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId}"""
    user_id: int
    id: Optional[str] = None  # Formatted as "U-123"
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: str
    email: str
    is_active: bool
    last_login_at: Optional[datetime] = None
    tenant_id: int
    pgid: Optional[str] = None  # Formatted as "P-1"
    pgid_name: str
    home_office_id: Optional[int] = None
    home_office_name: Optional[str] = None
    assigned_office_ids: List[int] = []
    assigned_office_names: List[str] = []
    role: Optional[str] = None
    security_group: Optional[str] = None
    password_last_changed: Optional[datetime] = None
    must_change_password: bool = False
    account_locked_until: Optional[datetime] = None
    failed_login_attempts: int = 0
    require_ip_check: bool = False
    time_clock_enabled: bool = False
    clock_in_required: bool = False
    created_by: Optional[str] = None
    created_at: datetime
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class UserIPRuleDetailResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId}/ip-rules"""
    id: str  # Formatted as "IP-001"
    ip_address: str
    description: Optional[str] = None
    active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class UserGroupDetailResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId}/groups"""
    group_id: str  # Formatted as "GRP-001"
    group_name: str
    description: Optional[str] = None
    joined_date: datetime
    role: Optional[str] = None


class TimeClockEntryResponse(BaseModel):
    """Response schema for time clock entries"""
    id: str  # Formatted as "TC-001"
    date: str  # YYYY-MM-DD
    clock_in: str  # HH:MM:SS
    clock_out: Optional[str] = None  # HH:MM:SS
    total_hours: str  # Decimal as string
    notes: Optional[str] = None


class UserTimeClockDetailResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId}/time-clock"""
    enabled: bool
    clock_in_required: bool
    recent_entries: List[TimeClockEntryResponse] = []


class UserPreferencesDetailResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId}/preferences"""
    theme: Optional[str] = None
    language: Optional[str] = None
    date_format: Optional[str] = None
    time_format: Optional[str] = None
    email_notifications: Optional[bool] = None
    sms_notifications: Optional[bool] = None
    default_view: Optional[str] = None
    startup_screen: Optional[str] = None
    items_per_page: Optional[int] = None



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


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

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


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

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


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

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


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

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


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

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


# ==================================================
# USER SETUP API SCHEMAS
# ==================================================

class TenantListResponse(BaseModel):
    """Response schema for GET /api/v1/users/all-tenants"""
    id: int
    name: str
    code: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class OfficeListResponse(BaseModel):
    """Response schema for GET /api/v1/users/all-offices"""
    id: int
    officeId: int
    officeCode: Optional[str] = None
    officeName: str
    city: Optional[str] = None
    state: Optional[str] = None
    phone1: Optional[str] = None
    tenantId: int
    timezone: Optional[str] = None
    isActive: bool
    createdAt: datetime
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


# ==================================================
# ADD/EDIT USER API SCHEMAS
# ==================================================

class UserLoginRestrictions(BaseModel):
    """Login restrictions for Add/Edit User API"""
    use_24x7_access: bool
    allowed_days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or null
    allowed_from: Optional[str] = None  # HH:MM format or null
    allowed_until: Optional[str] = None  # HH:MM format or null

    class Config:
        from_attributes = True


class UserTimeClockConfig(BaseModel):
    """Time clock configuration for Add/Edit User API"""
    pay_rate: Optional[Decimal] = None
    overtime_method: Optional[str] = None  # "daily", "weekly", or "none"
    overtime_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserPreferencesConfig(BaseModel):
    """User preferences for Add/Edit User API"""
    startup_screen: Optional[str] = None  # "Dashboard", "Scheduler", "Patient"
    default_perio_screen: Optional[str] = None  # "Standard", "Advanced"
    default_navigation_search: Optional[str] = None  # "Patient", "Appointment", "Claim"
    default_search_by: Optional[str] = None  # "lastName", "firstName", "patientId", "chartNumber"
    default_referral_view: Optional[str] = None  # "All", "Active", "Pending"
    show_production_view: Optional[bool] = None
    hide_provider_time: Optional[bool] = None
    print_labels: Optional[bool] = None
    prompt_entry_date: Optional[bool] = None
    include_inactive_patients: Optional[bool] = None
    hipaa_compliant_scheduler: Optional[bool] = None
    is_ortho_assistant: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateRequest(BaseModel):
    """Request schema for POST /api/v1/users"""
    username: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for PUT /api/v1/users/{userId}"""
    username: str
    password: Optional[str] = None  # Optional - only if changing password
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]  # Array of role names/codes
    security_groups: List[str]  # Array of security group codes
    permitted_ips: Optional[List[str]] = []
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserEditResponse(BaseModel):
    """Response schema for GET /api/v1/users/{userId} (Add/Edit User modal)"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    """Response schema for POST /api/v1/users"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True


class UserUpdateResponse(BaseModel):
    """Response schema for PUT /api/v1/users/{userId}"""
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    home_office_id: int
    assigned_offices: List[int]
    roles: List[str]
    security_groups: List[str]
    permitted_ips: List[str]
    time_clock: Optional[UserTimeClockConfig] = None
    preferences: Optional[UserPreferencesConfig] = None
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================================================
# USER SETUP METADATA API SCHEMAS
# ==================================================

class OrganizationInfo(BaseModel):
    """Organization context information"""
    pgid: str
    pgid_name: str
    tenant_id: str

    class Config:
        from_attributes = True


class OfficeSetupInfo(BaseModel):
    """Office information for setup"""
    office_id: int
    office_oid: str
    office_name: str
    is_active: bool

    class Config:
        from_attributes = True


class SecurityGroupInfo(BaseModel):
    """Security group information"""
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Role information"""
    code: str
    label: str

    class Config:
        from_attributes = True


class PatientAccessLevel(BaseModel):
    """Patient access level option"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeMethod(BaseModel):
    """Overtime calculation method"""
    code: str
    label: str

    class Config:
        from_attributes = True


class OvertimeRate(BaseModel):
    """Overtime rate multiplier"""
    value: Decimal
    label: str

    class Config:
        from_attributes = True


class TimeClockConfig(BaseModel):
    """Time clock configuration"""
    enabled: bool
    overtime_methods: List[OvertimeMethod]
    overtime_rates: List[OvertimeRate]

    class Config:
        from_attributes = True


class LoginRestrictions(BaseModel):
    """Login restriction defaults"""
    allow_24x7_default: bool
    allowed_days: List[str]
    default_allowed_from: str
    default_allowed_until: str

    class Config:
        from_attributes = True


class PreferenceOptions(BaseModel):
    """Options for a preference field"""
    options: List[str]

    class Config:
        from_attributes = True


class PreferenceFlags(BaseModel):
    """Default values for boolean preference flags"""
    show_production_view: bool
    hide_provider_time: bool
    print_labels: bool
    prompt_entry_date: bool
    include_inactive_patients: bool
    hipaa_compliant_scheduler: bool
    is_ortho_assistant: bool

    class Config:
        from_attributes = True


class UserPreferencesSchema(BaseModel):
    """Schema defining available options for user preferences"""
    startup_screen: PreferenceOptions
    default_perio_screen: PreferenceOptions
    default_navigation_search: PreferenceOptions
    default_search_by: PreferenceOptions
    default_referral_view: PreferenceOptions
    flags: PreferenceFlags

    class Config:
        from_attributes = True


class UserSetupResponse(BaseModel):
    """Response schema for GET /api/v1/users/setup"""
    organization: OrganizationInfo
    offices: List[OfficeSetupInfo]
    security_groups: List[SecurityGroupInfo]
    roles: List[RoleInfo]
    patient_access_levels: List[PatientAccessLevel]
    time_clock: TimeClockConfig
    login_restrictions: LoginRestrictions
    user_preferences_schema: UserPreferencesSchema

    class Config:
        from_attributes = True