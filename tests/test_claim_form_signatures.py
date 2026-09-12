"""ADA claim-form signatures — SIG-11…16 + the SIG-9 follow-up of
``docs/signature/topaz_signature_backend_devreport (2).md`` §5.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.db.models import (
    Office,
    Patient,
    PatientSignature,
    Provider,
    ProviderSignature,
    SignatureAuditEvent,
)
from app.services import signature_service as svc

V1 = "/api/v1"
SIGSTRING = "02008C00D5A1" * 8


def _jpeg_data_url() -> str:
    """A real JPEG, so reportlab embeds it on the form."""
    import base64
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 12), (20, 20, 120)).save(buf, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


JPEG = _jpeg_data_url()
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

TOPAZ = {"signature_data": JPEG, "device_source": "topaz", "sig_string": SIGSTRING,
         "point_count": 300, "stroke_count": 4, "device_model": "T-LBK755SE", "device_serial": "755-1"}


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="SIG1", name="Pad Dental", short_id="SIG",
               address_line1="1 Main", city="Austin", state="TX", zip="78701", timezone="America/Chicago")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    p = Provider(id="DRS", tenant_id=db_session._tenant_id, office_id=office.id, name="Dr Signer",
                 short_id="DRS", npi="1234567893", license="TX-9")
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def patient(db_session, office, provider) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Minor", last_name="Child", chart_no="SIG-1",
                home_office_id=office.id, dob=date(2015, 3, 4), preferred_provider_id=provider.id,
                is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def claim(client, db_session, patient, office, provider):
    r = client.post(f"{V1}/procedure-codes", json={"code": "D0120", "description": "Eval", "category": "T",
                                                   "default_fee": 60})
    assert r.status_code == 201, r.text
    r = client.post(f"{V1}/patient-procedures", json={
        "id": "P-SIG", "patient_id": patient.id, "office_id": office.id, "provider_id": provider.id,
        "procedure_code": "D0120", "fee": 60, "date_of_service": "2026-09-01"})
    assert r.status_code == 201, r.text
    r = client.post(f"{V1}/insurance-claims", json={
        "id": "CLM-SIG", "patient_id": patient.id, "office_id": office.id, "claim_number": "CLM-SIG",
        "status": "draft", "procedure_ids": ["P-SIG"]})
    assert r.status_code == 201, r.text
    return r.json()


def _sign(client, patient_id, signature_type, **extra):
    r = client.post(f"{V1}/patient-signatures",
                    json={"patient_id": patient_id, "signature_type": signature_type, **TOPAZ, **extra})
    assert r.status_code == 201, r.text
    return r.json()


# ── SIG-11/12/13/15: the row ─────────────────────────────────────────────────
def test_claim_binding_signer_fields_and_types(client, db_session, patient, claim, provider):
    sig = _sign(client, patient.id, "Claim_Patient_Consent", claim_id=claim["id"],
                signer_name="  Pat Parent ", signer_relationship="Guardian")
    assert sig["claim_id"] == claim["id"]
    assert sig["signature_type"] == "claim_patient_consent"  # SIG-12: normalised, accepted unchanged
    assert sig["signer_name"] == "Pat Parent" and sig["signer_relationship"] == "guardian"  # SIG-13
    assert sig["content_hash"] and sig["signature_status"] == "signed"
    ev = db_session.execute(select(SignatureAuditEvent).where(
        SignatureAuditEvent.entity_id == sig["id"], SignatureAuditEvent.entity_type == "patient_signature"
    )).scalars().one()
    assert ev.signer_name == "Pat Parent" and ev.signer_relationship == "guardian"

    # SIG-15: the attesting provider is its own column.
    dentist = _sign(client, patient.id, "claim_treating_dentist", claim_id=claim["id"],
                    signer_provider_id=provider.id, is_user_sig=True)
    assert dentist["signer_provider_id"] == provider.id
    assert dentist["signed_by_user_id"] == db_session._admin.id  # the operator, unless told otherwise
    bad = client.post(f"{V1}/patient-signatures", json={
        "patient_id": patient.id, "signature_type": "claim_treating_dentist", "signer_provider_id": "NOPE", **TOPAZ})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "signature_provider_not_found"

    # A claim on another patient cannot be the subject.
    other = Patient(tenant_id=db_session._tenant_id, first_name="O", last_name="Ther", chart_no="SIG-2",
                    is_active=True)
    db_session.add(other)
    db_session.commit()
    bad = client.post(f"{V1}/patient-signatures", json={
        "patient_id": other.id, "signature_type": "claim_assign_benefits", "claim_id": claim["id"], **TOPAZ})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "signature_document_mismatch"

    # ?claim_id= filter (SIG-11).
    listed = client.get(f"{V1}/patient-signatures", params={"claim_id": claim["id"]}).json()
    assert {i["signature_type"] for i in listed["items"]} == {"claim_patient_consent", "claim_treating_dentist"}

    # Re-pricing a claimed line after signing reads as stale.
    assert client.patch(f"{V1}/patient-procedures/P-SIG", json={"fee": 75}).status_code == 200
    assert client.get(f"{V1}/patient-signatures/{sig['id']}").json()["signature_status"] == "stale"


# ── SIG-9 follow-up: one small call for the on-file set ─────────────────────
def test_latest_per_type_and_type_list_filters(client, patient):
    first = _sign(client, patient.id, "claim_assign_benefits", signed_at="2026-01-01T10:00:00Z")
    latest = _sign(client, patient.id, "claim_assign_benefits", signed_at="2026-05-01T10:00:00Z")
    _sign(client, patient.id, "medical_history")
    _sign(client, patient.id, "claim_patient_consent")

    r = client.get(f"{V1}/patient-signatures", params={
        "patient_id": patient.id, "latest_per_type": "true", "include_image": "false",
        "signature_types": "claim_patient_consent,claim_assign_benefits,claim_treating_dentist"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    by_type = {i["signature_type"]: i for i in items}
    assert set(by_type) == {"claim_assign_benefits", "claim_patient_consent"}
    assert by_type["claim_assign_benefits"]["id"] == latest["id"] != first["id"]
    assert all(i["signature_data"] is None and i["image_omitted"] for i in items)


# ── SIG-14: provider signature store ─────────────────────────────────────────
def test_provider_signature_store_and_user_fallback(client, db_session, provider):
    missing = client.get(f"{V1}/providers/{provider.id}/signature")
    assert missing.status_code == 404

    # Linked-user fallback first: the pre-SIG-14 path still answers.
    provider.user_id = db_session._admin.id
    db_session.commit()
    client.put(f"{V1}/users/me/signature", json={"signature_data": PNG, "device_source": "web-pad"})
    via_user = client.get(f"{V1}/providers/{provider.id}/signature").json()
    assert via_user["source"] == "user" and via_user["user_id"] == db_session._admin.id
    assert client.get(f"{V1}/providers/{provider.id}/signature", params={"resolve": "false"}).status_code == 404

    # The provider store wins once it exists, and carries the Topaz block.
    r = client.put(f"{V1}/providers/{provider.id}/signature", json=TOPAZ)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "provider" and body["has_sig_string"] is True and body["sig_string"] is None
    assert body["device_model"] == "T-LBK755SE" and body["signature_data"] == JPEG
    row = db_session.execute(select(ProviderSignature).where(ProviderSignature.provider_id == provider.id)).scalar_one()
    assert svc.is_encrypted(row.sig_string)
    got = client.get(f"{V1}/providers/{provider.id}/signature", params={"include_sig_string": "true"}).json()
    assert got["source"] == "provider" and got["sig_string"] == SIGSTRING
    events = [e.event for e in db_session.execute(select(SignatureAuditEvent).where(
        SignatureAuditEvent.entity_type == "provider").order_by(SignatureAuditEvent.id)).scalars()]
    assert events == ["captured", "sig_string_exported"]

    # Replace, then clear.
    client.put(f"{V1}/providers/{provider.id}/signature", json={"signature_data": PNG, "device_source": "web-pad"})
    assert client.get(f"{V1}/providers/{provider.id}/signature").json()["has_sig_string"] is False
    assert client.delete(f"{V1}/providers/{provider.id}/signature").status_code == 204
    assert client.get(f"{V1}/providers/{provider.id}/signature").json()["source"] == "user"
    assert client.get(f"{V1}/providers/NOPE/signature").status_code == 404


# ── SIG-16: resolution + the printed form ────────────────────────────────────
def test_claim_signature_resolution_and_pdf(client, db_session, patient, claim, provider):
    pre = client.get(f"{V1}/insurance-claims/{claim['id']}/signatures").json()
    assert pre["treating_provider_id"] == provider.id
    assert all(pre[item]["signature_id"] is None for item in ("item_36", "item_37", "item_53"))

    # Patient-level "on file" rows, then a pinned Item 36 that must win over the newer on-file one.
    onfile_36 = _sign(client, patient.id, "claim_consent", signed_at="2026-02-01T09:00:00Z")
    _sign(client, patient.id, "claim_assign_benefits", signed_at="2026-02-01T09:00:00Z")
    pinned_36 = _sign(client, patient.id, "claim_patient_consent", claim_id=claim["id"],
                      signer_name="Pat Parent", signer_relationship="parent",
                      signed_at="2026-01-01T09:00:00Z")
    newer_onfile_36 = _sign(client, patient.id, "claim_patient_consent", signed_at="2026-08-01T09:00:00Z")
    client.put(f"{V1}/providers/{provider.id}/signature", json=TOPAZ)

    res = client.get(f"{V1}/insurance-claims/{claim['id']}/signatures", params={"include_image": "true"}).json()
    assert res["item_36"]["signature_id"] == pinned_36["id"] and res["item_36"]["source"] == "claim"
    assert res["item_36"]["signer_name"] == "Pat Parent" and res["item_36"]["signature_data"] == JPEG
    assert res["item_37"]["source"] == "patient" and res["item_37"]["has_image"] is True
    assert res["item_53"]["source"] == "provider" and res["item_53"]["printed_name"] == "Dr Signer"
    assert onfile_36["id"] != newer_onfile_36["id"]  # both lost to the pin

    # The assembled form carries the same resolution; JSON omits images by default.
    form = client.get(f"{V1}/insurance-claims/{claim['id']}/ada-claim-form").json()
    auth = form["authorizations"]
    assert auth["signature_on_file"] is True and auth["signature_source"] == "claim_consent_signature"
    assert auth["consent_signature_id"] == pinned_36["id"]
    assert auth["assignment_of_benefits"] is True
    assert auth["signatures"]["item_36"]["signature_data"] is None
    assert not [w for w in form["warnings"] if w["code"] == "signature_not_printable"]

    pdf = client.get(f"{V1}/insurance-claims/{claim['id']}/reports/ada-claim-form")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    # Images were embedded as XObjects; the placeholder text is gone.
    assert b"/Image" in pdf.content or b"/XObject" in pdf.content

    # A legacy SigString-only row cannot print: reported, and the line stays blank.
    client.post(f"{V1}/patient-signatures/{pinned_36['id']}/void", json={"reason": "redo"})
    legacy = PatientSignature(patient_id=patient.id, signature_type="claim_patient_consent", claim_id=claim["id"],
                              sig_string=svc.encrypt_sig_string(SIGSTRING), device_source="0", is_active=True)
    db_session.add(legacy)
    db_session.commit()
    res = client.get(f"{V1}/insurance-claims/{claim['id']}/signatures").json()
    assert res["item_36"]["signature_id"] == legacy.id and res["item_36"]["legacy_sig_string_only"] is True
    form = client.get(f"{V1}/insurance-claims/{claim['id']}/ada-claim-form").json()
    assert [w["item"] for w in form["warnings"] if w["code"] == "signature_not_printable"] == ["36"]
    assert client.get(f"{V1}/insurance-claims/{claim['id']}/reports/ada-claim-form").status_code == 200


def test_item_53_falls_back_to_linked_user_then_nothing(client, db_session, patient, claim, provider):
    res = client.get(f"{V1}/insurance-claims/{claim['id']}/signatures").json()
    assert res["item_53"]["source"] is None and res["item_53"]["printed_name"] == "Dr Signer"
    provider.user_id = db_session._admin.id
    db_session.commit()
    client.put(f"{V1}/users/me/signature", json={"signature_data": PNG, "device_source": "web-pad"})
    res = client.get(f"{V1}/insurance-claims/{claim['id']}/signatures").json()
    assert res["item_53"]["source"] == "user" and res["item_53"]["signed_by_user_id"] == db_session._admin.id
    # A per-claim dentist row beats both stores.
    row = _sign(client, patient.id, "claim_treating_dentist", claim_id=claim["id"], signer_provider_id=provider.id)
    res = client.get(f"{V1}/insurance-claims/{claim['id']}/signatures").json()
    assert res["item_53"]["signature_id"] == row["id"] and res["item_53"]["source"] == "claim"
    assert res["item_53"]["signer_provider_id"] == provider.id


def test_rules_publish_claim_vocabulary(client):
    body = client.get(f"{V1}/metadata/signature-capture").json()
    assert "claim_patient_consent" in body["signature_types"] and "claim_consent" in body["signature_types"]
    assert body["claim_signature_items"]["item_36"] == ["claim_patient_consent", "claim_consent"]
    assert body["signer_relationships"][:3] == ["self", "parent", "guardian"]
    assert body["provider_signature_write"] == "PUT /providers/{id}/signature"
    rules = client.get(f"{V1}/metadata/ada-claim-form-rules").json()
    assert rules["signatures"]["print_geometry_pt"]["item_53"] == [78, 16]
