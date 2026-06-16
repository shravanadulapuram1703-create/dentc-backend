"""Provider Setup module tests (Setup -> Providers, provider dev-report gaps #1-#7)."""

from __future__ import annotations

import pytest

from app.db.models import InsuranceCarrier, Office, Provider, Tenant, User
from app.core.security import hash_password


@pytest.fixture
def office_id(db_session) -> int:
    office = Office(tenant_id=db_session._tenant_id, office_code="MAIN", name="Main Office")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    return office.id


@pytest.fixture
def provider_id(db_session, office_id) -> str:
    provider = Provider(
        id="prov-1", tenant_id=db_session._tenant_id, office_id=office_id, name="Dr. Smith"
    )
    db_session.add(provider)
    db_session.commit()
    return provider.id


def test_info_extra_fields_roundtrip(client, provider_id):
    # Gap #7: new Info/Advanced fields flow through the generated Provider CRUD.
    r = client.patch(f"/api/v1/providers/{provider_id}", json={
        "scheduler_color": "#FF0000", "is_ortho_provider": True,
        "dosespot_user_id": "ds-42", "custom_1": "x",
    })
    assert r.status_code == 200
    g = client.get(f"/api/v1/providers/{provider_id}").json()
    assert g["scheduler_color"] == "#FF0000"
    assert g["is_ortho_provider"] is True
    assert g["dosespot_user_id"] == "ds-42"


def test_provider_schedule_replace(client, provider_id, office_id):
    base = f"/api/v1/providers/{provider_id}"
    assert client.get(f"{base}/schedule").json() == []
    days = [{"day_of_week": d, "is_closed": d >= 5,
             "start_time": None if d >= 5 else "08:00:00",
             "end_time": None if d >= 5 else "17:00:00",
             "office_id": office_id, "effective_from": "2026-01-01"} for d in range(7)]
    r = client.put(f"{base}/schedule", json={"days": days})
    assert r.status_code == 200
    sched = r.json()
    assert len(sched) == 7
    monday = next(x for x in sched if x["day_of_week"] == 0)
    assert monday["start_time"] == "08:00:00"
    assert monday["office_id"] == office_id


def test_provider_holidays_crud(client, provider_id):
    base = f"/api/v1/providers/{provider_id}"
    c = client.post(f"{base}/holidays", json={
        "holiday_date": "2026-07-04", "holiday_name": "Vacation", "status": "CLOSED"
    })
    assert c.status_code == 201
    hid = c.json()["id"]
    assert len(client.get(f"{base}/holidays").json()) == 1
    u = client.patch(f"{base}/holidays/{hid}", json={"holiday_name": "PTO"})
    assert u.json()["holiday_name"] == "PTO"
    assert client.delete(f"{base}/holidays/{hid}").status_code == 204
    assert client.get(f"{base}/holidays").json() == []


def test_provider_watermarks_upsert(client, provider_id):
    base = f"/api/v1/providers/{provider_id}"
    assert client.get(f"{base}/watermarks").status_code == 200
    r = client.put(f"{base}/watermarks", json={"is_enabled": True, "opacity": 50, "position": "center"})
    assert r.status_code == 200
    g = client.get(f"{base}/watermarks").json()
    assert g["is_enabled"] is True
    assert g["opacity"] == 50


def test_provider_referral_offices_set(client, provider_id, office_id):
    base = f"/api/v1/providers/{provider_id}"
    assert client.get(f"{base}/referral-offices").json() == []
    r = client.put(f"{base}/referral-offices", json={"office_ids": [office_id]})
    assert r.status_code == 200
    assert [o["id"] for o in r.json()] == [office_id]
    # Replace with empty set removes the assignment.
    assert client.put(f"{base}/referral-offices", json={"office_ids": []}).json() == []


def test_provider_carrier_logins_masked(client, provider_id, db_session):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Delta")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    c = client.post("/api/v1/provider-carrier-logins", json={
        "provider_id": provider_id, "carrier_id": carrier.id,
        "portal_name": "Delta Portal", "username": "drsmith", "password": "s3cret",
    })
    assert c.status_code == 201
    body = c.json()
    lid = body["id"]
    assert "password" not in body and "password_enc" not in body
    assert body["password_masked"].endswith("et")
    listed = client.get("/api/v1/provider-carrier-logins", params={"provider_id": provider_id}).json()
    assert len(listed) == 1
    assert client.patch(f"/api/v1/provider-carrier-logins/{lid}", json={"username": "smith2"}).json()["username"] == "smith2"
    assert client.delete(f"/api/v1/provider-carrier-logins/{lid}").status_code == 204


def test_provider_user_link(client, provider_id, db_session):
    user = User(
        tenant_id=db_session._tenant_id, email="prov@test.local", username="provuser",
        password_hash=hash_password("x"), role="provider", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    base = f"/api/v1/providers/{provider_id}"
    assert client.get(f"{base}/user").json() is None
    r = client.put(f"{base}/user", json={"user_id": user.id})
    assert r.status_code == 200
    assert r.json()["id"] == user.id
    # Unlink.
    assert client.put(f"{base}/user", json={"user_id": None}).json() is None


def test_provider_not_in_tenant_forbidden(client, db_session):
    other = Tenant(name="Other", code="other", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    office = Office(tenant_id=other.id, office_code="O2", name="O2")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    foreign = Provider(id="prov-x", tenant_id=other.id, office_id=office.id, name="Foreign")
    db_session.add(foreign)
    db_session.commit()
    assert client.get(f"/api/v1/providers/{foreign.id}/schedule").status_code == 403
