"""Backend gaps for the docs/Final modules: scheduler, reports, my_page, help, utilities."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.db.models import (
    Appointment,
    InsuranceCarrier,
    InsurancePlan,
    Office,
    Patient,
    PatientAlert,
    PatientInsurance,
    InsuranceSubscriber,
    Provider,
    TreatmentPlan,
)

PREFIX = "/api/v1"


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="MOON", name="Moon", short_id="MOON")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    pr = Provider(id="PRV-1", tenant_id=db_session._tenant_id, office_id=office.id,
                  name="Dr Who", short_id="WHO", user_id=db_session._admin.id, is_active=True)
    db_session.add(pr)
    db_session.commit()
    db_session.refresh(pr)
    return pr


@pytest.fixture
def patient(db_session, office) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Al", last_name="Ice",
                dob=date(1990, 6, 1), gender="F", chart_no="F-1", home_office_id=office.id,
                responsible_party_id="RP-9", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _appt(db_session, office, provider, patient, appt_id="A1") -> Appointment:
    a = Appointment(id=appt_id, patient_id=patient.id,
                    provider_id=provider.id, office_id=office.id, date=date(2026, 7, 1),
                    start_time=time(9, 0), end_time=time(9, 30), duration=30, status="Scheduled")
    db_session.add(a)
    db_session.commit()
    return a


# ── Scheduler G1/G2/G5: enriched feed ─────────────────────────────────────────
def test_scheduler_feed_enrichment(client, db_session, office, provider, patient):
    _appt(db_session, office, provider, patient)
    db_session.add(PatientAlert(patient_id=patient.id, alert="Allergy: penicillin", is_active=True))
    db_session.commit()

    rows = client.get(f"{PREFIX}/appointments/scheduler?office_id={office.id}").json()
    assert len(rows) == 1
    r = rows[0]
    assert r["has_alert"] is True
    assert r["patient_age"] == 36  # 1990 → 2026
    assert r["patient_gender"] == "F"
    assert r["responsible_party_id"] == "RP-9"
    assert r["account_balance"] is not None
    assert "insurance_eligibility" in r


def test_scheduler_provider_filter(client, db_session, office, provider, patient):
    _appt(db_session, office, provider, patient, "A1")
    rows = client.get(
        f"{PREFIX}/appointments/scheduler?office_id={office.id}&provider_id={provider.id}").json()
    assert len(rows) == 1
    none = client.get(f"{PREFIX}/appointments/scheduler?office_id={office.id}&provider_id=PRV-NONE").json()
    assert none == []


# ── Scheduler G3: cancellation metadata persists ──────────────────────────────
def test_scheduler_cancellation_metadata(client, db_session, office, provider, patient):
    _appt(db_session, office, provider, patient)
    r = client.patch(f"{PREFIX}/appointments/A1/status", json={
        "status": "cancelled", "cancellation_note": "patient called",
        "cancellation_reason": "same_day", "add_to_call_list": True})
    assert r.status_code == 200, r.text
    assert r.json()["cancellation_reason"] == "same_day"
    assert r.json()["add_to_call_list"] is True
    assert r.json()["is_cancelled"] is True


# ── Reports G7/G9: denormalized names + TP totals ─────────────────────────────
def test_reports_denormalized_names(client, db_session, office, provider, patient):
    client.post(f"{PREFIX}/procedure-codes", json={"code": "D1110", "description": "Prophy",
                                                   "category": "Prev", "default_fee": 100})
    client.post(f"{PREFIX}/patient-procedures", json={
        "id": "PP1", "patient_id": patient.id, "provider_id": provider.id, "office_id": office.id,
        "procedure_code": "D1110", "fee": 100, "date_of_service": "2026-07-01"})
    rows = client.get(f"{PREFIX}/patient-procedures?patient_id={patient.id}").json()["items"]
    assert rows[0]["patient_name"] == "Ice, Al"
    assert rows[0]["provider_name"] == "Dr Who"


def test_reports_treatment_plan_totals(client, db_session, office, provider, patient):
    client.post(f"{PREFIX}/procedure-codes", json={"code": "D2740", "description": "Crown",
                                                   "category": "Rest", "default_fee": 1000})
    client.post(f"{PREFIX}/treatment-plans", json={"id": "TP1", "patient_id": patient.id, "name": "P"})
    client.post(f"{PREFIX}/treatment-plan-items", json={
        "id": "TPI1", "plan_id": "TP1", "procedure_code": "D2740", "fee": 1000,
        "insurance_estimate": 600})
    plans = client.get(f"{PREFIX}/treatment-plans?patient_id={patient.id}").json()["items"]
    tp = next(p for p in plans if p["id"] == "TP1")
    assert tp["patient_name"] == "Ice, Al"
    assert tp["item_count"] == 1
    assert float(tp["total_fee"]) == 1000
    assert float(tp["est_patient"]) == 400


# ── Reports G10: claim date-range filter ──────────────────────────────────────
def test_reports_claim_date_filter(client, db_session, patient, office):
    client.post(f"{PREFIX}/insurance-claims", json={
        "id": "C1", "patient_id": patient.id, "claim_number": "CL-1", "office_id": office.id,
        "submitted_date": "2026-03-15"})
    hit = client.get(f"{PREFIX}/insurance-claims?submitted_date_from=2026-03-01&submitted_date_to=2026-03-31")
    assert hit.json()["meta"]["total"] == 1
    miss = client.get(f"{PREFIX}/insurance-claims?submitted_date_from=2026-04-01")
    assert miss.json()["meta"]["total"] == 0


# ── My Page MP-1/3/4/6/7 ──────────────────────────────────────────────────────
def test_my_page_profile_update(client, db_session):
    r = client.patch(f"{PREFIX}/users/me", json={"first_name": "New", "phone": "555-9"})
    assert r.status_code == 200, r.text
    assert r.json()["first_name"] == "New" and r.json()["phone"] == "555-9"


def test_my_page_tasks_crud(client):
    c = client.post(f"{PREFIX}/users/me/tasks", json={"title": "Call lab", "priority": "high"})
    assert c.status_code == 201, c.text
    tid = c.json()["id"]
    assert client.get(f"{PREFIX}/users/me/tasks").json()[0]["title"] == "Call lab"
    u = client.patch(f"{PREFIX}/users/me/tasks/{tid}", json={"is_done": True})
    assert u.json()["is_done"] is True
    assert client.delete(f"{PREFIX}/users/me/tasks/{tid}").status_code == 204


def test_my_page_preferences_blob(client):
    put = client.put(f"{PREFIX}/users/me/preferences", json={"preferences": {"theme": "dark", "pins": [1, 2]}})
    assert put.status_code == 200
    got = client.get(f"{PREFIX}/users/me/preferences").json()
    assert got["preferences"]["theme"] == "dark" and got["preferences"]["pins"] == [1, 2]


def test_my_page_notifications(client, db_session):
    from app.db.models import Notification
    db_session.add(Notification(tenant_id=db_session._tenant_id, user_id=db_session._admin.id,
                                title="Claim rejected", is_read=False))
    db_session.commit()
    lst = client.get(f"{PREFIX}/users/me/notifications").json()
    assert lst["unread_count"] == 1
    nid = lst["items"][0]["id"]
    client.post(f"{PREFIX}/users/me/notifications/{nid}/read")
    assert client.get(f"{PREFIX}/users/me/notifications").json()["unread_count"] == 0


def test_my_page_provider_link_in_me_full(client, provider):
    me = client.get(f"{PREFIX}/auth/me-full").json()
    assert me["provider_id"] == "PRV-1"  # linked via Provider.user_id


# ── Help HELP-1/2 ─────────────────────────────────────────────────────────────
def test_help_ticket_create_and_list(client, db_session):
    r = client.post(f"{PREFIX}/support/tickets", json={
        "project_key": "SUP", "summary": "Slot not saving", "issue_type": "Bug",
        "priority": "Medium", "context": {"module": "Scheduler", "user_id": "999"}})
    assert r.status_code == 200, r.text
    assert r.json()["issue_key"].startswith("LOCAL-")  # no Jira configured → local key

    mine = client.get(f"{PREFIX}/support/tickets").json()["tickets"]
    assert len(mine) == 1
    assert mine[0]["title"] == "Slot not saving"
    assert mine[0]["module"] == "Scheduler"
    assert mine[0]["reporter_id"] == str(db_session._admin.id)  # reporter from token, not context


# ── Utilities UTIL-1/2/3 ──────────────────────────────────────────────────────
def test_utilities_run_and_audit(client, office):
    run = client.post(f"{PREFIX}/utilities/claims-batch/run", json={"office_id": office.id})
    assert run.status_code == 201, run.text
    job_id = run.json()["id"]
    assert run.json()["status"] == "completed"

    got = client.get(f"{PREFIX}/utilities/jobs/{job_id}")
    assert got.status_code == 200 and got.json()["utility_id"] == "claims-batch"

    audit = client.get(f"{PREFIX}/utilities/audit?utility_id=claims-batch").json()["runs"]
    assert len(audit) == 1
