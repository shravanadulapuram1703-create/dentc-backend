"""Time Clock — punches, corrections, overtime and the hours report (TC-BE-1…14).

The one home for every time-clock rule, so the punch button, the manager editor,
the report and the sweeps cannot disagree:

* **TC-BE-1** a self punch is stamped with the *server's* clock — the client's
  ``clock_in`` / ``clock_out`` never reach a self punch, even through the
  generic POST/PATCH (the transitional path below routes those to the actions).
* **TC-BE-2** one open shift per user: a service pre-check for the friendly
  409, and the partial unique index for the race two workstations can win.
* **TC-BE-3** ``total_hours`` is derived on every write and the client value is
  ignored; a reversed pair is 422 ``clock_out_before_clock_in``.
* **TC-BE-5** authorization is by *caller*: a non-manager sees and punches only
  their own rows; corrections are manager-only (role or the Time Clock Editor
  right).
* **TC-BE-6** delete is soft and every manager change appends a
  ``time_clock_entry_edits`` row carrying the times before and after.
* **TC-BE-7/8/13** overtime vocabulary + the server report (+ wages, gated).
* **TC-BE-9** legacy Denticon rows hold the office *wall clock* with a ``Z``;
  ``clock_basis`` says which rows those are, so every date computation here
  treats them as local and the FE can render per row.
* **TC-BE-10** a shift left open past ``auto_close_after_hours`` is a
  *missing clock-out*, never a running shift — flagged, 0 paid hours, never a
  guessed time unless the practice opts into ``office_close``.
* **TC-BE-14** a locked pay period freezes its entries (409 ``period_locked``).
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import concurrency
from app.core.config import settings as app_settings
from app.core.datetimes import DEFAULT_TIMEZONE, office_tz
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.models import (
    Office,
    TimeClockEntry,
    TimeClockEntryEdit,
    TimeClockPeriod,
    TimeClockSettings,
    User,
    UserTimeClockConfig,
)
from app.db.models.office_setup import OfficeScheduleDay
from app.services import permission_service
from app.services.office_scope_service import (
    OfficeScope,
    resolve_list_office_filter,
    validate_target_office,
)

# ── vocabularies ─────────────────────────────────────────────────────────────
ENTRY_TYPES: tuple[str, ...] = ("work", "break", "lunch")
#: Only ``work`` is paid; break / lunch are reported, never summed into hours.
PAID_ENTRY_TYPES: frozenset[str] = frozenset({"work"})
SOURCES: tuple[str, ...] = ("punch", "manual", "legacy")
CLOCK_BASIS: tuple[str, ...] = ("utc", "wall_clock", "utc_converted")
OVERTIME_METHODS: tuple[str, ...] = ("none", "weekly", "daily", "daily_weekly")
OVERTIME_LABELS: dict[str, str] = {
    "none": "None",
    "weekly": "Weekly > threshold (default 40h)",
    "daily": "Daily > threshold (default 8h)",
    "daily_weekly": "Daily > 8h + Weekly > 40h",
}
#: Spellings the Users screen / migrated rows used before TC-BE-7. ``california``
#: is daily + weekly (the 7th-day / double-time rules are not modelled).
OVERTIME_ALIASES: dict[str, str] = {
    "weekly_40": "weekly", "weekly>40": "weekly", "weekly40": "weekly", "week": "weekly",
    "daily_8": "daily", "daily>8": "daily", "daily8": "daily", "day": "daily",
    "california": "daily_weekly", "daily_8_weekly_40": "daily_weekly",
    "daily+weekly": "daily_weekly", "daily_and_weekly": "daily_weekly", "both": "daily_weekly",
    "no": "none", "off": "none",
}
#: Python ``date.weekday()`` order.
WEEK_DAYS: tuple[str, ...] = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)
AUTO_CLOSE_POLICIES: tuple[str, ...] = ("flag", "office_close", "off")
PERIOD_STATUSES: tuple[str, ...] = ("open", "approved", "locked")
ISSUES: dict[str, str] = {
    "missing_clock_out": "Shift was never clocked out (open past the auto-close threshold or "
                         "auto-closed without a time) — counts 0 hours until corrected.",
    "auto_closed": "Closed by the auto-close policy at the office's scheduled end time.",
    "clock_out_before_clock_in": "Clock-out precedes clock-in (legacy data) — counts 0 hours.",
    "long_shift": "Shift longer than 12 hours.",
    "open": "Shift still running.",
}

#: Roles that correct anyone's punches without a group right (practice leadership).
MANAGER_ROLES: frozenset[str] = permission_service.OFFICE_ADMIN_ROLES
#: Roles that may see wages (TC-BE-13). ``manager`` deliberately excluded.
PAYROLL_ROLES: frozenset[str] = frozenset({"owner", "admin", "super_admin"})
EDIT_RIGHT = "utilities_time_clock_editor_full_control"
VIEW_RIGHT = "utilities_time_clock_editor_view_only"

LONG_SHIFT_HOURS = Decimal("12")
#: A single punch pair may not exceed this (catches a mistyped date).
MAX_SHIFT_HOURS = 24
#: Client clocks may run slightly fast; anything beyond this is "in the future".
FUTURE_SKEW = timedelta(minutes=5)
MAX_REPORT_DAYS = 366
_CENT = Decimal("0.01")
_ZERO = Decimal("0.00")

_DEFAULTS = {
    "overtime_method": "weekly",
    "daily_threshold_hours": Decimal("8.00"),
    "weekly_threshold_hours": Decimal("40.00"),
    "week_start_day": "sunday",
    "overtime_rate": Decimal("1.50"),
    "auto_close_after_hours": 20,
    "auto_close_policy": "flag",
    "require_edit_reason": False,
}


# ── small helpers ────────────────────────────────────────────────────────────
def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def naive_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def hours_between(clock_in: datetime | None, clock_out: datetime | None) -> Decimal | None:
    """TC-BE-3: ``round((clock_out - clock_in) / 3600, 2)``; None while open."""
    if clock_in is None or clock_out is None:
        return None
    seconds = Decimal(str((clock_out - clock_in).total_seconds()))
    return _q(seconds / Decimal(3600))


def canonical_overtime_method(value: str | None, *, field: str = "overtime_method") -> str | None:
    """TC-BE-7: fold a legacy spelling onto the enum; 422 on anything else.

    Unlike the PROV-3 "store as written" call, this one is a 422: the value
    decides how much a person is paid, and an unrecognised method would silently
    compute *no* overtime."""
    if value is None:
        return None
    key = str(value).strip().lower().replace(" ", "_")
    if key == "":
        return None
    key = OVERTIME_ALIASES.get(key, key)
    if key not in OVERTIME_METHODS:
        raise ValidationError(
            f"Unknown overtime method '{value}'",
            code="invalid_overtime_method",
            details={"field": field, "allowed": list(OVERTIME_METHODS)},
        )
    return key


def canonical_week_day(value: str | None, *, field: str = "week_start_day") -> str | None:
    if value is None or str(value).strip() == "":
        return None
    key = str(value).strip().lower()
    for day in WEEK_DAYS:
        if key in (day, day[:3]):
            return day
    raise ValidationError(
        f"Unknown week day '{value}'",
        code="invalid_week_start_day",
        details={"field": field, "allowed": list(WEEK_DAYS)},
    )


def _canonical_entry_type(value: str | None) -> str:
    key = (value or "work").strip().lower()
    if key not in ENTRY_TYPES:
        raise ValidationError(
            f"Unknown entry type '{value}'",
            code="invalid_entry_type",
            details={"field": "entry_type", "allowed": list(ENTRY_TYPES)},
        )
    return key


def _zone(name: str | None) -> ZoneInfo:
    return office_tz(name)


def parse_timezone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise ValidationError(
            f"Unknown timezone '{name}'", code="invalid_timezone", details={"field": "tz"},
        ) from exc


# ── caller access (TC-BE-5) ──────────────────────────────────────────────────
@dataclass
class Caller:
    user: User
    can_edit: bool
    can_view_all: bool
    can_view_wages: bool

    @property
    def id(self) -> int:
        return self.user.id


def caller_access(db: Session, user: User) -> Caller:
    """Managers = owner / admin / manager / super_admin, or a holder of the Time
    Clock Editor right. ``has_strict`` on purpose: a user in no group is *not*
    a manager — the punch data was never theirs to edit."""
    role = (user.role or "").strip().lower()
    perms = permission_service.effective_permissions(db, user)
    can_edit = role in MANAGER_ROLES or perms.has_strict(EDIT_RIGHT)
    can_view_all = can_edit or perms.has_strict(VIEW_RIGHT)
    return Caller(
        user=user,
        can_edit=can_edit,
        can_view_all=can_view_all,
        can_view_wages=role in PAYROLL_ROLES or perms.full_access,
    )


def require_editor(caller: Caller) -> None:
    if not caller.can_edit:
        raise ForbiddenError(
            "Only a manager can add, correct or delete time clock entries",
            code="time_clock_manager_required",
            details={"required_any_of": [EDIT_RIGHT], "roles": sorted(MANAGER_ROLES)},
        )


def require_view_all(caller: Caller) -> None:
    if not caller.can_view_all:
        raise ForbiddenError(
            "Only a manager can view every employee's time clock data",
            code="time_clock_forbidden",
            details={"required_any_of": [VIEW_RIGHT, EDIT_RIGHT]},
        )


def _require_viewer_of(caller: Caller, user_id: int) -> None:
    if user_id != caller.id and not caller.can_view_all:
        raise ForbiddenError(
            "You can only view your own time clock entries",
            code="time_clock_forbidden",
            details={"required_any_of": [VIEW_RIGHT, EDIT_RIGHT]},
        )


# ── settings + effective rules (TC-BE-7) ─────────────────────────────────────
def get_settings_row(db: Session, tenant_id: int) -> TimeClockSettings | None:
    return db.execute(
        select(TimeClockSettings).where(TimeClockSettings.tenant_id == tenant_id)
    ).scalar_one_or_none()


def settings_dict(db: Session, tenant_id: int) -> dict[str, Any]:
    row = get_settings_row(db, tenant_id)
    out = dict(_DEFAULTS)
    out["updated_at"] = None
    out["updated_by"] = None
    if row is not None:
        for key in _DEFAULTS:
            value = getattr(row, key)
            if value is not None:
                out[key] = value
        out["updated_at"] = row.updated_at
        out["updated_by"] = row.updated_by
    return out


def update_settings(db: Session, tenant_id: int, data: dict[str, Any], *, actor_id: int) -> dict[str, Any]:
    if "overtime_method" in data:
        data["overtime_method"] = canonical_overtime_method(data["overtime_method"]) or "none"
    if "week_start_day" in data:
        data["week_start_day"] = canonical_week_day(data["week_start_day"]) or "sunday"
    if "auto_close_policy" in data and data["auto_close_policy"] is not None:
        policy = str(data["auto_close_policy"]).strip().lower()
        if policy not in AUTO_CLOSE_POLICIES:
            raise ValidationError(
                f"Unknown auto-close policy '{data['auto_close_policy']}'",
                code="invalid_auto_close_policy",
                details={"field": "auto_close_policy", "allowed": list(AUTO_CLOSE_POLICIES)},
            )
        data["auto_close_policy"] = policy
    row = get_settings_row(db, tenant_id)
    if row is None:
        row = TimeClockSettings(tenant_id=tenant_id, **{k: v for k, v in _DEFAULTS.items()})
        db.add(row)
    for key, value in data.items():
        if value is not None:
            setattr(row, key, value)
    row.updated_by = actor_id
    row.updated_at = utcnow()
    db.commit()
    return settings_dict(db, tenant_id)


def _configs_for(db: Session, user_ids: set[int]) -> dict[int, UserTimeClockConfig]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(UserTimeClockConfig).where(UserTimeClockConfig.user_id.in_(user_ids))
    ).scalars().all()
    return {r.user_id: r for r in rows}


def effective_rules(
    practice: dict[str, Any], config: UserTimeClockConfig | None, *, override: str | None = None,
) -> dict[str, Any]:
    """The overtime rule one person is paid under: report override → the user's
    config → the practice default. A legacy method string on the config is
    folded; an unrecognisable one falls back to the practice method (the report
    must still run)."""
    method = override
    source = "override" if override else None
    if method is None and config is not None and config.overtime_method:
        try:
            method = canonical_overtime_method(config.overtime_method)
            source = "user"
        except ValidationError:
            method = None
    if method is None:
        method = practice["overtime_method"]
        source = "practice"

    def pick(field: str) -> Any:  # noqa: ANN401
        value = getattr(config, field, None) if config is not None else None
        return value if value is not None else practice[field]

    return {
        "overtime_method": method,
        "source": source,
        "daily_threshold_hours": Decimal(str(pick("daily_threshold_hours"))),
        "weekly_threshold_hours": Decimal(str(pick("weekly_threshold_hours"))),
        "week_start_day": pick("week_start_day"),
    }


# ── offices / names / timezones ──────────────────────────────────────────────
@dataclass
class _OfficeInfo:
    name: str | None
    timezone: str


def _office_info(db: Session, office_ids: set[int]) -> dict[int, _OfficeInfo]:
    ids = {i for i in office_ids if i is not None}
    if not ids:
        return {}
    rows = db.execute(select(Office.id, Office.name, Office.timezone).where(Office.id.in_(ids))).all()
    return {oid: _OfficeInfo(name, tz or DEFAULT_TIMEZONE) for oid, name, tz in rows}


def _user_info(db: Session, user_ids: set[int]) -> dict[int, tuple[str, str | None]]:
    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    rows = db.execute(
        select(User.id, User.first_name, User.last_name, User.username).where(User.id.in_(ids))
    ).all()
    out = {}
    for uid, first, last, username in rows:
        name = " ".join(p for p in (first, last) if p).strip() or username or f"User {uid}"
        out[uid] = (name, username)
    return out


def work_date(entry: TimeClockEntry, tz_name: str | None) -> date:
    """The office-local calendar date the shift started on. A ``wall_clock``
    legacy row already *is* local time (its ``Z`` is a lie), so it is read as-is."""
    if entry.clock_basis == "wall_clock":
        return entry.clock_in.date()
    return entry.clock_in.replace(tzinfo=timezone.utc).astimezone(_zone(tz_name)).date()


def _local_to_utc(local: datetime, tz_name: str | None) -> datetime:
    return local.replace(tzinfo=_zone(tz_name)).astimezone(timezone.utc).replace(tzinfo=None)


def _entry_issues(entry: TimeClockEntry, *, stale_hours: int, now: datetime) -> list[str]:
    issues: list[str] = []
    if entry.clock_out is None:
        if entry.auto_closed or (now - entry.clock_in) > timedelta(hours=stale_hours):
            issues.append("missing_clock_out")
        else:
            issues.append("open")
        return issues
    if entry.clock_out < entry.clock_in:
        issues.append("clock_out_before_clock_in")
        return issues
    if entry.auto_closed:
        issues.append("auto_closed")
    hours = hours_between(entry.clock_in, entry.clock_out) or _ZERO
    if hours > LONG_SHIFT_HOURS:
        issues.append("long_shift")
    return issues


def enrich_entries(db: Session, entries: list[TimeClockEntry], tenant_id: int) -> None:
    """TC-BE-11: names + derived state as transient attributes, batched."""
    if not entries:
        return
    practice = settings_dict(db, tenant_id)
    stale_hours = int(practice["auto_close_after_hours"])
    now = utcnow()
    offices = _office_info(db, {e.office_id for e in entries})
    actor_ids = {e.user_id for e in entries}
    for e in entries:
        actor_ids.update(x for x in (e.created_by, e.updated_by, e.deleted_by) if x is not None)
    users = _user_info(db, actor_ids)
    for e in entries:
        office = offices.get(e.office_id) if e.office_id is not None else None
        tz_name = office.timezone if office else DEFAULT_TIMEZONE
        name, username = users.get(e.user_id, (None, None))
        e.user_name = name
        e.username = username
        e.office_name = office.name if office else None
        e.timezone = tz_name
        e.work_date = work_date(e, tz_name)
        e.created_by_name = users.get(e.created_by, (None,))[0] if e.created_by else None
        e.updated_by_name = users.get(e.updated_by, (None,))[0] if e.updated_by else None
        e.deleted_by_name = users.get(e.deleted_by, (None,))[0] if e.deleted_by else None
        e.is_open = is_open(e)
        e.is_stale = e.is_open and (now - e.clock_in) > timedelta(hours=stale_hours)
        e.issues = _entry_issues(e, stale_hours=stale_hours, now=now)


def serialise(db: Session, entry: TimeClockEntry, tenant_id: int) -> dict[str, Any]:
    """An entry as JSON — for ``error.details`` (409 already_clocked_in …)."""
    from app.schemas.time_clock import TimeClockEntryRead  # noqa: PLC0415

    enrich_entries(db, [entry], tenant_id)
    return TimeClockEntryRead.model_validate(entry).model_dump(mode="json")


# ── open-shift lookups (TC-BE-2) ─────────────────────────────────────────────
def is_open(entry: TimeClockEntry) -> bool:
    return entry.clock_out is None and entry.is_active and not entry.auto_closed


def _open_clause():
    return and_(
        TimeClockEntry.clock_out.is_(None),
        TimeClockEntry.is_active.is_(True),
        TimeClockEntry.auto_closed.is_(False),
    )


def open_entry(
    db: Session, tenant_id: int, user_id: int, *, for_update: bool = False,
    exclude_id: int | None = None,
) -> TimeClockEntry | None:
    stmt = select(TimeClockEntry).where(
        TimeClockEntry.tenant_id == tenant_id,
        TimeClockEntry.user_id == user_id,
        _open_clause(),
    )
    if exclude_id is not None:
        stmt = stmt.where(TimeClockEntry.id != exclude_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt.order_by(TimeClockEntry.clock_in.desc()).limit(1)).scalar_one_or_none()


def _is_stale(entry: TimeClockEntry, practice: dict[str, Any], now: datetime) -> bool:
    return (now - entry.clock_in) > timedelta(hours=int(practice["auto_close_after_hours"]))


def _already_clocked_in(db: Session, entry: TimeClockEntry, tenant_id: int, *, stale: bool = False) -> ConflictError:
    return ConflictError(
        "You are already clocked in" if not stale
        else "This user has an open shift past the auto-close threshold; a manager must close it",
        code="already_clocked_in",
        details={"entry": serialise(db, entry, tenant_id), "stale": stale},
    )


# ── edit log (TC-BE-6) ───────────────────────────────────────────────────────
def _log(
    db: Session, entry: TimeClockEntry, action: str, *, actor_id: int | None, reason: str | None,
    before: tuple[datetime | None, datetime | None], changes: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> None:
    db.add(TimeClockEntryEdit(
        tenant_id=entry.tenant_id,
        entry_id=entry.id,
        action=action,
        edited_by=actor_id,
        edited_at=now or utcnow(),
        edit_reason=reason,
        original_clock_in=before[0],
        original_clock_out=before[1],
        new_clock_in=entry.clock_in,
        new_clock_out=entry.clock_out,
        changes=changes or None,
    ))


def _json_value(value: Any) -> Any:  # noqa: ANN401
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


# ── pay-period lock (TC-BE-14) ───────────────────────────────────────────────
def locked_period_for(
    db: Session, tenant_id: int, office_id: int | None, day: date,
) -> TimeClockPeriod | None:
    stmt = select(TimeClockPeriod).where(
        TimeClockPeriod.tenant_id == tenant_id,
        TimeClockPeriod.locked.is_(True),
        TimeClockPeriod.period_start <= day,
        TimeClockPeriod.period_end >= day,
    )
    if office_id is None:
        stmt = stmt.where(TimeClockPeriod.office_id.is_(None))
    else:
        stmt = stmt.where(or_(TimeClockPeriod.office_id.is_(None), TimeClockPeriod.office_id == office_id))
    return db.execute(stmt.limit(1)).scalar_one_or_none()


def _assert_unlocked(db: Session, entry: TimeClockEntry, tz_name: str | None) -> None:
    period = locked_period_for(db, entry.tenant_id, entry.office_id, work_date(entry, tz_name))
    if period is not None:
        raise ConflictError(
            "This entry falls inside a locked pay period",
            code="period_locked",
            details={
                "period_id": period.id,
                "period_start": period.period_start.isoformat(),
                "period_end": period.period_end.isoformat(),
                "office_id": period.office_id,
            },
        )


# ── validation (TC-BE-3) ─────────────────────────────────────────────────────
def _validate_times(clock_in: datetime, clock_out: datetime | None, now: datetime) -> None:
    if clock_in > now + FUTURE_SKEW:
        raise ValidationError(
            "clock_in is in the future", code="punch_in_future", details={"field": "clock_in"},
        )
    if clock_out is None:
        return
    if clock_out < clock_in:
        raise ValidationError(
            "clock_out must not be earlier than clock_in",
            code="clock_out_before_clock_in",
            details={"field": "clock_out"},
        )
    if clock_out > now + FUTURE_SKEW:
        raise ValidationError(
            "clock_out is in the future", code="punch_in_future", details={"field": "clock_out"},
        )
    if clock_out - clock_in > timedelta(hours=MAX_SHIFT_HOURS):
        raise ValidationError(
            f"A single entry may not exceed {MAX_SHIFT_HOURS} hours",
            code="shift_too_long",
            details={"field": "clock_out", "max_hours": MAX_SHIFT_HOURS},
        )


def _resolve_office(
    db: Session, tenant_id: int, scope: OfficeScope | None, office_id: int | None, *, required: bool,
) -> tuple[int | None, str]:
    """Body office → X-Office-ID → none. Validated against the tenant and the
    caller's assignments. Returns ``(office_id, timezone)``."""
    if office_id is None and scope is not None:
        office_id = scope.x_office_id
    if office_id is None:
        if required:
            raise ValidationError(
                "office_id is required", code="office_id_required", details={"field": "office_id"},
            )
        return None, DEFAULT_TIMEZONE
    office = db.get(Office, office_id)
    if office is None or office.tenant_id != tenant_id:
        raise ValidationError(
            f"Office '{office_id}' was not found", code="office_not_found",
            details={"field": "office_id", "office_id": office_id},
        )
    if scope is not None:
        validate_target_office(scope, office_id, field="office_id")
    return office_id, office.timezone or DEFAULT_TIMEZONE


def _office_tz_name(db: Session, office_id: int | None) -> str:
    if office_id is None:
        return DEFAULT_TIMEZONE
    office = db.get(Office, office_id)
    return (office.timezone if office is not None else None) or DEFAULT_TIMEZONE


def _commit_open(db: Session, tenant_id: int, user_id: int) -> None:
    """Commit, mapping the TC-BE-2 partial-unique collision to the same 409 the
    pre-check raises (the race two workstations can win)."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = open_entry(db, tenant_id, user_id)
        if existing is not None:
            raise _already_clocked_in(db, existing, tenant_id) from exc
        raise


# ── auto-close (TC-BE-10) ────────────────────────────────────────────────────
def _office_close_time(db: Session, office_id: int | None, day: date) -> time | None:
    if office_id is None:
        return None
    row = db.execute(
        select(OfficeScheduleDay).where(
            OfficeScheduleDay.office_id == office_id,
            OfficeScheduleDay.day_of_week == day.weekday(),
        )
    ).scalar_one_or_none()
    if row is None or row.is_closed or row.end_time is None:
        return None
    return row.end_time


def auto_close(
    db: Session, entry: TimeClockEntry, practice: dict[str, Any], *, now: datetime,
    actor_id: int | None = None, reason: str = "missing_clock_out",
) -> str:
    """Close one stale shift per the practice policy. Returns ``flagged`` or
    ``office_close``. Never commits.

    ``flag`` records the missing clock-out and pays nothing — a guessed time is
    a guessed wage. ``office_close`` stamps the office's scheduled end time for
    that day when one exists, is after the punch-in, and the period is not
    locked; otherwise it degrades to ``flag``."""
    tz_name = _office_tz_name(db, entry.office_id)
    before = (entry.clock_in, entry.clock_out)
    outcome = "flagged"
    if practice["auto_close_policy"] == "office_close":
        day = work_date(entry, tz_name)
        end = _office_close_time(db, entry.office_id, day)
        if end is not None and locked_period_for(db, entry.tenant_id, entry.office_id, day) is None:
            local_end = datetime.combine(day, end)
            close_at = local_end if entry.clock_basis == "wall_clock" else _local_to_utc(local_end, tz_name)
            if entry.clock_in < close_at <= now:
                entry.clock_out = close_at
                entry.total_hours = hours_between(entry.clock_in, close_at)
                outcome = "office_close"
    entry.auto_closed = True
    entry.auto_closed_at = now
    entry.auto_close_reason = "office_close" if outcome == "office_close" else reason
    _log(db, entry, "auto_close", actor_id=actor_id, reason=entry.auto_close_reason,
         before=before, now=now)
    return outcome


def auto_close_stale(
    db: Session, *, tenant_id: int | None = None, now: datetime | None = None, dry_run: bool = False,
    force_policy: str | None = None,
) -> dict[str, Any]:
    """The sweep (cron: ``scripts/auto_close_time_clock.py``; manager:
    ``POST /time-clock/auto-close``). A practice whose policy is ``off`` is
    skipped unless ``force_policy`` is given."""
    now = now or utcnow()
    stmt = select(TimeClockEntry).where(_open_clause())
    if tenant_id is not None:
        stmt = stmt.where(TimeClockEntry.tenant_id == tenant_id)
    candidates = db.execute(stmt.order_by(TimeClockEntry.id)).scalars().all()
    practice_by_tenant: dict[int, dict[str, Any]] = {}
    result = {"dry_run": dry_run, "examined": len(candidates), "flagged": 0,
              "closed_at_office_close": 0, "entry_ids": []}
    for entry in candidates:
        practice = practice_by_tenant.get(entry.tenant_id)
        if practice is None:
            practice = settings_dict(db, entry.tenant_id)
            if force_policy:
                practice["auto_close_policy"] = force_policy
            practice_by_tenant[entry.tenant_id] = practice
        if practice["auto_close_policy"] == "off" or not _is_stale(entry, practice, now):
            continue
        result["entry_ids"].append(entry.id)
        if dry_run:
            result["flagged"] += 1
            continue
        outcome = auto_close(db, entry, practice, now=now)
        result["closed_at_office_close" if outcome == "office_close" else "flagged"] += 1
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return result


# ── punch actions (TC-BE-1) ──────────────────────────────────────────────────
def clock_in(
    db: Session, tenant_id: int, user: User, scope: OfficeScope | None, *,
    office_id: int | None = None, entry_type: str | None = None, notes: str | None = None,
) -> TimeClockEntry:
    now = utcnow()
    practice = settings_dict(db, tenant_id)
    existing = open_entry(db, tenant_id, user.id, for_update=True)
    if existing is not None:
        if not _is_stale(existing, practice, now):
            raise _already_clocked_in(db, existing, tenant_id)
        if practice["auto_close_policy"] == "off":
            raise _already_clocked_in(db, existing, tenant_id, stale=True)
        # Yesterday's forgotten clock-out must not lock the user out today: it
        # becomes a flagged missing clock-out for a manager to correct.
        auto_close(db, existing, practice, now=now)
    resolved_office, _tz = _resolve_office(
        db, tenant_id, scope, office_id,
        required=app_settings.OFFICE_REQUIRE_POS_OFFICE,
    )
    entry = TimeClockEntry(
        tenant_id=tenant_id,
        user_id=user.id,
        office_id=resolved_office,
        clock_in=now,
        entry_type=_canonical_entry_type(entry_type),
        source="punch",
        clock_basis="utc",
        notes=notes,
        created_by=user.id,
        is_active=True,
        auto_closed=False,
        is_edited=False,
    )
    db.add(entry)
    _commit_open(db, tenant_id, user.id)
    db.refresh(entry)
    return entry


def clock_out(db: Session, tenant_id: int, user: User, *, notes: str | None = None) -> TimeClockEntry:
    now = utcnow()
    practice = settings_dict(db, tenant_id)
    entry = open_entry(db, tenant_id, user.id, for_update=True)
    if entry is None:
        raise ConflictError("You are not clocked in", code="not_clocked_in")
    if _is_stale(entry, practice, now) and practice["auto_close_policy"] != "off":
        # A 30-hour "shift" is a forgotten clock-out, not 30 payable hours.
        auto_close(db, entry, practice, now=now)
        db.commit()
        db.refresh(entry)
        raise ConflictError(
            "Your open shift was past the auto-close threshold and has been flagged as a "
            "missing clock-out; ask a manager to enter the correct time",
            code="not_clocked_in",
            details={"auto_closed_entry": serialise(db, entry, tenant_id)},
        )
    entry.clock_out = max(now, entry.clock_in)
    entry.total_hours = hours_between(entry.clock_in, entry.clock_out)
    if notes is not None:
        entry.notes = notes
    db.commit()
    db.refresh(entry)
    return entry


def active_entry(db: Session, tenant_id: int, user: User) -> TimeClockEntry | None:
    """The caller's running shift, or None. A stale open row is a missing
    clock-out, not "you are clocked in" — the punch button must not show a
    30-hour timer."""
    entry = open_entry(db, tenant_id, user.id)
    if entry is None:
        return None
    if _is_stale(entry, settings_dict(db, tenant_id), utcnow()):
        return None
    return entry


# ── list (TC-BE-4 / TC-BE-5) ─────────────────────────────────────────────────
SORTABLE = ("clock_in", "clock_out", "created_at", "updated_at", "total_hours", "user_id", "id")


def _parse_bound(raw: str | None, *, upper: bool, tz_name: str, field: str):  # noqa: ANN202
    """``(utc_bound, wall_bound, inclusive)`` for an ISO date or datetime.

    A bare date is a whole office-local day (``to`` is inclusive of it); a
    datetime is an instant. The wall bound is what a ``wall_clock`` legacy row
    must be compared against (its stored value is local time)."""
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip()
    try:
        if len(text) == 10:
            day = date.fromisoformat(text)
            local = datetime.combine(day + timedelta(days=1) if upper else day, time.min)
            return _local_to_utc(local, tz_name), local, False
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(
            f"{field} must be an ISO date (YYYY-MM-DD) or datetime",
            code="invalid_date", details={"field": field},
        ) from exc
    if value.tzinfo is None:
        local = value
        utc = _local_to_utc(value, tz_name)
    else:
        utc = naive_utc(value)
        local = value.astimezone(_zone(tz_name)).replace(tzinfo=None)
    return utc, local, True


def _range_clause(lo, hi):  # noqa: ANN001, ANN202
    col = TimeClockEntry.clock_in
    wall = TimeClockEntry.clock_basis == "wall_clock"
    utc_parts, wall_parts = [], []
    if lo is not None:
        utc_parts.append(col >= lo[0])
        wall_parts.append(col >= lo[1])
    if hi is not None:
        utc_parts.append(col <= hi[0] if hi[2] else col < hi[0])
        wall_parts.append(col <= hi[1] if hi[2] else col < hi[1])
    if not utc_parts:
        return None
    return or_(and_(~wall, *utc_parts), and_(wall, *wall_parts))


def _range_tz(db: Session, tz: str | None, office_id: int | None, scope: OfficeScope | None) -> str:
    if tz:
        parse_timezone(tz)
        return tz
    if office_id is not None:
        return _office_tz_name(db, office_id)
    if scope is not None and scope.x_office_id is not None:
        return _office_tz_name(db, scope.x_office_id)
    return DEFAULT_TIMEZONE


def list_entries(  # noqa: PLR0913, PLR0912
    db: Session, tenant_id: int, caller: Caller, scope: OfficeScope | None, *,
    page: int, size: int, sort: str | None, order: str, search: str | None,
    user_id: int | None = None, office_id: int | None = None,
    clock_in_from: str | None = None, clock_in_to: str | None = None, tz: str | None = None,
    entry_type: str | None = None, source: str | None = None, is_open: bool | None = None,
    auto_closed: bool | None = None, is_edited: bool | None = None,
    include_deleted: bool = False, is_active: bool | None = None,
) -> tuple[list[TimeClockEntry], int]:
    stmt = select(TimeClockEntry).where(TimeClockEntry.tenant_id == tenant_id)

    # TC-BE-5: a non-manager reads their own punches only.
    if not caller.can_view_all:
        if user_id is not None and user_id != caller.id:
            _require_viewer_of(caller, user_id)
        user_id = caller.id
        include_deleted = False
        is_active = None
    if user_id is not None:
        stmt = stmt.where(TimeClockEntry.user_id == user_id)

    # Office: one's own time card spans every office one worked at; a
    # manager's staff list follows the usual office scope (OFF-SCOPE-2).
    own_rows = user_id is not None and user_id == caller.id
    if scope is not None and caller.can_view_all and not own_rows:
        resolved = resolve_list_office_filter(
            scope, column="office_id", kind="day_data", explicit_value=office_id,
        )
        if resolved.office_ids is not None:
            stmt = stmt.where(TimeClockEntry.office_id.in_(resolved.office_ids))
    elif office_id is not None:
        stmt = stmt.where(TimeClockEntry.office_id == office_id)

    # TC-BE-6: soft-deleted rows are hidden unless asked for.
    if is_active is not None:
        stmt = stmt.where(TimeClockEntry.is_active.is_(is_active))
    elif not include_deleted:
        stmt = stmt.where(TimeClockEntry.is_active.is_(True))

    # TC-BE-4: inclusive date / datetime range on clock_in.
    tz_name = _range_tz(db, tz, office_id, scope)
    clause = _range_clause(
        _parse_bound(clock_in_from, upper=False, tz_name=tz_name, field="clock_in_from"),
        _parse_bound(clock_in_to, upper=True, tz_name=tz_name, field="clock_in_to"),
    )
    if clause is not None:
        stmt = stmt.where(clause)

    if entry_type is not None:
        stmt = stmt.where(TimeClockEntry.entry_type == _canonical_entry_type(entry_type))
    if source is not None:
        stmt = stmt.where(TimeClockEntry.source == source)
    if is_open is True:
        stmt = stmt.where(_open_clause())
    elif is_open is False:
        stmt = stmt.where(~_open_clause())
    if auto_closed is not None:
        stmt = stmt.where(TimeClockEntry.auto_closed.is_(auto_closed))
    if is_edited is not None:
        stmt = stmt.where(TimeClockEntry.is_edited.is_(is_edited))
    if search:
        term = f"%{search.strip()}%"
        users = select(User.id).where(
            User.tenant_id == tenant_id,
            or_(User.first_name.ilike(term), User.last_name.ilike(term), User.username.ilike(term),
                func.concat(User.first_name, " ", User.last_name).ilike(term)),
        )
        stmt = stmt.where(or_(TimeClockEntry.user_id.in_(users), TimeClockEntry.notes.ilike(term)))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    column = getattr(TimeClockEntry, sort if sort in SORTABLE else "clock_in")
    order_by = [column.desc() if order == "desc" else column.asc(), TimeClockEntry.id.desc()]
    rows = db.execute(stmt.order_by(*order_by).offset((page - 1) * size).limit(size)).scalars().all()
    return list(rows), total


def get_entry(
    db: Session, tenant_id: int, entry_id: int, caller: Caller | None = None, *,
    for_update: bool = False,
) -> TimeClockEntry:
    stmt = select(TimeClockEntry).where(TimeClockEntry.id == entry_id, TimeClockEntry.tenant_id == tenant_id)
    if for_update:
        stmt = stmt.with_for_update()
    entry = db.execute(stmt).scalar_one_or_none()
    if entry is None or (caller is not None and not entry.is_active and not caller.can_view_all):
        raise NotFoundError(f"TimeClockEntry '{entry_id}' was not found")
    if caller is not None:
        _require_viewer_of(caller, entry.user_id)
    return entry


# ── manager writes (TC-BE-5 / 6 / 14) ────────────────────────────────────────
def _require_reason(practice: dict[str, Any], caller: Caller, owner_id: int, reason: str | None) -> None:
    if practice["require_edit_reason"] and owner_id != caller.id and not (reason or "").strip():
        raise ValidationError(
            "A reason is required when changing another user's time clock entry",
            code="edit_reason_required",
            details={"field": "reason"},
        )


def _assert_user(db: Session, tenant_id: int, user_id: int) -> None:
    user = db.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise ValidationError(
            f"User '{user_id}' was not found", code="user_not_found",
            details={"field": "user_id", "user_id": user_id},
        )


def create_entry(
    db: Session, tenant_id: int, caller: Caller, scope: OfficeScope | None, data: dict[str, Any],
) -> TimeClockEntry:
    data.pop("total_hours", None)  # TC-BE-3: never client-set
    target = data.get("user_id") or caller.id

    if not caller.can_edit:
        # Transitional path: today's FE punches through the generic POST. A self
        # punch with no clock-out is treated as the TC-BE-1 action — the
        # client's clock_in is discarded and the server stamps now().
        if target == caller.id and data.get("clock_out") is None:
            return clock_in(db, tenant_id, caller.user, scope, office_id=data.get("office_id"),
                            entry_type=data.get("entry_type"), notes=data.get("notes"))
        require_editor(caller)

    practice = settings_dict(db, tenant_id)
    reason = data.pop("reason", None)
    _assert_user(db, tenant_id, target)
    _require_reason(practice, caller, target, reason)
    now = utcnow()
    cin = naive_utc(data.get("clock_in"))
    if cin is None:
        raise ValidationError("clock_in is required", code="clock_in_required", details={"field": "clock_in"})
    cout = naive_utc(data.get("clock_out"))
    _validate_times(cin, cout, now)
    office_id, tz_name = _resolve_office(db, tenant_id, scope, data.get("office_id"),
                                         required=app_settings.OFFICE_REQUIRE_POS_OFFICE)
    entry = TimeClockEntry(
        tenant_id=tenant_id, user_id=target, office_id=office_id, clock_in=cin, clock_out=cout,
        total_hours=hours_between(cin, cout), entry_type=_canonical_entry_type(data.get("entry_type")),
        source="manual", clock_basis="utc", notes=data.get("notes"), created_by=caller.id,
        is_active=True, auto_closed=False, is_edited=False,
    )
    _assert_unlocked(db, entry, tz_name)
    if cout is None:
        existing = open_entry(db, tenant_id, target, for_update=True)
        if existing is not None:
            raise _already_clocked_in(db, existing, tenant_id)
    db.add(entry)
    db.flush()
    _log(db, entry, "create", actor_id=caller.id, reason=reason, before=(None, None), now=now)
    if cout is None:
        _commit_open(db, tenant_id, target)
    else:
        db.commit()
    db.refresh(entry)
    return entry


_EDITABLE = ("clock_in", "clock_out", "office_id", "entry_type", "notes")
#: A change to any of these marks the entry ``is_edited`` (a notes-only
#: correction does not alter what is paid).
_PAY_FIELDS = frozenset({"clock_in", "clock_out", "office_id", "entry_type"})


def update_entry(
    db: Session, tenant_id: int, caller: Caller, scope: OfficeScope | None, entry_id: int,
    data: dict[str, Any],
) -> TimeClockEntry:
    data.pop("total_hours", None)  # TC-BE-3
    data.pop("expected_updated_at", None)  # set on the precondition by the router
    entry = get_entry(db, tenant_id, entry_id, caller, for_update=concurrency.snapshot() is not None)

    if not caller.can_edit:
        # Transitional path: today's FE closes a shift with PATCH {clock_out,
        # total_hours}. On one's own open shift that *is* a clock-out — routed
        # to the action, so the client's time is discarded.
        keys = set(data) - {"reason"}
        if (
            entry.user_id == caller.id and is_open(entry) and "clock_out" in keys
            and data.get("clock_out") is not None and keys <= {"clock_out", "notes"}
        ):
            return clock_out(db, tenant_id, caller.user, notes=data.get("notes"))
        require_editor(caller)

    if not entry.is_active:
        raise ConflictError("A deleted entry cannot be edited; restore it first", code="entry_deleted")
    concurrency.check(entry, concurrency.snapshot(), db=db, resource="TimeClockEntry")
    practice = settings_dict(db, tenant_id)
    reason = data.pop("reason", None)

    changes: dict[str, list[Any]] = {}
    proposed = {k: getattr(entry, k) for k in _EDITABLE}
    for key in _EDITABLE:
        if key not in data:
            continue
        value = data[key]
        if key in ("clock_in", "clock_out"):
            value = naive_utc(value)
        if key == "clock_in" and value is None:
            raise ValidationError("clock_in cannot be cleared", code="clock_in_required",
                                  details={"field": "clock_in"})
        if key == "entry_type":
            value = _canonical_entry_type(value)
        if value != proposed[key]:
            proposed[key] = value
            changes[key] = [_json_value(getattr(entry, key)), _json_value(value)]
    if not changes:
        return entry

    _require_reason(practice, caller, entry.user_id, reason)
    now = utcnow()
    if "clock_in" in changes or "clock_out" in changes:
        _validate_times(proposed["clock_in"], proposed["clock_out"], now)
    old_tz = _office_tz_name(db, entry.office_id)
    _assert_unlocked(db, entry, old_tz)
    new_tz = old_tz
    if "office_id" in changes:
        _office_id, new_tz = _resolve_office(db, tenant_id, scope, proposed["office_id"], required=False)

    before = (entry.clock_in, entry.clock_out)
    if changes.keys() & _PAY_FIELDS and not entry.is_edited:
        entry.original_clock_in = entry.clock_in
        entry.original_clock_out = entry.clock_out
    reopening = "clock_out" in changes and proposed["clock_out"] is None
    for key, value in proposed.items():
        setattr(entry, key, value)
    if reopening and entry.auto_closed:
        # Clearing the clock-out of an auto-closed row puts it back to running.
        entry.auto_closed = False
    entry.total_hours = hours_between(entry.clock_in, entry.clock_out)
    _assert_unlocked(db, entry, new_tz)
    if is_open(entry) and open_entry(db, tenant_id, entry.user_id, exclude_id=entry.id) is not None:
        raise _already_clocked_in(db, open_entry(db, tenant_id, entry.user_id, exclude_id=entry.id), tenant_id)
    if changes.keys() & _PAY_FIELDS:
        entry.is_edited = True
    entry.edit_reason = reason if reason is not None else entry.edit_reason
    entry.updated_by = caller.id
    entry.updated_at = now
    _log(db, entry, "update", actor_id=caller.id, reason=reason, before=before, changes=changes, now=now)
    _commit_open(db, tenant_id, entry.user_id)
    db.refresh(entry)
    return entry


def delete_entry(
    db: Session, tenant_id: int, caller: Caller, entry_id: int, *, reason: str | None = None,
) -> None:
    require_editor(caller)
    entry = get_entry(db, tenant_id, entry_id, caller, for_update=concurrency.snapshot() is not None)
    if not entry.is_active:
        return  # idempotent
    concurrency.check(entry, concurrency.snapshot(), db=db, resource="TimeClockEntry")
    practice = settings_dict(db, tenant_id)
    _require_reason(practice, caller, entry.user_id, reason)
    _assert_unlocked(db, entry, _office_tz_name(db, entry.office_id))
    now = utcnow()
    entry.is_active = False
    entry.deleted_at = now
    entry.deleted_by = caller.id
    entry.delete_reason = reason
    entry.updated_at = now
    entry.updated_by = caller.id
    _log(db, entry, "delete", actor_id=caller.id, reason=reason,
         before=(entry.clock_in, entry.clock_out), now=now)
    db.commit()


def restore_entry(
    db: Session, tenant_id: int, caller: Caller, entry_id: int, *, reason: str | None = None,
) -> TimeClockEntry:
    require_editor(caller)
    entry = get_entry(db, tenant_id, entry_id, caller)
    if entry.is_active:
        return entry
    _assert_unlocked(db, entry, _office_tz_name(db, entry.office_id))
    if entry.clock_out is None and not entry.auto_closed:
        existing = open_entry(db, tenant_id, entry.user_id)
        if existing is not None:
            raise _already_clocked_in(db, existing, tenant_id)
    now = utcnow()
    entry.is_active = True
    entry.deleted_at = None
    entry.deleted_by = None
    entry.delete_reason = None
    entry.updated_at = now
    entry.updated_by = caller.id
    _log(db, entry, "restore", actor_id=caller.id, reason=reason,
         before=(entry.clock_in, entry.clock_out), now=now)
    _commit_open(db, tenant_id, entry.user_id)
    db.refresh(entry)
    return entry


def entry_history(db: Session, tenant_id: int, caller: Caller, entry_id: int) -> list[TimeClockEntryEdit]:
    get_entry(db, tenant_id, entry_id, caller)
    rows = db.execute(
        select(TimeClockEntryEdit)
        .where(TimeClockEntryEdit.tenant_id == tenant_id, TimeClockEntryEdit.entry_id == entry_id)
        .order_by(TimeClockEntryEdit.edited_at.asc(), TimeClockEntryEdit.id.asc())
    ).scalars().all()
    names = _user_info(db, {r.edited_by for r in rows})
    for r in rows:
        r.edited_by_name = names.get(r.edited_by, (None,))[0] if r.edited_by else None
    return list(rows)


# ── pay periods (TC-BE-14) ───────────────────────────────────────────────────
def enrich_periods(db: Session, periods: list[TimeClockPeriod]) -> None:
    offices = _office_info(db, {p.office_id for p in periods})
    users = _user_info(db, {x for p in periods for x in (p.approved_by, p.locked_by) if x})
    for p in periods:
        p.office_name = offices[p.office_id].name if p.office_id in offices else None
        p.approved_by_name = users.get(p.approved_by, (None,))[0] if p.approved_by else None
        p.locked_by_name = users.get(p.locked_by, (None,))[0] if p.locked_by else None


def list_periods(
    db: Session, tenant_id: int, *, office_id: int | None = None, locked: bool | None = None,
    date_from: date | None = None, date_to: date | None = None,
) -> list[TimeClockPeriod]:
    stmt = select(TimeClockPeriod).where(TimeClockPeriod.tenant_id == tenant_id)
    if office_id is not None:
        stmt = stmt.where(or_(TimeClockPeriod.office_id == office_id, TimeClockPeriod.office_id.is_(None)))
    if locked is not None:
        stmt = stmt.where(TimeClockPeriod.locked.is_(locked))
    if date_from is not None:
        stmt = stmt.where(TimeClockPeriod.period_end >= date_from)
    if date_to is not None:
        stmt = stmt.where(TimeClockPeriod.period_start <= date_to)
    rows = list(db.execute(stmt.order_by(TimeClockPeriod.period_start.desc())).scalars().all())
    enrich_periods(db, rows)
    return rows


def _get_period(db: Session, tenant_id: int, period_id: int) -> TimeClockPeriod:
    row = db.get(TimeClockPeriod, period_id)
    if row is None or row.tenant_id != tenant_id:
        raise NotFoundError(f"TimeClockPeriod '{period_id}' was not found")
    return row


def _assert_period_shape(db: Session, tenant_id: int, office_id: int | None, start: date, end: date,
                         exclude_id: int | None = None) -> None:
    if end < start:
        raise ValidationError("period_end must not be before period_start",
                              code="period_end_before_start", details={"field": "period_end"})
    if (end - start).days > MAX_REPORT_DAYS:
        raise ValidationError("A pay period may not exceed one year", code="period_too_long",
                              details={"max_days": MAX_REPORT_DAYS})
    stmt = select(TimeClockPeriod).where(
        TimeClockPeriod.tenant_id == tenant_id,
        TimeClockPeriod.period_start <= end,
        TimeClockPeriod.period_end >= start,
    )
    if office_id is not None:
        stmt = stmt.where(or_(TimeClockPeriod.office_id.is_(None), TimeClockPeriod.office_id == office_id))
    if exclude_id is not None:
        stmt = stmt.where(TimeClockPeriod.id != exclude_id)
    clash = db.execute(stmt.limit(1)).scalar_one_or_none()
    if clash is not None:
        raise ConflictError(
            "This period overlaps an existing pay period", code="period_overlap",
            details={"period_id": clash.id, "period_start": clash.period_start.isoformat(),
                     "period_end": clash.period_end.isoformat(), "office_id": clash.office_id},
        )


def create_period(db: Session, tenant_id: int, caller: Caller, data: dict[str, Any]) -> TimeClockPeriod:
    require_editor(caller)
    if data.get("office_id") is not None:
        _resolve_office(db, tenant_id, None, data["office_id"], required=False)
    _assert_period_shape(db, tenant_id, data.get("office_id"), data["period_start"], data["period_end"])
    row = TimeClockPeriod(tenant_id=tenant_id, status="open", locked=False, created_by=caller.id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    enrich_periods(db, [row])
    return row


def update_period(db: Session, tenant_id: int, caller: Caller, period_id: int, data: dict[str, Any]) -> TimeClockPeriod:
    require_editor(caller)
    row = _get_period(db, tenant_id, period_id)
    if row.locked and ({"period_start", "period_end"} & set(data)):
        raise ConflictError("Unlock the period before changing its dates", code="period_locked",
                            details={"period_id": row.id})
    start = data.get("period_start", row.period_start)
    end = data.get("period_end", row.period_end)
    _assert_period_shape(db, tenant_id, row.office_id, start, end, exclude_id=row.id)
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_by = caller.id
    db.commit()
    db.refresh(row)
    enrich_periods(db, [row])
    return row


def set_period_state(db: Session, tenant_id: int, caller: Caller, period_id: int, action: str) -> TimeClockPeriod:
    """``approve`` | ``lock`` (approves first when needed) | ``unlock`` (back to
    ``approved``) | ``reopen`` (unlocked, approval cleared)."""
    require_editor(caller)
    row = _get_period(db, tenant_id, period_id)
    now = utcnow()
    if action in ("approve", "lock") and row.approved_at is None:
        row.approved_by, row.approved_at = caller.id, now
    if action == "approve":
        row.status = "locked" if row.locked else "approved"
    elif action == "lock":
        row.locked, row.locked_by, row.locked_at, row.status = True, caller.id, now, "locked"
    elif action == "unlock":
        row.locked, row.status = False, "approved" if row.approved_at else "open"
    elif action == "reopen":
        row.locked, row.status = False, "open"
        row.approved_by = row.approved_at = None
    row.updated_by = caller.id
    db.commit()
    db.refresh(row)
    enrich_periods(db, [row])
    return row


def delete_period(db: Session, tenant_id: int, caller: Caller, period_id: int) -> None:
    require_editor(caller)
    row = _get_period(db, tenant_id, period_id)
    if row.locked:
        raise ConflictError("A locked pay period cannot be deleted; unlock it first",
                            code="period_locked", details={"period_id": row.id})
    db.delete(row)
    db.commit()


# ── the hours report (TC-BE-8 / TC-BE-13) ────────────────────────────────────
def _week_key(day: date, week_start: str) -> date:
    start_idx = WEEK_DAYS.index(week_start) if week_start in WEEK_DAYS else WEEK_DAYS.index("sunday")
    return day - timedelta(days=(day.weekday() - start_idx) % 7)


def split_overtime(daily_hours: dict[date, Decimal], rule: dict[str, Any]) -> dict[date, tuple[Decimal, Decimal]]:
    """``{day: (regular, overtime)}``, chronologically.

    * ``daily``: hours past the daily threshold are OT.
    * ``weekly``: regular hours accumulate per week; those past the weekly
      threshold are OT (allocated to the day that crossed it).
    * ``daily_weekly``: daily OT first, then the weekly test over the remaining
      *regular* hours — never double-counted.
    """
    method = rule["overtime_method"]
    daily_cap = rule["daily_threshold_hours"]
    weekly_cap = rule["weekly_threshold_hours"]
    week_used: dict[date, Decimal] = defaultdict(lambda: _ZERO)
    out: dict[date, tuple[Decimal, Decimal]] = {}
    for day in sorted(daily_hours):
        worked = daily_hours[day]
        daily_ot = max(_ZERO, worked - daily_cap) if method in ("daily", "daily_weekly") else _ZERO
        regular = worked - daily_ot
        weekly_ot = _ZERO
        if method in ("weekly", "daily_weekly"):
            key = _week_key(day, rule["week_start_day"])
            room = max(_ZERO, weekly_cap - week_used[key])
            weekly_ot = max(_ZERO, regular - room)
            regular -= weekly_ot
            week_used[key] += regular
        out[day] = (_q(regular), _q(daily_ot + weekly_ot))
    return out


def _paid_hours(entry: TimeClockEntry) -> Decimal:
    if entry.clock_out is None or entry.clock_out < entry.clock_in:
        return _ZERO
    return hours_between(entry.clock_in, entry.clock_out) or _ZERO


def build_report(  # noqa: PLR0913, PLR0915
    db: Session, tenant_id: int, caller: Caller, scope: OfficeScope | None, *,
    date_from: date, date_to: date, user_id: int | None = None, office_id: int | None = None,
    overtime_method: str | None = None, include_wages: bool = False, include_entries: bool = True,
) -> dict[str, Any]:
    if date_to < date_from:
        raise ValidationError("to must not be before from", code="invalid_date_range",
                              details={"field": "to"})
    if (date_to - date_from).days >= MAX_REPORT_DAYS:
        raise ValidationError(f"The report range may not exceed {MAX_REPORT_DAYS} days",
                              code="range_too_large", details={"max_days": MAX_REPORT_DAYS})
    override = canonical_overtime_method(overtime_method) if overtime_method else None
    if include_wages and not caller.can_view_wages:
        raise ForbiddenError("Wages are visible to payroll administrators only",
                             code="permission_denied", details={"roles": sorted(PAYROLL_ROLES)})
    if not caller.can_view_all:
        if user_id is not None and user_id != caller.id:
            _require_viewer_of(caller, user_id)
        user_id = caller.id

    # Weekly OT needs the part of the first week that precedes ``from``; ±1 day
    # covers every US office offset on the UTC side.
    fetch_from = date_from - timedelta(days=7)
    stmt = select(TimeClockEntry).where(
        TimeClockEntry.tenant_id == tenant_id,
        TimeClockEntry.is_active.is_(True),
        TimeClockEntry.clock_in >= datetime.combine(fetch_from - timedelta(days=1), time.min),
        TimeClockEntry.clock_in < datetime.combine(date_to + timedelta(days=2), time.min),
    )
    if user_id is not None:
        stmt = stmt.where(TimeClockEntry.user_id == user_id)
    own_rows = user_id is not None and user_id == caller.id
    if scope is not None and caller.can_view_all and not own_rows:
        resolved = resolve_list_office_filter(
            scope, column="office_id", kind="day_data", explicit_value=office_id, reports=True,
        )
        if resolved.office_ids is not None:
            stmt = stmt.where(TimeClockEntry.office_id.in_(resolved.office_ids))
    elif office_id is not None:
        stmt = stmt.where(TimeClockEntry.office_id == office_id)
    entries = db.execute(stmt.order_by(TimeClockEntry.clock_in.asc(), TimeClockEntry.id.asc())).scalars().all()

    practice = settings_dict(db, tenant_id)
    stale_hours = int(practice["auto_close_after_hours"])
    now = utcnow()
    offices = _office_info(db, {e.office_id for e in entries})
    by_user: dict[int, list[tuple[date, TimeClockEntry]]] = defaultdict(list)
    for e in entries:
        tz_name = offices[e.office_id].timezone if e.office_id in offices else DEFAULT_TIMEZONE
        day = work_date(e, tz_name)
        if fetch_from <= day <= date_to:
            by_user[e.user_id].append((day, e))

    users = _user_info(db, set(by_user))
    configs = _configs_for(db, set(by_user))
    grand = defaultdict(lambda: _ZERO)
    grand_counts = defaultdict(int)
    out_users = []
    for uid, rows in by_user.items():
        config = configs.get(uid)
        rule = effective_rules(practice, config, override=override)
        worked: dict[date, Decimal] = defaultdict(lambda: _ZERO)
        breaks: dict[date, Decimal] = defaultdict(lambda: _ZERO)
        day_entries: dict[date, list[dict]] = defaultdict(list)
        day_issues: dict[date, set[str]] = defaultdict(set)
        for day, e in rows:
            hours = _paid_hours(e)
            if e.entry_type in PAID_ENTRY_TYPES:
                worked[day] += hours
            else:
                breaks[day] += hours
            issues = _entry_issues(e, stale_hours=stale_hours, now=now)
            day_issues[day].update(issues)
            if include_entries and date_from <= day <= date_to:
                day_entries[day].append({
                    "id": e.id, "clock_in": e.clock_in, "clock_out": e.clock_out, "hours": hours,
                    "entry_type": e.entry_type, "office_id": e.office_id,
                    "office_name": offices[e.office_id].name if e.office_id in offices else None,
                    "clock_basis": e.clock_basis, "is_edited": e.is_edited, "issues": issues,
                })
        split = split_overtime(dict(worked), rule)
        days_out = []
        tot = defaultdict(lambda: _ZERO)
        entry_count = issue_count = 0
        for day in sorted(set(worked) | set(breaks)):
            if not (date_from <= day <= date_to):
                continue
            regular, overtime = split.get(day, (_ZERO, _ZERO))
            issues = sorted(day_issues[day])
            days_out.append({
                "date": day, "regular": regular, "overtime": overtime, "total": _q(regular + overtime),
                "break_hours": _q(breaks[day]), "issues": issues, "entries": day_entries.get(day, []),
            })
            tot["regular"] += regular
            tot["overtime"] += overtime
            tot["break_hours"] += breaks[day]
            entry_count += sum(1 for d, _ in rows if d == day)
            issue_count += sum(1 for d, e in rows if d == day and _entry_issues(e, stale_hours=stale_hours, now=now))
        if not days_out:
            continue
        totals = {
            "regular": _q(tot["regular"]), "overtime": _q(tot["overtime"]),
            "total": _q(tot["regular"] + tot["overtime"]), "break_hours": _q(tot["break_hours"]),
            "days_worked": sum(1 for d in days_out if d["total"] > 0),
            "entry_count": entry_count, "issue_count": issue_count,
        }
        pay_rate = ot_rate = None
        if include_wages:
            pay_rate = config.pay_rate if config is not None else None
            ot_rate = (config.overtime_rate if config is not None and config.overtime_rate is not None
                       else Decimal(str(practice["overtime_rate"])))
            if pay_rate is not None:
                totals["regular_pay"] = _q(totals["regular"] * pay_rate)
                totals["overtime_pay"] = _q(totals["overtime"] * pay_rate * ot_rate)
                totals["total_pay"] = _q(totals["regular_pay"] + totals["overtime_pay"])
                for k in ("regular_pay", "overtime_pay", "total_pay"):
                    grand[k] += totals[k]
        for k in ("regular", "overtime", "total", "break_hours"):
            grand[k] += totals[k]
        for k in ("days_worked", "entry_count", "issue_count"):
            grand_counts[k] += totals[k]
        name, username = users.get(uid, (f"User {uid}", None))
        out_users.append({
            "user_id": uid, "user_name": name, "username": username,
            "rule": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in rule.items()},
            "pay_rate": pay_rate, "overtime_rate": ot_rate, "days": days_out, "totals": totals,
        })
    out_users.sort(key=lambda u: (u["user_name"].lower(), u["user_id"]))
    grand_totals = {k: _q(grand[k]) for k in ("regular", "overtime", "total", "break_hours")}
    grand_totals.update(grand_counts)
    for k in ("days_worked", "entry_count", "issue_count"):
        grand_totals.setdefault(k, 0)
    if include_wages:
        for k in ("regular_pay", "overtime_pay", "total_pay"):
            grand_totals[k] = _q(grand[k])
    return {
        "date_from": date_from, "date_to": date_to,
        "timezone_note": "Days are the office-local date of clock-in; legacy wall-clock rows "
                         "(clock_basis=wall_clock) are read as local time.",
        "overtime_method_override": override, "include_wages": include_wages,
        "users": out_users, "totals": grand_totals, "generated_at": now,
    }


def report_csv(report: dict[str, Any], *, layout: str = "summary") -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    wages = report["include_wages"]
    if layout == "detail":
        w.writerow(["Employee", "Username", "Date", "Clock In (UTC)", "Clock Out (UTC)", "Type",
                    "Office", "Hours", "Edited", "Issues"])
        for u in report["users"]:
            for d in u["days"]:
                for e in d["entries"]:
                    w.writerow([
                        u["user_name"], u["username"] or "", d["date"].isoformat(),
                        e["clock_in"].isoformat(), e["clock_out"].isoformat() if e["clock_out"] else "",
                        e["entry_type"], e["office_name"] or "", e["hours"],
                        "Y" if e["is_edited"] else "", ";".join(e["issues"]),
                    ])
        return buf.getvalue()
    head = ["Employee", "Username", "Overtime Rule", "Days", "Regular", "Overtime", "Total", "Breaks", "Issues"]
    if wages:
        head += ["Pay Rate", "OT Multiplier", "Regular Pay", "Overtime Pay", "Total Pay"]
    w.writerow(head)
    for u in report["users"]:
        t = u["totals"]
        row = [u["user_name"], u["username"] or "", u["rule"]["overtime_method"], t["days_worked"],
               t["regular"], t["overtime"], t["total"], t["break_hours"], t["issue_count"]]
        if wages:
            row += [u["pay_rate"] or "", u["overtime_rate"] or "", t.get("regular_pay", ""),
                    t.get("overtime_pay", ""), t.get("total_pay", "")]
        w.writerow(row)
    g = report["totals"]
    total_row = ["TOTAL", "", "", g["days_worked"], g["regular"], g["overtime"], g["total"],
                 g["break_hours"], g["issue_count"]]
    if wages:
        total_row += ["", "", g.get("regular_pay", ""), g.get("overtime_pay", ""), g.get("total_pay", "")]
    w.writerow(total_row)
    return buf.getvalue()


def report_pdf(db: Session, tenant_id: int, report: dict[str, Any], *, office_id: int | None,
               detail: bool = True) -> bytes:
    from app.services import pdf_report  # noqa: PLC0415 - reportlab is lazy
    from app.services.lab_tracking_service import _office_header  # noqa: PLC0415

    extra = [("Period", f"{pdf_report.fmt_date(report['date_from'])} - {pdf_report.fmt_date(report['date_to'])}")]
    if report["overtime_method_override"]:
        extra.append(("Overtime rule", OVERTIME_LABELS[report["overtime_method_override"]]))
    doc = pdf_report.PatientReport(
        _office_header(db, tenant_id, office_id, "Time Clock Report", extra), landscape=True,
    )
    wages = report["include_wages"]
    doc.section_title(f"Summary ({len(report['users'])} employees)")
    head = ["Employee", "Rule", "Days", "Regular", "Overtime", "Total", "Breaks", "Issues"]
    if wages:
        head += ["Rate", "Total Pay"]
    body = []
    for u in report["users"]:
        t = u["totals"]
        row = [u["user_name"], u["rule"]["overtime_method"], str(t["days_worked"]), str(t["regular"]),
               str(t["overtime"]), str(t["total"]), str(t["break_hours"]), str(t["issue_count"] or "")]
        if wages:
            row += [pdf_report.money_or_dash(u["pay_rate"]), pdf_report.money_or_dash(t.get("total_pay"))]
        body.append(row)
    g = report["totals"]
    foot = ["Total", "", str(g["days_worked"]), str(g["regular"]), str(g["overtime"]), str(g["total"]),
            str(g["break_hours"]), str(g["issue_count"] or "")]
    if wages:
        foot += ["", pdf_report.money_or_dash(g.get("total_pay"))]
    doc.data_table(head, body, right=tuple(range(2, len(head))), foot=foot,
                   empty="No time clock entries in the selected period.")
    if detail:
        for u in report["users"]:
            doc.section_title(f"{u['user_name']} — {u['totals']['total']} h")
            rows = []
            for d in u["days"]:
                for e in d["entries"] or [None]:
                    rows.append([
                        pdf_report.fmt_date(d["date"]),
                        pdf_report.fmt_time(e["clock_in"]) if e else "",
                        pdf_report.fmt_time(e["clock_out"]) if e and e["clock_out"] else "",
                        e["entry_type"] if e else "", str(e["hours"]) if e else "",
                        str(d["regular"]), str(d["overtime"]), ", ".join(d["issues"]),
                    ])
            doc.data_table(["Date", "In (UTC)", "Out (UTC)", "Type", "Hours", "Day Reg", "Day OT", "Issues"],
                           rows, right=(4, 5, 6), empty="No entries.")
    return doc.render()


# ── TC-BE-9 legacy wall-clock conversion (used by the backfill script) ───────
def wall_to_utc(value: datetime | None, tz_name: str | None) -> datetime | None:
    return None if value is None else _local_to_utc(value, tz_name)


def utc_to_wall(value: datetime | None, tz_name: str | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone(_zone(tz_name)).replace(tzinfo=None)


def metadata(db: Session, tenant_id: int, caller: Caller) -> dict[str, Any]:
    practice = settings_dict(db, tenant_id)
    config = _configs_for(db, {caller.id}).get(caller.id)
    rule = effective_rules(practice, config)
    # The punch button needs this for every user, and /users/{id}/time-clock-config
    # is admin-only.
    rule["clock_in_required"] = bool(config.clock_in_required) if config is not None else False
    return {
        "entry_types": list(ENTRY_TYPES),
        "sources": list(SOURCES),
        "clock_basis": list(CLOCK_BASIS),
        "overtime_methods": [{"value": m, "label": OVERTIME_LABELS[m]} for m in OVERTIME_METHODS],
        "week_days": list(WEEK_DAYS),
        "auto_close_policies": list(AUTO_CLOSE_POLICIES),
        "issues": dict(ISSUES),
        "period_statuses": list(PERIOD_STATUSES),
        "settings": practice,
        "capabilities": {
            "user_id": caller.id, "can_edit": caller.can_edit,
            "can_view_all": caller.can_view_all, "can_view_wages": caller.can_view_wages,
        },
        "effective_rules": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in rule.items()},
    }
