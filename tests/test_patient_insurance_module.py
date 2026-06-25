"""Patient-insurance backend-gap tests (patient-insurance dev-report INS-PT-1..6)."""

from __future__ import annotations

import pytest

from app.db.models import InsuranceCarrier, InsurancePlan, Patient

PREFIX = "/api/v1"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ins", last_name="Ured",
                chart_no="INS-PAT", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def carrier_plan(db_session):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Acme Dental",
                               carrier_type="True", supports_realtime_eligibility=True, is_active=True)
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id, is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return carrier, plan


# ── INS-PT-1/2/4/6: new subscriber columns persist ───────────────────────────
def test_subscriber_new_fields_persist(client, carrier_plan):
    _carrier, plan = carrier_plan
    r = client.post(f"{PREFIX}/insurance-subscribers", json={
        "ins_plan_id": plan.id, "sub_first_name": "Jo", "sub_last_name": "Sub",
        "sub_address": "1 Main St", "sub_address2": "Apt 4",  # INS-PT-4
        "marital_status": "married",                          # INS-PT-1
        "sub_phone": "555-1212",                              # INS-PT-2
        "plan_effective_date": "2026-01-01",                 # INS-PT-6
        "plan_term_date": "2026-12-31",
        "effective_date": "2026-02-01",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sub_address2"] == "Apt 4"
    assert body["marital_status"] == "married"
    assert body["sub_phone"] == "555-1212"
    assert body["plan_effective_date"] == "2026-01-01"
    assert body["plan_term_date"] == "2026-12-31"
    assert body["effective_date"] == "2026-02-01"  # subscriber ("Sub Date") still distinct


# ── INS-PT-3: secondary-subscriber relationship-to-primary persists ──────────
def test_patient_insurance_sec_sub_rel(client, patient, carrier_plan):
    _carrier, plan = carrier_plan
    r = client.post(f"{PREFIX}/patient-insurance", json={
        "patient_id": patient.id, "ins_plan_id": plan.id,
        "legacy_plan_type": "D", "insurance_type": "secondary",
        "sec_sub_rel_to_prim_sub": "spouse",
    })
    assert r.status_code == 201, r.text
    assert r.json()["sec_sub_rel_to_prim_sub"] == "spouse"

    # filterable slot by category + order (dental/secondary)
    listed = client.get(
        f"{PREFIX}/patient-insurance?patient_id={patient.id}&legacy_plan_type=D&insurance_type=secondary"
    ).json()
    assert listed["meta"]["total"] == 1


# ── INS-PT-5: eligibility verify stamp ───────────────────────────────────────
def test_verify_eligibility_stamps(client, carrier_plan, db_session):
    _carrier, plan = carrier_plan
    sub = client.post(f"{PREFIX}/insurance-subscribers",
                      json={"ins_plan_id": plan.id, "sub_first_name": "Eli"}).json()
    r = client.post(f"{PREFIX}/insurance-subscribers/{sub['id']}/verify-eligibility",
                    json={"elig_status": "active", "notes": "checked by phone"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subscriber_id"] == sub["id"]
    assert body["elig_status"] == "active"
    assert body["elig_verified_on"] is not None
    assert body["elig_verified_by"] == db_session._admin.username  # no first/last → username
    assert body["realtime_supported"] is True  # carrier flag echoed
    assert body["method"] == "manual"

    # persisted on the subscriber
    fetched = client.get(f"{PREFIX}/insurance-subscribers/{sub['id']}").json()
    assert fetched["elig_status"] == "active"
    assert fetched["elig_notes"] == "checked by phone"


def test_verify_eligibility_defaults_status(client, carrier_plan):
    _carrier, plan = carrier_plan
    sub = client.post(f"{PREFIX}/insurance-subscribers",
                      json={"ins_plan_id": plan.id, "sub_first_name": "Def"}).json()
    r = client.post(f"{PREFIX}/insurance-subscribers/{sub['id']}/verify-eligibility")
    assert r.status_code == 200, r.text
    assert r.json()["elig_status"] == "verified"  # server default


def test_verify_eligibility_unknown_404(client):
    r = client.post(f"{PREFIX}/insurance-subscribers/999999/verify-eligibility")
    assert r.status_code == 404
