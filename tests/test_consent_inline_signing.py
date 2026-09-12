"""Consent forms signed in the Report Viewer — CS-1…8 of
``docs/letters/consent_inline_signing_backend_devreport.md``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.models import ConsentSignature, Patient, PatientConsent, SignatureAuditEvent, User
from app.services import signature_service as svc

V1 = "/api/v1"
SIGSTRING = "02008C00D5A1" * 8
IMAGE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
TOPAZ = {"signature_data": IMAGE, "device_source": "topaz", "sig_string": SIGSTRING,
         "point_count": 300, "stroke_count": 4, "device_model": "T-L(BK)462"}


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ivy", last_name="Viewer", chart_no="CS-1",
                is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def other_patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ann", last_name="Other", chart_no="CS-2",
                is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _consent(client, patient_id, **extra):
    r = client.post(f"{V1}/patient-consents", json={
        "patient_id": patient_id, "title": "Ortho consent", "rendered_html": "<p>I consent.</p>",
        "status": "printed", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _document(client, patient_id, name="signed.pdf"):
    r = client.post(f"{V1}/patient-documents",
                    data={"patient_id": str(patient_id), "document_type": "consent-form"},
                    files={"file": (name, b"%PDF-1.4 signed", "application/pdf")})
    assert r.status_code == 201, r.text
    return r.json()


# ── CS-1: signed rendition beside the printed copy ───────────────────────────
def test_sign_accepts_signature_and_signed_document_together(client, db_session, patient, other_patient):
    printed = _document(client, patient.id, "printed.pdf")
    consent = _consent(client, patient.id, document_id=printed["id"])
    signed_pdf = _document(client, patient.id, "signed.pdf")

    r = client.post(f"{V1}/patient-consents/{consent['id']}/sign",
                    json={**TOPAZ, "signed_document_id": signed_pdf["id"], "signer_name": "Ivy"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["signature_method"] == "topaz"  # the capture decides, not the PDF
    assert body["document_id"] == printed["id"] and body["signed_document_id"] == signed_pdf["id"]
    assert body["has_sig_string"] is True and body["signature_status"] == "signed"
    assert body["capture_method"] == "topaz"  # CS-8
    assert body["signed_rendered_html"] == "<p>I consent.</p>"  # CS-4

    # The signed PDF must belong to the same patient.
    foreign = _document(client, other_patient.id)
    c2 = _consent(client, patient.id)
    bad = client.post(f"{V1}/patient-consents/{c2['id']}/sign",
                      json={"signature_data": IMAGE, "signed_document_id": foreign["id"]})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "document_patient_mismatch"
    assert bad.json()["error"]["details"]["field"] == "signed_document_id"


# ── CS-2: countersignatures ──────────────────────────────────────────────────
def test_countersigns_on_sign_and_later(client, db_session, patient):
    consent = _consent(client, patient.id)
    r = client.post(f"{V1}/patient-consents/{consent['id']}/sign", json={
        **TOPAZ, "signer_name": "Ivy",
        "countersigns": [{"role": "Hygienist", "signature_data": IMAGE, "device_source": "web-pad",
                          "signer_user_id": db_session._admin.id, "signer_name": "Pat RDH"}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["countersigns"]) == 1
    cs = body["countersigns"][0]
    assert cs["role"] == "hygienist" and cs["signer_name"] == "Pat RDH" and cs["capture_method"] == "drawn"
    assert cs["signature_data"] is None and cs["has_image"] is True  # never inline on the consent read
    assert cs["content_hash"] == body["content_hash"]

    # The stored flow: a dentist countersigns later.
    later = client.post(f"{V1}/patient-consents/{consent['id']}/countersign",
                        json={"role": "dentist", **TOPAZ, "signer_name": "Dr Endo"})
    assert later.status_code == 201, later.text
    assert later.json()["role"] == "dentist" and later.json()["signature_data"] == IMAGE
    row = db_session.get(ConsentSignature, later.json()["id"])
    assert svc.is_encrypted(row.sig_string)

    lines = client.get(f"{V1}/patient-consents/{consent['id']}/signatures",
                       params={"include_image": "true"}).json()
    assert [line["role"] for line in lines] == ["hygienist", "dentist"]
    assert all(line["signature_data"] == IMAGE for line in lines)

    # Rules enforced: role vocabulary, signer must be in the practice, image required.
    bad = client.post(f"{V1}/patient-consents/{consent['id']}/countersign",
                      json={"role": "janitor", "signature_data": IMAGE})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_countersign_role"
    bad = client.post(f"{V1}/patient-consents/{consent['id']}/countersign",
                      json={"role": "dentist", "signature_data": IMAGE, "signer_user_id": 999})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "countersigner_not_found"

    # Void one; the consent read drops it, the list keeps it on request.
    void = client.post(f"{V1}/patient-consents/{consent['id']}/signatures/{later.json()['id']}/void",
                       json={"reason": "wrong dentist"})
    assert void.status_code == 200 and void.json()["is_active"] is False
    assert [c["role"] for c in client.get(f"{V1}/patient-consents/{consent['id']}").json()["countersigns"]] == ["hygienist"]
    assert len(client.get(f"{V1}/patient-consents/{consent['id']}/signatures",
                          params={"include_voided": "true"}).json()) == 2
    events = [e.event for e in db_session.execute(select(SignatureAuditEvent).where(
        SignatureAuditEvent.entity_type == "consent_signature").order_by(SignatureAuditEvent.id)).scalars()]
    assert events == ["captured", "captured", "voided"]

    # A declined consent cannot be countersigned.
    declined = _consent(client, patient.id)
    client.post(f"{V1}/patient-consents/{declined['id']}/sign", json={"status": "declined", "declined_reason": "no"})
    assert client.post(f"{V1}/patient-consents/{declined['id']}/countersign",
                       json={"role": "dentist", "signature_data": IMAGE}).status_code == 409


# ── CS-3: the client's capture time ──────────────────────────────────────────
def test_signed_at_honours_client_within_tolerance(client, patient):
    near = (datetime.now(timezone.utc) - timedelta(seconds=40)).replace(microsecond=0)
    c1 = _consent(client, patient.id)
    body = client.post(f"{V1}/patient-consents/{c1['id']}/sign",
                       json={"signature_data": IMAGE, "signed_at": near.isoformat()}).json()
    assert body["signed_at_source"] == "client"
    assert datetime.fromisoformat(body["signed_at"].replace("Z", "+00:00")) == near
    assert datetime.fromisoformat(body["captured_at"].replace("Z", "+00:00")) == near

    far = datetime(2020, 1, 1, tzinfo=timezone.utc)
    c2 = _consent(client, patient.id)
    body = client.post(f"{V1}/patient-consents/{c2['id']}/sign",
                       json={"signature_data": IMAGE, "signed_at": far.isoformat()}).json()
    assert body["signed_at_source"] == "server"
    assert datetime.fromisoformat(body["signed_at"].replace("Z", "+00:00")) > far
    assert datetime.fromisoformat(body["captured_at"].replace("Z", "+00:00")) == far  # kept for audit


# ── CS-4: the hash and the as-signed rendition ───────────────────────────────
def test_content_hash_is_over_rendered_html_only(client, patient):
    consent = _consent(client, patient.id)
    body = client.post(f"{V1}/patient-consents/{consent['id']}/sign", json={"signature_data": IMAGE}).json()
    assert body["content_hash"] == svc.consent_content_hash("<p>I consent.</p>")
    assert body["content_hash"] == svc.consent_content_hash("<p>I   consent.</p>\n")  # reflow is not an edit
    assert client.patch(f"{V1}/patient-consents/{consent['id']}",
                        json={"rendered_html": "<p>I consent to more.</p>"}).status_code == 200
    after = client.get(f"{V1}/patient-consents/{consent['id']}").json()
    assert after["signature_status"] == "stale"
    assert after["signed_rendered_html"] == "<p>I consent.</p>"  # immutable
    rules = client.get(f"{V1}/metadata/signature-capture").json()
    assert "rendered_html" in rules["consent_content_hash"] and "excludes signature_data" in rules["consent_content_hash"]


# ── CS-5: light history list ─────────────────────────────────────────────────
def test_list_include_signature_false(client, db_session, patient):
    consent = _consent(client, patient.id)
    client.post(f"{V1}/patient-consents/{consent['id']}/sign", json={"signature_data": IMAGE})
    r = client.get(f"{V1}/patient-consents", params={"patient_id": patient.id, "include_signature": "false"})
    assert r.status_code == 200
    row = r.json()["items"][0]
    assert row["signature_data"] is None and row["image_omitted"] is True and row["has_image"] is True
    assert row["signature_method"] == "drawn" and row["status"] == "signed"
    db_session.expire_all()
    assert db_session.get(PatientConsent, consent["id"]).signature_data == IMAGE
    assert client.get(f"{V1}/patient-consents/{consent['id']}").json()["signature_data"] == IMAGE


# ── CS-6: file_url follows the caller's origin ───────────────────────────────
def test_document_file_url_uses_request_origin(client, patient, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "PUBLIC_API_BASE_URL", "https://dentc-backend-xyz.run.app")
    doc = _document(client, patient.id)
    assert doc["file_url"].startswith("http://testserver/api/v1/patient-documents/")
    forwarded = client.get(f"{V1}/patient-documents/{doc['id']}",
                           headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "api.example.com"}).json()
    assert forwarded["file_url"].startswith("https://api.example.com/api/v1/patient-documents/")


# ── CS-7: any user of the practice may sign ──────────────────────────────────
def test_sign_does_not_require_the_creator(client, db_session, patient):
    consent = _consent(client, patient.id)
    other = User(tenant_id=db_session._tenant_id, email="rdh@test.local", username="rdh",
                 password_hash="x", role="provider", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.execute(
        PatientConsent.__table__.update().where(PatientConsent.id == consent["id"]).values(created_by=other.id)
    )
    db_session.commit()
    r = client.post(f"{V1}/patient-consents/{consent['id']}/sign", json={"signature_data": IMAGE})
    assert r.status_code == 200, r.text
    assert r.json()["signed_by"] == db_session._admin.id and r.json()["created_by"] == other.id


# ── CS-8: one capture vocabulary ─────────────────────────────────────────────
def test_capture_method_is_derived_on_every_store(client, db_session, patient):
    sig = client.post(f"{V1}/patient-signatures",
                      json={"patient_id": patient.id, "signature_data": IMAGE, "device_source": "web-pad"}).json()
    assert sig["capture_method"] == "drawn"
    topaz = client.post(f"{V1}/patient-signatures", json={"patient_id": patient.id, **TOPAZ}).json()
    assert topaz["capture_method"] == "topaz"
    consent = _consent(client, patient.id)
    scanned_doc = _document(client, patient.id, "scan.pdf")
    body = client.post(f"{V1}/patient-consents/{consent['id']}/sign", json={"document_id": scanned_doc["id"]}).json()
    assert body["capture_method"] == "scanned"
    user = client.put(f"{V1}/users/me/signature", json=TOPAZ).json()
    assert user["capture_method"] == "topaz"
    rules = client.get(f"{V1}/metadata/signature-capture").json()
    assert rules["capture_methods"] == ["topaz", "drawn", "scanned", "verbal", "legacy", "unknown"]
    assert rules["consent_countersign_roles"][0] == "dentist"
