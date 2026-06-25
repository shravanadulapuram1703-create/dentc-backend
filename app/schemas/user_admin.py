"""Security -> Users module DTOs (Gaps 1-7)."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


# ── Gap 3: time-clock config ─────────────────────────────────────────────────
class TimeClockConfig(BaseModel):
    pay_rate: Decimal | None = None
    overtime_method: str | None = None
    overtime_rate: Decimal | None = None
    clock_in_required: bool = False


class TimeClockConfigRead(ORMModel):
    user_id: int
    pay_rate: Decimal | None = None
    overtime_method: str | None = None
    overtime_rate: Decimal | None = None
    clock_in_required: bool = False


# ── Gap 4: login restrictions + patient access level ─────────────────────────
class LoginRestrictions(BaseModel):
    is_24_7: bool = True
    allowed_days: str | None = Field(None, description="CSV of weekdays, e.g. 'Mon,Tue,Wed'")
    start_time: time | None = None
    end_time: time | None = None


class SecuritySettings(BaseModel):
    patient_access_level: str | None = None
    login_restrictions: LoginRestrictions | None = None


class SecuritySettingsRead(BaseModel):
    user_id: int
    patient_access_level: str | None = None
    login_restrictions: LoginRestrictions


# ── Gap 1: compound create/update ────────────────────────────────────────────
class IpRuleInput(BaseModel):
    ip_address: str
    rule_type: str = "allow"
    description: str | None = None
    is_active: bool = True


class UserCompleteCreate(BaseModel):
    # identity
    email: EmailStr
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=8)
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    role: str = "staff"
    must_change_password: bool = False
    patient_access_level: str | None = None
    # structural gaps 1-4 (users_missing_fields dev-report); image via upload endpoint
    short_id: str | None = Field(None, max_length=6)
    report_access_provider_id: str | None = None
    custom_1: str | None = None
    custom_2: str | None = None
    signature_data: str | None = None
    # related
    home_office_id: int | None = None
    assigned_offices: list[int] = Field(default_factory=list)
    group_ids: list[int] = Field(default_factory=list)
    ip_rules: list[IpRuleInput] = Field(default_factory=list)
    login_restrictions: LoginRestrictions | None = None
    time_clock: TimeClockConfig | None = None
    preferences: dict[str, str] | None = None  # pref_key -> pref_value


class UserCompleteUpdate(BaseModel):
    # All optional; only provided sections are written (PATCH semantics).
    email: EmailStr | None = None
    username: str | None = Field(None, min_length=2, max_length=50)
    password: str | None = Field(None, min_length=8)
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    role: str | None = None
    is_active: bool | None = None
    must_change_password: bool | None = None
    patient_access_level: str | None = None
    short_id: str | None = Field(None, max_length=6)
    report_access_provider_id: str | None = None
    custom_1: str | None = None
    custom_2: str | None = None
    signature_data: str | None = None
    home_office_id: int | None = None
    assigned_offices: list[int] | None = None
    group_ids: list[int] | None = None
    ip_rules: list[IpRuleInput] | None = None
    login_restrictions: LoginRestrictions | None = None
    time_clock: TimeClockConfig | None = None
    preferences: dict[str, str] | None = None


# ── Gap 5: user image / avatar ───────────────────────────────────────────────
class UserImageResult(BaseModel):
    image_url: str | None = None


# ── PN-1: per-user signature store ("Load My Signature") ─────────────────────
class UserSignatureUpdate(BaseModel):
    signature_data: str = Field(..., description="Base64 / data-URL signature image")
    signature_len: int | None = None
    device_source: str | None = Field(None, max_length=20)


class UserSignatureRead(BaseModel):
    user_id: int
    signature_data: str | None = None
    signature_len: int | None = None
    device_source: str | None = None
    updated_at: datetime | None = Field(None, description="When the signature last changed")


# ── Gap 7: self-service password change ──────────────────────────────────────
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


# ── Gap 2 / 5: setup metadata + roles ────────────────────────────────────────
class Option(BaseModel):
    value: str
    label: str


class UserSetupMetadata(BaseModel):
    roles: list[Option]
    patient_access_levels: list[Option]
    overtime_methods: list[Option]
    time_clock_config: dict
    user_preferences_schema: dict
