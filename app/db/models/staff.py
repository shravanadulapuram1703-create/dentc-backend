"""Staff & operations domain models.

time_clock_entries · time_clock_entry_edits · time_clock_periods ·
time_clock_settings · provider_insurance_ids · provider_route_slips
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin

#: TC-BE-2: the predicate of an *open* shift — the partial unique index and every
#: "is this user clocked in?" query share it. An auto-closed row with no
#: clock-out is a flagged missing clock-out, not a running shift.
OPEN_SHIFT_PG = "clock_out IS NULL AND is_active AND NOT auto_closed"
OPEN_SHIFT_SQLITE = "clock_out IS NULL AND is_active = 1 AND auto_closed = 0"


class TimeClockEntry(Base, IntPKMixin, CreatedAtMixin):
    """One shift (or break) punch pair. Logic: ``app.services.time_clock_service``."""

    __tablename__ = "time_clock_entries"
    __table_args__ = (
        # TC-BE-2: one open shift per user — the race two tabs / workstations
        # can win past the service's pre-check lands here and maps to a 409.
        Index(
            "uq_time_clock_entries_open_shift", "tenant_id", "user_id", unique=True,
            postgresql_where=text(OPEN_SHIFT_PG),
            sqlite_where=text(OPEN_SHIFT_SQLITE),
        ),
        # TC-BE-4: the date-range list / report scan.
        Index("ix_time_clock_entries_tenant_clock_in", "tenant_id", "clock_in"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    clock_in: Mapped[datetime] = mapped_column()
    clock_out: Mapped[datetime | None]
    # TC-BE-3: derived from clock_in / clock_out on every write; never client-set.
    total_hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # TC-BE-12: ``work`` counts toward paid hours; ``break`` / ``lunch`` are
    # reported separately and never paid.
    entry_type: Mapped[str] = mapped_column(String(20), default="work", server_default="work")
    # TC-BE-1: ``punch`` (server-stamped action) | ``manual`` (manager entry) |
    # ``legacy`` (Denticon import).
    source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    # TC-BE-9: ``utc`` (a true instant) | ``wall_clock`` (a Denticon office wall
    # time stored with a Z, unconverted) | ``utc_converted`` (a legacy row the
    # backfill moved to real UTC — revertible).
    clock_basis: Mapped[str] = mapped_column(String(20), default="utc", server_default="utc")
    notes: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # TC-BE-6: edit summary on the row (the full history is time_clock_entry_edits).
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    original_clock_in: Mapped[datetime | None] = mapped_column(DateTime)
    original_clock_out: Mapped[datetime | None] = mapped_column(DateTime)
    edit_reason: Mapped[str | None] = mapped_column(String(500))
    # TC-BE-6: soft delete.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    delete_reason: Mapped[str | None] = mapped_column(String(500))
    # TC-BE-10: a shift left open past the practice threshold. With no clock_out
    # it is a flagged *missing clock-out* (0 paid hours, never a guessed time);
    # with one, the ``office_close`` policy closed it at the scheduled end time.
    auto_closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    auto_closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    auto_close_reason: Mapped[str | None] = mapped_column(String(50))


class TimeClockEntryEdit(Base, IntPKMixin):
    """TC-BE-6: append-only change log — one row per create / edit / delete /
    restore / auto-close of a punch, with the times before and after."""

    __tablename__ = "time_clock_entry_edits"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("time_clock_entries.id"), index=True)
    action: Mapped[str] = mapped_column(String(20))
    edited_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    edited_at: Mapped[datetime] = mapped_column(DateTime)
    edit_reason: Mapped[str | None] = mapped_column(String(500))
    original_clock_in: Mapped[datetime | None] = mapped_column(DateTime)
    original_clock_out: Mapped[datetime | None] = mapped_column(DateTime)
    new_clock_in: Mapped[datetime | None] = mapped_column(DateTime)
    new_clock_out: Mapped[datetime | None] = mapped_column(DateTime)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class TimeClockPeriod(Base, IntPKMixin, TimestampMixin):
    """TC-BE-14: a pay period. A *locked* period freezes every entry whose
    office-local work date falls inside it (``409 period_locked``)."""

    __tablename__ = "time_clock_periods"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    #: NULL = the period covers every office.
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    approved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    locked_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class TimeClockSettings(Base, IntPKMixin, TimestampMixin):
    """TC-BE-7/10: practice-level time-clock defaults (1:1 per tenant). A user's
    ``user_time_clock_config`` overrides any field it sets."""

    __tablename__ = "time_clock_settings"
    __table_args__ = (Index("uq_time_clock_settings_tenant", "tenant_id", unique=True),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"))
    overtime_method: Mapped[str] = mapped_column(String(20), default="weekly", server_default="weekly")
    daily_threshold_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("8"))
    weekly_threshold_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("40"))
    week_start_day: Mapped[str] = mapped_column(String(10), default="sunday", server_default="sunday")
    overtime_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("1.5"))
    #: Hours after which an open shift is a missing clock-out, not a running one.
    auto_close_after_hours: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    #: ``flag`` (default: mark it, 0 paid hours) | ``office_close`` (close at the
    #: office's scheduled end time that day, flagged) | ``off``.
    auto_close_policy: Mapped[str] = mapped_column(String(20), default="flag", server_default="flag")
    #: Require ``reason`` when a manager edits / deletes another user's punch.
    require_edit_reason: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"),
    )
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ProviderInsuranceId(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "provider_insurance_ids"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    carrier_id: Mapped[int] = mapped_column(Integer, ForeignKey("insurance_carriers.id"), index=True)
    ins_id: Mapped[str | None] = mapped_column(String(100))
    in_network: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100))


class ProviderRouteSlip(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "provider_route_slips"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    procedure_code: Mapped[str | None] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    num_times: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(String(100))
