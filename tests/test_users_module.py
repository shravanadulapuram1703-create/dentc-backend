"""Security -> Users module tests (Gaps 1-7)."""

from __future__ import annotations

import pytest

from app.db.models import (
    Office,
    User,
    UserGroup,
    UserGroupMembership,
    UserIpRule,
    UserLoginRestriction,
    UserOffice,
    UserTimeClockConfig,
)
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def office_and_group(db_session):
    office = Office(tenant_id=db_session._tenant_id, office_code="MAIN", name="Main")
    group = UserGroup(tenant_id=db_session._tenant_id, name="Hygienists", is_active=True)
    db_session.add_all([office, group])
    db_session.commit()
    db_session.refresh(office)
    db_session.refresh(group)
    return office, group


def test_setup_metadata(client):
    md = client.get("/api/v1/users/setup-metadata").json()
    assert {o["value"] for o in md["roles"]} >= {"admin", "staff"}
    assert md["patient_access_levels"] and md["overtime_methods"]
    assert "startup_screen" in md["user_preferences_schema"]


def test_roles_catalog(client):
    roles = client.get("/api/v1/roles").json()
    assert {o["value"] for o in roles} >= {"admin", "provider", "staff"}


def test_create_user_complete_persists_all_sections(client, db_session, office_and_group):
    office, group = office_and_group
    body = {
        "email": "newdoc@x.com", "username": "newdoc", "password": "secret12",
        "first_name": "New", "last_name": "Doc", "role": "provider",
        "patient_access_level": "full",
        "home_office_id": office.id, "assigned_offices": [office.id],
        "group_ids": [group.id],
        "ip_rules": [{"ip_address": "10.0.0.1", "rule_type": "allow"}],
        "login_restrictions": {"is_24_7": False, "allowed_days": "Mon,Tue", "start_time": "09:00:00", "end_time": "17:00:00"},
        "time_clock": {"pay_rate": 42.5, "overtime_method": "weekly_40", "clock_in_required": True},
        "preferences": {"startup_screen": "scheduler"},
    }
    r = client.post("/api/v1/users/complete", json=body)
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert r.json()["patient_access_level"] == "full"

    # Everything persisted to the DB in one shot.
    assert db_session.query(UserOffice).filter_by(user_id=uid).count() == 1
    primary = db_session.query(UserOffice).filter_by(user_id=uid, is_primary=True).one()
    assert primary.office_id == office.id
    assert db_session.query(UserGroupMembership).filter_by(user_id=uid).count() == 1
    assert db_session.query(UserIpRule).filter_by(user_id=uid).count() == 1
    tc = db_session.query(UserTimeClockConfig).filter_by(user_id=uid).one()
    assert float(tc.pay_rate) == 42.5 and tc.clock_in_required is True
    lr = db_session.query(UserLoginRestriction).filter_by(user_id=uid).one()
    assert lr.is_24_7 is False and lr.allowed_days == "Mon,Tue"


def test_update_user_complete_reconciles(client, db_session, office_and_group):
    office, group = office_and_group
    created = client.post("/api/v1/users/complete", json={
        "email": "u@x.com", "username": "u_complete", "password": "secret12",
        "assigned_offices": [office.id], "group_ids": [group.id],
    }).json()
    uid = created["id"]
    # Remove the group assignment via update (empty list reconciles to none).
    r = client.put(f"/api/v1/users/{uid}/complete", json={"group_ids": [], "patient_access_level": "limited"})
    assert r.status_code == 200
    assert r.json()["patient_access_level"] == "limited"
    assert db_session.query(UserGroupMembership).filter_by(user_id=uid).count() == 0
    # Offices untouched (not in payload).
    assert db_session.query(UserOffice).filter_by(user_id=uid).count() == 1


def test_time_clock_config_upsert(client, db_session):
    u = User(tenant_id=db_session._tenant_id, email="tc@x.com", username="tc",
             password_hash="x", role="staff", is_active=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    base = f"/api/v1/users/{u.id}/time-clock-config"
    assert client.get(base).status_code == 200  # upsert-on-get
    r = client.put(base, json={"pay_rate": 30, "overtime_method": "daily_8", "clock_in_required": True})
    assert r.status_code == 200
    assert float(client.get(base).json()["pay_rate"]) == 30.0


def test_security_settings_upsert(client, db_session):
    u = User(tenant_id=db_session._tenant_id, email="ss@x.com", username="ss",
             password_hash="x", role="staff", is_active=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    base = f"/api/v1/users/{u.id}/security-settings"
    r = client.put(base, json={"patient_access_level": "read_only",
                               "login_restrictions": {"is_24_7": False, "allowed_days": "Wed"}})
    assert r.status_code == 200
    g = client.get(base).json()
    assert g["patient_access_level"] == "read_only"
    assert g["login_restrictions"]["allowed_days"] == "Wed"


def test_change_my_password(client):
    # Wrong current password -> 401.
    bad = client.post("/api/v1/users/me/change-password",
                      json={"current_password": "wrong", "new_password": "brandnew123"})
    assert bad.status_code == 401
    # Correct current password -> 204.
    ok = client.post("/api/v1/users/me/change-password",
                     json={"current_password": TEST_PASSWORD, "new_password": "brandnew123"})
    assert ok.status_code == 204


def test_list_users_office_and_role_filter(client, db_session, office_and_group):
    office, _ = office_and_group
    client.post("/api/v1/users/complete", json={
        "email": "f@x.com", "username": "filtered", "password": "secret12",
        "role": "provider", "assigned_offices": [office.id],
    })
    # office_id filter (join via user_offices).
    by_office = client.get(f"/api/v1/users?office_id={office.id}").json()
    assert by_office["meta"]["total"] == 1
    assert by_office["items"][0]["username"] == "filtered"
    # role filter.
    by_role = client.get("/api/v1/users?role=provider").json()
    assert all(u["role"] == "provider" for u in by_role["items"])
