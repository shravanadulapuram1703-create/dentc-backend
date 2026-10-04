"""Time Clock backend gaps (TC-BE-1…14).

The shared ``client`` authenticates as a ``super_admin`` (a manager). ``staff``
swaps the auth override to a plain ``staff`` user so the caller-based rules
(TC-BE-5) can be exercised against a non-manager.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user
from app.core.security import hash_password
from app.db.models import (
    Office,
    Permission,
    TimeClockEntry,
    TimeClockEntryEdit,
    User,
    UserGroup,
    UserGroupMembership,
    UserGroupRight,
    UserTimeClockConfig,
)
from app.main import app
from app.services import time_clock_service as svc

pytestmark = pytest.mark.enforce_fks

P = "/api/v1/time-clock-entries"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def office(db_session):
    o = Office(tenant_id=db_session._tenant_id, office_code="TC", name="Clock Office",
               timezone="America/New_York")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


def _user(db_session, username: str, role: str = "staff", first: str = "Sam", last: str = "Staff") -> User:
    u = User(tenant_id=db_session._tenant_id, email=f"{username}@t.local", username=username,
             password_hash=hash_password("x"), role=role, is_active=True,
             first_name=first, last_name=last)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def staff(db_session):
    return _user(db_session, "staffer")


@contextmanager
def as_user(user: User):
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = previous


def _entry(db_session, user_id: int, clock_in: datetime, clock_out: datetime | None = None, *,
           office_id: int | None = None, entry_type: str = "work", basis: str = "utc",
           auto_closed: bool = False) -> TimeClockEntry:
    e = TimeClockEntry(tenant_id=db_session._tenant_id, user_id=user_id, office_id=office_id,
                       clock_in=clock_in, clock_out=clock_out,
                       total_hours=svc.hours_between(clock_in, clock_out), entry_type=entry_type,
                       source="legacy" if basis == "wall_clock" else "manual", clock_basis=basis,
                       is_active=True, auto_closed=auto_closed, is_edited=False)
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    return e


# ── TC-BE-1/2: punches ───────────────────────────────────────────────────────
def test_clock_in_out_server_stamped(client, office):
    before = _now()
    r = client.post(f"{P}/clock-in", json={"office_id": office.id})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "punch" and body["is_open"] is True
    assert body["office_name"] == "Clock Office" and body["timezone"] == "America/New_York"
    assert abs((_parse(body["clock_in"]) - before).total_seconds()) < 5

    # TC-BE-2: second clock-in while open.
    dup = client.post(f"{P}/clock-in", json={})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "already_clocked_in"
    assert dup.json()["error"]["details"]["entry"]["id"] == body["id"]

    assert client.get(f"{P}/me/active").json()["id"] == body["id"]
    out = client.post(f"{P}/clock-out", json={"notes": "done"})
    assert out.status_code == 200, out.text
    assert out.json()["clock_out"] is not None and out.json()["total_hours"] is not None
    assert out.json()["notes"] == "done" and out.json()["is_open"] is False

    assert client.get(f"{P}/me/active").status_code == 204
    again = client.post(f"{P}/clock-out")
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_clocked_in"


def test_clock_in_defaults_office_from_header(client, office):
    r = client.post(f"{P}/clock-in", headers={"X-Office-ID": str(office.id)})
    assert r.status_code == 201, r.text
    assert r.json()["office_id"] == office.id


def test_partial_unique_index_blocks_second_open_row(db_session, staff):
    _entry(db_session, staff.id, _now() - timedelta(hours=1))
    db_session.add(TimeClockEntry(tenant_id=db_session._tenant_id, user_id=staff.id,
                                  clock_in=_now(), is_active=True, auto_closed=False))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    # An auto-closed (missing clock-out) row does not count as open.
    _entry(db_session, staff.id, _now() - timedelta(days=3), auto_closed=True)


def test_stale_open_shift_is_flagged_on_clock_in(client, db_session, staff):
    stale = _entry(db_session, staff.id, _now() - timedelta(hours=30))
    with as_user(staff):
        assert client.get(f"{P}/me/active").status_code == 204  # stale ≠ running
        r = client.post(f"{P}/clock-in", json={})
    assert r.status_code == 201, r.text
    db_session.refresh(stale)
    assert stale.auto_closed is True and stale.clock_out is None
    assert stale.auto_close_reason == "missing_clock_out"
    assert db_session.query(TimeClockEntryEdit).filter_by(entry_id=stale.id, action="auto_close").count() == 1


def test_stale_open_shift_clock_out_is_409_not_30_hours(client, db_session, staff):
    stale = _entry(db_session, staff.id, _now() - timedelta(hours=30))
    with as_user(staff):
        r = client.post(f"{P}/clock-out")
    assert r.status_code == 409
    assert r.json()["error"]["details"]["auto_closed_entry"]["id"] == stale.id
    db_session.refresh(stale)
    assert stale.clock_out is None and stale.auto_closed is True


# ── TC-BE-5: authorization by caller ─────────────────────────────────────────
def test_non_manager_sees_only_own_rows(client, db_session, staff):
    other = _user(db_session, "other")
    _entry(db_session, staff.id, _now() - timedelta(hours=9), _now() - timedelta(hours=1))
    _entry(db_session, other.id, _now() - timedelta(hours=9), _now() - timedelta(hours=1))
    with as_user(staff):
        rows = client.get(P, params={"all_offices": "true"}).json()
        assert rows["meta"]["total"] == 1 and rows["items"][0]["user_id"] == staff.id
        assert rows["items"][0]["user_name"] == "Sam Staff"
        assert client.get(P, params={"user_id": other.id}).status_code == 403
        theirs = rows["items"][0]["id"]
        other_id = db_session.query(TimeClockEntry).filter_by(user_id=other.id).one().id
        assert client.get(f"{P}/{other_id}").status_code == 403
        assert client.get(f"{P}/{theirs}").status_code == 200
    assert client.get(P).json()["meta"]["total"] == 2  # manager sees both


def test_non_manager_generic_post_is_a_server_stamped_punch(client, db_session, staff):
    fake = _now() - timedelta(hours=5)
    with as_user(staff):
        r = client.post(P, json={"user_id": staff.id, "clock_in": _iso(fake)})
        assert r.status_code == 201, r.text
        assert abs((_parse(r.json()["clock_in"]) - _now()).total_seconds()) < 5  # client time discarded
        assert r.json()["source"] == "punch"
        entry_id = r.json()["id"]
        # PATCH {clock_out, total_hours} on one's own open shift == clock-out.
        r2 = client.patch(f"{P}/{entry_id}", json={"clock_out": _iso(_now() + timedelta(hours=3)),
                                                   "total_hours": "99.00"})
        assert r2.status_code == 200, r2.text
        assert _parse(r2.json()["clock_out"]) <= _now() + timedelta(seconds=5)
        assert Decimal(r2.json()["total_hours"]) < 1
        # Anything else is a manager action.
        assert client.patch(f"{P}/{entry_id}", json={"clock_in": _iso(fake)}).status_code == 403
        assert client.delete(f"{P}/{entry_id}").status_code == 403
        assert client.post(P, json={"user_id": staff.id, "clock_in": _iso(fake),
                                    "clock_out": _iso(fake + timedelta(hours=8))}).status_code == 403
        other = _user(db_session, "other2")
        assert client.post(P, json={"user_id": other.id, "clock_in": _iso(fake)}).status_code == 403


def test_editor_right_grants_manager_access(client, db_session, staff):
    group = UserGroup(tenant_id=db_session._tenant_id, name="Payroll", is_active=True)
    perm = Permission(code=svc.EDIT_RIGHT, label="x", category="Utilities", is_active=True)
    db_session.add_all([group, perm])
    db_session.commit()
    db_session.add_all([
        UserGroupMembership(tenant_id=db_session._tenant_id, user_id=staff.id, group_id=group.id),
        UserGroupRight(tenant_id=db_session._tenant_id, group_id=group.id, permission_id=perm.id),
    ])
    db_session.commit()
    other = _user(db_session, "other3")
    start = _now() - timedelta(days=1)
    with as_user(staff):
        meta = client.get("/api/v1/time-clock/metadata").json()
        assert meta["capabilities"]["can_edit"] is True and meta["capabilities"]["can_view_wages"] is False
        r = client.post(P, json={"user_id": other.id, "clock_in": _iso(start),
                                 "clock_out": _iso(start + timedelta(hours=8))})
        assert r.status_code == 201, r.text


# ── TC-BE-3: computed hours + validation ─────────────────────────────────────
def test_manager_create_computes_hours_and_validates(client, staff):
    start = (_now() - timedelta(days=2)).replace(microsecond=0)
    r = client.post(P, json={"user_id": staff.id, "clock_in": _iso(start),
                             "clock_out": _iso(start + timedelta(hours=8, minutes=15)), "total_hours": "1.00"})
    assert r.status_code == 201, r.text
    assert r.json()["total_hours"] == "8.25" and r.json()["source"] == "manual"

    bad = client.post(P, json={"user_id": staff.id, "clock_in": _iso(start),
                               "clock_out": _iso(start - timedelta(minutes=1))})
    assert bad.json()["error"]["code"] == "clock_out_before_clock_in"
    future = client.post(P, json={"user_id": staff.id, "clock_in": _iso(_now() + timedelta(hours=2))})
    assert future.json()["error"]["code"] == "punch_in_future"
    long_ = client.post(P, json={"user_id": staff.id, "clock_in": _iso(start),
                                 "clock_out": _iso(start + timedelta(hours=25))})
    assert long_.json()["error"]["code"] == "shift_too_long"

    # An open manager entry respects the one-open-shift rule.
    assert client.post(P, json={"user_id": staff.id, "clock_in": _iso(_now() - timedelta(hours=1))}).status_code == 201
    dup = client.post(P, json={"user_id": staff.id, "clock_in": _iso(_now() - timedelta(minutes=30))})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "already_clocked_in"


# ── TC-BE-6: edit trail + soft delete ────────────────────────────────────────
def test_edit_keeps_originals_and_history(client, db_session, staff):
    start = (_now() - timedelta(days=1)).replace(microsecond=0)
    e = _entry(db_session, staff.id, start, start + timedelta(hours=8))
    r = client.patch(f"{P}/{e.id}", json={"clock_out": _iso(start + timedelta(hours=9)), "reason": "forgot"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_edited"] is True and body["total_hours"] == "9.00"
    assert _parse(body["original_clock_out"]) == start + timedelta(hours=8)
    assert body["updated_by_name"] and body["edit_reason"] == "forgot"
    assert r.headers.get("ETag")

    # A second edit keeps the *first* originals.
    client.patch(f"{P}/{e.id}", json={"clock_out": _iso(start + timedelta(hours=10))})
    db_session.refresh(e)
    assert e.original_clock_out == start + timedelta(hours=8)

    hist = client.get(f"{P}/{e.id}/history").json()
    assert [h["action"] for h in hist] == ["update", "update"]
    assert _parse(hist[0]["original_clock_out"]) == start + timedelta(hours=8)
    assert hist[0]["edit_reason"] == "forgot" and hist[0]["edited_by_name"]

    # No-op PATCH stamps nothing.
    n = len(hist)
    client.patch(f"{P}/{e.id}", json={"clock_out": _iso(start + timedelta(hours=10))})
    assert len(client.get(f"{P}/{e.id}/history").json()) == n

    # Reversed pair on PATCH.
    bad = client.patch(f"{P}/{e.id}", json={"clock_in": _iso(start + timedelta(hours=11))})
    assert bad.json()["error"]["code"] == "clock_out_before_clock_in"

    # Stale precondition.
    stale = client.patch(f"{P}/{e.id}", json={"notes": "x"}, headers={"If-Match": 'W/"2001-01-01T00:00:00.000Z"'})
    assert stale.status_code == 412


def test_soft_delete_and_restore(client, db_session, staff):
    start = _now() - timedelta(days=1)
    e = _entry(db_session, staff.id, start, start + timedelta(hours=8))
    assert client.delete(f"{P}/{e.id}", params={"reason": "duplicate"}).status_code == 204
    db_session.refresh(e)
    assert e.is_active is False and e.delete_reason == "duplicate" and e.deleted_by is not None
    assert client.get(P).json()["meta"]["total"] == 0
    assert client.get(P, params={"include_deleted": "true"}).json()["meta"]["total"] == 1
    assert client.get(f"{P}/{e.id}").json()["is_active"] is False  # manager still opens it
    with as_user(staff):
        assert client.get(f"{P}/{e.id}").status_code == 404
    assert client.patch(f"{P}/{e.id}", json={"notes": "x"}).json()["error"]["code"] == "entry_deleted"
    r = client.post(f"{P}/{e.id}/restore")
    assert r.status_code == 200 and r.json()["is_active"] is True
    assert [h["action"] for h in client.get(f"{P}/{e.id}/history").json()] == ["delete", "restore"]


def test_require_edit_reason_setting(client, db_session, staff):
    assert client.put("/api/v1/time-clock/settings", json={"require_edit_reason": True}).status_code == 200
    start = _now() - timedelta(days=1)
    e = _entry(db_session, staff.id, start, start + timedelta(hours=8))
    r = client.patch(f"{P}/{e.id}", json={"clock_out": _iso(start + timedelta(hours=7))})
    assert r.status_code == 422 and r.json()["error"]["code"] == "edit_reason_required"
    assert client.delete(f"{P}/{e.id}").json()["error"]["code"] == "edit_reason_required"
    assert client.patch(f"{P}/{e.id}", json={"clock_out": _iso(start + timedelta(hours=7)),
                                             "reason": "late"}).status_code == 200


# ── TC-BE-4: date range ──────────────────────────────────────────────────────
def test_date_range_filter_office_local_and_wall_clock(client, db_session, staff, office):
    # 2026-03-02 23:30 New York (EST) = 2026-03-03 04:30Z → office-local day is 03-02.
    utc_row = _entry(db_session, staff.id, datetime(2026, 3, 3, 4, 30), datetime(2026, 3, 3, 6, 0),
                     office_id=office.id)
    # A legacy wall-clock row stored as "09:25Z" on 03-03 means 9:25 local that day.
    wall_row = _entry(db_session, staff.id, datetime(2026, 3, 3, 9, 25), datetime(2026, 3, 3, 17, 0),
                      office_id=office.id, basis="wall_clock")
    _entry(db_session, staff.id, datetime(2026, 3, 10, 14, 0), datetime(2026, 3, 10, 22, 0), office_id=office.id)

    def ids(**params):
        return {i["id"] for i in client.get(P, params={"office_id": office.id, **params}).json()["items"]}

    assert ids(clock_in_from="2026-03-02", clock_in_to="2026-03-02") == {utc_row.id}
    assert ids(clock_in_from="2026-03-03", clock_in_to="2026-03-03") == {wall_row.id}
    assert ids(clock_in_from="2026-03-01", clock_in_to="2026-03-04") == {utc_row.id, wall_row.id}
    assert len(ids(clock_in_from="2026-03-01")) == 3
    assert client.get(P, params={"clock_in_from": "nope"}).json()["error"]["code"] == "invalid_date"
    row = client.get(f"{P}/{utc_row.id}").json()
    assert row["work_date"] == "2026-03-02" and row["clock_basis"] == "utc"


# ── TC-BE-7: overtime vocabulary + split ─────────────────────────────────────
def test_user_config_overtime_method_canonicalised(client, db_session, staff):
    base = f"/api/v1/users/{staff.id}/time-clock-config"
    r = client.put(base, json={"overtime_method": "weekly_40", "week_start_day": "Mon",
                               "weekly_threshold_hours": 38})
    assert r.status_code == 200, r.text
    assert r.json()["overtime_method"] == "weekly" and r.json()["week_start_day"] == "monday"
    bad = client.put(base, json={"overtime_method": "fortnightly"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_overtime_method"


def _rule(method, daily="8", weekly="40", start="sunday"):
    return {"overtime_method": method, "daily_threshold_hours": Decimal(daily),
            "weekly_threshold_hours": Decimal(weekly), "week_start_day": start}


def test_split_overtime_rules():
    # Sun 2026-03-01 … Sat 2026-03-07: five 10h days.
    days = {date(2026, 3, d): Decimal("10") for d in (2, 3, 4, 5, 6)}
    weekly = svc.split_overtime(days, _rule("weekly"))
    assert sum(r for r, _ in weekly.values()) == Decimal("40.00")
    assert weekly[date(2026, 3, 6)] == (Decimal("0.00"), Decimal("10.00"))
    daily = svc.split_overtime(days, _rule("daily"))
    assert all(v == (Decimal("8.00"), Decimal("2.00")) for v in daily.values())
    both = svc.split_overtime({**days, date(2026, 3, 7): Decimal("10")}, _rule("daily_weekly"))
    # 6 days x 8 regular = 48 → 8 more past the weekly 40, on top of 6 x 2 daily OT.
    assert sum(r for r, _ in both.values()) == Decimal("40.00")
    assert sum(o for _, o in both.values()) == Decimal("20.00")
    assert svc.split_overtime(days, _rule("none"))[date(2026, 3, 2)] == (Decimal("10.00"), Decimal("0.00"))
    # Week boundary: a Monday-start week resets on 03-09.
    split = svc.split_overtime({date(2026, 3, 8): Decimal("45"), date(2026, 3, 9): Decimal("5")},
                               _rule("weekly", start="monday"))
    assert split[date(2026, 3, 9)] == (Decimal("5.00"), Decimal("0.00"))


# ── TC-BE-8/13: report ───────────────────────────────────────────────────────
def test_hours_report(client, db_session, staff, office):
    other = _user(db_session, "zed", first="Zed", last="Worker")
    db_session.add(UserTimeClockConfig(tenant_id=db_session._tenant_id, user_id=staff.id,
                                       overtime_method="daily", pay_rate=Decimal("20")))
    db_session.commit()
    # 2026-03-02 (Mon) 13:00Z-23:00Z = 8:00-18:00 EST (10h) + a 30-minute lunch.
    _entry(db_session, staff.id, datetime(2026, 3, 2, 13), datetime(2026, 3, 2, 23), office_id=office.id)
    _entry(db_session, staff.id, datetime(2026, 3, 2, 17), datetime(2026, 3, 2, 17, 30),
           office_id=office.id, entry_type="lunch")
    _entry(db_session, other.id, datetime(2026, 3, 3, 14), datetime(2026, 3, 3, 18), office_id=office.id)
    params = {"from": "2026-03-01", "to": "2026-03-07"}
    rep = client.get("/api/v1/reports/time-clock", params=params).json()
    by = {u["user_name"]: u for u in rep["users"]}
    sam = by["Sam Staff"]
    assert sam["rule"]["overtime_method"] == "daily" and sam["rule"]["source"] == "user"
    assert sam["totals"]["regular"] == "8.00" and sam["totals"]["overtime"] == "2.00"
    assert sam["totals"]["break_hours"] == "0.50" and sam["days"][0]["date"] == "2026-03-02"
    assert by["Zed Worker"]["totals"]["total"] == "4.00"
    assert rep["totals"]["total"] == "14.00" and sam["totals"]["regular_pay"] is None

    wages = client.get("/api/v1/reports/time-clock", params={**params, "include_wages": "true"}).json()
    s = {u["user_name"]: u for u in wages["users"]}["Sam Staff"]
    assert s["totals"]["regular_pay"] == "160.00" and s["totals"]["overtime_pay"] == "60.00"

    override = client.get("/api/v1/reports/time-clock", params={**params, "overtime_method": "none"}).json()
    assert {u["user_name"]: u for u in override["users"]}["Sam Staff"]["totals"]["overtime"] == "0.00"

    csv_ = client.get("/api/v1/reports/time-clock/report.csv", params={**params, "layout": "detail"})
    assert csv_.status_code == 200 and csv_.text.startswith("Employee,")
    pdf = client.get("/api/v1/reports/time-clock/report.pdf", params=params)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    with as_user(staff):
        mine = client.get("/api/v1/reports/time-clock", params=params).json()
        assert [u["user_id"] for u in mine["users"]] == [staff.id]
        assert client.get("/api/v1/reports/time-clock", params={**params, "user_id": other.id}).status_code == 403
        assert client.get("/api/v1/reports/time-clock",
                          params={**params, "include_wages": "true"}).status_code == 403


# ── TC-BE-14: pay periods ────────────────────────────────────────────────────
def test_locked_period_freezes_entries(client, db_session, staff, office):
    e = _entry(db_session, staff.id, datetime(2026, 2, 10, 14), datetime(2026, 2, 10, 22), office_id=office.id)
    base = "/api/v1/time-clock/periods"
    r = client.post(base, json={"period_start": "2026-02-01", "period_end": "2026-02-14"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    overlap = client.post(base, json={"office_id": office.id, "period_start": "2026-02-10",
                                      "period_end": "2026-02-20"})
    assert overlap.status_code == 409 and overlap.json()["error"]["code"] == "period_overlap"

    locked = client.post(f"{base}/{pid}/lock").json()
    assert locked["locked"] is True and locked["status"] == "locked" and locked["approved_by_name"]
    r = client.patch(f"{P}/{e.id}", json={"clock_out": "2026-02-10T23:00:00Z"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "period_locked"
    assert client.delete(f"{P}/{e.id}").status_code == 409
    new = client.post(P, json={"user_id": staff.id, "office_id": office.id,
                               "clock_in": "2026-02-11T14:00:00Z", "clock_out": "2026-02-11T15:00:00Z"})
    assert new.status_code == 409
    assert client.delete(f"{base}/{pid}").status_code == 409

    client.post(f"{base}/{pid}/unlock")
    assert client.patch(f"{P}/{e.id}", json={"clock_out": "2026-02-10T23:00:00Z"}).status_code == 200
    assert client.delete(f"{base}/{pid}").status_code == 204


# ── TC-BE-10 sweep + settings ────────────────────────────────────────────────
def test_auto_close_sweep_office_close_policy(client, db_session, staff, office):
    from app.db.models.office_setup import OfficeScheduleDay

    day = date(2026, 3, 2)  # Monday
    db_session.add(OfficeScheduleDay(tenant_id=db_session._tenant_id, office_id=office.id,
                                     day_of_week=day.weekday(), start_time=time(8), end_time=time(17)))
    db_session.commit()
    stale = _entry(db_session, staff.id, datetime(2026, 3, 2, 13, 0), office_id=office.id)
    dry = client.post("/api/v1/time-clock/auto-close").json()
    assert dry["dry_run"] is True and dry["entry_ids"] == [stale.id]
    db_session.refresh(stale)
    assert stale.auto_closed is False

    client.put("/api/v1/time-clock/settings", json={"auto_close_policy": "office_close"})
    res = client.post("/api/v1/time-clock/auto-close", params={"dry_run": "false"}).json()
    assert res["closed_at_office_close"] == 1
    db_session.refresh(stale)
    # 17:00 EST = 22:00Z; 13:00Z → 22:00Z = 9 h.
    assert stale.clock_out == datetime(2026, 3, 2, 22, 0) and stale.total_hours == Decimal("9.00")
    assert stale.auto_closed is True and stale.auto_close_reason == "office_close"
    row = client.get(f"{P}/{stale.id}").json()
    assert "auto_closed" in row["issues"]


def test_settings_validation_and_metadata(client):
    bad = client.put("/api/v1/time-clock/settings", json={"overtime_method": "monthly"})
    assert bad.status_code == 422
    ok = client.put("/api/v1/time-clock/settings", json={"overtime_method": "daily_8", "week_start_day": "monday"})
    assert ok.json()["overtime_method"] == "daily" and ok.json()["week_start_day"] == "monday"
    meta = client.get("/api/v1/time-clock/metadata").json()
    assert meta["settings"]["overtime_method"] == "daily"
    assert meta["capabilities"]["can_edit"] is True
    assert "missing_clock_out" in meta["issues"]
    assert meta["effective_rules"]["clock_in_required"] is False


def test_non_manager_cannot_change_settings_or_periods(client, staff):
    with as_user(staff):
        assert client.put("/api/v1/time-clock/settings", json={"require_edit_reason": True}).status_code == 403
        assert client.get("/api/v1/time-clock/periods").status_code == 403
        assert client.post("/api/v1/time-clock/periods", json={"period_start": "2026-01-01",
                                                               "period_end": "2026-01-14"}).status_code == 403
