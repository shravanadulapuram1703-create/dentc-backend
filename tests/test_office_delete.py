"""Office delete / reactivate — OFF-QA-15…18 of
docs/office-scope/office_setup_new_office_qa_backend_devreport.md."""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app.db.models import Appointment, Office, Operatory, Patient, Provider, User, UserOffice
from app.db.models.office_setup import OfficeIntegrations, OfficeScheduleDay

P = "/api/v1"


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="DEL1", short_id="DEL", name="Delete Me")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def other_office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="KEEP1", short_id="KEEP", name="Keep Me")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


def _user(db_session, email: str) -> User:
    u = User(tenant_id=db_session._tenant_id, email=email, username=email, password_hash="x", first_name="U", last_name=email[:3],
             role="staff", is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


def _future_appt(db_session, office: Office) -> Appointment:
    tid = office.tenant_id
    db_session.add_all([Provider(id="PRV-DEL", tenant_id=tid, office_id=office.id, name="Dr. Del"),
                        Operatory(id="OPR-DEL", office_id=office.id, name="Op Del")])
    pt = Patient(tenant_id=tid, first_name="D", last_name="E", chart_no="DEL-1", home_office_id=office.id)
    db_session.add(pt)
    db_session.commit()
    a = Appointment(id="APPT-DEL", patient_id=pt.id, provider_id="PRV-DEL", operatory_id="OPR-DEL",
                    office_id=office.id, date=date.today() + timedelta(days=30),
                    start_time=time(9), end_time=time(9, 30), duration=30, status="Scheduled")
    db_session.add(a)
    db_session.commit()
    return a


# ── OFF-QA-15.1 impact ───────────────────────────────────────────────────────
def test_delete_impact_counts(client, db_session, office, other_office):
    _future_appt(db_session, office)
    lonely, shared = _user(db_session, "lonely@x.test"), _user(db_session, "shared@x.test")
    db_session.add_all([UserOffice(user_id=lonely.id, office_id=office.id),
                        UserOffice(user_id=shared.id, office_id=office.id),
                        UserOffice(user_id=shared.id, office_id=other_office.id)])
    db_session.commit()
    body = client.get(f"{P}/offices/{office.id}/delete-impact").json()
    assert body["future_appointments"] == 1
    assert body["home_patients"] == 1
    assert body["assigned_users"] == 2
    assert body["users_with_no_other_office"] == 1 and body["stranded_user_ids"] == [lonely.id]
    assert body["providers"] == 1 and body["operatories"] == 1
    assert body["blocking"] == ["future_appointments", "users_with_no_other_office"]


# ── OFF-QA-15.2 / 16 soft delete ─────────────────────────────────────────────
def test_delete_is_409_while_in_use_then_force_deactivates_operatories(client, db_session, office):
    _future_appt(db_session, office)
    r = client.delete(f"{P}/offices/{office.id}")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "office_in_use" and err["details"]["impact"]["future_appointments"] == 1
    assert client.get(f"{P}/offices/{office.id}").json()["is_active"] is True

    assert client.delete(f"{P}/offices/{office.id}?force=true").status_code == 204
    body = client.get(f"{P}/offices/{office.id}").json()
    assert body["is_active"] is False
    assert body["deleted_at"] is not None and body["deleted_by"] is not None
    assert body["deleted_by_name"]
    db_session.expire_all()
    assert db_session.get(Operatory, "OPR-DEL").is_active is False


def test_unused_office_deletes_without_force(client, office):
    assert client.delete(f"{P}/offices/{office.id}").status_code == 204


def test_inactive_vs_deleted_and_reactivate_restores_only_its_chairs(client, db_session, office):
    db_session.add_all([Operatory(id="OP-A", office_id=office.id, name="A"),
                        Operatory(id="OP-RETIRED", office_id=office.id, name="R", is_active=False)])
    db_session.commit()
    # Set Inactive on the Info tab: no delete stamp.
    r = client.patch(f"{P}/offices/{office.id}", json={"is_active": False})
    assert r.json()["deleted_at"] is None
    client.patch(f"{P}/offices/{office.id}", json={"is_active": True})

    assert client.delete(f"{P}/offices/{office.id}").status_code == 204
    r = client.patch(f"{P}/offices/{office.id}", json={"is_active": True})
    assert r.status_code == 200, r.text
    assert r.json()["deleted_at"] is None and r.json()["deleted_by"] is None
    db_session.expire_all()
    assert db_session.get(Operatory, "OP-A").is_active is True
    assert db_session.get(Operatory, "OP-RETIRED").is_active is False  # was retired before


def test_delete_stamp_is_not_writable(client, office):
    r = client.patch(f"{P}/offices/{office.id}", json={"deleted_at": "2026-01-01T00:00:00"})
    assert r.status_code == 200
    assert r.json()["deleted_at"] is None


# ── OFF-QA-15.3 writes into an inactive office ───────────────────────────────
def test_new_writes_into_inactive_office_are_409(client, db_session, office, other_office):
    a = _future_appt(db_session, office)
    client.delete(f"{P}/offices/{office.id}?force=true")
    body = {"id": "APPT-NEW", "patient_id": a.patient_id, "provider_id": "PRV-DEL", "office_id": office.id,
            "date": "2026-12-01", "start_time": "09:00", "end_time": "09:30", "duration": 30}
    r = client.post(f"{P}/appointments", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "office_inactive"
    # Even with the override for closed hours.
    r = client.post(f"{P}/appointments", json={**body, "allow_outside_office_hours": True})
    assert r.json()["error"]["code"] == "office_inactive"
    # X-Office-ID of the inactive office stamping a new record.
    r = client.post(f"{P}/explosion-codes", json={"code": "EXDEL", "description": "x"},
                    headers={"X-Office-ID": str(office.id)})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["details"]["loc"] == ["header", "X-Office-ID"]
    # ...and an explicit body office.
    r = client.post(f"{P}/operatories", json={"name": "New chair", "office_id": office.id})
    assert r.status_code == 409 and r.json()["error"]["code"] == "office_inactive"
    # The existing appointment stays editable.
    assert client.patch(f"{P}/appointments/{a.id}", json={"notes": "moved later"}).status_code == 200
    # ...but moving a record onto the inactive office is refused.
    db_session.add(Operatory(id="OPR-KEEP", office_id=other_office.id, name="Keep"))
    db_session.commit()
    op = client.patch(f"{P}/operatories/OPR-KEEP", json={"office_id": office.id})
    assert op.status_code == 409


def test_appointnow_page_is_closed_for_inactive_office(client, office):
    client.delete(f"{P}/offices/{office.id}")
    r = client.get(f"{P}/appointnow/offices/{office.office_code}")
    assert r.status_code == 404


# ── OFF-QA-17 hard delete ────────────────────────────────────────────────────
def test_hard_delete_removes_an_unreferenced_office_and_its_settings(client, db_session, office):
    client.get(f"{P}/offices/{office.id}/integrations")  # creates the settings row
    db_session.add_all([OfficeScheduleDay(tenant_id=office.tenant_id, office_id=office.id, day_of_week=0),
                        Operatory(id="OP-H", office_id=office.id, name="H")])
    db_session.commit()
    assert client.delete(f"{P}/offices/{office.id}?hard=true").status_code == 204
    db_session.expire_all()
    assert db_session.get(Office, office.id) is None
    assert db_session.query(OfficeIntegrations).filter_by(office_id=office.id).count() == 0
    assert db_session.get(Operatory, "OP-H") is None


def test_hard_delete_refused_when_referenced(client, db_session, office):
    _future_appt(db_session, office)
    r = client.delete(f"{P}/offices/{office.id}?hard=true")
    assert r.status_code == 409
    tables = {ref["table"] for ref in r.json()["error"]["details"]["references"]}
    assert {"appointments", "patients", "providers"} <= tables


def test_hard_delete_is_admin_only(client, db_session, office, monkeypatch):
    from app.services import office_lifecycle_service

    monkeypatch.setattr(office_lifecycle_service, "HARD_DELETE_ROLES", frozenset({"owner"}))
    r = client.delete(f"{P}/offices/{office.id}?hard=true")
    assert r.status_code == 403 and r.json()["error"]["code"] == "hard_delete_forbidden"


# ── OFF-QA-18 me-full ────────────────────────────────────────────────────────
def test_me_full_marks_inactive_offices_and_never_resolves_one(client, db_session, office, other_office):
    from app.api.deps import get_current_user
    from app.main import app

    me = app.dependency_overrides[get_current_user]()
    db_session.add_all([UserOffice(user_id=me.id, office_id=office.id, is_primary=True),
                        UserOffice(user_id=me.id, office_id=other_office.id)])
    db_session.commit()
    client.delete(f"{P}/offices/{office.id}?force=true")
    body = client.get(f"{P}/auth/me-full").json()
    flags = {o["office_id"]: o["is_active"] for o in body["offices"]}
    assert flags == {office.id: False, other_office.id: True}
    assert body["current_office_id"] == other_office.id
