"""AppointNow (external online booking) module tests.

Covers the public surface (office info / availability / intake, AN-1..3), the
soft-hold (AN-8), the staff inbox with counts (AN-4/AN-13), atomic approve +
booking (AN-5), decline, and duplicate-patient matching (AN-9).
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app.db.models import (
    Appointment,
    AppointNowReason,
    BookingRequest,
    Office,
    Operatory,
    Patient,
    Provider,
)


@pytest.fixture
def booking_fixtures(db_session):
    tid = db_session._tenant_id
    office = Office(
        tenant_id=tid, office_code="MAINST", name="Reckon Dental — Main St",
        timezone="America/New_York", phone="(555) 123-4567",
        address_line1="123 Main St", city="Springfield", state="IL", zip="62701",
    )
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    provider = Provider(
        id="PRV-1", tenant_id=tid, office_id=office.id, name="Dr. Jane Smith",
        title="DDS", visible_in_appointnow=True,
    )
    hidden = Provider(
        id="PRV-2", tenant_id=tid, office_id=office.id, name="Dr. Hidden",
        visible_in_appointnow=False,
    )
    operatory = Operatory(id="OPR-1", office_id=office.id, name="Op 1", provider_id="PRV-1")
    db_session.add_all([provider, hidden, operatory])
    db_session.commit()
    # A safely-future weekday so no slot is dropped as "already started".
    future = date.today() + timedelta(days=14)
    return {"office": office, "provider": provider, "future": future}


# ── AN-1: public office info ─────────────────────────────────────────────────
def test_public_office_info(client, booking_fixtures):
    r = client.get("/api/v1/appointnow/offices/MAINST")
    assert r.status_code == 200
    body = r.json()
    assert body["office_code"] == "MAINST"
    assert body["name"] == "Reckon Dental — Main St"
    assert body["timezone"] == "America/New_York"
    # Only AppointNow-visible providers (PRV-2 hidden).
    assert [p["id"] for p in body["providers"]] == ["PRV-1"]
    assert body["providers"][0]["title"] == "DDS"
    # Default reason catalog is served when none are customised.
    assert len(body["reasons"]) > 0
    assert all("duration_minutes" in reason for reason in body["reasons"])


def test_public_office_info_unknown_is_404_not_401(client):
    r = client.get("/api/v1/appointnow/offices/NOPE")
    assert r.status_code == 404  # AN-12: never 401 for a public visitor


def test_custom_reason_catalog_overrides_default(client, booking_fixtures, db_session):
    db_session.add(AppointNowReason(
        tenant_id=db_session._tenant_id, office_id=booking_fixtures["office"].id,
        reason_code="whitening", label="Teeth Whitening", duration_minutes=45,
        display_order=1, is_active=True,
    ))
    db_session.commit()
    reasons = client.get("/api/v1/appointnow/offices/MAINST").json()["reasons"]
    assert [r["id"] for r in reasons] == ["whitening"]
    assert reasons[0]["duration_minutes"] == 45


# ── AN-2: availability ───────────────────────────────────────────────────────
def test_availability_returns_slots(client, booking_fixtures):
    iso = booking_fixtures["future"].isoformat()
    r = client.get(f"/api/v1/appointnow/offices/MAINST/availability?date={iso}&duration_minutes=60")
    assert r.status_code == 200
    body = r.json()
    assert body["timezone"] == "America/New_York"
    assert len(body["slots"]) > 0
    slot = body["slots"][0]
    assert slot["date"] == iso
    assert slot["provider_id"] == "PRV-1"
    assert slot["duration_minutes"] == 60
    # Fallback office hours are 08:00–17:00; a 60-min slot starts no earlier than 08:00.
    assert slot["start_time"] >= "08:00"


def test_availability_past_date_is_empty(client, booking_fixtures):
    past = (date.today() - timedelta(days=1)).isoformat()
    body = client.get(f"/api/v1/appointnow/offices/MAINST/availability?date={past}").json()
    assert body["slots"] == []


# ── AN-3 + AN-8: intake soft-holds the slot ──────────────────────────────────
def _submit(client, iso, start_time="09:00", **contact):
    payload = {
        "reason_id": "cleaning",
        "reason_label": "Cleaning",
        "slot": {"date": iso, "start_time": start_time, "duration_minutes": 60,
                 "provider_id": "PRV-1"},
        "contact": {
            "first_name": contact.get("first_name", "Alex"),
            "last_name": contact.get("last_name", "Rivera"),
            "phone": contact.get("phone", "555-987-6543"),
            "email": contact.get("email", "alex@example.com"),
            "is_new_patient": True,
        },
    }
    return client.post("/api/v1/appointnow/offices/MAINST/requests", json=payload)


def test_submit_creates_pending_and_holds_slot(client, booking_fixtures):
    iso = booking_fixtures["future"].isoformat()
    r = _submit(client, iso, "09:00")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["office_code"] == "MAINST"
    assert body["slot"]["start_time"] == "09:00"
    assert body["contact"]["first_name"] == "Alex"

    # The held slot no longer appears in availability (AN-8).
    slots = client.get(
        f"/api/v1/appointnow/offices/MAINST/availability?date={iso}&duration_minutes=60"
    ).json()["slots"]
    assert "09:00" not in [s["start_time"] for s in slots]


def test_double_submit_same_slot_conflicts(client, booking_fixtures):
    iso = booking_fixtures["future"].isoformat()
    assert _submit(client, iso, "10:00").status_code == 201
    second = _submit(client, iso, "10:00")
    assert second.status_code == 409  # slot no longer available


# ── AN-4 / AN-13: staff inbox with counts ────────────────────────────────────
def test_inbox_lists_with_counts(client, booking_fixtures):
    iso = booking_fixtures["future"].isoformat()
    _submit(client, iso, "09:00")
    _submit(client, iso, "11:00", first_name="Sam", phone="555-111-2222")

    body = client.get("/api/v1/appointnow/requests").json()
    assert body["total"] == 2
    assert body["counts"]["pending"] == 2
    assert body["counts"]["all"] == 2
    assert len(body["items"]) == 2

    # Free-text search narrows the list but counts stay unfiltered.
    filtered = client.get("/api/v1/appointnow/requests?q=Sam").json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["contact"]["first_name"] == "Sam"
    assert filtered["counts"]["pending"] == 2


# ── AN-5: approve books an appointment atomically ────────────────────────────
def test_approve_books_appointment(client, booking_fixtures, db_session):
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "13:00").json()["id"]

    r = client.post(f"/api/v1/appointnow/requests/{req_id}/approve")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["appointment_id"] is not None

    appt = db_session.get(Appointment, body["appointment_id"])
    assert appt is not None
    assert appt.provider_id == "PRV-1"
    assert appt.office_id == booking_fixtures["office"].id
    assert appt.start_time == time(13, 0)
    assert appt.procedure_label == "Cleaning"

    # Re-approving a settled request is a conflict.
    assert client.post(f"/api/v1/appointnow/requests/{req_id}/approve").status_code == 409


def test_approve_with_create_patient(client, booking_fixtures, db_session):
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "14:00", first_name="New", last_name="Patient",
                     phone="555-222-3333", email="new@example.com").json()["id"]

    body = client.post(
        f"/api/v1/appointnow/requests/{req_id}/approve", json={"create_patient": True}
    ).json()
    assert body["patient_id"] is not None
    patient = db_session.get(Patient, body["patient_id"])
    assert patient.first_name == "New"
    assert patient.tenant_id == db_session._tenant_id
    assert patient.chart_no  # auto-generated


# ── AN-5: decline ────────────────────────────────────────────────────────────
def test_decline_request(client, booking_fixtures):
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "15:00").json()["id"]
    body = client.post(
        f"/api/v1/appointnow/requests/{req_id}/decline", json={"reason": "Fully booked"}
    ).json()
    assert body["status"] == "declined"
    assert body["decline_reason"] == "Fully booked"

    counts = client.get("/api/v1/appointnow/requests").json()["counts"]
    assert counts["declined"] == 1
    assert counts["pending"] == 0


# ── AN-9: duplicate-patient matching ─────────────────────────────────────────
def test_patient_matches(client, booking_fixtures, db_session):
    db_session.add(Patient(
        tenant_id=db_session._tenant_id, first_name="Alex", last_name="Rivera",
        phone="5559876543", email="alex@example.com", chart_no="CH-EXIST",
    ))
    db_session.commit()
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "16:00", phone="555-987-6543",
                     email="alex@example.com").json()["id"]

    matches = client.get(f"/api/v1/appointnow/requests/{req_id}/patient-matches").json()
    assert len(matches) == 1
    assert matches[0]["chart_no"] == "CH-EXIST"
    assert set(matches[0]["match_on"]) >= {"phone", "email"}


def test_reason_catalog_crud(client, booking_fixtures):
    created = client.post("/api/v1/appointnow-reasons", json={
        "tenant_id": 0, "office_id": booking_fixtures["office"].id,
        "reason_code": "consult", "label": "Consult", "duration_minutes": 30,
    })
    assert created.status_code in (200, 201)
    listed = client.get("/api/v1/appointnow-reasons?office_id=" + str(booking_fixtures["office"].id))
    assert listed.status_code == 200
    assert any(r["reason_code"] == "consult" for r in listed.json()["items"])
