"""Office Setup new-office QA pass — OFF-QA-1…13 of
docs/office-scope/office_setup_new_office_qa_backend_devreport.md."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.core.config import settings
from app.db.models import Appointment, Office, Operatory, Patient, Provider, Tenant
from app.db.models.account import AccountHoliday
from app.db.models.billing import InsuranceClaim
from app.db.models.office_setup import (
    OfficeAdvancedSettings,
    OfficeIntegrations,
    OfficeScheduleDay,
    OfficeStatementSettings,
)
from app.services import holiday_service, office_rules

P = "/api/v1"


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="QA1", short_id="QA", name="QA Office",
               address_line1="100 Test Street", address_line2="Suite 2", city="Pittsburgh",
               state="PA", zip="15201", phone="412-555-0100")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


# ── OFF-QA-1 letterhead ──────────────────────────────────────────────────────
def test_custom_address_is_used_as_a_block(db_session, office):
    from app.services.print_service import resolve_letterhead

    db_session.add(OfficeStatementSettings(
        tenant_id=office.tenant_id, office_id=office.id, address_source="custom",
        statement_address_1="PO Box 55", statement_address_2="", statement_city="Wexford",
        statement_state="PA", statement_zip="15090",
    ))
    db_session.commit()
    lh = resolve_letterhead(db_session, office, office.tenant_id)
    assert (lh["address_line1"], lh["address_line2"], lh["city"]) == ("PO Box 55", None, "Wexford")
    assert lh["phone"] == "412-555-0100"  # phone is not part of the postal block


def test_empty_custom_block_falls_back_to_office(db_session, office):
    from app.services.print_service import resolve_letterhead

    db_session.add(OfficeStatementSettings(tenant_id=office.tenant_id, office_id=office.id,
                                           address_source="custom"))
    db_session.commit()
    lh = resolve_letterhead(db_session, office, office.tenant_id)
    assert (lh["address_line1"], lh["address_line2"]) == ("100 Test Street", "Suite 2")


# ── OFF-QA-2 vocabularies ────────────────────────────────────────────────────
def test_statement_enums_are_validated_and_case_folded(client, office):
    base = f"{P}/offices/{office.id}/statement-settings"
    r = client.patch(base, json={"logo_option": "garbage", "address_source": "weird"})
    assert r.status_code == 422
    r = client.patch(base, json={"logo_option": "OFFICE", "address_source": "Custom"})
    assert r.status_code == 200, r.text
    assert (r.json()["logo_option"], r.json()["address_source"]) == ("office", "custom")


def test_holiday_enums_are_validated_and_case_folded(client, office):
    base = f"{P}/offices/{office.id}/holidays"
    bad = client.post(base, json={"holiday_date": "2026-03-02", "holiday_name": "X",
                                  "status": "WHATEVER", "holiday_type": "weird"})
    assert bad.status_code == 422
    ok = client.post(base, json={"holiday_date": "2026-03-02", "holiday_name": "X",
                                 "status": "half day", "holiday_type": "Custom"})
    assert ok.status_code == 201, ok.text
    assert (ok.json()["status"], ok.json()["holiday_type"]) == ("HALF_DAY", "CUSTOM")


# ── OFF-QA-3 short_id / office_code ──────────────────────────────────────────
def test_duplicate_short_id_is_409_and_existing_duplicates_stay_editable(client, db_session, office):
    r = client.post(f"{P}/offices", json={"name": "Dup", "office_code": "QA2", "short_id": " qa "})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "duplicate_short_id"
    assert r.json()["error"]["details"]["office_id"] == office.id

    # A pre-existing duplicate (the MOON pair) can still be edited.
    twin = Office(tenant_id=office.tenant_id, office_code="QA3", short_id="QA", name="Twin")
    db_session.add(twin)
    db_session.commit()
    r = client.patch(f"{P}/offices/{twin.id}", json={"name": "Twin renamed", "short_id": "QA"})
    assert r.status_code == 200, r.text
    # ...but moving onto another office's id is refused.
    r = client.patch(f"{P}/offices/{twin.id}", json={"short_id": "QA"})
    assert r.status_code == 200
    other = client.post(f"{P}/offices", json={"name": "Other", "office_code": "QA4", "short_id": "ZZ"}).json()
    assert client.patch(f"{P}/offices/{other['id']}", json={"short_id": "qa"}).status_code == 409


def test_short_id_is_per_tenant(client, db_session, office):
    t = Tenant(name="T2", code="t2", is_active=True)
    db_session.add(t)
    db_session.commit()
    db_session.add(Office(tenant_id=t.id, office_code="T2A", short_id="SAME", name="T2 Office"))
    db_session.commit()
    r = client.post(f"{P}/offices", json={"name": "Mine", "office_code": "QA5", "short_id": "SAME"})
    assert r.status_code == 201, r.text


def test_office_code_is_globally_unique_case_insensitive(client, office):
    r = client.post(f"{P}/offices", json={"name": "Dup", "office_code": "qa1"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "duplicate_office_code"


# ── OFF-QA-4 schedule ────────────────────────────────────────────────────────
def test_schedule_times_are_validated(client, office):
    r = client.put(f"{P}/offices/{office.id}/schedule", json={"days": [
        {"day_of_week": 0, "start_time": "17:00", "end_time": "08:00",
         "lunch_start": "19:00", "lunch_end": "18:00"}]})
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["loc"][:3] == ["body", "days", 0]
    for bad in (
        {"day_of_week": 1, "start_time": "08:00", "end_time": "17:00", "lunch_start": "12:00"},
        {"day_of_week": 1, "start_time": "08:00", "end_time": "17:00",
         "lunch_start": "18:00", "lunch_end": "19:00"},
        {"day_of_week": 1, "start_time": "08:00"},
    ):
        assert client.put(f"{P}/offices/{office.id}/schedule", json={"days": [bad]}).status_code == 422
    dup = [{"day_of_week": 2, "is_closed": True}, {"day_of_week": 2, "is_closed": True}]
    assert client.put(f"{P}/offices/{office.id}/schedule", json={"days": dup}).status_code == 422


def test_partial_schedule_put_keeps_omitted_days(client, office):
    base = f"{P}/offices/{office.id}/schedule"
    week = [{"day_of_week": d, "is_closed": d >= 5,
             "start_time": None if d >= 5 else "09:00", "end_time": None if d >= 5 else "18:00"}
            for d in range(7)]
    assert client.put(base, json={"days": week}).status_code == 200
    r = client.put(base, json={"days": [{"day_of_week": 0, "start_time": "07:00", "end_time": "15:00",
                                         "lunch_start": "11:00", "lunch_end": "11:30"}]})
    assert r.status_code == 200
    days = {d["day_of_week"]: d for d in r.json()}
    assert len(days) == 7
    assert days[0]["start_time"] == "07:00:00"
    assert days[1]["start_time"] == "09:00:00"  # untouched
    assert days[6]["is_closed"] is True


# ── OFF-QA-5 integrations ────────────────────────────────────────────────────
def test_integrations_reject_bad_email_and_javascript_urls(client, office):
    base = f"{P}/offices/{office.id}/integrations"
    assert client.patch(base, json={"service_email": "not-an-email"}).status_code == 422
    assert client.patch(base, json={"patient_portal_url": "javascript:alert(1)"}).status_code == 422
    assert client.patch(base, json={"patient_comm_url": "ftp://x.example"}).status_code == 422
    r = client.patch(base, json={"service_email": "front@qa.example",
                                 "patient_portal_url": "https://portal.qa.example/x"})
    assert r.status_code == 200, r.text
    # The verification flag is server-owned.
    assert client.patch(base, json={"service_email_verified": True}).json()["service_email_verified"] is False


def test_service_email_verification_round_trip(client, db_session, office, monkeypatch):
    sent: dict = {}
    from app.integrations import email as transport

    monkeypatch.setattr(transport, "send_email", lambda to, subject, body: sent.update(to=to, body=body) or True)
    base = f"{P}/offices/{office.id}/integrations"
    assert client.post(f"{base}/verify-email").status_code == 422  # no address yet
    client.patch(base, json={"service_email": "front@qa.example"})
    r = client.post(f"{base}/verify-email")
    assert r.status_code == 200, r.text
    assert sent["to"] == "front@qa.example"
    code = next(tok.rstrip(".") for tok in sent["body"].split() if tok.rstrip(".").isdigit())
    wrong = client.post(f"{base}/verify-email/confirm", json={"code": "000000" if code != "000000" else "111111"})
    assert wrong.status_code == 422
    ok = client.post(f"{base}/verify-email/confirm", json={"code": code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["service_email_verified"] is True
    # Changing the address un-verifies it.
    r = client.patch(base, json={"service_email": "billing@qa.example"})
    assert r.json()["service_email_verified"] is False
    assert "service_email_verification_hash" not in r.json()


# ── OFF-QA-6 SmartAssist ─────────────────────────────────────────────────────
def test_smart_assist_serves_catalog_until_saved(client, db_session, office):
    base = f"{P}/offices/{office.id}/smart-assist"
    body = client.get(base).json()
    assert body["items_source"] == "catalog"
    codes = [i["item_code"] for i in body["items"]]
    assert {"payment", "eligibility", "consent_form_4", "ledger_posting"} <= set(codes)
    assert all(i["id"] is None for i in body["items"])
    # A GET writes nothing (OFF-QA-13).
    from app.db.models.office_setup import OfficeSmartAssist

    assert db_session.query(OfficeSmartAssist).filter_by(office_id=office.id).count() == 0
    assert len(client.get(f"{P}/offices/smart-assist/catalog").json()) == len(codes)

    r = client.patch(base, json={"enabled": True, "items": [
        {"item_code": "payment", "frequency": "EVERY_VISIT", "sms_template_id": "PLACEHOLDER-1"}]})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unknown_sms_template"

    from app.db.models.comms import SmsTemplate

    tpl = SmsTemplate(tenant_id=office.tenant_id, office_id=None, name="Balance due", body="Hi")
    db_session.add(tpl)
    db_session.commit()
    assert [t["id"] for t in client.get(f"{base}/sms-templates").json()] == [str(tpl.id)]
    r = client.patch(base, json={"enabled": True, "items": [
        {"item_code": "payment", "frequency": "EVERY_VISIT", "sms_template_id": str(tpl.id)}]})
    assert r.status_code == 200, r.text
    assert r.json()["items_source"] == "stored"
    assert r.json()["items"][0]["label"] == "Payment"


# ── OFF-QA-7 calendar + booking enforcement ──────────────────────────────────
@pytest.fixture
def booking(db_session, office):
    tid = office.tenant_id
    db_session.add_all([
        Provider(id="PRV-QA", tenant_id=tid, office_id=office.id, name="Dr. QA"),
        Operatory(id="OPR-QA", office_id=office.id, name="Op QA", provider_id="PRV-QA"),
    ])
    pt = Patient(tenant_id=tid, first_name="Q", last_name="A", chart_no="QA-1")
    db_session.add(pt)
    db_session.commit()
    pt.office_id_for_test = office.id
    return pt


def _appt(pt, day, start, end, **extra):
    return {"id": extra.pop("id", "APPT-QA"), "patient_id": pt.id, "provider_id": "PRV-QA",
            "office_id": pt.office_id_for_test,
            "operatory_id": "OPR-QA", "date": day, "start_time": start, "end_time": end,
            "duration": 30, "status": "Scheduled", **extra}


def test_unconfigured_office_hours_do_not_block(client, booking):
    # No saved week -> defaults are reported but not enforced.
    r = client.post(f"{P}/appointments", json=_appt(booking, "2026-10-17", "20:00", "20:30"))
    assert r.status_code == 201, r.text


def test_saved_week_blocks_outside_hours_lunch_and_closed_day(client, db_session, office, booking):
    db_session.add_all([
        OfficeScheduleDay(tenant_id=office.tenant_id, office_id=office.id, day_of_week=0,
                          start_time=time(8), end_time=time(17), lunch_start=time(12), lunch_end=time(13)),
        OfficeScheduleDay(tenant_id=office.tenant_id, office_id=office.id, day_of_week=6, is_closed=True),
    ])
    db_session.commit()
    monday, sunday = "2026-10-12", "2026-10-18"
    for day, s, e, kind in ((monday, "17:00", "17:30", "outside_hours"),
                            (monday, "12:30", "13:00", "lunch"),
                            (sunday, "09:00", "09:30", "closed_day")):
        r = client.post(f"{P}/appointments", json=_appt(booking, day, s, e))
        assert r.status_code == 409, (kind, r.text)
        err = r.json()["error"]
        assert err["code"] == "office_closed"
        assert err["details"]["reasons"][0]["kind"] == kind
    ok = client.post(f"{P}/appointments", json=_appt(booking, monday, "09:00", "09:30"))
    assert ok.status_code == 201, ok.text
    # Moving it over lunch is refused; the override books it on purpose.
    assert client.patch(f"{P}/appointments/APPT-QA", json={"start_time": "12:00", "end_time": "12:30"}).status_code == 409
    r = client.patch(f"{P}/appointments/APPT-QA", json={"start_time": "12:00", "end_time": "12:30",
                                                        "allow_outside_office_hours": True})
    assert r.status_code == 200, r.text
    # A non-move edit of an appointment already in a closed slot is fine.
    assert client.patch(f"{P}/appointments/APPT-QA", json={"notes": "x"}).status_code == 200


def test_closing_holiday_blocks_even_without_a_saved_week(client, db_session, office, booking):
    db_session.add(AccountHoliday(tenant_id=office.tenant_id, office_id=None, holiday_date=date(2026, 11, 26),
                                  holiday_name="Thanksgiving Day", status="CLOSED", holiday_type="FEDERAL"))
    db_session.commit()
    r = client.post(f"{P}/appointments", json=_appt(booking, "2026-11-26", "09:00", "09:30"))
    assert r.status_code == 409
    assert r.json()["error"]["details"]["reasons"][0]["kind"] == "holiday"
    cal = client.get(f"{P}/offices/{office.id}/calendar?from_date=2026-11-25&to_date=2026-11-27").json()
    assert [d["is_open"] for d in cal["days"]] == [True, False, True]
    assert cal["days"][1]["holiday"]["name"] == "Thanksgiving Day"


def test_enforcement_kill_switch(client, db_session, office, booking, monkeypatch):
    db_session.add(OfficeScheduleDay(tenant_id=office.tenant_id, office_id=office.id, day_of_week=6, is_closed=True))
    db_session.commit()
    monkeypatch.setattr(settings, "OFFICE_HOURS_ENFORCED", False)
    assert client.post(f"{P}/appointments", json=_appt(booking, "2026-10-18", "09:00", "09:30")).status_code == 201


# ── OFF-QA-8 advanced settings ───────────────────────────────────────────────
def test_advanced_settings_validation(client, office):
    base = f"{P}/offices/{office.id}/advanced-settings"
    for bad in ({"finance_charge_pct": -5}, {"finance_charge_pct": 101}, {"area_code": "abcd"},
                {"place_of_service": "zzz"}, {"default_state": "Penn"}, {"min_balance": -1},
                {"days_before_charge": -1}):
        assert client.patch(base, json=bad).status_code == 422, bad
    r = client.patch(base, json={"place_of_service": "hospital", "area_code": "412", "default_state": "pa"})
    assert r.status_code == 200, r.text
    assert (r.json()["place_of_service"], r.json()["default_state"]) == ("22", "PA")


def test_claim_item_38_defaults_from_office_place_of_service(db_session, office):
    from app.services import claim_form_service

    db_session.add(OfficeAdvancedSettings(tenant_id=office.tenant_id, office_id=office.id, place_of_service="22"))
    pt = Patient(tenant_id=office.tenant_id, first_name="C", last_name="F", chart_no="CF-1",
                 home_office_id=office.id)
    db_session.add(pt)
    db_session.commit()
    claim = InsuranceClaim(id="CLM-QA", claim_number="CLM-QA", patient_id=pt.id, office_id=office.id)
    db_session.add(claim)
    db_session.commit()
    form = claim_form_service.assemble(db_session, "CLM-QA", office.tenant_id)
    assert (form["ancillary"]["place_of_treatment"], form["ancillary"]["place_of_treatment_source"]) == ("22", "office")


# ── OFF-QA-9 NPI / taxonomy ──────────────────────────────────────────────────
def test_npi_and_taxonomy_validation(client, office):
    assert office_rules.npi_is_valid("1234567893") and not office_rules.npi_is_valid("1234567890")
    base = f"{P}/offices/{office.id}"
    assert client.patch(base, json={"npi": "123"}).status_code == 422
    r = client.patch(base, json={"npi": "1234567890"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_npi"
    assert client.patch(base, json={"taxonomy_code": "nope"}).status_code == 422
    r = client.patch(base, json={"npi": "1234567893", "taxonomy_code": "1223g0001x"})
    assert r.status_code == 200, r.text
    assert r.json()["taxonomy_code"] == "1223G0001X"


# ── OFF-QA-10 FK errors ──────────────────────────────────────────────────────
def test_bad_pointers_are_field_level_and_carry_no_db_text(client, office):
    for field, code in (("billing_provider_id", "provider_not_found"),
                        ("default_fee_schedule_id", "fee_schedule_not_found")):
        value = "NOPE" if field == "billing_provider_id" else 999999
        r = client.patch(f"{P}/offices/{office.id}", json={field: value})
        assert r.status_code == 422, r.text
        err = r.json()["error"]
        assert err["code"] == code
        assert err["details"]["loc"] == ["body", field]
        assert "db_message" not in err["details"]
    r = client.patch(f"{P}/offices/{office.id}/advanced-settings", json={"preferred_provider_id": "NOPE"})
    assert r.status_code == 422 and r.json()["error"]["details"]["loc"] == ["body", "preferred_provider_id"]


def test_driver_text_never_reaches_the_response():
    from sqlalchemy.exc import IntegrityError

    from app.core.exceptions import app_error_from_db

    exc = IntegrityError("INSERT …", {}, Exception("FOREIGN KEY constraint failed: offices.billing_provider_id"))
    err = app_error_from_db(exc)
    assert "db_message" not in err.details
    assert err.details["loc"] == ["body", "billing_provider_id"]


# ── OFF-QA-11 operatory ids ──────────────────────────────────────────────────
def test_operatory_id_is_server_generated(client, db_session, office):
    db_session.add(Operatory(id=f"op-{office.id}-1", office_id=office.id, name="Existing"))
    db_session.commit()
    r = client.post(f"{P}/operatories", json={"office_id": office.id, "name": "Op 2", "display_order": 1})
    assert r.status_code == 201, r.text
    assert r.json()["id"] == f"op-{office.id}-2"
    r = client.post(f"{P}/operatories", json={"office_id": office.id, "name": "Legacy", "id": "OPR-999"})
    assert r.json()["id"] == "OPR-999"


# ── OFF-QA-12 observed federal holidays ──────────────────────────────────────
def test_federal_import_uses_observed_dates(client, office):
    rows = client.post(f"{P}/offices/{office.id}/holidays/federal", json={"year": 2026}).json()
    by_date = {r["holiday_date"]: r["holiday_name"] for r in rows}
    assert "2026-07-03" in by_date and "2026-07-04" not in by_date  # Sat -> Fri
    assert by_date["2026-07-03"] == "Independence Day (observed)"
    assert holiday_service.observed_date(date(2027, 12, 26)) == date(2027, 12, 27)  # Sun -> Mon
    raw = client.post(f"{P}/offices/{office.id}/holidays/federal",
                      json={"year": 2026, "observed": False}).json()
    assert [r["holiday_date"] for r in raw] == ["2026-07-04"]  # the only new date


# ── OFF-QA-13 side-effect-free reads ─────────────────────────────────────────
def test_schedule_get_writes_nothing(client, db_session, office):
    days = client.get(f"{P}/offices/{office.id}/schedule").json()
    assert len(days) == 7 and all(d["id"] is None for d in days)
    assert db_session.query(OfficeScheduleDay).filter_by(office_id=office.id).count() == 0


def test_singleton_first_read_is_idempotent(client, db_session, office):
    a = client.get(f"{P}/offices/{office.id}/integrations").json()
    b = client.get(f"{P}/offices/{office.id}/integrations").json()
    assert a["id"] == b["id"]
    assert db_session.query(OfficeIntegrations).filter_by(office_id=office.id).count() == 1


# ── OFF-QA-14 X-Office-ID on POST /offices ───────────────────────────────────
def test_create_office_with_working_office_header(client, office):
    r = client.post(f"{P}/offices", json={"name": "ZZ header probe", "short_id": "ZZHP", "office_code": "ZZHP"},
                    headers={"X-Office-ID": str(office.id)})
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "ZZ header probe"
    r = client.patch(f"{P}/offices/{r.json()['id']}", json={"name": "ZZ renamed"},
                     headers={"X-Office-ID": str(office.id)})
    assert r.status_code == 200, r.text


def test_write_stamp_skips_columns_the_model_lacks(office):
    from types import SimpleNamespace

    from app.services.office_scope_service import OfficeScopeSpec, apply_write_office

    scope = SimpleNamespace(x_office_id=office.id)
    data: dict = {"name": "x"}
    apply_write_office(scope, data, OfficeScopeSpec(), model=Office)
    assert "office_id" not in data
    data = {}
    apply_write_office(scope, data, OfficeScopeSpec(), model=Operatory)
    assert data["office_id"] == office.id  # a real office-owned record is still stamped
