"""Time Clock DTOs (TC-BE-1…14).

Wire names match the frontend's ``src/features/time-clock`` model (snake_case,
ids as integers — this resource predates the messaging string-id convention).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.datetimes import UtcDatetime
from app.schemas.common import ORMModel


# ── entries ──────────────────────────────────────────────────────────────────
class TimeClockEntryRead(ORMModel):
    id: int
    tenant_id: int
    user_id: int
    office_id: int | None = None
    legacy_id: str | None = None
    clock_in: UtcDatetime
    clock_out: UtcDatetime | None = None
    total_hours: Decimal | None = Field(
        None, description="TC-BE-3: server-computed (clock_out - clock_in) in hours, 2dp.",
    )
    entry_type: str = Field("work", description="TC-BE-12: work | break | lunch")
    source: str = Field("manual", description="punch (server-stamped) | manual | legacy")
    clock_basis: str = Field(
        "utc",
        description="TC-BE-9: utc | wall_clock (legacy office wall time stored with a Z — render "
                    "in UTC) | utc_converted (legacy row moved to real UTC — render in office tz)",
    )
    notes: str | None = None
    created_at: UtcDatetime
    created_by: int | None = None
    updated_at: UtcDatetime | None = None
    updated_by: int | None = None
    is_edited: bool = False
    original_clock_in: UtcDatetime | None = None
    original_clock_out: UtcDatetime | None = None
    edit_reason: str | None = None
    is_active: bool = True
    deleted_at: UtcDatetime | None = None
    deleted_by: int | None = None
    delete_reason: str | None = None
    auto_closed: bool = False
    auto_closed_at: UtcDatetime | None = None
    auto_close_reason: str | None = None
    # TC-BE-11 + derived (set by ``time_clock_service.enrich_entries``).
    user_name: str | None = None
    username: str | None = None
    office_name: str | None = None
    timezone: str | None = Field(None, description="The office's IANA timezone (render zone).")
    work_date: dt.date | None = Field(None, description="Office-local date of clock_in.")
    created_by_name: str | None = None
    updated_by_name: str | None = None
    deleted_by_name: str | None = None
    is_open: bool = Field(False, description="A running shift (no clock_out, not auto-closed).")
    is_stale: bool = Field(
        False, description="Open longer than the practice's auto_close_after_hours.",
    )
    issues: list[str] = Field(default_factory=list)


class TimeClockEntryCreate(BaseModel):
    """Manager entry (add a missed shift / start someone's shift)."""

    model_config = ConfigDict(extra="forbid")

    user_id: int | None = Field(None, description="Defaults to the caller.")
    office_id: int | None = Field(None, description="Defaults to X-Office-ID.")
    clock_in: dt.datetime | None = Field(
        None, description="Required for a manager entry; ignored on a self punch (server time).",
    )
    clock_out: dt.datetime | None = None
    total_hours: Decimal | None = Field(None, description="Ignored — computed server-side (TC-BE-3).")
    entry_type: str | None = None
    notes: str | None = Field(None, max_length=500)
    reason: str | None = Field(None, max_length=500, description="TC-BE-6 edit reason.")


class TimeClockEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    office_id: int | None = None
    clock_in: dt.datetime | None = None
    clock_out: dt.datetime | None = None
    total_hours: Decimal | None = Field(None, description="Ignored — computed server-side (TC-BE-3).")
    entry_type: str | None = None
    notes: str | None = Field(None, max_length=500)
    reason: str | None = Field(None, max_length=500, description="TC-BE-6 edit reason.")
    expected_updated_at: dt.datetime | None = Field(
        None, description="Optimistic concurrency (explicit null = never updated).",
    )


class ClockInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    office_id: int | None = Field(None, description="Defaults to X-Office-ID.")
    entry_type: str | None = Field(None, description="work (default) | break | lunch")
    notes: str | None = Field(None, max_length=500)


class ClockOutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(None, max_length=500)


class TimeClockEntryEditRead(ORMModel):
    id: int
    entry_id: int
    action: str
    edited_by: int | None = None
    edited_by_name: str | None = None
    edited_at: UtcDatetime
    edit_reason: str | None = None
    original_clock_in: UtcDatetime | None = None
    original_clock_out: UtcDatetime | None = None
    new_clock_in: UtcDatetime | None = None
    new_clock_out: UtcDatetime | None = None
    changes: dict[str, Any] | None = None


# ── settings / metadata ──────────────────────────────────────────────────────
class TimeClockSettingsRead(BaseModel):
    overtime_method: str
    daily_threshold_hours: Decimal
    weekly_threshold_hours: Decimal
    week_start_day: str
    overtime_rate: Decimal
    auto_close_after_hours: int
    auto_close_policy: str
    require_edit_reason: bool
    updated_at: UtcDatetime | None = None
    updated_by: int | None = None


class TimeClockSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overtime_method: str | None = None
    daily_threshold_hours: Decimal | None = Field(None, gt=0, le=24)
    weekly_threshold_hours: Decimal | None = Field(None, gt=0, le=168)
    week_start_day: str | None = None
    overtime_rate: Decimal | None = Field(None, ge=1, le=10)
    auto_close_after_hours: int | None = Field(None, ge=1, le=72)
    auto_close_policy: str | None = None
    require_edit_reason: bool | None = None


class TimeClockCapabilities(BaseModel):
    user_id: int
    can_edit: bool = Field(description="Add / correct / delete anyone's punches (TC-BE-5).")
    can_view_all: bool = Field(description="List and report every employee's punches.")
    can_view_wages: bool = Field(description="Wages in the hours report (TC-BE-13).")


class TimeClockMetadata(BaseModel):
    entry_types: list[str]
    sources: list[str]
    clock_basis: list[str]
    overtime_methods: list[dict[str, str]]
    week_days: list[str]
    auto_close_policies: list[str]
    issues: dict[str, str]
    period_statuses: list[str]
    settings: TimeClockSettingsRead
    capabilities: TimeClockCapabilities
    effective_rules: dict[str, Any] = Field(description="The caller's own resolved overtime rule.")


class AutoCloseResult(BaseModel):
    dry_run: bool
    examined: int
    flagged: int
    closed_at_office_close: int
    entry_ids: list[int]


# ── periods (TC-BE-14) ───────────────────────────────────────────────────────
class TimeClockPeriodRead(ORMModel):
    id: int
    office_id: int | None = None
    office_name: str | None = None
    period_start: dt.date
    period_end: dt.date
    status: str
    locked: bool
    approved_by: int | None = None
    approved_by_name: str | None = None
    approved_at: UtcDatetime | None = None
    locked_by: int | None = None
    locked_by_name: str | None = None
    locked_at: UtcDatetime | None = None
    notes: str | None = None
    created_at: UtcDatetime
    created_by: int | None = None
    updated_at: UtcDatetime | None = None


class TimeClockPeriodCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    office_id: int | None = Field(None, description="NULL = every office.")
    period_start: dt.date
    period_end: dt.date
    notes: str | None = None


class TimeClockPeriodUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_start: dt.date | None = None
    period_end: dt.date | None = None
    notes: str | None = None


# ── report (TC-BE-8 / TC-BE-13) ──────────────────────────────────────────────
class ReportEntry(BaseModel):
    id: int
    clock_in: UtcDatetime
    clock_out: UtcDatetime | None = None
    hours: Decimal
    entry_type: str
    office_id: int | None = None
    office_name: str | None = None
    clock_basis: str
    is_edited: bool
    issues: list[str]


class ReportDay(BaseModel):
    date: dt.date
    regular: Decimal
    overtime: Decimal
    total: Decimal
    break_hours: Decimal
    issues: list[str]
    entries: list[ReportEntry] = Field(default_factory=list)


class ReportTotals(BaseModel):
    regular: Decimal
    overtime: Decimal
    total: Decimal
    break_hours: Decimal
    days_worked: int
    entry_count: int
    issue_count: int
    regular_pay: Decimal | None = None
    overtime_pay: Decimal | None = None
    total_pay: Decimal | None = None


class ReportUser(BaseModel):
    user_id: int
    user_name: str
    username: str | None = None
    rule: dict[str, Any]
    pay_rate: Decimal | None = None
    overtime_rate: Decimal | None = None
    days: list[ReportDay]
    totals: ReportTotals


class TimeClockReport(BaseModel):
    date_from: dt.date
    date_to: dt.date
    timezone_note: str
    overtime_method_override: str | None = None
    include_wages: bool
    users: list[ReportUser]
    totals: ReportTotals
    generated_at: UtcDatetime
