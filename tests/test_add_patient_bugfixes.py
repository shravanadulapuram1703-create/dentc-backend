"""Add-Patient test-report backend bugs (docs/patients/add_patient_test_report.md)."""

from __future__ import annotations

import pytest

from app.db.models import Office, Patient, Provider


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ins", last_name="Slot", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


# ── BUG-3: dental + medical primary must coexist ─────────────────────────────
def test_dental_and_medical_primary_coexist(client, patient):
    dental = client.post("/api/v1/patient-insurance",
                         json={"patient_id": patient.id, "insurance_type": "primary",
                               "legacy_plan_type": "D"})
    assert dental.status_code == 201, dental.text
    medical = client.post("/api/v1/patient-insurance",
                          json={"patient_id": patient.id, "insurance_type": "primary",
                                "legacy_plan_type": "M"})
    assert medical.status_code == 201, medical.text


def test_true_duplicate_slot_still_rejected(client, patient):
    first = client.post("/api/v1/patient-insurance",
                        json={"patient_id": patient.id, "insurance_type": "primary",
                              "legacy_plan_type": "D"})
    assert first.status_code == 201, first.text
    dup = client.post("/api/v1/patient-insurance",
                      json={"patient_id": patient.id, "insurance_type": "primary",
                            "legacy_plan_type": "D"})
    assert dup.status_code == 409, dup.text


# ── BUG-1: duplicate-candidate enrichment ─────────────────────────────────────
def test_duplicate_candidate_has_office_email_provider(client, db_session):
    tid = db_session._tenant_id
    office = Office(tenant_id=tid, office_code="OFF-DUP", name="Dup Office", short_id="DUP")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    provider = Provider(id="PRV-DUP", tenant_id=tid, office_id=office.id, name="Dr Who")
    db_session.add(provider)
    db_session.add(Patient(
        tenant_id=tid, first_name="Autumn", last_name="Smith", email="autumn@example.com",
        home_office_id=office.id, preferred_provider_id="PRV-DUP", is_active=True,
    ))
    db_session.commit()

    r = client.post("/api/v1/patients/check-duplicate",
                    json={"first_name": "Autumn", "last_name": "Smith"})
    assert r.status_code == 200, r.text
    cand = next(c for c in r.json()["candidates"] if c["last_name"] == "Smith")
    assert cand["email"] == "autumn@example.com"
    assert cand["home_office_short_id"] == "DUP"
    assert cand["preferred_provider_name"] == "Dr Who"
