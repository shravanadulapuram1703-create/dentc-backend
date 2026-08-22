"""Add/Edit Appointment gap tests.

Covers the gaps raised in ``docs/scheduler/add_edit_appointment_backend_devreport.md``:

* SCHED-DEL-1  soft-deleted appointments must not come back on the calendar feed
* SCHED-DEL-2  ``POST /appointments/{id}/restore`` puts one back
* APPT-PROC-1/2/3  per-line duration / provider units / bill-to round-trip
* APPT-PROC-4  the archived appointment-procedure must not come back on reload
* APPT-5      ``lab_dds`` round-trips
* APPT-7      the campaign catalog exists and is tenant-scoped
* APPT-10     ``GET /procedure-code-categories``
"""

from __future__ import annotations

from datetime import date, time

import pytest

from app.db.models import Appointment, Office, Operatory, Patient, ProcedureCode, Provider


@pytest.fixture
def appt_fixtures(db_session):
    tid = db_session._tenant_id
    office = Office(tenant_id=tid, office_code="APPT", name="Appt Office")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    provider = Provider(id="PRV-A1", tenant_id=tid, office_id=office.id, name="Dr. Bell")
    operatory = Operatory(id="OPR-A1", office_id=office.id, name="Op A", provider_id="PRV-A1")
    patient = Patient(tenant_id=tid, first_name="Ayaan", last_name="Allu", chart_no="CH-A1")
    db_session.add_all([
        provider, operatory, patient,
        ProcedureCode(code="D2391", description="Resin composite one surface posterior",
                      category="restorative"),
        ProcedureCode(code="D0150", description="Comprehensive oral evaluation",
                      category="diagnostic"),
        ProcedureCode(code="D4341", description="Periodontal scaling and root planing",
                      category="periodontics", is_active=False),
    ])
    db_session.commit()
    db_session.refresh(patient)
    appt = Appointment(
        id="APPT-A1", patient_id=patient.id, provider_id="PRV-A1", operatory_id="OPR-A1",
        office_id=office.id, date=date(2026, 8, 19), start_time=time(9, 0), end_time=time(9, 30),
        duration=30, status="Scheduled",
    )
    db_session.add(appt)
    db_session.commit()
    return {"office": office, "patient": patient, "appt": appt}


# ── SCHED-DEL-1 / SCHED-DEL-2 ────────────────────────────────────────────────
def test_deleted_appointment_leaves_the_scheduler_feed(client, appt_fixtures):
    feed = "/api/v1/appointments/scheduler?date_from=2026-08-01&date_to=2026-08-31"
    assert [r["id"] for r in client.get(feed).json()] == ["APPT-A1"]

    assert client.delete("/api/v1/appointments/APPT-A1").status_code == 204
    # The row survives (soft delete) but must not be handed back to the calendar.
    assert client.get("/api/v1/appointments/APPT-A1").json()["is_archived"] is True
    assert client.get(feed).json() == []


def test_scheduler_feed_can_opt_back_into_archived_rows(client, appt_fixtures):
    client.delete("/api/v1/appointments/APPT-A1")
    rows = client.get(
        "/api/v1/appointments/scheduler"
        "?date_from=2026-08-01&date_to=2026-08-31&include_archived=true"
    ).json()
    assert [r["id"] for r in rows] == ["APPT-A1"]
    # is_archived is exposed so the caller can tell the tombstone apart.
    assert rows[0]["is_archived"] is True


def test_restore_puts_the_appointment_back(client, appt_fixtures):
    feed = "/api/v1/appointments/scheduler?date_from=2026-08-01&date_to=2026-08-31"
    client.delete("/api/v1/appointments/APPT-A1")
    assert client.get(feed).json() == []

    restored = client.post("/api/v1/appointments/APPT-A1/restore")
    assert restored.status_code == 200
    assert restored.json()["is_archived"] is False
    assert [r["id"] for r in client.get(feed).json()] == ["APPT-A1"]

    # Idempotent — restoring a live appointment is a no-op, not a 409.
    assert client.post("/api/v1/appointments/APPT-A1/restore").status_code == 200


def test_restore_rejects_an_unknown_appointment(client, appt_fixtures):
    assert client.post("/api/v1/appointments/APPT-nope/restore").status_code == 404


# ── APPT-5 ───────────────────────────────────────────────────────────────────
def test_lab_dds_round_trips(client, appt_fixtures):
    updated = client.patch(
        "/api/v1/appointments/APPT-A1",
        json={"has_lab": True, "lab_dds": "Dr. Bell", "lab_cost": "125.00"},
    ).json()
    assert updated["lab_dds"] == "Dr. Bell"
    assert client.get("/api/v1/appointments/APPT-A1").json()["lab_dds"] == "Dr. Bell"


# ── APPT-PROC-1 / 2 / 3 ──────────────────────────────────────────────────────
def test_appointment_procedure_line_columns_round_trip(client, appt_fixtures):
    created = client.post("/api/v1/appointment-procedures", json={
        "appointment_id": "APPT-A1",
        "procedure_code": "D2391",
        "provider_id": "PRV-A1",
        "tooth": "19",
        "surface": "MO",
        "fee": "92.00",
        "duration_minutes": 45,
        "provider_units": 2,
        "bill_to": "I",
    })
    assert created.status_code == 201
    body = created.json()
    assert body["duration_minutes"] == 45
    assert body["provider_units"] == 2
    assert body["bill_to"] == "I"

    reloaded = client.get(f"/api/v1/appointment-procedures/{body['id']}").json()
    assert (reloaded["duration_minutes"], reloaded["provider_units"], reloaded["bill_to"]) \
        == (45, 2, "I")


def test_provider_units_defaults_to_one(client, appt_fixtures):
    body = client.post("/api/v1/appointment-procedures", json={
        "appointment_id": "APPT-A1", "procedure_code": "D0150", "fee": "50.00",
    }).json()
    assert body["provider_units"] == 1
    assert body["duration_minutes"] is None  # "not set" stays distinct from zero


# ── APPT-PROC-4 ──────────────────────────────────────────────────────────────
def test_deleted_appointment_procedure_does_not_come_back(client, appt_fixtures):
    listing = "/api/v1/appointment-procedures?appointment_id=APPT-A1"
    first = client.post("/api/v1/appointment-procedures", json={
        "appointment_id": "APPT-A1", "procedure_code": "D2391", "fee": "92.00",
    }).json()
    client.post("/api/v1/appointment-procedures", json={
        "appointment_id": "APPT-A1", "procedure_code": "D0150", "fee": "50.00",
    })
    assert client.get(listing).json()["meta"]["total"] == 2

    assert client.delete(f"/api/v1/appointment-procedures/{first['id']}").status_code == 204
    remaining = client.get(listing).json()
    assert remaining["meta"]["total"] == 1
    assert [i["procedure_code"] for i in remaining["items"]] == ["D0150"]

    # ...but the archived line is still reachable on purpose.
    archived = client.get(f"{listing}&is_archived=true").json()
    assert [i["id"] for i in archived["items"]] == [first["id"]]


# ── APPT-7 ───────────────────────────────────────────────────────────────────
def test_campaign_catalog_is_listable_and_filterable(client, appt_fixtures):
    office_id = appt_fixtures["office"].id
    created = client.post("/api/v1/campaigns", json={
        "code": "SPRING26", "name": "Spring 2026 whitening", "channel": "email",
        "office_id": office_id, "start_date": "2026-03-01", "end_date": "2026-05-31",
    })
    assert created.status_code == 201
    assert created.json()["code"] == "SPRING26"

    listed = client.get("/api/v1/campaigns?channel=email").json()
    assert [c["code"] for c in listed["items"]] == ["SPRING26"]
    assert client.get("/api/v1/campaigns?channel=sms").json()["meta"]["total"] == 0

    # The appointment still stores the code as a string — no wire change.
    appt = client.patch("/api/v1/appointments/APPT-A1", json={"campaign_id": "SPRING26"}).json()
    assert appt["campaign_id"] == "SPRING26"


# ── APPT-10 ──────────────────────────────────────────────────────────────────
def test_procedure_code_categories(client, appt_fixtures):
    rows = client.get("/api/v1/procedure-code-categories").json()
    by_name = {r["category"]: r for r in rows}
    assert by_name["restorative"]["code_count"] == 1
    assert by_name["periodontics"]["code_count"] == 1
    assert by_name["periodontics"]["active_code_count"] == 0  # the D4341 row is inactive
    # Sorted case-insensitively so the buttons render in a stable order.
    assert [r["category"] for r in rows] == sorted(by_name, key=str.lower)


def test_procedure_code_categories_active_only(client, appt_fixtures):
    rows = client.get("/api/v1/procedure-code-categories?active_only=true").json()
    assert "periodontics" not in {r["category"] for r in rows}


# ── APPT-8 / APPT-9: the CDT rule derivation behind the seed script ──────────
def test_cdt_requirement_flags_are_derived_from_the_code_family():
    from scripts.seed_procedure_code_rules import derive

    # The exact code the dev report caught: needs a tooth *and* a surface.
    d2391 = derive("D2391")
    assert (d2391["requires_tooth"], d2391["requires_surface"]) == (True, True)
    # Scaling and root planing is quadrant-scoped, not tooth-scoped.
    d4341 = derive("D4341")
    assert (d4341["requires_quadrant"], d4341["requires_tooth"]) == (True, False)
    # A crown is tooth-scoped and lab-fabricated.
    d2740 = derive("D2740")
    assert (d2740["requires_tooth"], d2740["requires_lab"]) == (True, True)
    # An exam needs none of them but does carry a chair time.
    d0150 = derive("D0150")
    assert not any(d0150[f] for f in
                   ("requires_tooth", "requires_surface", "requires_quadrant", "requires_lab"))
    assert d0150["default_duration_minutes"] == 60
    # Non-CDT (medical/CPT) codes carry no ADA taxonomy to derive from.
    assert derive("41899") is None
