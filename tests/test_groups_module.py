"""Security -> Groups module tests (rights catalog, assignment, copy)."""

from __future__ import annotations

import pytest

from app.db.models import Permission, UserGroup, UserGroupRight


@pytest.fixture
def catalog(db_session):
    """A small rights catalog (global) + one group in the test tenant."""
    perms = [
        Permission(code="appointments_add_new_appointment",
                   label="Appointments - Add New Appointment", category="Appointments"),
        Permission(code="patient_search_patient_full_control",
                   label="Patient - Search Patient Full Control", category="Patient"),
        Permission(code="reports_daily_reports_screen_view_only",
                   label="Reports - Daily Reports Screen View Only", category="Reports"),
    ]
    group = UserGroup(tenant_id=db_session._tenant_id, name="Front Desk", is_active=True)
    db_session.add_all([*perms, group])
    db_session.commit()
    for p in perms:
        db_session.refresh(p)
    db_session.refresh(group)
    return perms, group


def test_permissions_catalog(client, catalog):
    rows = client.get("/api/v1/permissions").json()
    assert len(rows) >= 3
    sample = next(r for r in rows if r["code"] == "appointments_add_new_appointment")
    assert sample["label"] == "Appointments - Add New Appointment"
    assert sample["category"] == "Appointments"


def test_group_rights_get_put_roundtrip(client, db_session, catalog):
    _, group = catalog
    # starts empty
    assert client.get(f"/api/v1/user-groups/{group.id}/rights").json() == []
    # assign two
    codes = ["appointments_add_new_appointment", "patient_search_patient_full_control"]
    r = client.put(f"/api/v1/user-groups/{group.id}/rights", json={"right_codes": codes})
    assert r.status_code == 200
    assert sorted(r.json()) == sorted(codes)
    # persisted as normalized join rows
    assert db_session.query(UserGroupRight).filter_by(group_id=group.id).count() == 2
    # full-replace shrinks to one
    r2 = client.put(f"/api/v1/user-groups/{group.id}/rights",
                    json={"right_codes": ["reports_daily_reports_screen_view_only"]})
    assert r2.json() == ["reports_daily_reports_screen_view_only"]
    assert db_session.query(UserGroupRight).filter_by(group_id=group.id).count() == 1


def test_put_unknown_right_code_rejected(client, catalog):
    _, group = catalog
    r = client.put(f"/api/v1/user-groups/{group.id}/rights",
                   json={"right_codes": ["does_not_exist"]})
    assert r.status_code == 422
    assert "does_not_exist" in r.text


def test_rights_on_missing_group_404(client, catalog):
    assert client.get("/api/v1/user-groups/999999/rights").status_code == 404


def test_copy_group_duplicates_rights(client, db_session, catalog):
    _, group = catalog
    codes = ["appointments_add_new_appointment", "reports_daily_reports_screen_view_only"]
    client.put(f"/api/v1/user-groups/{group.id}/rights", json={"right_codes": codes})

    r = client.post(f"/api/v1/user-groups/{group.id}/copy")
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["name"] == "Front Desk (copy)"
    assert new["id"] != group.id
    # the copy carries the same rights
    copied = client.get(f"/api/v1/user-groups/{new['id']}/rights").json()
    assert sorted(copied) == sorted(codes)
    # original untouched
    assert sorted(client.get(f"/api/v1/user-groups/{group.id}/rights").json()) == sorted(codes)
