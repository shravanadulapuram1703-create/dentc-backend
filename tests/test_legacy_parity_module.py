"""Legacy-parity backend gaps (docs/patients/add_patient_legacy_parity_devreport.md, LEG-1..14)."""

from __future__ import annotations

import pytest

from app.db.models import InsuranceCarrier, InsurancePlan, Office, Patient, PatientInsurance
from app.services.patient_service import assign_chart_no


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Leg", last_name="Parity",
                chart_no="CH-LEG1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


# ── §0: chart_no collision-safe ───────────────────────────────────────────────
def test_chart_no_collision_safe(db_session):
    tid = db_session._tenant_id
    new = Patient(tenant_id=tid, first_name="New")
    db_session.add(new)
    db_session.flush()
    # An existing row already occupies the chart_no this patient's id maps to.
    occupied = Patient(tenant_id=tid, first_name="Occ", chart_no=str(new.id))
    db_session.add(occupied)
    db_session.flush()
    assign_chart_no(db_session, new)
    assert new.chart_no == f"{new.id}-1"


# ── LEG-2: alert response tri-state enum ──────────────────────────────────────
def test_alert_response_enum(client, patient):
    ok = client.post("/api/v1/patient-medical-alerts",
                     json={"patient_id": patient.id, "alert_code": "LATEX", "response": "unknown"})
    assert ok.status_code == 201, ok.text
    bad = client.post("/api/v1/patient-medical-alerts",
                      json={"patient_id": patient.id, "alert_code": "LATEX", "response": "maybe"})
    assert bad.status_code == 422


# ── LEG-3: emergency contact is_primary ───────────────────────────────────────
def test_emergency_contact_is_primary(client, patient):
    r = client.post("/api/v1/patient-emergency-contacts",
                    json={"patient_id": patient.id, "name": "Mum", "is_primary": True})
    assert r.status_code == 201, r.text
    assert r.json()["is_primary"] is True
    listed = client.get(f"/api/v1/patient-emergency-contacts?patient_id={patient.id}&is_primary=true").json()
    assert listed["meta"]["total"] == 1


# ── LEG-8: recall interval_unit + scheduled date/time ─────────────────────────
def test_recall_interval_unit_and_schedule(client, patient):
    r = client.post("/api/v1/patient-recalls",
                    json={"patient_id": patient.id, "recall_type": "prophy", "interval_months": 36,
                          "interval_unit": "year", "scheduled_date": "2026-09-01",
                          "scheduled_time": "09:30"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["interval_unit"] == "year" and body["scheduled_date"] == "2026-09-01"
    assert body["scheduled_time"] == "09:30"


# ── LEG-6/7: insurance dentical + plan anniversary expiry ─────────────────────
def test_insurance_additive_columns(client, db_session, patient):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Acme Dental")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)

    plan = client.post("/api/v1/insurance-plans",
                       json={"carrier_id": carrier.id, "group_number": "GRP-1",
                             "anniversary_expiry_date": "2027-01-01"})
    assert plan.status_code == 201, plan.text
    assert plan.json()["anniversary_expiry_date"] == "2027-01-01"

    pi = client.post("/api/v1/patient-insurance",
                     json={"patient_id": patient.id, "insurance_type": "primary",
                           "ins_plan_id": plan.json()["id"], "dentical_share_amount": 25.5,
                           "dentical_share_month": 7, "dentical_share_year": 2026})
    assert pi.status_code == 201, pi.text
    assert float(pi.json()["dentical_share_amount"]) == 25.5

    # LEG-5: exact Group # filter.
    by_group = client.get("/api/v1/insurance-plans?group_number=GRP-1").json()
    assert by_group["meta"]["total"] == 1


# ── LEG-4: definition section ─────────────────────────────────────────────────
def test_definition_section(client):
    r = client.post("/api/v1/definitions",
                    json={"group_code": "DENTQUEST", "key1": "Q1", "description": "Bleeding gums?",
                          "section": "Women Only", "sort_order": 3, "input_type": "yesno"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["section"] == "Women Only" and body["input_type"] == "yesno"


# ── LEG-10/11/12/13: responsible-party billing entity ─────────────────────────
def test_responsible_party_crud(client):
    r = client.post("/api/v1/responsible-parties",
                    json={"first_name": "Pat", "last_name": "Guarantor", "resp_party_type": "CA",
                          "send_collections": True, "statement_message": "Pay promptly",
                          "statement_message_print_count": 3, "ssn": "555-00-1234"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] and body["resp_party_type"] == "CA" and body["send_collections"] is True
    got = client.get(f"/api/v1/responsible-parties?resp_party_type=CA").json()
    assert got["meta"]["total"] == 1


# ── LEG-10 + LEG-14: inline guarantor via register + roster ───────────────────
def test_register_inline_guarantor_and_roster(client):
    body = {
        "patient": {"first_name": "Dep", "last_name": "Endant"},
        "responsible_party": {
            "relationship": "parent",
            "person": {"first_name": "Parent", "last_name": "Endant", "resp_party_type": "CA"},
        },
    }
    reg = client.post("/api/v1/patients/register", json=body)
    assert reg.status_code == 201, reg.text
    rp_id = reg.json()["responsible_party_id"]
    assert rp_id is not None

    # Roster lists the dependent under the guarantor, with a balance field.
    roster = client.get(f"/api/v1/responsible-parties/{rp_id}/patients")
    assert roster.status_code == 200, roster.text
    rows = roster.json()
    assert len(rows) == 1 and rows[0]["last_name"] == "Endant" and "balance" in rows[0]

    # LEG-14: responsible_party_id filter on GET /patients.
    by_rp = client.get(f"/api/v1/patients?responsible_party_id={rp_id}").json()
    assert by_rp["meta"]["total"] == 1


# ── LEG-5: account plans reuse across the account ─────────────────────────────
def test_account_plans(client, db_session, patient):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Acme Dental")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id, group_number="G9")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(PatientInsurance(patient_id=patient.id, insurance_type="primary", ins_plan_id=plan.id))
    db_session.commit()

    plans = client.get(f"/api/v1/patients/{patient.id}/account-plans")
    assert plans.status_code == 200, plans.text
    data = plans.json()
    assert len(data) == 1
    assert data[0]["id"] == plan.id and data[0]["carrier_name"] == "Acme Dental"


# ── LEG-16: home_office_name / home_office_code on PatientRead ─────────────────
def test_patient_read_home_office_name(client, db_session):
    office = Office(tenant_id=db_session._tenant_id, office_code="OFF-9",
                    name="Moon Dental", short_id="9")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)

    created = client.post("/api/v1/patients",
                          json={"first_name": "Off", "last_name": "Ice", "home_office_id": office.id})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["home_office_name"] == "Moon Dental"
    assert body["home_office_code"] == "9"
    # Also present on list + get.
    got = client.get(f"/api/v1/patients/{body['id']}").json()
    assert got["home_office_name"] == "Moon Dental"
