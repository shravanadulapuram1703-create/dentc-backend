"""Office Setup DTOs (gaps #10–#17; validation per OFF-QA-2/4/5/6/8)."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.db.models.office_setup import (
    OfficeAdvancedSettings,
    OfficeIntegrations,
    OfficeScheduleDay,
    OfficeSmartAssistItem,
    OfficeStatementSettings,
)
from app.schemas.factory import build_schemas
from app.services import office_rules


def _blank_to_none(value):  # noqa: ANN001, ANN202
    return None if isinstance(value, str) and not value.strip() else value


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
# OFF-QA-2: the two choices are closed vocabularies. Input is case-folded first
# (older frontend builds sent ``OFFICE``/``CUSTOM``), then anything else is 422.
LogoOption = Annotated[Literal["office", "custom", "none"], BeforeValidator(office_rules.fold_lower)]
AddressSource = Annotated[Literal["office", "custom"], BeforeValidator(office_rules.fold_lower)]

_, _StatementSettingsUpdate, StatementSettingsRead = build_schemas(
    OfficeStatementSettings, "OfficeStatementSettings",
    update_exclude=("office_id", "updated_by"),
)


class OfficeStatementSettingsUpdate(_StatementSettingsUpdate):  # type: ignore[valid-type, misc]
    logo_option: LogoOption | None = None
    address_source: AddressSource | None = None


# ── #13 Integrations (DoseSpot key write-only/masked) ────────────────────────
# OFF-QA-5: the verification state is server-owned (set only by the confirm
# endpoint), so it is not writable; the code hash never leaves the server.
_INTEGRATION_SERVER_FIELDS = (
    "service_email_verified", "service_email_verified_at",
    "service_email_verification_hash", "service_email_verification_sent_at",
    "service_email_verification_expires_at", "service_email_verification_attempts",
)
_, _IntegrationsUpdate, _IntegrationsRead = build_schemas(
    OfficeIntegrations, "OfficeIntegrations",
    read_exclude=("dosespot_key_enc", "service_email_verification_hash",
                  "service_email_verification_attempts"),
    update_exclude=("dosespot_key_enc", "office_id", "updated_by", *_INTEGRATION_SERVER_FIELDS),
)


class OfficeIntegrationsRead(_IntegrationsRead):  # type: ignore[valid-type, misc]
    dosespot_key_masked: str | None = Field(None, description="DoseSpot key, masked")


class OfficeIntegrationsUpdate(_IntegrationsUpdate):  # type: ignore[valid-type, misc]
    dosespot_key: str | None = Field(None, description="Write-only; encrypted at rest")
    # OFF-QA-5: a real address (blank clears it) and http(s)-only links.
    service_email: Annotated[EmailStr | None, BeforeValidator(_blank_to_none)] = Field(None, max_length=255)
    patient_comm_url: Annotated[str | None, BeforeValidator(_blank_to_none)] = Field(None, max_length=500)
    patient_portal_url: Annotated[str | None, BeforeValidator(_blank_to_none)] = Field(None, max_length=500)

    @field_validator("patient_comm_url", "patient_portal_url")
    @classmethod
    def _http_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        err = office_rules.http_url_error(value)
        if err:
            raise ValueError(err)
        return value.strip()


class ServiceEmailVerifyResult(BaseModel):
    service_email: str
    sent: bool
    expires_at: datetime
    transport: str = Field(description="graph | smtp | log (log = no mail transport configured)")


class ServiceEmailConfirm(BaseModel):
    code: str = Field(..., min_length=4, max_length=12)


# ── #14 Schedule (weekly grid) ───────────────────────────────────────────────
_, _ScheduleUpdate, _ScheduleDayRead = build_schemas(
    OfficeScheduleDay, "OfficeScheduleDay", update_exclude=("office_id",)
)


class OfficeScheduleDayRead(_ScheduleDayRead):  # type: ignore[valid-type, misc]
    """OFF-QA-13: an office that never saved its week reads the default grid
    without a row being written, so ``id``/``created_at`` are null until saved."""

    id: int | None = None  # type: ignore[assignment]
    created_at: datetime | None = None  # type: ignore[assignment]


class OfficeScheduleDayInput(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Mon … 6=Sun")
    is_closed: bool = False
    start_time: time | None = None
    end_time: time | None = None
    lunch_start: time | None = None
    lunch_end: time | None = None

    @model_validator(mode="after")
    def _times_make_sense(self) -> OfficeScheduleDayInput:
        # OFF-QA-4: an open day needs start < end; lunch both-or-neither, in
        # order, inside the day. pydantic prefixes ``loc`` with the day's index.
        errs = office_rules.schedule_day_errors(self.model_dump())
        if errs:
            raise ValueError("; ".join(f"{field}: {msg}" for field, msg in errs))
        return self


class OfficeScheduleReplace(BaseModel):
    """OFF-QA-4: only the days sent are written (upsert by ``day_of_week``); an
    omitted day keeps its stored row. Send all seven to set the whole week."""

    days: list[OfficeScheduleDayInput] = Field(..., min_length=1, max_length=7)

    @model_validator(mode="after")
    def _unique_days(self) -> OfficeScheduleReplace:
        seen = [d.day_of_week for d in self.days]
        if len(seen) != len(set(seen)):
            raise ValueError("Each day_of_week may appear only once")
        return self


# ── #16 Advanced settings ─────────────────────────────────────────────────────
_, _AdvancedSettingsUpdate, AdvancedSettingsRead = build_schemas(
    OfficeAdvancedSettings, "OfficeAdvancedSettings",
    update_exclude=("office_id", "updated_by"),
)

_Percent = Annotated[Decimal | None, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
_Money = Annotated[Decimal | None, Field(ge=0, max_digits=12, decimal_places=2)]


class OfficeAdvancedSettingsUpdate(_AdvancedSettingsUpdate):  # type: ignore[valid-type, misc]
    """OFF-QA-8: ranges and formats the database cannot express."""

    finance_charge_pct: _Percent = None
    sales_tax_pct: _Percent = None
    min_balance: _Money = None
    min_charge: _Money = None
    days_before_charge: int | None = Field(None, ge=0, le=3650)
    default_appt_duration: int | None = Field(None, ge=5, le=720)
    # Legacy words (office/hospital/…) are folded to the CMS code before the check.
    place_of_service: Annotated[
        str | None, BeforeValidator(office_rules.canonical_place_of_service)
    ] = None
    area_code: Annotated[str | None, BeforeValidator(_blank_to_none)] = None
    default_state: Annotated[
        str | None, BeforeValidator(lambda v: office_rules.fold_upper(_blank_to_none(v)))
    ] = None

    @field_validator("place_of_service")
    @classmethod
    def _pos(cls, value: str | None) -> str | None:
        if value is not None and not office_rules.is_pos_code(value):
            raise ValueError("place_of_service is a two-digit CMS place-of-service code (e.g. 11)")
        return value

    @field_validator("area_code")
    @classmethod
    def _area(cls, value: str | None) -> str | None:
        if value is not None and not office_rules.is_area_code(value.strip()):
            raise ValueError("area_code must be 3 digits")
        return value.strip() if value else value

    @field_validator("default_state")
    @classmethod
    def _state(cls, value: str | None) -> str | None:
        if value is not None and not office_rules.is_state_code(value):
            raise ValueError("default_state must be a 2-letter state code")
        return value


# ── #17 SmartAssist ───────────────────────────────────────────────────────────
_, _SAItemUpdate, _SAItemRead = build_schemas(
    OfficeSmartAssistItem, "OfficeSmartAssistItem"
)


class OfficeSmartAssistItemRead(_SAItemRead):  # type: ignore[valid-type, misc]
    """OFF-QA-6: an office that never saved its grid reads the catalog defaults;
    those rows are not stored yet, so ``id``/``created_at`` are null (the first
    PATCH persists them). ``label`` is the catalog's display name."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None  # type: ignore[assignment]
    created_at: datetime | None = None  # type: ignore[assignment]
    label: str | None = None


class SmartAssistItemInput(BaseModel):
    item_code: str = Field(..., max_length=50)
    description: str | None = Field(None, max_length=500)
    frequency: str | None = Field(None, max_length=30)
    sms_template_id: Annotated[str | None, BeforeValidator(_blank_to_none)] = Field(None, max_length=50)
    include_unpaid_balance: bool = False
    is_enabled: bool = True


class SmartAssistRead(BaseModel):
    enabled: bool
    #: ``stored`` = the office's saved grid; ``catalog`` = not configured yet,
    #: these are the defaults (nothing persisted).
    items_source: Literal["stored", "catalog"] = "stored"
    items: list[OfficeSmartAssistItemRead]


class SmartAssistUpdate(BaseModel):
    enabled: bool | None = None
    items: list[SmartAssistItemInput] | None = None


class SmartAssistCatalogItem(BaseModel):
    item_code: str
    label: str
    description: str
    frequency: str
    include_unpaid_balance: bool = False


class SmartAssistSmsTemplate(BaseModel):
    id: str
    name: str
    message_type: str
    office_id: int | None = None


# The subclasses keep the factory's component names (OpenAPI/Orval stay stable);
# the routes import them under their historical short names.
StatementSettingsUpdate = OfficeStatementSettingsUpdate
AdvancedSettingsUpdate = OfficeAdvancedSettingsUpdate
ScheduleDayRead = OfficeScheduleDayRead
SmartAssistItemRead = OfficeSmartAssistItemRead
ScheduleReplace = OfficeScheduleReplace
