"""Office calendar — opening hours + holidays per date (OFF-QA-7).

The Schedule tab promises "Scheduler blocks bookings outside these hours" and
"Lunch time blocks availability", but only AppointNow read the week or the
holidays. This is the one place a date is turned into "open 08:00–17:00, lunch
12–13" or "closed: Independence Day", read two ways:

* ``GET /offices/{id}/calendar?from_date&to_date`` — the scheduler greys out
  closures from the same answer the server enforces;
* ``booking_conflicts`` — run by ``AppointmentCRUD`` on create and on a move, a
  non-empty list is a 409 ``office_closed`` unless the caller sends
  ``allow_outside_office_hours`` (staff can still book on purpose).

**Hours bind only an office that saved its week.** With no stored
``office_schedule_days`` row for the weekday the default grid is reported
(``hours_source="default"``) but not enforced — enforcing a default nobody
chose would 409 every migrated office's existing workflow on deploy day. A
closing holiday always binds: someone entered it.
"""

from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, ValidationError
from app.db.models import Office
from app.db.models.account import AccountHoliday
from app.db.models.office_setup import OfficeScheduleDay

MAX_RANGE_DAYS = 400
#: ``status`` values that close the whole day. ``HALF_DAY`` stores no hours, so
#: it is reported but never blocks; ``OPEN`` explicitly overrides a closure.
CLOSING_STATUSES = frozenset({"CLOSED"})


def _fmt(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def _holidays(db: Session, office: Office, start: date, end: date) -> dict[date, list[AccountHoliday]]:
    rows = db.execute(
        select(AccountHoliday).where(
            AccountHoliday.tenant_id == office.tenant_id,
            or_(AccountHoliday.office_id == office.id, AccountHoliday.office_id.is_(None)),
        )
    ).scalars().all()
    out: dict[date, list[AccountHoliday]] = {}
    span = (end - start).days + 1
    for h in rows:
        if h.is_recurring:
            for i in range(span):
                d = start + timedelta(days=i)
                if (d.month, d.day) == (h.holiday_date.month, h.holiday_date.day):
                    out.setdefault(d, []).append(h)
        elif start <= h.holiday_date <= end:
            out.setdefault(h.holiday_date, []).append(h)
    return out


def _week(db: Session, office_id: int) -> dict[int, OfficeScheduleDay]:
    return {r.day_of_week: r for r in db.execute(
        select(OfficeScheduleDay).where(OfficeScheduleDay.office_id == office_id)
    ).scalars().all()}


def _default_window(office: Office, weekday: int) -> dict:
    # Mirrors the Schedule tab's unsaved default (office_setup_service.default_schedule_day).
    if weekday >= 5:
        return {"is_closed": True, "start": None, "end": None, "lunch_start": None, "lunch_end": None}
    return {"is_closed": False, "start": time(8, 0), "end": time(17, 0), "lunch_start": None, "lunch_end": None}


def _day(office: Office, d: date, week: dict[int, OfficeScheduleDay], hols: list[AccountHoliday]) -> dict:
    row = week.get(d.weekday())
    if row is not None:
        w = {"is_closed": bool(row.is_closed) or row.start_time is None or row.end_time is None,
             "start": row.start_time, "end": row.end_time,
             "lunch_start": row.lunch_start, "lunch_end": row.lunch_end}
        source = "stored"
    else:
        w = _default_window(office, d.weekday())
        source = "default"
    holiday_rows = [
        {"id": h.id, "name": h.holiday_name, "status": (h.status or "CLOSED").upper(),
         "holiday_type": h.holiday_type, "office_id": h.office_id}
        for h in hols
    ]
    # An office-level row beats the account-level one for the same date.
    effective = sorted(holiday_rows, key=lambda h: h["office_id"] is None)[0] if holiday_rows else None
    holiday_closed = bool(effective and effective["status"] in CLOSING_STATUSES)
    is_open = not w["is_closed"] and not holiday_closed
    return {
        "date": d.isoformat(),
        "day_of_week": d.weekday(),
        "is_open": is_open,
        "hours_source": source,
        "hours_enforced": source == "stored",
        "start_time": _fmt(w["start"]) if not w["is_closed"] else None,
        "end_time": _fmt(w["end"]) if not w["is_closed"] else None,
        "lunch_start": _fmt(w["lunch_start"]) if not w["is_closed"] else None,
        "lunch_end": _fmt(w["lunch_end"]) if not w["is_closed"] else None,
        "closed_reason": None if is_open else ("holiday" if holiday_closed else "closed_day"),
        "holiday": effective,
        "holidays": holiday_rows,
        "_window": w,
    }


def calendar(db: Session, office: Office, from_date: date, to_date: date) -> dict:
    if to_date < from_date:
        raise ValidationError("to_date must be on or after from_date", code="invalid_date_range")
    if (to_date - from_date).days + 1 > MAX_RANGE_DAYS:
        raise ValidationError(f"The range may span at most {MAX_RANGE_DAYS} days", code="date_range_too_long")
    week = _week(db, office.id)
    hols = _holidays(db, office, from_date, to_date)
    days = []
    for i in range((to_date - from_date).days + 1):
        d = from_date + timedelta(days=i)
        day = _day(office, d, week, hols.get(d, []))
        day.pop("_window")
        days.append(day)
    return {
        "office_id": office.id,
        "timezone": office.timezone,
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "schedule_configured": bool(week),
        "enforced": settings.OFFICE_HOURS_ENFORCED,
        "days": days,
    }


def booking_conflicts(db: Session, office: Office, d: date, start: time, end: time) -> list[dict]:
    """Why ``[start, end)`` on ``d`` is not bookable at ``office``; empty = fine."""
    day = _day(office, d, _week(db, office.id), _holidays(db, office, d, d).get(d, []))
    w = day["_window"]
    out: list[dict] = []
    hol = day["holiday"]
    if hol and hol["status"] in CLOSING_STATUSES:
        out.append({"kind": "holiday", "message": f"The office is closed for {hol['name']}",
                    "holiday": hol})
    if not day["hours_enforced"]:
        return out
    if w["is_closed"]:
        out.append({"kind": "closed_day", "message": "The office is closed on this day"})
        return out
    if start < w["start"] or end > w["end"]:
        out.append({"kind": "outside_hours",
                    "message": f"Office hours are {_fmt(w['start'])}–{_fmt(w['end'])}",
                    "start_time": _fmt(w["start"]), "end_time": _fmt(w["end"])})
    ls, le = w["lunch_start"], w["lunch_end"]
    if ls and le and start < le and ls < end:
        out.append({"kind": "lunch", "message": f"Overlaps lunch {_fmt(ls)}–{_fmt(le)}",
                    "lunch_start": _fmt(ls), "lunch_end": _fmt(le)})
    return out


def enforce_booking(
    db: Session, office_id: int | None, d: date | None, start: time | None, end: time | None,
    *, allow: bool,
) -> None:
    """409 ``office_closed`` for a booking into a closed slot, unless overridden."""
    if allow or not settings.OFFICE_HOURS_ENFORCED or None in (office_id, d, start, end):
        return
    office = db.get(Office, office_id)
    if office is None:
        return
    reasons = booking_conflicts(db, office, d, start, end)
    if reasons:
        raise ConflictError(
            reasons[0]["message"], code="office_closed",
            details={"code": "office_closed", "office_id": office_id, "date": d.isoformat(),
                     "reasons": reasons, "override_field": "allow_outside_office_hours"},
        )
