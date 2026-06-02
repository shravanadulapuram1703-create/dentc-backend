"""Account holidays service — CRUD, bulk delete, federal import, range create."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models.account import AccountHoliday


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th given weekday (Mon=0) of month; n=-1 → last."""
    if n > 0:
        d = date(year, month, 1)
        offset = (weekday - d.weekday()) % 7
        return d + timedelta(days=offset + 7 * (n - 1))
    # last occurrence
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def federal_holidays(year: int) -> list[tuple[date, str]]:
    return [
        (date(year, 1, 1), "New Year's Day"),
        (_nth_weekday(year, 1, 0, 3), "Birthday of Martin Luther King, Jr."),
        (_nth_weekday(year, 2, 0, 3), "Washington's Birthday"),
        (_nth_weekday(year, 5, 0, -1), "Memorial Day"),
        (date(year, 6, 19), "Juneteenth National Independence Day"),
        (date(year, 7, 4), "Independence Day"),
        (_nth_weekday(year, 9, 0, 1), "Labor Day"),
        (_nth_weekday(year, 10, 0, 2), "Columbus Day"),
        (date(year, 11, 11), "Veterans Day"),
        (_nth_weekday(year, 11, 3, 4), "Thanksgiving Day"),
        (date(year, 12, 25), "Christmas Day"),
    ]


def _scope(stmt, tenant_id: int, office_id: int | None):  # noqa: ANN001
    """Scope to a tenant and either account-level (office_id IS NULL) or one office."""
    stmt = stmt.where(AccountHoliday.tenant_id == tenant_id)
    if office_id is None:
        return stmt.where(AccountHoliday.office_id.is_(None))
    return stmt.where(AccountHoliday.office_id == office_id)


def list_holidays(
    db: Session, tenant_id: int, from_date: date | None = None, to_date: date | None = None,
    office_id: int | None = None,
) -> list[AccountHoliday]:
    stmt = _scope(select(AccountHoliday), tenant_id, office_id)
    if from_date is not None:
        stmt = stmt.where(AccountHoliday.holiday_date >= from_date)
    if to_date is not None:
        stmt = stmt.where(AccountHoliday.holiday_date <= to_date)
    stmt = stmt.order_by(AccountHoliday.holiday_date.asc())
    return list(db.execute(stmt).scalars().all())


def get_holiday(db: Session, tenant_id: int, holiday_id: int, office_id: int | None = None) -> AccountHoliday:
    row = db.execute(
        _scope(select(AccountHoliday).where(AccountHoliday.id == holiday_id), tenant_id, office_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Holiday '{holiday_id}' was not found")
    return row


def create_holiday(
    db: Session, tenant_id: int, data: dict, user_id: int | None, office_id: int | None = None
) -> AccountHoliday:
    row = AccountHoliday(tenant_id=tenant_id, office_id=office_id, created_by=user_id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_holiday(
    db: Session, tenant_id: int, holiday_id: int, data: dict, office_id: int | None = None
) -> AccountHoliday:
    row = get_holiday(db, tenant_id, holiday_id, office_id)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def delete_holiday(db: Session, tenant_id: int, holiday_id: int, office_id: int | None = None) -> None:
    row = get_holiday(db, tenant_id, holiday_id, office_id)
    db.delete(row)
    db.commit()


def bulk_delete(db: Session, tenant_id: int, ids: list[int], office_id: int | None = None) -> int:
    result = db.execute(
        _scope(sa_delete(AccountHoliday).where(AccountHoliday.id.in_(ids)), tenant_id, office_id)
    )
    db.commit()
    return result.rowcount or 0


def _existing_dates(db: Session, tenant_id: int, dates: list[date], office_id: int | None) -> set[date]:
    rows = db.execute(
        _scope(select(AccountHoliday.holiday_date).where(AccountHoliday.holiday_date.in_(dates)),
               tenant_id, office_id)
    ).scalars().all()
    return set(rows)


def import_federal(
    db: Session, tenant_id: int, year: int, status: str, user_id: int | None,
    office_id: int | None = None,
) -> list[AccountHoliday]:
    holidays = federal_holidays(year)
    existing = _existing_dates(db, tenant_id, [d for d, _ in holidays], office_id)
    created = [
        AccountHoliday(
            tenant_id=tenant_id, office_id=office_id, holiday_date=d, holiday_name=name,
            status=status, holiday_type="FEDERAL", is_recurring=False, created_by=user_id,
        )
        for d, name in holidays
        if d not in existing
    ]
    db.add_all(created)
    db.commit()
    for row in created:
        db.refresh(row)
    return created


def create_range(
    db: Session, tenant_id: int, from_date: date, to_date: date, name: str,
    status: str, holiday_type: str, user_id: int | None, office_id: int | None = None,
) -> list[AccountHoliday]:
    if to_date < from_date:
        from_date, to_date = to_date, from_date
    span = [from_date + timedelta(days=i) for i in range((to_date - from_date).days + 1)]
    existing = _existing_dates(db, tenant_id, span, office_id)
    created = [
        AccountHoliday(
            tenant_id=tenant_id, office_id=office_id, holiday_date=d, holiday_name=name,
            status=status, holiday_type=holiday_type, is_recurring=False, created_by=user_id,
        )
        for d in span
        if d not in existing
    ]
    db.add_all(created)
    db.commit()
    for row in created:
        db.refresh(row)
    return created
