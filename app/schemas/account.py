"""Account Information DTOs.

The bulk of the field set is derived from the ORM models via ``build_schemas``
(so they never drift), then specialised where secrets need write-only / masked
handling (AI-assist client secret, EIN).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.db.models.account import (
    AccountCommunications,
    AccountConsent,
    AccountHoliday,
    OfficePhoneAssignment,
)
from app.db.models.account import AccountSettings as _AccountSettings
from app.schemas.common import ORMModel
from app.schemas.factory import build_schemas

# ── Account settings (Basic + Advanced) ─────────────────────────────────────
_SettingsCreate, _SettingsUpdate, _SettingsRead = build_schemas(
    _AccountSettings,
    "AccountSettingsBase",
    read_exclude=("ai_assist_client_secret_enc",),
    update_exclude=("ai_assist_client_secret_enc", "updated_by"),
)


class AccountSettingsRead(_SettingsRead):  # type: ignore[valid-type, misc]
    ai_assist_has_secret: bool = Field(False, description="Whether an AI-assist secret is stored")


class AccountSettingsUpdate(_SettingsUpdate):  # type: ignore[valid-type, misc]
    ai_assist_client_secret: str | None = Field(
        None, description="Write-only; encrypted at rest, never returned"
    )


# ── Communications ───────────────────────────────────────────────────────────
_CommCreate, _CommUpdate, _CommRead = build_schemas(
    AccountCommunications,
    "AccountCommunicationsBase",
    read_exclude=("ein_enc",),
    update_exclude=("ein_enc", "telecom_verified_by", "updated_by"),
)


class AccountCommunicationsRead(_CommRead):  # type: ignore[valid-type, misc]
    ein_masked: str | None = Field(None, description="EIN masked to the last 4 digits")


class AccountCommunicationsUpdate(_CommUpdate):  # type: ignore[valid-type, misc]
    ein: str | None = Field(None, description="Write-only; encrypted at rest, returned masked")


class TelecomVerifyResult(ORMModel):
    telecom_status: str
    telecom_verified_at: str | None = None


# ── Phone assignments ────────────────────────────────────────────────────────
_PhoneCreate, _PhoneUpdate, PhoneAssignmentRead = build_schemas(
    OfficePhoneAssignment, "OfficePhoneAssignment"
)


class PhoneAssignmentInput(BaseModel):
    office_id: int
    assignment_type: str = Field("office_specific", examples=["office_specific", "multi_office_shared"])
    phone_number: str | None = None
    is_model_office: bool = False


class PhoneAssignmentsReplace(BaseModel):
    assignments: list[PhoneAssignmentInput] = Field(default_factory=list)


# ── Holidays ───────────────────────────────────────────────────────────────
# office_id is set from the route scope (path), never the body.
HolidayCreate, HolidayUpdate, HolidayRead = build_schemas(
    AccountHoliday, "AccountHoliday", create_exclude=("office_id",), update_exclude=("office_id",)
)


class HolidayBulkDelete(BaseModel):
    ids: list[int] = Field(..., min_length=1)


class FederalHolidaysImport(BaseModel):
    year: int = Field(..., ge=1900, le=2200)
    status: str = Field("CLOSED")


class HolidayRangeCreate(BaseModel):
    from_date: date
    to_date: date
    name: str = Field(..., max_length=255)
    status: str = Field("CLOSED")
    holiday_type: str = Field("CUSTOM")


# ── Consents ───────────────────────────────────────────────────────────────
_ConsentCreate, _ConsentUpdate, ConsentRead = build_schemas(AccountConsent, "AccountConsent")


class ConsentCreate(BaseModel):
    header: str = Field(..., max_length=500)
    body_html: str
    effective_date: date | None = None


class ConsentPreview(BaseModel):
    header: str
    body_html: str


# ── Logo ───────────────────────────────────────────────────────────────────
class LogoResult(BaseModel):
    logo_url: str | None = None
