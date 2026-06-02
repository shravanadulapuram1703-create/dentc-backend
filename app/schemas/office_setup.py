"""Office Setup DTOs (gaps #10–#17)."""

from __future__ import annotations

from datetime import time

from pydantic import BaseModel, Field

from app.db.models.office_setup import (
    OfficeAdvancedSettings,
    OfficeIntegrations,
    OfficeScheduleDay,
    OfficeSmartAssistItem,
    OfficeStatementSettings,
)
from app.schemas.factory import build_schemas


# ── #10 Info-tab metadata aggregate ──────────────────────────────────────────
class TimeZoneOption(BaseModel):
    value: str
    label: str


class ProviderOption(BaseModel):
    id: str
    name: str


class FeeScheduleOption(BaseModel):
    id: int
    name: str


class OfficeMetadata(BaseModel):
    time_zones: list[TimeZoneOption]
    billing_providers: list[ProviderOption]
    fee_schedules: list[FeeScheduleOption]


# ── #12 Statement settings ───────────────────────────────────────────────────
_, StatementSettingsUpdate, StatementSettingsRead = build_schemas(
    OfficeStatementSettings, "OfficeStatementSettings",
    update_exclude=("office_id", "updated_by"),
)


# ── #13 Integrations (DoseSpot key write-only/masked) ────────────────────────
_, _IntegrationsUpdate, _IntegrationsRead = build_schemas(
    OfficeIntegrations, "OfficeIntegrations",
    read_exclude=("dosespot_key_enc",),
    update_exclude=("dosespot_key_enc", "office_id", "updated_by"),
)


class OfficeIntegrationsRead(_IntegrationsRead):  # type: ignore[valid-type, misc]
    dosespot_key_masked: str | None = Field(None, description="DoseSpot key, masked")


class OfficeIntegrationsUpdate(_IntegrationsUpdate):  # type: ignore[valid-type, misc]
    dosespot_key: str | None = Field(None, description="Write-only; encrypted at rest")


# ── #14 Schedule (weekly grid) ───────────────────────────────────────────────
_, _ScheduleUpdate, ScheduleDayRead = build_schemas(
    OfficeScheduleDay, "OfficeScheduleDay", update_exclude=("office_id",)
)


class ScheduleDayInput(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Mon … 6=Sun")
    is_closed: bool = False
    start_time: time | None = None
    end_time: time | None = None
    lunch_start: time | None = None
    lunch_end: time | None = None


class ScheduleReplace(BaseModel):
    days: list[ScheduleDayInput] = Field(..., min_length=1, max_length=7)


# ── #16 Advanced settings ─────────────────────────────────────────────────────
_, AdvancedSettingsUpdate, AdvancedSettingsRead = build_schemas(
    OfficeAdvancedSettings, "OfficeAdvancedSettings",
    update_exclude=("office_id", "updated_by"),
)


# ── #17 SmartAssist ───────────────────────────────────────────────────────────
_, _SAItemUpdate, SmartAssistItemRead = build_schemas(
    OfficeSmartAssistItem, "OfficeSmartAssistItem"
)


class SmartAssistItemInput(BaseModel):
    item_code: str
    description: str | None = None
    frequency: str | None = None
    sms_template_id: str | None = None
    include_unpaid_balance: bool = False
    is_enabled: bool = True


class SmartAssistRead(BaseModel):
    enabled: bool
    items: list[SmartAssistItemRead]


class SmartAssistUpdate(BaseModel):
    enabled: bool | None = None
    items: list[SmartAssistItemInput] | None = None
