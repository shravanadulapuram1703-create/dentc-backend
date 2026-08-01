"""AppointNow service: public office info, availability, request intake, and the
staff approve/decline transitions.

The **availability** computation mirrors the frontend reference
(`src/features/appointnow/lib/availability.ts`):

1. office per-day working window (``office_schedule_days``, minus lunch, honouring
   ``is_closed``; falls back to the office ``schedule_start_hour``/``end_hour``);
2. intersect the provider's window (``provider_schedule_days``) when a provider is
   in play;
3. drop office/tenant holidays (``account_holidays``) and provider holidays
   (``provider_holidays``);
4. slice into ``office.slot_interval_minutes`` steps that fit ``duration_minutes``;
5. subtract already-booked appointments **and active soft-holds** (AN-8), honouring
   per-provider / per-operatory capacity;
6. for *today* (office-local, AN-10) drop slots that already started.

Everything on the public path resolves the tenant from ``office_code`` (unique) —
there is no JWT — and never raises 401 (AN-12): the errors are 404 (unknown/
disabled office), 409 (slot taken), 422 (bad input), 429 (rate-limited).
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from app.core.ids import uuid7
from app.core.logging import get_logger
from app.db.models import (
    AccountHoliday,
    Appointment,
    AppointNowReason,
    BookingRequest,
    Office,
    Operatory,
    Patient,
    Provider,
    ProviderHoliday,
    ProviderScheduleDay,
)
from app.db.models.office_setup import OfficeScheduleDay
from app.integrations import redis_store
from app.services.patient_service import PatientCRUD

logger = get_logger(__name__)

_patient_crud = PatientCRUD(Patient)

# Built-in reason catalog served when an office has customised none. Mirrors the
# frontend ``APPOINTMENT_REASONS`` fallback so a fresh office still books.
_DEFAULT_REASONS: tuple[dict, ...] = (
    {"id": "new_patient", "label": "New Patient Exam", "duration_minutes": 60},
    {"id": "cleaning", "label": "Cleaning / Hygiene", "duration_minutes": 60},
    {"id": "checkup", "label": "Checkup / Recall", "duration_minutes": 30},
    {"id": "emergency", "label": "Emergency / Tooth Pain", "duration_minutes": 30},
    {"id": "consultation", "label": "Consultation", "duration_minutes": 30},
    {"id": "other", "label": "Other", "duration_minutes": 30},
)
_DEFAULT_DURATION = 60


# ── formatting helpers ───────────────────────────────────────────────────────
def _fmt_time(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t is not None else None


def _parse_time(value: str) -> time:
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).time()
        except (ValueError, AttributeError):
            continue
    raise ValidationError(f"Invalid time '{value}' (expected HH:MM)", code="bad_time")


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        raise ValidationError(f"Invalid date '{value}' (expected YYYY-MM-DD)", code="bad_date")


def _office_tz(office: Office) -> ZoneInfo:
    try:
        return ZoneInfo(office.timezone or "America/New_York")
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("America/New_York")


def _office_now(office: Office) -> datetime:
    """Wall-clock 'now' in the office's own timezone (naive, to compare with the
    naive ``date``/``time`` columns)."""
    return datetime.now(_office_tz(office)).replace(tzinfo=None)


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _add_minutes(base: time, minutes: int) -> time:
    total = _minutes(base) + minutes
    total = max(0, min(total, 24 * 60))
    return time(hour=total // 60 % 24, minute=total % 60) if total < 24 * 60 else time(23, 59)


def _overlaps(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    return a_start < b_end and b_start < a_end


# ── office resolution (public: tenant from office_code) ──────────────────────
def resolve_public_office(db: Session, office_code: str) -> Office:
    """Resolve an *active* office from its (globally unique) code. 404 otherwise
    — never 401, so an anonymous visitor never gets redirected to /login (AN-12)."""
    office = db.execute(
        select(Office).where(func.lower(Office.office_code) == office_code.strip().lower())
    ).scalar_one_or_none()
    if office is None or not office.is_active:
        raise NotFoundError("This booking page is not available", code="office_not_found")
    return office


def _visible_providers(db: Session, office: Office) -> list[Provider]:
    return list(
        db.execute(
            select(Provider)
            .where(
                Provider.office_id == office.id,
                Provider.tenant_id == office.tenant_id,
                Provider.is_active.is_(True),
                Provider.visible_in_appointnow.is_(True),
            )
            .order_by(Provider.name.asc(), Provider.id.asc())
        )
        .scalars()
        .all()
    )


def _office_reasons(db: Session, office: Office) -> list[dict]:
    rows = list(
        db.execute(
            select(AppointNowReason)
            .where(
                AppointNowReason.office_id == office.id,
                AppointNowReason.tenant_id == office.tenant_id,
                AppointNowReason.is_active.is_(True),
            )
            .order_by(AppointNowReason.display_order.asc(), AppointNowReason.id.asc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return [dict(r, requires_provider=False) for r in _DEFAULT_REASONS]
    return [
        {
            "id": r.reason_code,
            "label": r.label,
            "duration_minutes": r.duration_minutes,
            "requires_provider": r.requires_provider,
        }
        for r in rows
    ]


def _reason_duration(reasons: list[dict], reason_id: str | None) -> int | None:
    if reason_id is None:
        return None
    for r in reasons:
        if r["id"] == reason_id:
            return r["duration_minutes"]
    return None


def get_public_office_info(db: Session, office_code: str) -> dict:
    """AN-1: public-safe branding + AppointNow-visible providers + reason catalog."""
    office = resolve_public_office(db, office_code)
    address = ", ".join(
        p for p in (office.address_line1, office.city, office.state, office.zip) if p
    )
    return {
        "office_code": office.office_code,
        "office_id": office.id,
        "name": office.name,  # human office name only — never the code/id (AN-1)
        "timezone": office.timezone or "America/New_York",
        "phone": office.phone,
        "address": address or None,
        "providers": [
            {"id": p.id, "name": p.name, "title": p.title}
            for p in _visible_providers(db, office)
        ],
        "reasons": _office_reasons(db, office),
    }


# ── holidays & schedule windows ──────────────────────────────────────────────
def _is_office_closed_holiday(db: Session, office: Office, day: date) -> bool:
    """True if an account/office holiday closes the office on ``day``."""
    rows = db.execute(
        select(AccountHoliday.status, AccountHoliday.holiday_date, AccountHoliday.is_recurring)
        .where(
            AccountHoliday.tenant_id == office.tenant_id,
            or_(AccountHoliday.office_id == office.id, AccountHoliday.office_id.is_(None)),
        )
    ).all()
    for status_, hdate, recurring in rows:
        if _holiday_hits(hdate, recurring, day) and _closed(status_):
            return True
    return False


def _provider_holiday_dates(db: Session, provider_ids: list[str], day: date) -> set[str]:
    """Providers on holiday (closed) on ``day``."""
    if not provider_ids:
        return set()
    rows = db.execute(
        select(
            ProviderHoliday.provider_id,
            ProviderHoliday.status,
            ProviderHoliday.holiday_date,
            ProviderHoliday.is_recurring,
        ).where(ProviderHoliday.provider_id.in_(provider_ids))
    ).all()
    return {
        pid
        for pid, status_, hdate, recurring in rows
        if _holiday_hits(hdate, recurring, day) and _closed(status_)
    }


def _holiday_hits(hdate: date, recurring: bool, day: date) -> bool:
    if hdate == day:
        return True
    return bool(recurring) and hdate.month == day.month and hdate.day == day.day


def _closed(status_: str | None) -> bool:
    # A holiday closes the day unless it is explicitly flagged OPEN.
    return (status_ or "CLOSED").strip().upper() != "OPEN"


class _Window:
    """A day's bookable window with an optional lunch cut-out."""

    __slots__ = ("start", "end", "lunch_start", "lunch_end", "closed")

    def __init__(self, start, end, lunch_start=None, lunch_end=None, closed=False):
        self.start = start
        self.end = end
        self.lunch_start = lunch_start
        self.lunch_end = lunch_end
        self.closed = closed

    def fits(self, s: time, e: time) -> bool:
        if self.closed or self.start is None or self.end is None:
            return False
        if s < self.start or e > self.end:
            return False
        if self.lunch_start and self.lunch_end and _overlaps(s, e, self.lunch_start, self.lunch_end):
            return False
        return True


def _office_window(db: Session, office: Office, weekday: int) -> _Window:
    row = db.execute(
        select(OfficeScheduleDay).where(
            OfficeScheduleDay.office_id == office.id,
            OfficeScheduleDay.day_of_week == weekday,
        )
    ).scalar_one_or_none()
    if row is None:
        # Fallback: office-level default hours (identity.Office.schedule_start/end_hour).
        return _Window(time(office.schedule_start_hour or 8), time(office.schedule_end_hour or 17))
    if row.is_closed or row.start_time is None or row.end_time is None:
        return _Window(None, None, closed=True)
    return _Window(row.start_time, row.end_time, row.lunch_start, row.lunch_end)


def _provider_window(
    db: Session, provider_id: str, office_id: int, weekday: int, day: date, office_window: _Window
) -> _Window:
    """Provider hours for the day, most-specific row first (office-specific over
    all-office, latest ``effective_from`` that is on/before ``day``). Falls back to
    the office window when the provider has no configured hours."""
    rows = list(
        db.execute(
            select(ProviderScheduleDay).where(
                ProviderScheduleDay.provider_id == provider_id,
                ProviderScheduleDay.day_of_week == weekday,
                or_(
                    ProviderScheduleDay.office_id == office_id,
                    ProviderScheduleDay.office_id.is_(None),
                ),
            )
        )
        .scalars()
        .all()
    )
    rows = [r for r in rows if r.effective_from is None or r.effective_from <= day]
    if not rows:
        return office_window
    rows.sort(
        key=lambda r: (r.office_id is not None, r.effective_from or date.min),
        reverse=True,
    )
    row = rows[0]
    if row.is_closed or row.start_time is None or row.end_time is None:
        return _Window(None, None, closed=True)
    # Intersect with the office window so a provider can't be booked outside office hours.
    start = max(row.start_time, office_window.start) if office_window.start else row.start_time
    end = min(row.end_time, office_window.end) if office_window.end else row.end_time
    return _Window(start, end, row.lunch_start, row.lunch_end)


# ── availability (AN-2) ──────────────────────────────────────────────────────
def _booked_ranges(
    db: Session, office_id: int, day: date
) -> tuple[dict[str, list[tuple[time, time]]], list[tuple[time, time]]]:
    """Return (per-provider booked ranges, all booked ranges) for the day —
    active appointments only (not archived/cancelled)."""
    rows = db.execute(
        select(Appointment.provider_id, Appointment.start_time, Appointment.end_time).where(
            Appointment.office_id == office_id,
            Appointment.date == day,
            Appointment.is_archived.is_(False),
            Appointment.is_cancelled.is_(False),
        )
    ).all()
    per_provider: dict[str, list[tuple[time, time]]] = {}
    every: list[tuple[time, time]] = []
    for pid, s, e in rows:
        if s is None or e is None:
            continue
        per_provider.setdefault(pid, []).append((s, e))
        every.append((s, e))
    return per_provider, every


def _held_ranges(
    db: Session, office: Office, day: date, now: datetime, exclude_request_id: str | None = None
) -> tuple[dict[str, list[tuple[time, time]]], list[tuple[time, time]]]:
    """Active soft-holds (AN-8): pending requests whose hold has not expired."""
    stmt = select(
        BookingRequest.id,
        BookingRequest.provider_id,
        BookingRequest.start_time,
        BookingRequest.end_time,
    ).where(
        BookingRequest.office_id == office.id,
        BookingRequest.slot_date == day,
        BookingRequest.status == "pending",
        BookingRequest.hold_expires_at.isnot(None),
        BookingRequest.hold_expires_at > now,
    )
    per_provider: dict[str, list[tuple[time, time]]] = {}
    every: list[tuple[time, time]] = []
    for rid, pid, s, e in db.execute(stmt).all():
        if rid == exclude_request_id or s is None or e is None:
            continue
        if pid:
            per_provider.setdefault(pid, []).append((s, e))
        every.append((s, e))
    return per_provider, every


def compute_availability(
    db: Session,
    office: Office,
    *,
    day: date,
    provider_id: str | None,
    duration_minutes: int,
) -> list[dict]:
    """Core slot engine. Returns bookable slots as serialisable dicts."""
    expire_stale_requests(db, [office])

    weekday = day.weekday()  # 0=Mon..6=Sun (matches the schedule tables)
    office_window = _office_window(db, office, weekday)
    if office_window.closed or office_window.start is None:
        return []
    if _is_office_closed_holiday(db, office, day):
        return []

    now = _office_now(office)
    if day < now.date():
        return []
    drop_before = now.time() if day == now.date() else None

    step = max(office.slot_interval_minutes or 15, 5)
    duration = max(duration_minutes, step)

    all_providers = _visible_providers(db, office)
    if provider_id is not None:
        candidates = [p for p in all_providers if p.id == provider_id]
        if not candidates:
            # Requested provider isn't offered for online booking → no slots.
            return []
    else:
        candidates = all_providers

    booked_by_provider, booked_all = _booked_ranges(db, office.id, day)
    held_by_provider, held_all = _held_ranges(db, office, day, now)
    holiday_providers = _provider_holiday_dates(db, [p.id for p in candidates], day)

    # Per-provider windows (only for candidate providers).
    provider_windows = {
        p.id: _provider_window(db, p.id, office.id, weekday, day, office_window)
        for p in candidates
    }

    # Capacity when no provider is offered/requested: number of active chairs.
    if not candidates:
        operatory_count = db.execute(
            select(func.count())
            .select_from(Operatory)
            .where(Operatory.office_id == office.id, Operatory.is_active.is_(True))
        ).scalar_one()
        capacity = max(int(operatory_count or 0), 1)

    slots: list[dict] = []
    cursor = office_window.start
    while True:
        end = _add_minutes(cursor, duration)
        if _minutes(end) - _minutes(cursor) < duration or end <= cursor:
            break
        if _minutes(end) > _minutes(office_window.end):
            break
        if drop_before is not None and cursor <= drop_before:
            cursor = _add_minutes(cursor, step)
            continue

        chosen = _first_free_provider(
            cursor,
            end,
            candidates,
            provider_windows,
            booked_by_provider,
            held_by_provider,
            holiday_providers,
        )
        if candidates:
            if chosen is not None:
                slots.append(_slot_dict(day, cursor, end, duration, chosen))
        else:
            # No AppointNow providers configured: fall back to office-chair capacity.
            if office_window.fits(cursor, end):
                busy = sum(1 for s, e in booked_all if _overlaps(cursor, end, s, e))
                busy += sum(1 for s, e in held_all if _overlaps(cursor, end, s, e))
                if busy < capacity:
                    slots.append(_slot_dict(day, cursor, end, duration, None))

        cursor = _add_minutes(cursor, step)

    return slots


def _first_free_provider(
    s: time,
    e: time,
    candidates: list[Provider],
    windows: dict[str, _Window],
    booked: dict[str, list[tuple[time, time]]],
    held: dict[str, list[tuple[time, time]]],
    holiday_providers: set[str],
) -> Provider | None:
    for p in candidates:
        if p.id in holiday_providers:
            continue
        window = windows.get(p.id)
        if window is None or not window.fits(s, e):
            continue
        if any(_overlaps(s, e, bs, be) for bs, be in booked.get(p.id, ())):
            continue
        if any(_overlaps(s, e, hs, he) for hs, he in held.get(p.id, ())):
            continue
        return p
    return None


def _slot_dict(day: date, s: time, e: time, duration: int, provider: Provider | None) -> dict:
    return {
        "date": day.strftime("%Y-%m-%d"),
        "start_time": _fmt_time(s),
        "end_time": _fmt_time(e),
        "duration_minutes": duration,
        "provider_id": provider.id if provider else None,
        "provider_name": provider.name if provider else None,
    }


def get_availability(
    db: Session,
    office_code: str,
    *,
    date_str: str,
    provider_id: str | None,
    duration_minutes: int | None,
) -> dict:
    office = resolve_public_office(db, office_code)
    day = _parse_date(date_str)
    duration = duration_minutes or _DEFAULT_DURATION
    # Cheap short-TTL cache (AN-2): identical public queries hit Redis, not the DB.
    cache_key = f"appointnow:avail:{office.id}:{day}:{provider_id or '-'}:{duration}"
    cached = redis_store.cache_get(cache_key)
    if cached is not None:
        try:
            return {"slots": json.loads(cached), "timezone": office.timezone or "America/New_York"}
        except ValueError:
            pass
    slots = compute_availability(
        db, office, day=day, provider_id=provider_id, duration_minutes=duration
    )
    redis_store.cache_set(
        cache_key, json.dumps(slots), settings.APPOINTNOW_AVAILABILITY_CACHE_SECONDS
    )
    return {"slots": slots, "timezone": office.timezone or "America/New_York"}


# ── request intake (AN-3) ────────────────────────────────────────────────────
def _rate_limit(office_id: int, ip: str | None) -> None:
    """Per-IP/office throttle for the public write. Degrades open when Redis is off."""
    if not ip:
        return
    key = f"appointnow:rl:{office_id}:{ip}"
    window = settings.APPOINTNOW_RATE_LIMIT_WINDOW_MINUTES * 60
    count = redis_store.incr_counter(key, window)
    if count is not None and count > settings.APPOINTNOW_RATE_LIMIT_MAX:
        raise RateLimitError(
            "Too many booking requests from this device. Please try again later.",
            code="appointnow_rate_limited",
        )


def _verify_turnstile(token: str | None, ip: str | None) -> None:
    """Cloudflare Turnstile verification — enforced only when a secret is configured
    (so dev/tests without a secret are unaffected). Network failures fail-open so a
    Cloudflare outage can't take booking down; a *rejected* token fails-closed."""
    secret = settings.APPOINTNOW_TURNSTILE_SECRET
    if not secret:
        return
    if not token:
        raise ForbiddenError("Human verification required", code="captcha_required")
    import urllib.error
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode(
        {k: v for k, v in {"secret": secret, "response": token, "remoteip": ip}.items() if v}
    ).encode()
    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed Cloudflare endpoint
            urllib.request.Request(settings.APPOINTNOW_TURNSTILE_VERIFY_URL, data=data),
            timeout=5,
        ) as resp:
            result = json.loads(resp.read().decode())
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:  # noqa: BLE001
        logger.warning("Turnstile verify unreachable, allowing request: %s", exc)
        return
    if not result.get("success"):
        raise ForbiddenError("Human verification failed", code="captcha_failed")


def submit_request(
    db: Session, office_code: str, payload, *, source_ip: str | None
) -> BookingRequest:
    office = resolve_public_office(db, office_code)
    _rate_limit(office.id, source_ip)
    _verify_turnstile(payload.turnstile_token, source_ip)

    reasons = _office_reasons(db, office)
    day = _parse_date(payload.slot.date)
    start = _parse_time(payload.slot.start_time)
    duration = (
        _reason_duration(reasons, payload.reason_id)
        or payload.slot.duration_minutes
        or _DEFAULT_DURATION
    )
    end = _parse_time(payload.slot.end_time) if payload.slot.end_time else _add_minutes(start, duration)
    provider_id = payload.slot.provider_id or None

    # AN-3: validate the slot is still open at submit time (re-run the engine).
    open_slots = compute_availability(
        db, office, day=day, provider_id=provider_id, duration_minutes=duration
    )
    start_str = _fmt_time(start)
    match = next((s for s in open_slots if s["start_time"] == start_str), None)
    if match is None:
        raise ConflictError(
            "That time was just taken. Please pick another slot.", code="slot_unavailable"
        )
    # Adopt the provider the engine actually assigned (matters when none was requested).
    resolved_provider_id = match.get("provider_id") or provider_id
    resolved_provider_name = match.get("provider_name") or payload.slot.provider_name

    contact = payload.contact
    req = BookingRequest(
        id=str(uuid7()),
        tenant_id=office.tenant_id,
        office_id=office.id,
        status="pending",
        reason_id=payload.reason_id,
        reason_label=payload.reason_label or _reason_label(reasons, payload.reason_id),
        duration_minutes=duration,
        provider_id=resolved_provider_id,
        provider_name=resolved_provider_name,
        slot_date=day,
        start_time=start,
        end_time=end,
        first_name=contact.first_name,
        last_name=contact.last_name,
        phone=contact.phone,
        email=contact.email,
        date_of_birth=contact.date_of_birth,
        is_new_patient=contact.is_new_patient,
        notes=contact.notes,
        hold_expires_at=_office_now(office)
        + timedelta(minutes=settings.APPOINTNOW_HOLD_TTL_MINUTES),
        source_ip=source_ip,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    _invalidate_availability_cache(office.id, day)
    notify_new_request(office, req)
    return req


def _reason_label(reasons: list[dict], reason_id: str | None) -> str | None:
    for r in reasons:
        if r["id"] == reason_id:
            return r["label"]
    return None


# ── staff inbox (AN-4 / AN-13) ───────────────────────────────────────────────
_VALID_STATUSES = {"pending", "approved", "declined", "expired"}
_SORTS = {
    "created_desc": (BookingRequest.created_at.desc(), BookingRequest.id.desc()),
    "created_asc": (BookingRequest.created_at.asc(), BookingRequest.id.asc()),
    "slot_asc": (BookingRequest.slot_date.asc(), BookingRequest.start_time.asc()),
    "slot_desc": (BookingRequest.slot_date.desc(), BookingRequest.start_time.desc()),
}


def list_requests(
    db: Session,
    tenant_id: int,
    *,
    status: str | None = None,
    office_id: int | None = None,
    q: str | None = None,
    reason_id: str | None = None,
    reason_label: str | None = None,
    is_new_patient: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = "created_desc",
    page: int = 1,
    size: int = 20,
) -> dict:
    expire_stale_requests(db, _tenant_offices(db, tenant_id, office_id))

    base = select(BookingRequest).where(BookingRequest.tenant_id == tenant_id)
    if office_id is not None:
        base = base.where(BookingRequest.office_id == office_id)

    # Filters that apply to the returned page (status is one of them).
    filtered = base
    if status is not None:
        if status not in _VALID_STATUSES:
            raise ValidationError(f"Unknown status '{status}'", code="bad_status")
        filtered = filtered.where(BookingRequest.status == status)
    if reason_id is not None:
        filtered = filtered.where(BookingRequest.reason_id == reason_id)
    if reason_label is not None:
        filtered = filtered.where(BookingRequest.reason_label == reason_label)
    if is_new_patient is not None:
        filtered = filtered.where(BookingRequest.is_new_patient.is_(is_new_patient))
    if date_from is not None:
        filtered = filtered.where(BookingRequest.slot_date >= date_from)
    if date_to is not None:
        filtered = filtered.where(BookingRequest.slot_date <= date_to)
    if q:
        term = f"%{q.strip()}%"
        filtered = filtered.where(
            or_(
                BookingRequest.first_name.ilike(term),
                BookingRequest.last_name.ilike(term),
                BookingRequest.phone.ilike(term),
                BookingRequest.email.ilike(term),
                BookingRequest.reason_label.ilike(term),
                BookingRequest.id.ilike(term),
            )
        )

    total = db.execute(
        select(func.count()).select_from(filtered.subquery())
    ).scalar_one()

    order = _SORTS.get(sort, _SORTS["created_desc"])
    rows = list(
        db.execute(
            filtered.order_by(*order).offset((page - 1) * size).limit(size)
        )
        .scalars()
        .all()
    )

    # AN-13: unfiltered per-status counts (respecting only the office scope) so the
    # tab badges stay accurate independent of the active filter.
    count_conditions = [BookingRequest.tenant_id == tenant_id]
    if office_id is not None:
        count_conditions.append(BookingRequest.office_id == office_id)
    count_rows = db.execute(
        select(BookingRequest.status, func.count())
        .where(*count_conditions)
        .group_by(BookingRequest.status)
    ).all()
    counts = {s: 0 for s in _VALID_STATUSES}
    for st, n in count_rows:
        counts[st] = int(n)
    counts["all"] = sum(counts[s] for s in _VALID_STATUSES)

    return {
        "items": rows,
        "counts": counts,
        "page": page,
        "size": size,
        "total": int(total),
    }


def get_request(db: Session, tenant_id: int, request_id: str) -> BookingRequest:
    req = db.get(BookingRequest, request_id)
    if req is None or req.tenant_id != tenant_id:
        raise NotFoundError(f"Booking request '{request_id}' was not found")
    return req


# ── duplicate-patient matching (AN-9) ────────────────────────────────────────
def find_patient_matches(db: Session, tenant_id: int, req: BookingRequest) -> list[dict]:
    """Match the request contact against existing patients by phone/email/DOB."""
    clauses = []
    if req.phone:
        digits = _digits(req.phone)
        if digits:
            clauses.append(func.replace(func.replace(func.replace(func.replace(
                Patient.phone, "-", ""), " ", ""), "(", ""), ")", "").ilike(f"%{digits}%"))
    if req.email:
        clauses.append(func.lower(Patient.email) == req.email.strip().lower())
    if not clauses:
        return []
    rows = list(
        db.execute(
            select(Patient)
            .where(Patient.tenant_id == tenant_id, or_(*clauses))
            .limit(25)
        )
        .scalars()
        .all()
    )
    matches: list[dict] = []
    for p in rows:
        match_on: list[str] = []
        if req.phone and p.phone and _digits(p.phone) and _digits(req.phone) in _digits(p.phone):
            match_on.append("phone")
        if req.email and p.email and p.email.strip().lower() == req.email.strip().lower():
            match_on.append("email")
        if req.date_of_birth and p.dob == req.date_of_birth:
            match_on.append("dob")
        if not match_on:
            continue
        matches.append(
            {
                "patient_id": p.id,
                "chart_no": p.chart_no,
                "name": ", ".join(x for x in (p.last_name, p.first_name) if x) or None,
                "phone": p.phone,
                "email": p.email,
                "dob": p.dob,
                "match_on": match_on,
            }
        )
    # Strongest matches first (more corroborating fields = higher confidence).
    matches.sort(key=lambda m: len(m["match_on"]), reverse=True)
    return matches


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


# ── approve / decline (AN-5) ─────────────────────────────────────────────────
def _appointment_conflict(
    db: Session, office_id: int, provider_id: str | None, operatory_id: str | None,
    day: date, start: time, end: time,
) -> bool:
    """A hard conflict for booking: an existing active appointment overlaps the
    same provider or the same operatory."""
    if provider_id is None and operatory_id is None:
        return False
    rows = db.execute(
        select(Appointment.provider_id, Appointment.operatory_id,
               Appointment.start_time, Appointment.end_time).where(
            Appointment.office_id == office_id,
            Appointment.date == day,
            Appointment.is_archived.is_(False),
            Appointment.is_cancelled.is_(False),
        )
    ).all()
    for pid, oid, s, e in rows:
        if s is None or e is None or not _overlaps(start, end, s, e):
            continue
        if provider_id is not None and pid == provider_id:
            return True
        if operatory_id is not None and oid == operatory_id:
            return True
    return False


def _resolve_provider_for_booking(
    db: Session, office: Office, req: BookingRequest, override: str | None
) -> Provider | None:
    pid = override or req.provider_id
    if pid:
        p = db.get(Provider, pid)
        if p is None or p.office_id != office.id or p.tenant_id != office.tenant_id:
            raise ValidationError(f"Provider '{pid}' is not valid for this office",
                                  code="bad_provider")
        return p
    visible = _visible_providers(db, office)
    if visible:
        return visible[0]
    # No AppointNow-visible provider on the request: fall back to any active provider
    # in the office so the appointment (provider_id is NOT NULL) can still be booked.
    return db.execute(
        select(Provider)
        .where(
            Provider.office_id == office.id,
            Provider.tenant_id == office.tenant_id,
            Provider.is_active.is_(True),
        )
        .order_by(Provider.name.asc(), Provider.id.asc())
    ).scalars().first()


def _resolve_operatory_for_booking(
    db: Session, office: Office, provider_id: str | None, override: str | None
) -> str | None:
    if override:
        op = db.get(Operatory, override)
        if op is None or op.office_id != office.id:
            raise ValidationError(f"Operatory '{override}' is not valid for this office",
                                  code="bad_operatory")
        return op.id
    if provider_id:
        op = db.execute(
            select(Operatory).where(
                Operatory.office_id == office.id,
                Operatory.provider_id == provider_id,
                Operatory.is_active.is_(True),
            ).order_by(Operatory.display_order.asc())
        ).scalars().first()
        if op is not None:
            return op.id
    op = db.execute(
        select(Operatory).where(
            Operatory.office_id == office.id, Operatory.is_active.is_(True)
        ).order_by(Operatory.display_order.asc())
    ).scalars().first()
    return op.id if op is not None else None


def _resolve_patient_for_booking(
    db: Session, office: Office, req: BookingRequest, body, actor_id: int | None
) -> int | None:
    if body.patient_id is not None:
        p = db.get(Patient, body.patient_id)
        if p is None or p.tenant_id != office.tenant_id:
            raise ValidationError("Selected patient is not valid", code="bad_patient")
        return p.id
    if not body.create_patient:
        return None  # book with patient_id=null; contact carried in the label/notes
    matches = find_patient_matches(db, office.tenant_id, req)
    if len(matches) == 1:
        return matches[0]["patient_id"]  # single confident match → link it (AN-9)
    patient = _patient_crud.create(
        db,
        {
            "home_office_id": office.id,
            "first_name": req.first_name,
            "last_name": req.last_name,
            "phone": req.phone,
            "email": req.email,
            "dob": req.date_of_birth,
        },
        tenant_id=office.tenant_id,
        created_by=actor_id,
    )
    return patient.id


def approve_request(
    db: Session, tenant_id: int, request_id: str, body, *, actor_id: int | None
) -> BookingRequest:
    """AN-5: re-check the slot, book the appointment, link it, mark approved — all
    in one transaction."""
    req = get_request(db, tenant_id, request_id)
    if req.status != "pending":
        raise ConflictError(
            f"Request is already {req.status}", code="request_not_pending"
        )
    office = db.get(Office, req.office_id)
    if office is None or office.tenant_id != tenant_id:
        raise ForbiddenError("Request does not belong to the authenticated tenant")

    provider = _resolve_provider_for_booking(db, office, req, body.provider_id)
    if provider is None:
        # appointments.provider_id is NOT NULL — can't book without one.
        raise ValidationError(
            "This office has no provider to book the appointment against.",
            code="no_provider",
        )
    provider_id = provider.id
    operatory_id = _resolve_operatory_for_booking(db, office, provider_id, body.operatory_id)

    if _appointment_conflict(
        db, office.id, provider_id, operatory_id, req.slot_date, req.start_time, req.end_time
    ):
        raise ConflictError(
            "That slot was booked by someone else. Decline or pick a new time.",
            code="slot_conflict",
        )

    patient_id = _resolve_patient_for_booking(db, office, req, body, actor_id)

    duration = _minutes(req.end_time) - _minutes(req.start_time)
    contact_label = " ".join(x for x in (req.first_name, req.last_name) if x).strip()
    note_lines = [f"AppointNow request {req.id}"]
    if contact_label:
        note_lines.append(f"Contact: {contact_label}")
    if req.phone:
        note_lines.append(f"Phone: {req.phone}")
    if req.email:
        note_lines.append(f"Email: {req.email}")
    if req.notes:
        note_lines.append(f"Notes: {req.notes}")

    appt = Appointment(
        id=f"AN{uuid7().hex[:22]}",
        patient_id=patient_id,
        provider_id=provider_id,
        operatory_id=operatory_id,
        office_id=office.id,
        date=req.slot_date,
        start_time=req.start_time,
        end_time=req.end_time,
        duration=max(duration, 0),
        status="Scheduled",
        is_new_patient=req.is_new_patient,
        procedure_label=req.reason_label,
        notes="\n".join(note_lines),
        created_by=actor_id,
    )
    db.add(appt)

    req.status = "approved"
    req.appointment_id = appt.id
    req.patient_id = patient_id
    req.actioned_by = actor_id
    req.actioned_at = datetime.utcnow()
    req.hold_expires_at = None
    db.commit()
    db.refresh(req)
    _invalidate_availability_cache(office.id, req.slot_date)
    notify_updated_request(office, req)
    return req


def decline_request(
    db: Session, tenant_id: int, request_id: str, reason: str | None, *, actor_id: int | None
) -> BookingRequest:
    req = get_request(db, tenant_id, request_id)
    if req.status not in {"pending", "expired"}:
        raise ConflictError(f"Request is already {req.status}", code="request_not_pending")
    office = db.get(Office, req.office_id)
    req.status = "declined"
    req.decline_reason = reason
    req.actioned_by = actor_id
    req.actioned_at = datetime.utcnow()
    req.hold_expires_at = None
    db.commit()
    db.refresh(req)
    if office is not None:
        _invalidate_availability_cache(office.id, req.slot_date)
        notify_updated_request(office, req)
    return req


# ── expiry sweep (AN-8) ──────────────────────────────────────────────────────
def _tenant_offices(db: Session, tenant_id: int, office_id: int | None) -> list[Office]:
    stmt = select(Office).where(Office.tenant_id == tenant_id)
    if office_id is not None:
        stmt = stmt.where(Office.id == office_id)
    return list(db.execute(stmt).scalars().all())


def expire_stale_requests(db: Session, offices: list[Office]) -> None:
    """Flip pending requests whose slot datetime has passed to ``expired`` so the
    inbox and availability stay truthful. Best-effort; never raises."""
    if not offices:
        return
    changed = False
    try:
        for office in offices:
            now = _office_now(office)
            pending = list(
                db.execute(
                    select(BookingRequest).where(
                        BookingRequest.office_id == office.id,
                        BookingRequest.status == "pending",
                    )
                )
                .scalars()
                .all()
            )
            for req in pending:
                slot_dt = datetime.combine(req.slot_date, req.start_time)
                if slot_dt < now:
                    req.status = "expired"
                    req.hold_expires_at = None
                    changed = True
        if changed:
            db.commit()
    except Exception as exc:  # noqa: BLE001 - a sweep must never break the request
        logger.warning("AppointNow expiry sweep failed: %s", exc)
        db.rollback()


# ── realtime notification seam (AN-6) ────────────────────────────────────────
def _publish_event(office: Office, event: str, req: BookingRequest) -> None:
    """Best-effort fan-out for a future staff SSE/WS consumer. Published on
    ``appointnow:{tenant}:{office}``; a missing consumer is harmless (the inbox
    still refreshes on load and the badge polls the count summary)."""
    payload = json.dumps(
        {"event": event, "office_id": office.id, "request_id": req.id, "status": req.status}
    )
    try:
        redis_store.publish(f"appointnow:{office.tenant_id}:{office.id}", payload)
    except Exception as exc:  # noqa: BLE001
        logger.debug("AppointNow publish skipped: %s", exc)


def notify_new_request(office: Office, req: BookingRequest) -> None:
    _publish_event(office, "request.created", req)


def notify_updated_request(office: Office, req: BookingRequest) -> None:
    _publish_event(office, "request.updated", req)


def _invalidate_availability_cache(office_id: int, day: date) -> None:
    # The keys embed provider+duration; a scan-delete is overkill, so let the short
    # TTL age them out and only best-effort-clear the common default.
    redis_store.cache_delete(f"appointnow:avail:{office_id}:{day}:-:{_DEFAULT_DURATION}")


# ── serialisation (ORM → wire) ───────────────────────────────────────────────
def to_read(req: BookingRequest, office_code: str | None = None) -> dict:
    return {
        "id": req.id,
        "office_code": office_code,
        "office_id": req.office_id,
        "status": req.status,
        "reason_id": req.reason_id,
        "reason_label": req.reason_label,
        "slot": {
            "date": req.slot_date.strftime("%Y-%m-%d"),
            "start_time": _fmt_time(req.start_time),
            "end_time": _fmt_time(req.end_time),
            "duration_minutes": req.duration_minutes,
            "provider_id": req.provider_id,
            "provider_name": req.provider_name,
        },
        "contact": {
            "first_name": req.first_name,
            "last_name": req.last_name,
            "phone": req.phone,
            "email": req.email,
            "date_of_birth": req.date_of_birth,
            "is_new_patient": req.is_new_patient,
            "notes": req.notes,
        },
        "appointment_id": req.appointment_id,
        "patient_id": req.patient_id,
        "decline_reason": req.decline_reason,
        "actioned_at": req.actioned_at,
        "created_at": req.created_at,
        "updated_at": req.updated_at,
    }
