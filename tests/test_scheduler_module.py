"""Scheduler module tests (denormalized feed, status stamping, patient context, new fields)."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.db.models import (
    Appointment,
    Definition,
    Office,
    Operatory,
    Patient,
    Provider,
)


@pytest.fixture
def scheduler_fixtures(db_session):
    tid = db_session._tenant_id
    office = Office(tenant_id=tid, office_code="MAIN", name="Main")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    provider = Provider(id="PRV-1", tenant_id=tid, office_id=office.id, name="Dr. Adams")
    operatory = Operatory(id="OPR-1", office_id=office.id, name="Op 1", provider_id="PRV-1")
    patient = Patient(tenant_id=tid, first_name="Jane", last_name="Doe", chart_no="CH-1")
    db_session.add_all([provider, operatory, patient])
    db_session.commit()
    db_session.refresh(patient)
    appt = Appointment(
        id="APPT-1", patient_id=patient.id, provider_id="PRV-1", operatory_id="OPR-1",
        office_id=office.id, date=date(2026, 6, 10), start_time=time(9, 0), end_time=time(9, 30),
        duration=30, status="Scheduled",
    )
    db_session.add(appt)
    db_session.commit()
    return {"office": office, "patient": patient, "appt": appt}


def test_scheduler_feed_resolves_names(client, scheduler_fixtures):
    rows = client.get("/api/v1/appointments/scheduler?date_from=2026-06-01&date_to=2026-06-30").json()
    assert len(rows) == 1
    r = rows[0]
    assert r["patient_name"] == "Doe, Jane"
    assert r["provider_name"] == "Dr. Adams"
    assert r["operatory_name"] == "Op 1"


def test_scheduler_feed_office_and_date_filter(client, scheduler_fixtures):
    # Out-of-range date returns nothing.
    assert client.get("/api/v1/appointments/scheduler?date_from=2026-07-01&date_to=2026-07-31").json() == []


def test_status_transition_stamps_timestamps(client, scheduler_fixtures):
    base = "/api/v1/appointments/APPT-1/status"
    confirmed = client.patch(base, json={"status": "Confirmed"}).json()
    assert confirmed["status"] == "Confirmed"
    assert confirmed["confirmed_on"] is not None

    checked_out = client.patch(base, json={"status": "Checked Out"}).json()
    assert checked_out["checked_out_on"] is not None

    cancelled = client.patch(base, json={"status": "Cancelled"}).json()
    assert cancelled["is_cancelled"] is True


def test_patient_context_aggregate(client, scheduler_fixtures):
    pid = scheduler_fixtures["patient"].id
    ctx = client.get(f"/api/v1/patients/{pid}/context").json()
    assert ctx["patient"]["id"] == pid
    assert ctx["patient"]["first_name"] == "Jane"
    assert "balance" in ctx and "total_charged" in ctx["balance"]
    assert isinstance(ctx["insurance"], list)
    assert "visit" in ctx


def test_operatory_provider_id_roundtrips(client, scheduler_fixtures):
    op = client.get("/api/v1/operatories/OPR-1").json()
    assert op["provider_id"] == "PRV-1"


def test_definition_color_exposed(client, db_session):
    db_session.add(Definition(
        tenant_id=db_session._tenant_id, group_code="appt_status", key1="confirmed",
        description="Confirmed", color="#10B981", sort_order=1, is_active=True,
    ))
    db_session.commit()
    rows = client.get("/api/v1/definitions?group_code=appt_status").json()["items"]
    conf = next(r for r in rows if r["key1"] == "confirmed")
    assert conf["color"] == "#10B981"


def test_cross_tenant_status_forbidden(client, db_session, scheduler_fixtures):
    from app.db.models import Tenant
    other = Tenant(name="Other", code="other_sched", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    foreign_office = Office(tenant_id=other.id, office_code="F", name="Foreign")
    db_session.add(foreign_office)
    db_session.commit()
    db_session.refresh(foreign_office)
    appt = Appointment(
        id="APPT-X", provider_id="PRV-1", office_id=foreign_office.id, date=date(2026, 6, 10),
        start_time=time(9, 0), end_time=time(9, 30), duration=30, status="Scheduled",
    )
    db_session.add(appt)
    db_session.commit()
    assert client.patch("/api/v1/appointments/APPT-X/status", json={"status": "Confirmed"}).status_code == 403
