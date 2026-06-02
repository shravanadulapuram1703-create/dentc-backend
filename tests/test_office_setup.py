"""Office Setup module tests (Setup -> Offices, gaps #10-#17)."""

from __future__ import annotations

import pytest

from app.db.models import Office, Tenant


@pytest.fixture
def office_id(db_session) -> int:
    office = Office(tenant_id=db_session._tenant_id, office_code="MAIN", name="Main Office")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    return office.id


def test_office_metadata(client, office_id):
    r = client.get("/api/v1/offices/metadata")
    assert r.status_code == 200
    body = r.json()
    assert len(body["time_zones"]) == 7
    assert "billing_providers" in body and "fee_schedules" in body


def test_statement_settings_upsert(client, office_id):
    base = f"/api/v1/offices/{office_id}"
    assert client.get(f"{base}/statement-settings").status_code == 200
    r = client.patch(f"{base}/statement-settings",
                     json={"message_general": "Thank you", "logo_option": "custom",
                           "correspondence_name": "Main Office Billing"})
    assert r.status_code == 200
    g = client.get(f"{base}/statement-settings").json()
    assert g["message_general"] == "Thank you"
    assert g["logo_option"] == "custom"


def test_integrations_dosespot_masked(client, office_id):
    base = f"/api/v1/offices/{office_id}"
    r = client.patch(f"{base}/integrations",
                     json={"dosespot_clinic_id": "C-1", "dosespot_key": "sk_live_secret", "ai_assist_enabled": True})
    assert r.status_code == 200
    g = client.get(f"{base}/integrations").json()
    assert g["dosespot_clinic_id"] == "C-1"
    assert g["ai_assist_enabled"] is True
    assert g["dosespot_key_masked"].endswith("cret")
    assert "dosespot_key" not in g and "dosespot_key_enc" not in g


def test_schedule_replace(client, office_id):
    base = f"/api/v1/offices/{office_id}"
    # Auto-seeds 7 days on first GET.
    assert len(client.get(f"{base}/schedule").json()) == 7
    days = [{"day_of_week": d, "is_closed": d >= 5,
             "start_time": None if d >= 5 else "09:00:00",
             "end_time": None if d >= 5 else "18:00:00"} for d in range(7)]
    r = client.put(f"{base}/schedule", json={"days": days})
    assert r.status_code == 200
    sched = r.json()
    assert len(sched) == 7
    monday = next(x for x in sched if x["day_of_week"] == 0)
    assert monday["start_time"] == "09:00:00"


def test_office_holidays_scoped_and_isolated(client, office_id, db_session):
    base = f"/api/v1/offices/{office_id}"
    fed = client.post(f"{base}/holidays/federal", json={"year": 2026})
    assert len(fed.json()) == 11
    assert len(client.get(f"{base}/holidays").json()) == 11
    # Account-level holidays (office_id IS NULL) must NOT see the office's holidays.
    acct = client.get(f"/api/v1/tenants/{db_session._tenant_id}/holidays").json()
    assert len(acct) == 0


def test_advanced_settings(client, office_id):
    base = f"/api/v1/offices/{office_id}"
    r = client.patch(f"{base}/advanced-settings",
                     json={"finance_charge_pct": 1.5, "default_appt_duration": 30, "send_ecard": True})
    assert r.status_code == 200
    g = client.get(f"{base}/advanced-settings").json()
    assert float(g["finance_charge_pct"]) == 1.5
    assert g["default_appt_duration"] == 30
    assert g["send_ecard"] is True


def test_smart_assist(client, office_id):
    base = f"/api/v1/offices/{office_id}"
    r = client.patch(f"{base}/smart-assist",
                     json={"enabled": True, "items": [{"item_code": "recall", "frequency": "EVERY_YEAR"}]})
    assert r.status_code == 200
    g = client.get(f"{base}/smart-assist").json()
    assert g["enabled"] is True
    assert len(g["items"]) == 1
    assert g["items"][0]["item_code"] == "recall"


def test_office_not_in_tenant_forbidden(client, db_session):
    other = Tenant(name="Other", code="other", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    foreign = Office(tenant_id=other.id, office_code="OTHER", name="Other Office")
    db_session.add(foreign)
    db_session.commit()
    db_session.refresh(foreign)
    # Authenticated tenant is db_session._tenant_id; foreign office belongs to `other`.
    assert client.get(f"/api/v1/offices/{foreign.id}/statement-settings").status_code == 403
