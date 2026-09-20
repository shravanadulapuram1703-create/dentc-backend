"""AppointNow (external online booking) module tests.

Covers the public surface (office info / availability / intake, AN-1..3), the
soft-hold (AN-8), the staff inbox with counts (AN-4/AN-13), atomic approve +
booking (AN-5), decline, duplicate-patient matching (AN-9), and the round-2
gaps: approve FK ordering under enforced foreign keys (AN-BUG-1), reschedule
with conflict details (AN-14), persisted acknowledgements (AN-16), office_code
+ actor names on reads (AN-17), push events on the messaging tenant topic
(AN-6), opt-in provider exposure (AN-18), notifications (AN-21), purge (AN-24)
and the expiry sweep entry point (AN-25).
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
from app.integrations import sendgrid_client
from app.services import appointnow_notification_service as notify
from app.services import appointnow_service as svc
from app.services import messaging_events

# AN-BUG-1: run this module with SQLite foreign keys enforced (see conftest).
pytestmark = pytest.mark.enforce_fks


@pytest.fixture
def events(monkeypatch):
    """Capture appointnow.request envelopes instead of pushing to sockets (AN-6)."""
    captured: list[tuple[int, dict]] = []
    monkeypatch.setattr(messaging_events, "publish_tenant",
                        lambda tenant_id, envelope: captured.append((tenant_id, envelope)))
    return captured


@pytest.fixture
def booking_fixtures(db_session):
    # AN-20: the in-process rate-limit fallback (no Redis under test) is keyed
    # by office id + client IP, both identical across tests — reset it.
    svc._local_rate.clear()
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
    db_session.add_all([provider, hidden])
    db_session.flush()  # the operatory references PRV-1 and there is no relationship edge
    operatory = Operatory(id="OPR-1", office_id=office.id, name="Op 1", provider_id="PRV-1")
    db_session.add(operatory)
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
            "notes": contact.get("notes"),
            "insurance_info": contact.get("insurance_info", "Delta Dental #123"),
            # AN-16: both legal acknowledgements are required at intake.
            "disclaimer_accepted": contact.get("disclaimer_accepted", True),
            "consent_accepted": contact.get("consent_accepted", True),
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


# ── AN-16: intake acknowledgements are persisted and required ────────────────
def test_intake_persists_acknowledgements_as_columns(client, booking_fixtures, db_session):
    iso = booking_fixtures["future"].isoformat()
    body = _submit(client, iso, "09:00", notes="Prefers mornings").json()
    contact = body["contact"]
    assert contact["insurance_info"] == "Delta Dental #123"
    assert contact["disclaimer_accepted"] is True
    assert contact["consent_accepted"] is True
    assert contact["notes"] == "Prefers mornings"
    row = db_session.get(BookingRequest, body["id"])
    assert row.disclaimer_accepted is True and row.consent_accepted is True
    assert row.insurance_info == "Delta Dental #123"


@pytest.mark.parametrize("field", ["disclaimer_accepted", "consent_accepted"])
def test_intake_refuses_a_missing_or_false_acknowledgement(client, booking_fixtures, field):
    iso = booking_fixtures["future"].isoformat()
    for value in (False, None):
        r = _submit(client, iso, "09:00", **{field: value})
        assert r.status_code == 422, r.text
        err = r.json()["error"]
        assert err["code"] == "acknowledgement_required"
        assert err["details"]["field"] == field
    # Nothing was written — the slot is still open.
    slots = client.get(
        f"/api/v1/appointnow/offices/MAINST/availability?date={iso}&duration_minutes=60"
    ).json()["slots"]
    assert "09:00" in [s["start_time"] for s in slots]


def test_intake_accepts_the_frontends_interim_notes_markers(client, booking_fixtures):
    """A backend deployed before the frontend cut-over must keep booking: the
    acknowledgements folded into ``notes`` are lifted into their columns and the
    marker lines are stripped from the stored note."""
    iso = booking_fixtures["future"].isoformat()
    folded = (
        "Tooth hurts on the left\n"
        "Insurance: MetLife #987\n"
        "Disclaimer accepted: Yes\n"
        "Contact consent (calls/texts): Yes"
    )
    r = _submit(client, iso, "09:00", notes=folded, insurance_info=None,
                disclaimer_accepted=None, consent_accepted=None)
    assert r.status_code == 201, r.text
    contact = r.json()["contact"]
    assert contact["notes"] == "Tooth hurts on the left"
    assert contact["insurance_info"] == "MetLife #987"
    assert contact["disclaimer_accepted"] is True and contact["consent_accepted"] is True

    # A folded "No" is still a refusal.
    r2 = _submit(client, iso, "10:00", notes="Disclaimer accepted: No\nContact consent (calls/texts): Yes",
                 disclaimer_accepted=None, consent_accepted=None)
    assert r2.status_code == 422
    assert r2.json()["error"]["details"]["field"] == "disclaimer_accepted"


def test_split_contact_extras_is_the_inverse_of_the_frontend_fold():
    out = svc.split_contact_extras("free text\nInsurance: Aetna\nDisclaimer accepted: yes\n"
                                   "Contact consent (calls/texts): No")
    assert out == {"notes": "free text", "insurance_info": "Aetna",
                   "disclaimer_accepted": True, "consent_accepted": False}
    assert svc.split_contact_extras(None)["disclaimer_accepted"] is None


# ── AN-17: office_code + actor names on staff reads ──────────────────────────
def test_staff_reads_carry_office_code_and_actor_name(client, booking_fixtures, db_session):
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "09:00").json()["id"]

    listed = client.get("/api/v1/appointnow/requests").json()["items"][0]
    assert listed["office_code"] == "MAINST"
    assert listed["actioned_by_id"] is None and listed["actioned_by_name"] is None
    assert listed["original_slot"] is None

    admin = db_session._admin
    admin.first_name, admin.last_name = "Jane", "Doe"
    db_session.commit()
    approved = client.post(f"/api/v1/appointnow/requests/{req_id}/approve").json()
    assert approved["office_code"] == "MAINST"
    assert approved["actioned_by_id"] == admin.id
    assert approved["actioned_by_name"] == "Jane Doe"
    single = client.get(f"/api/v1/appointnow/requests/{req_id}").json()
    assert single["actioned_by_name"] == "Jane Doe"


# ── AN-BUG-1: approve under enforced foreign keys ────────────────────────────
def test_sqlite_enforces_foreign_keys_in_the_harness(db_session):
    """The harness turns ``PRAGMA foreign_keys`` on; without it the AN-BUG-1
    unit-of-work ordering bug (UPDATE booking_requests before INSERT
    appointments) passed here and was a 23503 on Postgres."""
    from sqlalchemy import text
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_approve_links_the_appointment_it_inserted(client, booking_fixtures, db_session):
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "13:00").json()["id"]
    body = client.post(f"/api/v1/appointnow/requests/{req_id}/approve",
                       json={"provider_id": "PRV-1", "operatory_id": "OPR-1"}).json()
    assert body["status"] == "approved", body
    appt = db_session.get(Appointment, body["appointment_id"])
    assert appt is not None and appt.operatory_id == "OPR-1"
    assert db_session.get(BookingRequest, req_id).appointment_id == appt.id


def test_approve_conflict_lists_the_overlapping_appointment(client, booking_fixtures, db_session):
    future = booking_fixtures["future"]
    req_id = _submit(client, future.isoformat(), "13:00").json()["id"]
    db_session.add(Appointment(
        id="APT-BLOCK", provider_id="PRV-1", operatory_id="OPR-1",
        office_id=booking_fixtures["office"].id, date=future,
        start_time=time(13, 30), end_time=time(14, 30), duration=60,
        status="Scheduled", procedure_label="Crown prep",
    ))
    db_session.commit()
    r = client.post(f"/api/v1/appointnow/requests/{req_id}/approve")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "slot_conflict"
    conflicts = err["details"]["conflicts"]
    assert conflicts[0]["appointment_id"] == "APT-BLOCK"
    assert conflicts[0]["kind"] == "provider"
    assert conflicts[0]["provider_name"] == "Dr. Jane Smith"
    assert conflicts[0]["operatory_name"] == "Op 1"
    assert conflicts[0]["procedure_label"] == "Crown prep"
    assert conflicts[0]["start_time"] == "13:30"
    # Nothing booked, still pending.
    assert client.get(f"/api/v1/appointnow/requests/{req_id}").json()["status"] == "pending"


# ── AN-14: reschedule ────────────────────────────────────────────────────────
def test_reschedule_pending_request(client, booking_fixtures, db_session, events):
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "09:00").json()["id"]
    later = (booking_fixtures["future"] + timedelta(days=1)).isoformat()

    r = client.post(f"/api/v1/appointnow/requests/{req_id}/reschedule",
                    json={"slot": {"date": later, "start_time": "14:00", "duration_minutes": 30}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["slot"] == {"date": later, "start_time": "14:00", "end_time": "14:30",
                            "duration_minutes": 30, "provider_id": "PRV-1",
                            "provider_name": "Dr. Jane Smith"}
    # The patient's first choice is preserved; the contact block is untouched.
    assert body["original_slot"]["date"] == iso
    assert body["original_slot"]["start_time"] == "09:00"
    assert body["original_slot"]["end_time"] == "10:00"
    assert body["contact"]["first_name"] == "Alex"
    assert body["reschedule_count"] == 1
    assert body["rescheduled_by_id"] == db_session._admin.id
    assert body["rescheduled_at"] is not None

    # The hold moved with it: the old slot is free again, the new one is held.
    old = client.get(f"/api/v1/appointnow/offices/MAINST/availability?date={iso}&duration_minutes=60").json()["slots"]
    assert "09:00" in [s["start_time"] for s in old]
    new = client.get(f"/api/v1/appointnow/offices/MAINST/availability?date={later}&duration_minutes=30").json()["slots"]
    assert "14:00" not in [s["start_time"] for s in new]

    # A second reschedule keeps the ORIGINAL original slot.
    r2 = client.post(f"/api/v1/appointnow/requests/{req_id}/reschedule",
                     json={"slot": {"date": later, "start_time": "15:00"}})
    assert r2.json()["original_slot"]["start_time"] == "09:00"
    assert r2.json()["reschedule_count"] == 2
    assert r2.json()["slot"]["duration_minutes"] == 30  # inherited from the current slot

    kinds = [e["event"] for _, e in events]
    assert kinds == ["created", "rescheduled", "rescheduled"]


def test_reschedule_conflict_returns_details(client, booking_fixtures, db_session):
    future = booking_fixtures["future"]
    req_id = _submit(client, future.isoformat(), "09:00").json()["id"]
    db_session.add(Appointment(
        id="APT-1", patient_id=None, provider_id="PRV-1", operatory_id="OPR-1",
        office_id=booking_fixtures["office"].id, date=future,
        start_time=time(15, 0), end_time=time(16, 0), duration=60, status="Scheduled",
    ))
    db_session.commit()
    r = client.post(f"/api/v1/appointnow/requests/{req_id}/reschedule",
                    json={"slot": {"date": future.isoformat(), "start_time": "15:30"}})
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "slot_conflict"
    assert [c["appointment_id"] for c in err["details"]["conflicts"]] == ["APT-1"]
    # Untouched.
    assert client.get(f"/api/v1/appointnow/requests/{req_id}").json()["slot"]["start_time"] == "09:00"


def test_reschedule_validation(client, booking_fixtures):
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "09:00").json()["id"]
    base = f"/api/v1/appointnow/requests/{req_id}/reschedule"
    # Unknown / other-office provider.
    r = client.post(base, json={"slot": {"date": iso, "start_time": "11:00",
                                         "provider_id": "NOPE"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_provider"
    # A hidden-from-public but active provider is fine for staff (AN-18 gates the page, not staff).
    r = client.post(base, json={"slot": {"date": iso, "start_time": "11:00",
                                         "provider_id": "PRV-2"}})
    assert r.status_code == 200 and r.json()["slot"]["provider_id"] == "PRV-2"
    # In the past.
    r = client.post(base, json={"slot": {"date": "2020-01-01", "start_time": "11:00"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "slot_in_past"
    # Settled requests cannot be rescheduled.
    client.post(f"/api/v1/appointnow/requests/{req_id}/decline")
    r = client.post(base, json={"slot": {"date": iso, "start_time": "11:00"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "request_not_pending"


# ── AN-6: push events on the messaging tenant topic ──────────────────────────
def test_push_events_ride_the_messaging_tenant_topic(client, booking_fixtures, db_session, events):
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "09:00").json()["id"]
    tenant_id, created = events[-1]
    assert tenant_id == db_session._tenant_id
    assert created["type"] == "appointnow.request"
    assert created["event"] == "created"
    assert created["office_id"] == booking_fixtures["office"].id
    assert created["request_id"] == req_id
    assert created["request"]["office_code"] == "MAINST"
    assert created["request"]["status"] == "pending"

    client.post(f"/api/v1/appointnow/requests/{req_id}/approve")
    _, updated = events[-1]
    assert updated["event"] == "updated"
    assert updated["status"] == "approved"
    assert updated["request"]["appointment_id"]

    client.delete(f"/api/v1/appointnow/requests/{req_id}?force=true")
    _, deleted = events[-1]
    assert deleted["event"] == "deleted" and deleted["request"] is None


# ── AN-18: provider exposure is opt-in ───────────────────────────────────────
def test_provider_visibility_defaults_to_hidden(client, booking_fixtures, db_session):
    db_session.add(Provider(id="PRV-3", tenant_id=db_session._tenant_id,
                            office_id=booking_fixtures["office"].id, name="Test Test"))
    db_session.commit()
    assert db_session.get(Provider, "PRV-3").visible_in_appointnow is False
    ids = [p["id"] for p in client.get("/api/v1/appointnow/offices/MAINST").json()["providers"]]
    assert ids == ["PRV-1"]


# ── AN-24: purge ─────────────────────────────────────────────────────────────
def test_purge_request(client, booking_fixtures, db_session):
    iso = booking_fixtures["future"].isoformat()
    spam = _submit(client, iso, "09:00").json()["id"]
    r = client.delete(f"/api/v1/appointnow/requests/{spam}")
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert db_session.get(BookingRequest, spam) is None
    assert client.get(f"/api/v1/appointnow/requests/{spam}").status_code == 404

    booked = _submit(client, iso, "10:00").json()["id"]
    appt_id = client.post(f"/api/v1/appointnow/requests/{booked}/approve").json()["appointment_id"]
    r = client.delete(f"/api/v1/appointnow/requests/{booked}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "request_approved"
    assert client.delete(f"/api/v1/appointnow/requests/{booked}?force=true").status_code == 200
    # The appointment survives a purge.
    assert db_session.get(Appointment, appt_id) is not None


# ── AN-21: notifications ─────────────────────────────────────────────────────
def test_contact_notification_is_log_only_without_transports(client, booking_fixtures):
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "09:00").json()["id"]
    body = client.post(f"/api/v1/appointnow/requests/{req_id}/approve").json()
    assert body["contact_notified_at"] is None and body["contact_notified_via"] is None


def test_contact_notification_emails_when_sendgrid_is_configured(
    client, booking_fixtures, db_session, monkeypatch
):
    sent: list[dict] = []
    monkeypatch.setattr(sendgrid_client, "is_configured", lambda: True)
    monkeypatch.setattr(sendgrid_client, "send_mail",
                        lambda **kw: sent.append(kw) or {"message_id": "m1"})
    booking_fixtures["office"].email = "front@mainst.example"
    db_session.commit()
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "09:00").json()["id"]
    # The office was e-mailed about the new request …
    assert sent and sent[0]["subject"].startswith("New online booking request")
    assert sent[0]["to_email"] == "front@mainst.example"
    assert "Delta Dental #123" in sent[0]["body_text"]

    sent.clear()
    body = client.post(f"/api/v1/appointnow/requests/{req_id}/decline",
                       json={"reason": "Fully booked"}).json()
    # … and the contact (no Twilio → e-mail) about the decline, stamped on the row.
    assert body["contact_notified_via"] == "email" and body["contact_notified_at"]
    assert sent[0]["to_email"] == "alex@example.com"
    assert "Fully booked" in sent[0]["body_text"]


def test_office_notification_address_fallback_chain(booking_fixtures, db_session):
    office = booking_fixtures["office"]
    assert notify.office_notification_email(db_session, office) is None
    office.email = "front@mainst.example"
    assert notify.office_notification_email(db_session, office) == "front@mainst.example"


def test_contact_message_wording(booking_fixtures, db_session):
    office = booking_fixtures["office"]
    req = BookingRequest(slot_date=date(2026, 9, 14), start_time=time(9, 0),
                         provider_name="Dr. Jane Smith")
    _, approved = notify.contact_message(office, req, "approved")
    assert approved.startswith(
        "Reckon Dental — Main St: your appointment request for Mon, Sep 14 at 9:00 AM "
        "with Dr. Jane Smith has been confirmed."
    )
    assert "(555) 123-4567" in approved
    req.decline_reason = "Provider unavailable"
    _, declined = notify.contact_message(office, req, "declined")
    assert "Provider unavailable" in declined


# ── AN-25: expiry entry point ────────────────────────────────────────────────
def test_expire_all_flips_passed_slots(client, booking_fixtures, db_session, events):
    iso = booking_fixtures["future"].isoformat()
    req_id = _submit(client, iso, "09:00").json()["id"]
    row = db_session.get(BookingRequest, req_id)
    row.slot_date = date.today() - timedelta(days=2)
    db_session.commit()
    summary = svc.expire_all(db_session)
    assert summary["expired"] == 1
    assert db_session.get(BookingRequest, req_id).status == "expired"
    assert events[-1][1]["event"] == "expired"
    assert client.get("/api/v1/appointnow/requests").json()["counts"]["expired"] == 1


# ── AN-19: office end-of-day cap + lunch on the provider fallback ────────────
def test_availability_honours_office_day_row_and_lunch(client, booking_fixtures, db_session):
    from app.db.models.office_setup import OfficeScheduleDay
    future = booking_fixtures["future"]
    db_session.add(OfficeScheduleDay(
        tenant_id=db_session._tenant_id, office_id=booking_fixtures["office"].id,
        day_of_week=future.weekday(), start_time=time(9, 0), end_time=time(13, 0),
        lunch_start=time(11, 0), lunch_end=time(11, 30),
    ))
    db_session.commit()
    starts = [s["start_time"] for s in client.get(
        f"/api/v1/appointnow/offices/MAINST/availability?date={future.isoformat()}&duration_minutes=60"
    ).json()["slots"]]
    assert starts and starts[0] == "09:00" and starts[-1] == "12:00"  # 13:00 end cap
    assert "10:30" not in starts and "11:00" not in starts  # lunch honoured
