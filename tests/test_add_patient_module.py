"""Add-Patient module backend-gap tests (docs/patients/add_patient_backend_devreport.md)."""

from __future__ import annotations

import pytest

from app.db.models import Patient


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ada", last_name="Byron",
                chart_no="CH-AP1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def test_new_patient_columns_persist(client):
    """GAP-AP-1..11: every previously-dropped Add-Patient field now round-trips."""
    body = {
        "first_name": "Grace", "last_name": "Hopper",
        "pronouns": "She/Her", "driver_license": "DL-TEST-777",
        "student_status": "full_time", "school_name": "Yale",
        "referred_to": "Dr. Specialist", "referral_to_date": "2026-07-01",
        "responsible_party_relationship": "self",
        "patient_types": ["CH", "OR", "SS"],
        "hipaa_sharing_notes": "Spouse may access records.",
        "assign_benefits": True, "add_to_quickfill": True, "no_correspondence": True,
    }
    created = client.post("/api/v1/patients", json=body)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    got = client.get(f"/api/v1/patients/{pid}").json()
    for key, val in body.items():
        assert got[key] == val, f"{key}: {got.get(key)!r} != {val!r}"


def test_chart_no_auto_generated(client):
    """GAP-AP-14: a create with no chart_no gets one server-side (not null)."""
    created = client.post("/api/v1/patients", json={"first_name": "No", "last_name": "Chart"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["chart_no"] and body["chart_no"] == str(body["id"])


def test_chart_no_respected_when_supplied(client):
    created = client.post("/api/v1/patients",
                          json={"first_name": "Has", "last_name": "Chart", "chart_no": "CN-9001"})
    assert created.json()["chart_no"] == "CN-9001"


def test_medical_alert_responses_crud(client, patient):
    """GAP-AP-16."""
    r = client.post("/api/v1/patient-medical-alerts",
                    json={"patient_id": patient.id, "alert_code": "PENICILLIN",
                          "alert_label": "Penicillin allergy", "response": "yes",
                          "comments": "rash"})
    assert r.status_code == 201, r.text
    listed = client.get(f"/api/v1/patient-medical-alerts?patient_id={patient.id}&response=yes").json()
    assert listed["meta"]["total"] == 1
    assert listed["items"][0]["alert_code"] == "PENICILLIN"


def test_questionnaire_responses_crud(client, patient):
    """GAP-AP-17."""
    r = client.post("/api/v1/patient-questionnaire-responses",
                    json={"patient_id": patient.id, "questionnaire_type": "dental",
                          "question_code": "Q1", "answer": "Yes"})
    assert r.status_code == 201, r.text
    listed = client.get(
        f"/api/v1/patient-questionnaire-responses?patient_id={patient.id}&questionnaire_type=dental"
    ).json()
    assert listed["meta"]["total"] == 1


def test_opening_balance_seed_and_balance(client, patient):
    """GAP-AP-12: seed opening A/R and see it in the computed balance + aging."""
    empty = client.get(f"/api/v1/patients/{patient.id}/opening-balance").json()
    assert empty["total"] == 0.0

    put = client.put(f"/api/v1/patients/{patient.id}/opening-balance",
                     json={"as_of_date": "2026-07-01", "current": 100.0, "over_30": 50.0})
    assert put.status_code == 200, put.text
    assert put.json()["total"] == 150.0

    bal = client.get(f"/api/v1/patients/{patient.id}/balance").json()
    assert bal["opening_balance"] == 150.0
    assert bal["balance"] == 150.0
    assert bal["aging"]["current"] == 100.0 and bal["aging"]["b30"] == 50.0


def test_register_composite_atomic(client):
    """GAP-AP-13/15/18: one call creates the patient + all related records."""
    body = {
        "patient": {"first_name": "Reg", "last_name": "Ister"},
        "responsible_party": {"relationship": "self", "is_self": True},
        "medical_alerts": [{"alert_code": "LATEX", "response": "no"}],
        "questionnaire_responses": [
            {"questionnaire_type": "medical", "question_code": "M1", "answer": "No"}
        ],
        "recalls": [{"recall_type": "prophy", "interval_months": 6}],
        "opening_balance": {"current": 25.0},
    }
    r = client.post("/api/v1/patients/register", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    pid = out["patient_id"]
    assert out["chart_no"] == str(pid)
    assert out["responsible_party_id"] == str(pid)  # self-linked guarantor
    assert len(out["medical_alert_ids"]) == 1
    assert len(out["questionnaire_response_ids"]) == 1
    assert len(out["recall_ids"]) == 1
    assert out["opening_balance_seeded"] is True

    # The related records are queryable and the opening balance is in the balance.
    assert client.get(f"/api/v1/patient-medical-alerts?patient_id={pid}").json()["meta"]["total"] == 1
    assert client.get(f"/api/v1/patient-recalls?patient_id={pid}").json()["meta"]["total"] == 1
    assert client.get(f"/api/v1/patients/{pid}/balance").json()["opening_balance"] == 25.0
