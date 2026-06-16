"""Provider Setup DTOs (provider dev-report gaps #1–#6).

Read shapes are derived from the models via ``build_schemas``; secrets are never
serialized (carrier-login password is write-only and returned masked).
"""

from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field

from app.db.models import Office
from app.db.models.provider_setup import (
    ProviderCarrierLogin,
    ProviderHoliday,
    ProviderScheduleDay,
    ProviderWatermark,
)
from app.schemas.factory import build_schemas


# ── Gap #1 Schedule (per-day grid) ───────────────────────────────────────────
_, _ScheduleUpdate, ScheduleDayRead = build_schemas(
    ProviderScheduleDay, "ProviderScheduleDay", update_exclude=("provider_id",)
)


class ScheduleDayInput(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Mon … 6=Sun")
    is_closed: bool = False
    start_time: time | None = None
    end_time: time | None = None
    lunch_start: time | None = None
    lunch_end: time | None = None
    effective_from: date | None = None
    office_id: int | None = Field(None, description="NULL = applies to every office")


class ScheduleReplace(BaseModel):
    days: list[ScheduleDayInput] = Field(default_factory=list, max_length=70)


# ── Gap #2 Holidays ──────────────────────────────────────────────────────────
ProviderHolidayCreate, ProviderHolidayUpdate, ProviderHolidayRead = build_schemas(
    ProviderHoliday, "ProviderHoliday",
    create_exclude=("provider_id", "created_by"),
    update_exclude=("provider_id", "created_by"),
)


# ── Gap #3 Watermarks ────────────────────────────────────────────────────────
_, _WatermarkUpdate, ProviderWatermarkRead = build_schemas(
    ProviderWatermark, "ProviderWatermark",
    update_exclude=("provider_id", "tenant_id", "updated_by"),
)


class ProviderWatermarkUpdate(BaseModel):
    is_enabled: bool | None = None
    opacity: int | None = Field(None, ge=0, le=100)
    position: str | None = None


# ── Gap #4 Referral offices (provider receives referrals at these offices) ────
AssignedOfficeRead = build_schemas(Office, "AssignedReferralOffice")[2]


class ReferralOfficesSet(BaseModel):
    office_ids: list[int] = Field(default_factory=list, description="Full assigned set (replaces existing)")


# ── Gap #5 Carrier logins (password write-only / masked) ─────────────────────
_CarrierCreate, _CarrierUpdate, _CarrierRead = build_schemas(
    ProviderCarrierLogin, "ProviderCarrierLoginBase",
    read_exclude=("password_enc",),
    create_exclude=("password_enc", "created_by", "updated_by"),
    update_exclude=("password_enc", "provider_id", "created_by", "updated_by"),
)


class ProviderCarrierLoginRead(_CarrierRead):  # type: ignore[valid-type, misc]
    password_masked: str | None = Field(None, description="Carrier password, masked")


class ProviderCarrierLoginCreate(_CarrierCreate):  # type: ignore[valid-type, misc]
    password: str | None = Field(None, description="Write-only; encrypted at rest")


class ProviderCarrierLoginUpdate(_CarrierUpdate):  # type: ignore[valid-type, misc]
    password: str | None = Field(None, description="Write-only; encrypted at rest")


# ── Gap #6 Provider ↔ user link ──────────────────────────────────────────────
class ProviderUserLink(BaseModel):
    user_id: int | None = Field(None, description="Linked user account id; null to unlink")
