"""Patient SMS (Twilio) module — SMS-1…10 + EMAIL-1 (docs/sms/SMS_BACKEND_DEVREPORT.md)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.core.config import settings
from app.db.models import (
    AccountCommunications,
    Appointment,
    Office,
    OfficePhoneAssignment,
    Patient,
    Provider,
    SmsMessage,
)
from app.integrations import twilio_client
from app.integrations.twilio_client import TwilioError, compute_signature
from app.services import sms_service
from app.services.sms_phone import normalize_e164, phone_variants

INBOUND_URL = "http://testserver/api/v1/sms/webhooks/inbound"
STATUS_URL = "http://testserver/api/v1/sms/webhooks/status"
OFFICE_NUMBER = "+14125550100"
PATIENT_CELL = "(210) 793-6174"          # legacy storage spelling
PATIENT_E164 = "+12107936174"


@pytest.fixture
def seed(db_session):
    tid = db_session._tenant_id
    office = Office(tenant_id=tid, office_code="SMSO", name="Moon Township", phone="(412) 555-0100",
                    timezone="America/New_York")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    provider = Provider(id="PRV-S1", tenant_id=tid, office_id=office.id, name="Dr. Bell", title="Dr.")
    patient = Patient(tenant_id=tid, first_name="Yolanda", last_name="Diaz", chart_no="CH-S1",
                      cell_phone=PATIENT_CELL, home_office_id=office.id, email="yolanda@example.com")
    db_session.add_all([provider, patient])
    db_session.commit()
    db_session.refresh(patient)
    appt = Appointment(
        id="APPT-S1", patient_id=patient.id, provider_id="PRV-S1", office_id=office.id,
        date=date(2026, 9, 10), start_time=time(9, 30), end_time=time(10, 0), duration=30,
        status="Scheduled",
    )
    db_session.add(appt)
    db_session.add(OfficePhoneAssignment(tenant_id=tid, office_id=office.id,
                                         assignment_type="office_specific", phone_number=OFFICE_NUMBER))
    # Quiet hours are judged against the wall clock in the office timezone, so
    # the suite would fail every evening without an always-open window here.
    comm = AccountCommunications(tenant_id=tid, sms_quiet_hours_start=0, sms_quiet_hours_end=24)
    db_session.add(comm)
    db_session.commit()
    return {"office": office, "patient": patient, "appt": appt, "tid": tid, "comm": comm}


@pytest.fixture
def no_validation(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_WEBHOOK_VALIDATE", False)


@pytest.fixture
def twilio_live(monkeypatch):
    """Configured Twilio with the REST call stubbed out."""
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "secret-token")
    calls: list[dict] = []

    def fake_send(**kwargs):
        calls.append(kwargs)
        return {"sid": f"SM{len(calls):032d}", "status": "queued", "num_segments": 1,
                "error_code": None, "error_message": None}

    monkeypatch.setattr(twilio_client, "send_message", fake_send)
    return calls


def _send_payload(seed, **over):
    body = {"patient_id": seed["patient"].id, "office_id": seed["office"].id,
            "appointment_id": "APPT-S1", "to_phone": PATIENT_E164,
            "body": "Hi Yolanda, see you Thursday.", "message_type": "manual",
            "client_id": "sms_abc123"}
    body.update(over)
    return body


# ── phone helpers ─────────────────────────────────────────────────────────────
def test_normalize_and_variants():
    assert normalize_e164("(210) 793-6174") == PATIENT_E164
    assert normalize_e164("12107936174") == PATIENT_E164
    assert normalize_e164(PATIENT_E164) == PATIENT_E164
    assert normalize_e164("12345") is None
    assert PATIENT_CELL in phone_variants(PATIENT_E164)
    assert "2107936174" in phone_variants(PATIENT_E164)


def test_infer_message_type():
    assert sms_service.infer_message_type("Reminder: your appointment is tomorrow", None) == "appointment_reminder"
    assert sms_service.infer_message_type("Please confirm your visit", None) == "appointment_confirmation"
    assert sms_service.infer_message_type("Your balance of $40 is due", None) == "balance"
    assert sms_service.infer_message_type(None, "ok thanks") == "inbound_reply"


# ── SMS-1: gateway ────────────────────────────────────────────────────────────
def test_send_probe_is_post_only_and_gateway_reports_log_only(client, seed):
    assert client.get("/api/v1/sms/send").status_code == 405  # FE probe: 405 == route exists
    r = client.get("/api/v1/sms/gateway")
    assert r.status_code == 200
    assert r.json()["configured"] is False and r.json()["mode"] == "log_only"
    assert r.json()["quiet_hours"] == {"start_hour": 0, "end_hour": 24}  # seed's always-open window


def test_send_persists_queued_in_log_only_mode(client, db_session, seed):
    r = client.post("/api/v1/sms/send", json=_send_payload(seed))
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["send_status"] == "queued" and row["direction"] == "outbound"
    assert row["from_phone"] == OFFICE_NUMBER            # SMS-7: office_specific assignment
    assert row["sent_phone"] == PATIENT_E164 and row["sent_at"] is not None
    assert row["patient_name"] == "Yolanda Diaz" and row["office_name"] == "Moon Township"
    assert row["created_by"] == db_session._admin.id  # SMS-10
    assert row["client_id"] == "sms_abc123" and row["appointment_id"] == "APPT-S1"

    # Idempotent: same client_id → 409 carrying the existing row.
    r2 = client.post("/api/v1/sms/send", json=_send_payload(seed))
    assert r2.status_code == 409
    err = r2.json()["error"]
    assert err["code"] == "duplicate_client_id"
    assert err["details"]["sms_message"]["id"] == row["id"]
    # It also appears in the patient's log via the generic resource.
    lst = client.get(f"/api/v1/sms-messages?patient_id={seed['patient'].id}").json()
    assert lst["meta"]["total"] == 1


def test_send_validation(client, seed):
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, to_phone="123", client_id="c1"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_phone"
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="inbound_reply", client_id="c2"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "sms_invalid_message_type"
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, patient_id=999999, client_id="c3"))
    assert r.status_code == 404


def test_sender_resolution_order(client, db_session, seed):
    r = client.get(f"/api/v1/sms/sender?office_id={seed['office'].id}").json()
    assert r["from_phone"] == OFFICE_NUMBER and r["source"] == "office_specific"
    # Another office with no assignment → tenant default → none.
    other = Office(tenant_id=seed["tid"], office_code="SMS2", name="Greentree")
    db_session.add(other)
    db_session.commit()
    r = client.get(f"/api/v1/sms/sender?office_id={other.id}").json()
    assert r["from_phone"] is None and r["source"] == "none"
    seed["comm"].sms_from_phone = "412-555-0199"
    seed["comm"].messaging_service_sid = "MGtenant"
    db_session.commit()
    r = client.get(f"/api/v1/sms/sender?office_id={other.id}").json()
    assert r["from_phone"] == "+14125550199" and r["source"] == "tenant_default"
    assert r["messaging_service_sid"] == "MGtenant"


# ── SMS-8: consent + quiet hours ─────────────────────────────────────────────
def test_consent_enforced(client, db_session, seed):
    seed["patient"].no_auto_sms = True
    db_session.commit()
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="appointment_reminder", client_id="k1"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "patient_opted_out"
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="manual", client_id="k2"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "consent_override_required"
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="manual", client_id="k3",
                                                          override_consent=True))
    assert r.status_code == 201


def test_quiet_hours_refuse_automated_only(client, db_session, seed):
    seed["comm"].sms_quiet_hours_start = 0
    seed["comm"].sms_quiet_hours_end = 0  # empty window: always quiet
    db_session.commit()
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="recall", client_id="q1"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "sms_quiet_hours"
    assert "next_allowed_at" in r.json()["error"]["details"]
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="manual", client_id="q2"))
    assert r.status_code == 201


def test_quiet_hours_window_math(seed):
    office = seed["office"]  # America/New_York
    comm = AccountCommunications(tenant_id=seed["tid"], sms_quiet_hours_start=8, sms_quiet_hours_end=21)
    # 02:00 UTC in September = 22:00 EDT → quiet; next allowed is 08:00 the next day.
    nxt = sms_service._quiet_hours_violation(comm, office, datetime(2026, 9, 10, 2, 0, tzinfo=UTC))
    assert nxt is not None and nxt.hour == 8 and nxt.date() == date(2026, 9, 10)
    # 15:00 UTC = 11:00 EDT → allowed.
    assert sms_service._quiet_hours_violation(comm, office, datetime(2026, 9, 10, 15, 0, tzinfo=UTC)) is None


# ── SMS-1 with Twilio configured ─────────────────────────────────────────────
def test_send_live_records_twilio_sid(client, db_session, seed, twilio_live):
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, client_id="live1"))
    assert r.status_code == 201, r.text
    assert r.json()["twilio_sid"].startswith("SM") and r.json()["segments"] == 1
    assert twilio_live[0]["to"] == PATIENT_E164 and twilio_live[0]["from_phone"] == OFFICE_NUMBER
    assert client.get("/api/v1/sms/gateway").json()["mode"] == "live"


def test_send_live_rejection_persists_failed_and_502(client, db_session, seed, monkeypatch, twilio_live):
    def boom(**kwargs):
        raise TwilioError("The 'To' number is not a valid phone number.", code=21211, status_code=400)

    monkeypatch.setattr(twilio_client, "send_message", boom)
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, client_id="bad1"))
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["code"] == "twilio_error" and err["details"]["code"] == 21211
    row = db_session.get(SmsMessage, err["details"]["sms_message"]["id"])
    assert row.send_status == "failed" and row.error_code == 21211


# ── SMS-2: webhooks ──────────────────────────────────────────────────────────
def _signed_post(client, url, form, token="secret-token"):
    sig = compute_signature(url, form, token)
    return client.post(url, data=form, headers={"X-Twilio-Signature": sig})


def test_webhook_signature_required(client, seed, monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "secret-token")
    form = {"MessageSid": "SMin1", "From": PATIENT_E164, "To": OFFICE_NUMBER, "Body": "hello"}
    r = client.post(INBOUND_URL, data=form)
    assert r.status_code == 403 and r.json()["error"]["code"] == "twilio_signature_invalid"
    r = client.post(INBOUND_URL, data=form, headers={"X-Twilio-Signature": "nope"})
    assert r.status_code == 403
    r = _signed_post(client, INBOUND_URL, form)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    assert "<Response></Response>" in r.text


def test_webhook_rejected_when_no_token_configured(client, seed, monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)
    r = client.post(INBOUND_URL, data={"MessageSid": "x", "From": PATIENT_E164, "To": OFFICE_NUMBER, "Body": "hi"},
                    headers={"X-Twilio-Signature": "anything"})
    assert r.status_code == 403


def test_inbound_reply_attaches_and_confirms_appointment(client, db_session, seed, no_validation):
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="appointment_reminder",
                                                          client_id="rem1"))
    assert r.status_code == 201
    out_id = r.json()["id"]
    form = {"MessageSid": "SMreply1", "From": "2107936174", "To": OFFICE_NUMBER, "Body": "C"}
    r = client.post(INBOUND_URL, data=form)
    assert r.status_code == 200
    row = db_session.get(SmsMessage, out_id)
    db_session.refresh(row)
    assert row.reply_text == "C" and row.reply_phone == PATIENT_E164 and row.is_read is False
    assert row.reply_intent == "confirm" and row.needs_attention is False
    assert row.reply_twilio_sid == "SMreply1"
    appt = db_session.get(Appointment, "APPT-S1")
    db_session.refresh(appt)
    assert appt.status == "Confirmed" and appt.confirmed_on is not None
    # Idempotent: Twilio retries with the same sid → no second row.
    client.post(INBOUND_URL, data=form)
    assert db_session.query(SmsMessage).count() == 1
    # A second text from the same number is now stand-alone (the outbound row has a reply).
    r = client.post(INBOUND_URL, data={**form, "MessageSid": "SMreply2", "Body": "see you then"})
    assert r.status_code == 200
    rows = db_session.query(SmsMessage).order_by(SmsMessage.id).all()
    assert len(rows) == 2
    standalone = rows[1]
    assert standalone.sent_text is None and standalone.direction == "inbound"
    assert standalone.send_status == "received" and standalone.message_type == "inbound_reply"
    assert standalone.patient_id == seed["patient"].id and standalone.from_phone == OFFICE_NUMBER


def test_inbound_reschedule_and_cancel_flags(client, db_session, seed, no_validation):
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="appointment_reminder", client_id="r1"))
    out_id = r.json()["id"]
    client.post(INBOUND_URL, data={"MessageSid": "SMr", "From": PATIENT_E164, "To": OFFICE_NUMBER, "Body": "R please"})
    appt = db_session.get(Appointment, "APPT-S1")
    db_session.refresh(appt)
    assert appt.add_to_call_list is True and appt.status == "Scheduled"
    row = db_session.get(SmsMessage, out_id)
    db_session.refresh(row)
    assert row.reply_intent == "reschedule" and row.needs_attention is True

    # New outbound, then "no" → flagged for staff, appointment NOT cancelled.
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="appointment_reminder", client_id="r2"))
    out2 = r.json()["id"]
    client.post(INBOUND_URL, data={"MessageSid": "SMn", "From": PATIENT_E164, "To": OFFICE_NUMBER, "Body": "No, cancel it"})
    row2 = db_session.get(SmsMessage, out2)
    db_session.refresh(row2)
    assert row2.reply_intent == "cancel" and row2.needs_attention is True
    db_session.refresh(appt)
    assert appt.status == "Scheduled"


def test_inbound_stop_and_start_keywords(client, db_session, seed, no_validation):
    r = client.post(INBOUND_URL, data={"MessageSid": "SMstop", "From": PATIENT_E164, "To": OFFICE_NUMBER, "Body": "STOP"})
    assert r.status_code == 200
    patient = db_session.get(Patient, seed["patient"].id)
    db_session.refresh(patient)
    assert patient.no_auto_sms is True and patient.sms_opt_out_at is not None
    row = db_session.query(SmsMessage).one()
    assert row.message_type == "opt_out" and row.reply_intent == "stop" and row.direction == "inbound"
    # Automated sends now refused …
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="recall", client_id="s1"))
    assert r.status_code == 400
    # … until START.
    client.post(INBOUND_URL, data={"MessageSid": "SMstart", "From": PATIENT_E164, "To": OFFICE_NUMBER, "Body": "start"})
    db_session.refresh(patient)
    assert patient.no_auto_sms is False and patient.sms_opt_in_at is not None
    rows = db_session.query(SmsMessage).order_by(SmsMessage.id).all()
    assert rows[-1].message_type == "opt_in"


def test_inbound_unmatched_family_number(client, db_session, seed, no_validation):
    sibling = Patient(tenant_id=seed["tid"], first_name="Marco", last_name="Diaz", chart_no="CH-S2",
                      phone="210-793-6174")
    db_session.add(sibling)
    db_session.commit()
    client.post(INBOUND_URL, data={"MessageSid": "SMfam", "From": PATIENT_E164, "To": OFFICE_NUMBER, "Body": "hi"})
    row = db_session.query(SmsMessage).one()
    assert row.patient_id is None
    assert sorted(row.candidate_patient_ids) == sorted([seed["patient"].id, sibling.id])
    # Once one of them has received a text from this office, the next reply resolves.
    client.post("/api/v1/sms/send", json=_send_payload(seed, patient_id=sibling.id, client_id="fam1"))
    client.post(INBOUND_URL, data={"MessageSid": "SMfam2", "From": PATIENT_E164, "To": OFFICE_NUMBER, "Body": "ok"})
    out = db_session.query(SmsMessage).filter(SmsMessage.client_id == "fam1").one()
    db_session.refresh(out)
    assert out.reply_text == "ok" and out.patient_id == sibling.id
    # Inbox filters (SMS-6).
    unmatched = client.get("/api/v1/sms-messages?unmatched=true").json()
    assert unmatched["meta"]["total"] == 1 and unmatched["items"][0]["id"] == row.id


def test_inbound_unknown_number_is_acknowledged(client, db_session, seed, no_validation):
    r = client.post(INBOUND_URL, data={"MessageSid": "SMx", "From": PATIENT_E164, "To": "+19995550000", "Body": "hi"})
    assert r.status_code == 200 and db_session.query(SmsMessage).count() == 0


def test_status_webhook_idempotent(client, db_session, seed, no_validation, twilio_live):
    r = client.post("/api/v1/sms/send", json=_send_payload(seed, client_id="st1"))
    sid = r.json()["twilio_sid"]
    r = client.post(STATUS_URL, data={"MessageSid": sid, "MessageStatus": "delivered"})
    assert r.status_code == 204
    row = db_session.query(SmsMessage).one()
    db_session.refresh(row)
    assert row.send_status == "delivered" and row.delivered_on is not None
    first_delivered = row.delivered_on
    # Late/out-of-order "sent" must not regress; duplicate "delivered" keeps the stamp.
    client.post(STATUS_URL, data={"MessageSid": sid, "MessageStatus": "sent"})
    client.post(STATUS_URL, data={"MessageSid": sid, "MessageStatus": "delivered"})
    db_session.refresh(row)
    assert row.send_status == "delivered" and row.delivered_on == first_delivered
    assert row.status_payload_hash and len(row.status_payload_hash) == 64
    # Failure carries the error.
    client.post(STATUS_URL, data={"MessageSid": sid, "MessageStatus": "undelivered",
                                  "ErrorCode": "30003", "ErrorMessage": "Unreachable destination"})
    db_session.refresh(row)
    assert row.send_status == "undelivered" and row.error_code == 30003
    # Unknown sid is a no-op, still 2xx (Twilio must not retry).
    assert client.post(STATUS_URL, data={"MessageSid": "SMnope", "MessageStatus": "delivered"}).status_code == 204


# ── SMS-6: inbox ─────────────────────────────────────────────────────────────
def test_inbox_filters_summary_and_mark_read(client, db_session, seed, no_validation):
    client.post("/api/v1/sms/send", json=_send_payload(seed, message_type="appointment_reminder", client_id="i1"))
    client.post(INBOUND_URL, data={"MessageSid": "SMi1", "From": PATIENT_E164, "To": OFFICE_NUMBER, "Body": "n"})
    client.post(INBOUND_URL, data={"MessageSid": "SMi2", "From": PATIENT_E164, "To": OFFICE_NUMBER, "Body": "also"})
    lst = client.get("/api/v1/sms-messages?unread_replies=true").json()
    assert lst["meta"]["total"] == 2
    assert all(i["patient_first_name"] == "Yolanda" for i in lst["items"])
    today = datetime.now(UTC).date().isoformat()  # sent_at is naive UTC
    assert client.get(f"/api/v1/sms-messages?date_from={today}&date_to={today}").json()["meta"]["total"] == 2
    assert client.get("/api/v1/sms-messages?date_to=2000-01-01").json()["meta"]["total"] == 0
    assert client.get(f"/api/v1/sms-messages?office_id={seed['office'].id}&direction=inbound").json()["meta"]["total"] == 1
    assert client.get("/api/v1/sms-messages?needs_attention=true").json()["meta"]["total"] == 2
    assert client.get("/api/v1/sms-messages?search=Diaz").json()["meta"]["total"] == 2

    s = client.get("/api/v1/sms/inbox/summary").json()
    assert s["unread_replies"] == 2 and s["needs_attention"] == 2 and s["unmatched"] == 0
    assert s["offices"][0]["office_name"] == "Moon Township"
    r = client.post("/api/v1/sms/inbox/mark-read", json={"patient_id": seed["patient"].id})
    assert r.json()["updated"] == 2
    assert client.get("/api/v1/sms/inbox/summary").json()["unread_replies"] == 0


def test_generic_post_normalises_fe_fallback_row(client, seed):
    """The FE's log-only fallback posts a bare row; the CRUD stamps the SMS-3 columns."""
    r = client.post("/api/v1/sms-messages", json={
        "patient_id": seed["patient"].id, "sent_text": "Reminder: your appointment is Thursday",
        "sent_phone": "(210) 793-6174", "send_status": "Success",
    })
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["direction"] == "outbound" and row["sent_at"] is not None
    assert row["message_type"] == "appointment_reminder" and row["send_status"] == "delivered"
    assert row["sent_phone"] == PATIENT_E164
    r = client.patch(f"/api/v1/sms-messages/{row['id']}", json={"is_read": True})
    assert r.status_code == 200 and r.json()["updated_at"] is not None
    r = client.post("/api/v1/sms-messages", json={"patient_id": seed["patient"].id, "sent_text": "x",
                                                  "message_type": "bogus"})
    assert r.status_code == 422


# ── SMS-5: templates + render ────────────────────────────────────────────────
def test_templates_and_render(client, seed):
    r = client.post("/api/v1/sms-templates", json={
        "name": "Reminder 48h", "message_type": "appointment_reminder",
        "body": "Hi {{patient_first_name}}, see {{provider_name}} at {{office_name}} on "
                "{{appointment_datetime}}. Call {{office_phone}}. {{unknown_field}}",
    })
    assert r.status_code == 201, r.text
    tpl = r.json()
    assert tpl["tenant_id"] == seed["tid"] and tpl["is_active"] is True
    r = client.post("/api/v1/sms/render", json={"patient_id": seed["patient"].id,
                                                 "template_id": tpl["id"], "appointment_id": "APPT-S1"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["body"] == ("Hi Yolanda, see Dr. Bell at Moon Township on Thu, Sep 10 at 9:30 AM. "
                           "Call (412) 555-0100.")
    assert out["unresolved_fields"] == ["unknown_field"] and out["segments"] == 1
    assert out["message_type"] == "appointment_reminder"
    assert client.get("/api/v1/sms-templates?message_type=appointment_reminder").json()["meta"]["total"] == 1
    meta = client.get("/api/v1/sms/metadata").json()
    assert "patient_first_name" in meta["merge_fields"] and "stop" in meta["stop_keywords"]


# ── SMS-9: reminders ─────────────────────────────────────────────────────────
def test_run_reminders_dedupes_and_respects_consent(client, db_session, seed):
    tid = seed["tid"]
    seed["comm"].sms_reminders_enabled = True
    seed["comm"].sms_reminder_lead_hours = [48, 2]
    seed["comm"].sms_quiet_hours_start, seed["comm"].sms_quiet_hours_end = 8, 21
    db_session.commit()
    # 15:00 UTC on Sep 8 = 11:00 EDT (inside quiet-hours window). The 48 h lead
    # for APPT-S1 (Sep 10 09:30 EDT) is due from Sep 8 09:30 EDT → due now.
    now = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)
    summary = sms_service.run_reminders(db_session, tenant_id=tid, now=now)
    assert summary["sent"] == 1 and summary["failed"] == 0, summary
    assert summary["skipped"].get("not_due") == 1  # the 2 h lead
    row = db_session.query(SmsMessage).one()
    assert row.message_type == "appointment_reminder" and row.reminder_lead_hours == 48
    assert row.client_id == "rem_APPT-S1_48" and row.sent_text.startswith("Hi Yolanda")
    assert row.created_by is None
    # Second run: nothing new.
    summary = sms_service.run_reminders(db_session, tenant_id=tid, now=now + timedelta(minutes=30))
    assert summary["sent"] == 0 and summary["skipped"].get("already_sent") == 1
    # 08:00 EDT on the day: the 48 h reminder is stale (catch-up window) and is
    # skipped rather than blasted late; the 2 h reminder is genuinely due, but
    # the patient has since opted out, so it is skipped too.
    seed["patient"].no_auto_sms = True
    db_session.commit()
    late = sms_service.run_reminders(db_session, tenant_id=tid, now=datetime(2026, 9, 10, 12, 0, tzinfo=UTC))
    assert late["sent"] == 0 and late["skipped"].get("too_late") == 1
    assert late["skipped"].get("opted_out") == 1
    seed["patient"].no_auto_sms = False
    db_session.commit()
    sent2 = sms_service.run_reminders(db_session, tenant_id=tid, now=datetime(2026, 9, 10, 12, 0, tzinfo=UTC))
    assert sent2["sent"] == 1
    assert db_session.query(SmsMessage).filter(SmsMessage.reminder_lead_hours == 2).count() == 1
    # The API entry point (admin).
    r = client.post("/api/v1/sms/reminders/run", json={"dry_run": True})
    assert r.status_code == 200 and r.json()["dry_run"] is True


# ── SMS-10: retention ────────────────────────────────────────────────────────
def test_purge_expired_blanks_bodies(db_session, seed):
    old = SmsMessage(tenant_id=seed["tid"], patient_id=seed["patient"].id, sent_text="old text",
                     sent_phone=PATIENT_E164, direction="outbound", send_status="delivered",
                     sent_at=datetime(2020, 1, 1, 12, 0), created_at=datetime(2020, 1, 1, 12, 0))
    db_session.add(old)
    db_session.commit()
    assert sms_service.purge_expired(db_session, days=365, dry_run=True)["affected"] == 1
    assert sms_service.purge_expired(db_session, days=365, dry_run=False)["affected"] == 1
    db_session.refresh(old)
    assert old.sent_text == "" and old.send_status == "delivered"
    assert sms_service.purge_expired(db_session, days=None)["affected"] == 0


# ── EMAIL-1 ──────────────────────────────────────────────────────────────────
def test_email_send_log_only_and_webhook(client, db_session, seed, monkeypatch):
    assert client.get("/api/v1/email/gateway").json()["mode"] == "log_only"
    r = client.post("/api/v1/email/send", json={
        "patient_id": seed["patient"].id, "subject": "Your statement",
        "body_html": "<p>Hi</p>", "message_type": "statement", "client_id": "em1",
    })
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["to_email"] == "yolanda@example.com" and row["send_status"] == "queued"
    assert client.post("/api/v1/email/send", json={
        "patient_id": seed["patient"].id, "subject": "x", "body_text": "y", "client_id": "em1",
    }).status_code == 409
    assert client.get(f"/api/v1/email-messages?patient_id={seed['patient'].id}").json()["meta"]["total"] == 1

    monkeypatch.setattr(settings, "SENDGRID_WEBHOOK_VALIDATE", False)
    r = client.post("/api/v1/email/webhooks/sendgrid", json=[
        {"event": "delivered", "email_message_id": str(row["id"])},
        {"event": "open", "email_message_id": str(row["id"])},
        {"event": "delivered", "sg_message_id": "unknown.filter"},
    ])
    assert r.status_code == 200 and r.json()["applied"] == 2
    got = client.get(f"/api/v1/email-messages/{row['id']}").json()
    assert got["send_status"] == "open" and got["delivered_at"] and got["opened_at"]
    monkeypatch.setattr(settings, "SENDGRID_WEBHOOK_VALIDATE", True)
    assert client.post("/api/v1/email/webhooks/sendgrid", json=[]).status_code == 403
