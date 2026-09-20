"""Office scope enforcement (OFF-SCOPE-1..19).

The shared ``client`` fixture authenticates as a ``super_admin`` who holds every
office right (so it is never narrowed) — that is what keeps every other module's
tests unaffected by scoping. These tests build a *non-privileged* ``front_desk``
user assigned to one office and exercise the enforcement against them.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_tenant_id
from app.core.security import hash_password
from app.db.models import (
    Appointment,
    Office,
    Operatory,
    Patient,
    Provider,
    User,
    UserOffice,
)
from app.db.session import get_db
from app.main import app

PREFIX = "/api/v1"
TODAY = date.today().isoformat()


@pytest.fixture
def scoped(db_session):
    """Two offices, a front-desk user assigned only to office A, a provider, and a
    patient homed at each office. Returns a dict of the built rows + a TestClient
    authenticated as the front-desk (non-privileged) user."""
    tenant_id = db_session._tenant_id  # type: ignore[attr-defined]

    office_a = Office(tenant_id=tenant_id, office_code="OA", name="Office A", timezone="UTC")
    office_b = Office(tenant_id=tenant_id, office_code="OB", name="Office B", timezone="UTC")
    db_session.add_all([office_a, office_b])
    db_session.commit()

    user = User(
        tenant_id=tenant_id, email="fd@test.local", username="fd",
        password_hash=hash_password("x"), role="front_desk", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.add(UserOffice(user_id=user.id, office_id=office_a.id, is_primary=True))

    provider = Provider(id="PRV-A", tenant_id=tenant_id, office_id=office_a.id,
                        name="Dr A", role="dentist", is_active=True)
    db_session.add(provider)

    pat_a = Patient(tenant_id=tenant_id, first_name="Al", last_name="Pat",
                    home_office_id=office_a.id, chart_no="PA", is_active=True)
    pat_b = Patient(tenant_id=tenant_id, first_name="Bo", last_name="Pat",
                    home_office_id=office_b.id, chart_no="PB", is_active=True)
    db_session.add_all([pat_a, pat_b])
    db_session.commit()

    op_a = Operatory(id="OP-A", office_id=office_a.id, name="Op A")
    op_b = Operatory(id="OP-B", office_id=office_b.id, name="Op B")
    db_session.add_all([op_a, op_b])

    # One appointment in each office (day-data). Appointments have no tenant_id
    # column — tenancy is scoped through the office.
    db_session.add_all([
        Appointment(id="AP-A", patient_id=pat_a.id, provider_id="PRV-A",
                    office_id=office_a.id, operatory_id="OP-A", date=date.today(),
                    start_time=time(9, 0), end_time=time(9, 30), duration=30, status="scheduled"),
        Appointment(id="AP-B", patient_id=pat_b.id, provider_id="PRV-A",
                    office_id=office_b.id, operatory_id="OP-B", date=date.today(),
                    start_time=time(9, 0), end_time=time(9, 30), duration=30, status="scheduled"),
    ])
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_tenant_id] = lambda: tenant_id
    try:
        with TestClient(app) as c:
            yield {
                "client": c, "user": user, "office_a": office_a, "office_b": office_b,
                "pat_a": pat_a, "pat_b": pat_b, "provider": provider,
            }
    finally:
        app.dependency_overrides.clear()


# ── OFF-SCOPE-1: explicit office target validated ────────────────────────────
def test_explicit_office_not_assigned_is_403(scoped):
    c, office_b = scoped["client"], scoped["office_b"]
    r = c.get(f"{PREFIX}/appointments?office_id={office_b.id}")
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "office_not_assigned"


def test_explicit_assigned_office_ok(scoped):
    c, office_a = scoped["client"], scoped["office_a"]
    r = c.get(f"{PREFIX}/appointments?office_id={office_a.id}")
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["items"]}
    assert ids == {"AP-A"}


# ── OFF-SCOPE-2: default narrowing + all_offices permission ──────────────────
def test_default_narrows_day_data_to_assigned(scoped):
    c = scoped["client"]
    r = c.get(f"{PREFIX}/appointments")
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["items"]}
    assert ids == {"AP-A"}  # office B's appointment is hidden by default


def test_all_offices_requires_permission(scoped):
    c = scoped["client"]
    r = c.get(f"{PREFIX}/appointments?all_offices=true")
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "office_not_assigned"


def test_super_admin_sees_all_offices(client):
    # The shared super_admin fixture holds view_all → never narrowed.
    r = client.get(f"{PREFIX}/appointments")
    assert r.status_code == 200


# ── OFF-SCOPE-1 (write) + OFF-SCOPE-3 (X-Office-ID) ──────────────────────────
def test_create_body_office_not_assigned_is_403(scoped):
    c, office_b, pat = scoped["client"], scoped["office_b"], scoped["pat_a"]
    r = c.post(f"{PREFIX}/patient-recalls", json={
        "patient_id": pat.id, "office_id": office_b.id, "status": "due"})
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "office_not_assigned"


def test_x_office_id_header_validated(scoped):
    c, office_b = scoped["client"], scoped["office_b"]
    r = c.get(f"{PREFIX}/appointments", headers={"X-Office-ID": str(office_b.id)})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "office_not_assigned"


def test_x_office_id_defaults_write_office(scoped):
    c, office_a, pat = scoped["client"], scoped["office_a"], scoped["pat_a"]
    r = c.post(f"{PREFIX}/patient-recalls", json={"patient_id": pat.id, "status": "due"},
               headers={"X-Office-ID": str(office_a.id)})
    assert r.status_code == 201, r.text
    assert r.json()["office_id"] == office_a.id


# ── OFF-SCOPE-3: me-full + PATCH /users/me ───────────────────────────────────
def test_me_full_office_context(scoped):
    c, office_a = scoped["client"], scoped["office_a"]
    body = c.get(f"{PREFIX}/auth/me-full").json()
    assert body["current_office_id"] == office_a.id  # falls back to primary
    assert [o["office_id"] for o in body["offices"]] == [office_a.id]
    assert body["offices"][0]["timezone"] == "UTC"


def test_patch_me_current_office_validated(scoped):
    c, office_a, office_b = scoped["client"], scoped["office_a"], scoped["office_b"]
    ok = c.patch(f"{PREFIX}/users/me", json={"current_office_id": office_a.id})
    assert ok.status_code == 200, ok.text
    bad = c.patch(f"{PREFIX}/users/me", json={"current_office_id": office_b.id})
    assert bad.status_code == 403
    assert bad.json()["error"]["code"] == "office_not_assigned"


# ── OFF-SCOPE-6: patient visibility ──────────────────────────────────────────
def test_patient_visibility_home_office(scoped):
    c, pat_a, pat_b = scoped["client"], scoped["pat_a"], scoped["pat_b"]
    assert c.get(f"{PREFIX}/patients/{pat_a.id}").status_code == 200
    r = c.get(f"{PREFIX}/patients/{pat_b.id}")
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "patient_not_in_office"


def test_patients_list_stays_org_wide(scoped):
    # Patients are organisation-wide: the default list is NOT narrowed.
    c = scoped["client"]
    r = c.get(f"{PREFIX}/patients")
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["items"]}
    assert {scoped["pat_a"].id, scoped["pat_b"].id} <= ids


# ── OFF-SCOPE-8: assigned_to_me ──────────────────────────────────────────────
def test_offices_assigned_to_me(scoped):
    c, office_a = scoped["client"], scoped["office_a"]
    everyone = c.get(f"{PREFIX}/offices").json()["items"]
    assert len({o["id"] for o in everyone}) >= 2  # default list is tenant-wide
    mine = c.get(f"{PREFIX}/offices?assigned_to_me=true").json()["items"]
    assert {o["id"] for o in mine} == {office_a.id}


# ── OFF-SCOPE-12: operatory/office agreement ─────────────────────────────────
def test_operatory_office_mismatch_422(scoped):
    c, office_a, pat = scoped["client"], scoped["office_a"], scoped["pat_a"]
    r = c.post(f"{PREFIX}/appointments", json={
        "id": "AP-X", "patient_id": pat.id, "provider_id": "PRV-A", "office_id": office_a.id,
        "operatory_id": "OP-B", "date": TODAY, "start_time": "10:00:00", "end_time": "10:30:00",
        "duration": 30, "status": "scheduled"})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "operatory_office_mismatch"


# ── OFF-SCOPE-13 / FE-OFF-2: office rights on me-full use the real catalog code ─
def test_super_admin_has_office_rights(client):
    body = client.get(f"{PREFIX}/auth/me-full").json()
    assert "office_scope_view_all_offices" in body["permissions"]
    # The invented colon-style codes are gone (they were never in the catalog).
    assert "offices:view_all" not in body["permissions"]


def test_front_desk_lacks_office_rights(scoped):
    body = scoped["client"].get(f"{PREFIX}/auth/me-full").json()
    assert "office_scope_view_all_offices" not in body["permissions"]


# ── FE-OFF-3/4: exact error body shapes ──────────────────────────────────────
def test_403_body_shape(scoped):
    c, office_b = scoped["client"], scoped["office_b"]
    body = c.get(f"{PREFIX}/appointments?office_id={office_b.id}").json()
    # The machine code is at error.code; structured context at error.details.
    assert body["error"]["code"] == "office_not_assigned"
    assert body["error"]["details"]["office_id"] == office_b.id
    assert "assigned_office_ids" in body["error"]["details"]


def test_422_office_id_required(scoped, monkeypatch):
    # OFF-SCOPE-11: with the flag on, a POS create with no office (and no
    # X-Office-ID) is 422 office_id_required at error.code.
    from app.core.config import settings

    monkeypatch.setattr(settings, "OFFICE_REQUIRE_POS_OFFICE", True)
    c, pat = scoped["client"], scoped["pat_a"]
    r = c.post(f"{PREFIX}/patient-recalls", json={"patient_id": pat.id, "status": "due"})
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "office_id_required"
    assert body["error"]["details"]["field"] == "office_id"


# ── OFF-SCOPE-18: dashboard summary ──────────────────────────────────────────
def test_dashboard_summary_default_scope(scoped):
    r = scoped["client"].get(f"{PREFIX}/dashboard/summary")
    assert r.status_code == 200, r.text
    assert r.json()["office_ids"] == [scoped["office_a"].id]


def test_dashboard_summary_all_offices_denied(scoped):
    r = scoped["client"].get(f"{PREFIX}/dashboard/summary?all_offices=true")
    assert r.status_code == 403
