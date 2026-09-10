"""Topaz signature capture — SIG-1…10 of
``docs/signature/topaz_signature_backend_devreport.md``.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.db.models import Patient, PatientSignature, SignatureAuditEvent, Tenant, User
from app.services import signature_service as svc

V1 = "/api/v1"
SIGSTRING = "02008C00D5A1" * 8  # hex, Topaz-shaped
IMAGE = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD"

TOPAZ = {
    "signature_data": IMAGE,
    "device_source": "topaz",
    "sig_string": SIGSTRING,
    "point_count": 412,
    "stroke_count": 6,
    "device_model": "T-L(BK)462",
    "device_serial": "TLBK462-0091",
}


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ada", last_name="Sign",
                chart_no="S-1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def other_patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Bo", last_name="Other",
                chart_no="S-2", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _events(db_session, entity_type: str, entity_id: int) -> list[SignatureAuditEvent]:
    return list(db_session.execute(
        select(SignatureAuditEvent).where(
            SignatureAuditEvent.entity_type == entity_type,
            SignatureAuditEvent.entity_id == entity_id,
        ).order_by(SignatureAuditEvent.id)
    ).scalars())


# ── SIG-1/2/3/4/8: the generic resource ─────────────────────────────────────
def test_create_signature_stores_topaz_block_encrypted_and_off_the_read(client, db_session, patient):
    r = client.post(f"{V1}/patient-signatures", json={"patient_id": patient.id, **TOPAZ},
                    headers={"User-Agent": "SigCapture/1.0 (workstation-3)"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "sig_string" not in body  # SIG-4: never on a read model
    assert body["has_sig_string"] is True
    assert body["has_image"] is True
    assert body["sig_format"] == "topaz_sigstring_v1"
    assert body["sig_compression"] == 0 and body["sig_encryption"] == 0
    assert body["device_vendor"] == "topaz"
    assert body["device_model"] == "T-L(BK)462"
    assert body["point_count"] == 412 and body["stroke_count"] == 6
    assert body["signature_len"] == len(IMAGE)
    assert body["captured_user_agent"] == "SigCapture/1.0 (workstation-3)"
    assert body["signed_at"] is not None

    row = db_session.get(PatientSignature, body["id"])
    assert row.sig_string != SIGSTRING and svc.is_encrypted(row.sig_string)
    assert svc.decrypt_sig_string(row.sig_string) == SIGSTRING

    # SIG-8: the capture is on the trail with the pad + workstation.
    events = _events(db_session, "patient_signature", body["id"])
    assert [e.event for e in events] == ["captured"]
    assert events[0].device_model == "T-L(BK)462"
    assert events[0].user_agent == "SigCapture/1.0 (workstation-3)"
    assert events[0].ip is not None
    assert events[0].actor_id == db_session._admin.id


def test_sig_string_endpoint_is_admin_only_and_audited(client, db_session, patient):
    sid = client.post(f"{V1}/patient-signatures", json={"patient_id": patient.id, **TOPAZ}).json()["id"]
    r = client.get(f"{V1}/patient-signatures/{sid}/sig-string")
    assert r.status_code == 200, r.text
    assert r.json()["sig_string"] == SIGSTRING
    assert r.json()["encrypted_at_rest"] is True
    assert r.json()["sig_string_readable"] is True
    assert [e.event for e in _events(db_session, "patient_signature", sid)] == [
        "captured", "sig_string_exported"]


def test_empty_pad_is_refused(client, patient):
    r = client.post(f"{V1}/patient-signatures",
                    json={"patient_id": patient.id, **TOPAZ, "point_count": 1})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "signature_empty"
    r = client.post(f"{V1}/patient-signatures",
                    json={"patient_id": patient.id, "signature_data": IMAGE, "sig_format": "svg"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_signature_field"


def test_web_pad_capture_needs_no_topaz_fields(client, patient):
    r = client.post(f"{V1}/patient-signatures",
                    json={"patient_id": patient.id, "signature_data": IMAGE, "device_source": "web-pad"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["has_sig_string"] is False
    assert body["sig_format"] is None and body["device_vendor"] is None
    assert body["device_source"] == "web-pad"


# ── SIG-9: list without the images ───────────────────────────────────────────
def test_list_include_image_false_strips_images_without_touching_the_rows(client, db_session, patient):
    sid = client.post(f"{V1}/patient-signatures", json={"patient_id": patient.id, **TOPAZ}).json()["id"]
    r = client.get(f"{V1}/patient-signatures", params={"patient_id": patient.id, "include_image": "false"})
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["signature_data"] is None
    assert item["image_omitted"] is True and item["has_image"] is True
    # The stored image survived the strip.
    db_session.expire_all()
    assert db_session.get(PatientSignature, sid).signature_data == IMAGE
    full = client.get(f"{V1}/patient-signatures", params={"patient_id": patient.id}).json()["items"][0]
    assert full["signature_data"] == IMAGE and full["image_omitted"] is False


# ── SIG-7: document binding ──────────────────────────────────────────────────
def test_progress_note_binding_hashes_and_goes_stale(client, patient, other_patient):
    note = client.post(f"{V1}/progress-notes", json={
        "patient_id": patient.id, "note_date": date.today().isoformat(), "notes": "Exam, no caries",
    })
    assert note.status_code == 201, note.text
    note_id = note.json()["id"]

    r = client.post(f"{V1}/patient-signatures",
                    json={"patient_id": patient.id, "progress_note_id": note_id, **TOPAZ})
    assert r.status_code == 201, r.text
    sig = r.json()
    assert sig["content_hash"] and sig["signature_type"] == "progress_note"
    assert sig["signature_status"] == "signed"

    # An edit after signing must read as stale, never as still-signed.
    upd = client.patch(f"{V1}/progress-notes/{note_id}", json={"notes": "Exam, one lesion #30"})
    assert upd.status_code == 200, upd.text
    assert client.get(f"{V1}/patient-signatures/{sig['id']}").json()["signature_status"] == "stale"

    # A note on another patient cannot be the subject of this patient's signature.
    bad = client.post(f"{V1}/patient-signatures",
                      json={"patient_id": other_patient.id, "progress_note_id": note_id, **TOPAZ})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "signature_document_mismatch"


def test_progress_note_sign_endpoint_freezes_content(client, patient):
    note_id = client.post(f"{V1}/progress-notes", json={
        "patient_id": patient.id, "note_date": date.today().isoformat(), "notes": "Prophy",
    }).json()["id"]
    before = client.get(f"{V1}/progress-notes/{note_id}").json()
    assert before["signature_status"] == "unsigned" and before["content_hash"] is None
    assert client.post(f"{V1}/progress-notes/{note_id}/sign", json={}).status_code == 200
    after = client.get(f"{V1}/progress-notes/{note_id}").json()
    assert after["signature_status"] == "signed" and after["content_hash"]


def test_consent_sign_with_topaz_defaults_method_and_goes_stale_on_edit(client, db_session, patient):
    consent = client.post(f"{V1}/patient-consents", json={
        "patient_id": patient.id, "title": "Ortho consent", "rendered_html": "<p>I consent.</p>",
    })
    assert consent.status_code == 201, consent.text
    cid = consent.json()["id"]
    assert consent.json()["signature_status"] == "unsigned"

    r = client.post(f"{V1}/patient-consents/{cid}/sign", json={**TOPAZ, "signer_name": "Ada Sign"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sig_string" not in body
    assert body["signature_method"] == "topaz"  # SIG-5
    assert body["has_sig_string"] is True
    assert body["device_model"] == "T-L(BK)462"
    assert body["content_hash"] and body["signature_status"] == "signed"
    assert [e.event for e in _events(db_session, "patient_consent", cid)] == ["captured"]

    vec = client.get(f"{V1}/patient-consents/{cid}/sig-string")
    assert vec.status_code == 200 and vec.json()["sig_string"] == SIGSTRING

    # Editing the rendered document after signing is visible, not silent.
    assert client.patch(f"{V1}/patient-consents/{cid}",
                        json={"rendered_html": "<p>I consent to more.</p>"}).status_code == 200
    assert client.get(f"{V1}/patient-consents/{cid}").json()["signature_status"] == "stale"


def test_consent_statuses_publish_topaz(client):
    r = client.get(f"{V1}/patient-consents/statuses")
    assert "topaz" in r.json()["signature_methods"]


# ── SIG-10: the medical-history sign path carries the block too ─────────────
def test_medical_history_sign_keeps_topaz_metadata(client, db_session, patient):
    r = client.post(f"{V1}/patients/{patient.id}/medical-history/sign", json=TOPAZ)
    assert r.status_code in (200, 201), r.text
    sig = r.json()["current_signature"]  # the sign call returns the whole document
    assert sig["has_sig_string"] is True and sig["device_model"] == "T-L(BK)462"
    assert "sig_string" not in sig
    row = db_session.get(PatientSignature, sig["id"])
    assert svc.decrypt_sig_string(row.sig_string) == SIGSTRING
    assert [e.event for e in _events(db_session, "patient_signature", sig["id"])] == ["captured"]

    # A second signing supersedes the first and records it.
    second = client.post(f"{V1}/patients/{patient.id}/medical-history/sign",
                         json=TOPAZ).json()["current_signature"]
    assert [e.event for e in _events(db_session, "patient_signature", sig["id"])] == [
        "captured", "superseded"]
    void = client.post(f"{V1}/patient-signatures/{second['id']}/void", json={"reason": "wrong patient"})
    assert void.status_code == 200
    ev = _events(db_session, "patient_signature", second["id"])
    assert [e.event for e in ev] == ["captured", "voided"] and ev[-1].reason == "wrong patient"

    trail = client.get(f"{V1}/signature-audit-events", params={"patient_id": patient.id})
    assert trail.status_code == 200 and trail.json()["meta"]["total"] == 4


# ── SIG-6: user signature store ──────────────────────────────────────────────
def test_user_signature_put_is_canonical_and_patch_clears_the_block(client, db_session):
    r = client.put(f"{V1}/users/me/signature", json=TOPAZ)
    assert r.status_code == 200, r.text
    assert r.json()["has_sig_string"] is True and r.json()["sig_string"] is None
    assert r.json()["device_model"] == "T-L(BK)462" and r.json()["device_source"] == "topaz"

    got = client.get(f"{V1}/users/me/signature", params={"include_sig_string": "true"})
    assert got.json()["sig_string"] == SIGSTRING
    me = db_session._admin.id
    assert [e.event for e in _events(db_session, "user", me)] == ["captured", "sig_string_exported"]
    db_session.expire_all()
    assert svc.is_encrypted(db_session.get(User, me).signature_sig_string)

    # Replacing through PUT is a "replaced" event; through PATCH the block is cleared.
    client.put(f"{V1}/users/{me}/signature", json={"signature_data": IMAGE, "device_source": "web-pad"})
    assert _events(db_session, "user", me)[-1].event == "replaced"
    assert client.get(f"{V1}/users/{me}/signature").json()["has_sig_string"] is False

    client.put(f"{V1}/users/{me}/signature", json=TOPAZ)
    p = client.patch(f"{V1}/users/{me}", json={"signature_data": "data:image/png;base64,AAAA"})
    assert p.status_code == 200, p.text
    after = client.get(f"{V1}/users/{me}/signature").json()
    assert after["signature_data"] == "data:image/png;base64,AAAA"
    assert after["signature_len"] == len("data:image/png;base64,AAAA")
    assert after["has_sig_string"] is False and after["device_model"] is None


# ── tenancy + rules ──────────────────────────────────────────────────────────
def test_signatures_are_tenant_scoped_through_the_patient(client, db_session):
    other = Tenant(name="Elsewhere", code="else", is_active=True)
    db_session.add(other)
    db_session.commit()
    foreign = Patient(tenant_id=other.id, first_name="X", last_name="Y", chart_no="F-1", is_active=True)
    db_session.add(foreign)
    db_session.commit()
    row = PatientSignature(patient_id=foreign.id, signature_data=IMAGE, is_active=True)
    db_session.add(row)
    db_session.commit()
    assert client.get(f"{V1}/patient-signatures/{row.id}").status_code == 404
    assert client.get(f"{V1}/patient-signatures/{row.id}/sig-string").status_code == 404
    assert client.post(f"{V1}/patient-signatures",
                       json={"patient_id": foreign.id, "signature_data": IMAGE}).status_code == 404


def test_signature_capture_rules_published(client):
    r = client.get(f"{V1}/metadata/signature-capture")
    assert r.status_code == 200
    body = r.json()
    assert body["device_sources"] == ["topaz", "web-pad", "0", "2"]
    assert "topaz" in body["signature_methods"]
    assert body["min_point_count"] == 2
    assert body["sig_string_encrypted_at_rest"] is True
    assert body["canonical_user_signature_write"] == "PUT /users/{id}/signature"


# ── legacy rows ──────────────────────────────────────────────────────────────
def test_legacy_sigstring_rows_are_reported_and_migrated(client, db_session, patient):
    legacy = PatientSignature(patient_id=patient.id, signature_data=SIGSTRING,
                              signature_len=len(SIGSTRING), device_source="0", is_active=True)
    db_session.add(legacy)
    db_session.commit()
    got = client.get(f"{V1}/patient-signatures/{legacy.id}").json()
    assert got["has_image"] is False and got["legacy_sig_string_in_image"] is True

    from scripts.migrate_legacy_sigstrings import _migrate_patient_signatures

    dry = _migrate_patient_signatures(db_session, tenant_id=db_session._tenant_id, apply=False)
    assert dry["sigstring_moved"] == 1 and dry["legacy_source"] == 1
    db_session.expire_all()
    assert db_session.get(PatientSignature, legacy.id).signature_data == SIGSTRING

    stats = _migrate_patient_signatures(db_session, tenant_id=db_session._tenant_id, apply=True)
    assert stats["sigstring_moved"] == 1
    db_session.expire_all()
    row = db_session.get(PatientSignature, legacy.id)
    assert row.signature_data is None and row.sig_format == "topaz_sigstring_v1"
    assert svc.decrypt_sig_string(row.sig_string) == SIGSTRING
    got = client.get(f"{V1}/patient-signatures/{legacy.id}").json()
    assert got["has_sig_string"] is True and got["has_image"] is False
    assert got["device_source"] == "0"  # the legacy marker is kept
    # Idempotent.
    assert _migrate_patient_signatures(db_session, tenant_id=db_session._tenant_id, apply=True)["scanned"] == 0
