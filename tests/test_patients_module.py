"""Patients-module backend-gap tests."""

from __future__ import annotations

import pytest

from app.db.models import InsuranceClaim, Patient, ProgressNote


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="John", last_name="Smith",
                ssn="111-22-3333", chart_no="CH-T1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def test_emergency_contact_crud(client, patient):
    r = client.post("/api/v1/patient-emergency-contacts",
                    json={"patient_id": patient.id, "name": "Jane Smith",
                          "relationship": "spouse", "phone": "555-1212"})
    assert r.status_code == 201
    listed = client.get(f"/api/v1/patient-emergency-contacts?patient_id={patient.id}").json()
    assert listed["meta"]["total"] == 1
    assert listed["items"][0]["name"] == "Jane Smith"


def test_patient_adjustment_crud(client, patient):
    r = client.post("/api/v1/patient-adjustments",
                    json={"patient_id": patient.id, "adjustment_date": "2026-06-05",
                          "amount": 50.0, "adjustment_type": "write_off"})
    assert r.status_code == 201
    assert client.get(f"/api/v1/patient-adjustments?patient_id={patient.id}").json()["meta"]["total"] == 1


def test_patient_document_upload_list_delete(client, patient):
    up = client.post("/api/v1/patient-documents",
                     data={"patient_id": str(patient.id), "document_type": "insurance_card"},
                     files={"file": ("card.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert up.status_code == 201, up.text
    doc = up.json()
    # NOTE-DOC-3: file_url is the authenticated /content route (or a signed GCS
    # URL when a bucket is configured) — never the public /uploads path.
    assert doc["file_url"].endswith(f"/patient-documents/{doc['id']}/content")
    assert "file_path" not in doc
    # LTR-12: the list is now the standard paginated envelope, like every other list.
    assert client.get(
        f"/api/v1/patient-documents?patient_id={patient.id}"
    ).json()["meta"]["total"] == 1
    assert client.delete(f"/api/v1/patient-documents/{doc['id']}").status_code == 204
    assert client.get(
        f"/api/v1/patient-documents?patient_id={patient.id}"
    ).json()["meta"]["total"] == 0


def test_claim_detail_and_status(client, patient, db_session):
    claim = InsuranceClaim(id="CLM-T1", patient_id=patient.id, claim_number="CN-T1", status="draft")
    db_session.add(claim)
    db_session.commit()
    detail = client.get("/api/v1/insurance-claims/CLM-T1/detail")
    assert detail.status_code == 200
    body = detail.json()
    assert body["claim"]["claim_number"] == "CN-T1"
    assert body["procedures"] == [] and body["payments"] == [] and body["coverage"] == []
    # lifecycle
    st = client.post("/api/v1/insurance-claims/CLM-T1/status", json={"status": "submitted"})
    assert st.status_code == 200 and st.json()["status"] == "submitted"


def test_progress_note_sign(client, patient, db_session):
    note = ProgressNote(patient_id=patient.id, notes="exam")
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)
    r = client.post(f"/api/v1/progress-notes/{note.id}/sign")
    assert r.status_code == 200
    assert r.json()["signed_by"] is not None and r.json()["signed_at"] is not None


def test_duplicate_check(client, patient):
    r = client.post("/api/v1/patients/check-duplicate",
                    json={"first_name": "John", "last_name": "Smith"})
    assert r.status_code == 200
    cands = r.json()["candidates"]
    assert any(c["id"] == patient.id and c["match_score"] >= 60 for c in cands)


def test_patients_advanced_filter(client, patient):
    by_ssn = client.get("/api/v1/patients?ssn=111-22-3333").json()
    assert by_ssn["meta"]["total"] == 1
    assert client.get("/api/v1/patients?ssn=000-00-0000").json()["meta"]["total"] == 0


def test_patient_notes_is_deleted_filter(client, patient):
    created = client.post("/api/v1/patient-notes", json={"patient_id": patient.id, "notes": "n1"})
    nid = created.json()["id"]
    client.delete(f"/api/v1/patient-notes/{nid}")  # soft-delete -> is_deleted=true
    assert client.get(f"/api/v1/patient-notes?patient_id={patient.id}&is_deleted=false").json()["meta"]["total"] == 0
    assert client.get(f"/api/v1/patient-notes?patient_id={patient.id}&is_deleted=true").json()["meta"]["total"] == 1


def test_balance_enrichment_fields(client, patient):
    b = client.get(f"/api/v1/patients/{patient.id}/balance").json()
    for k in ("insurance_balance", "today_charges", "aging", "recent_activity"):
        assert k in b
    assert "last_ins_amount" in b["recent_activity"] and "last_pat_amount" in b["recent_activity"]
