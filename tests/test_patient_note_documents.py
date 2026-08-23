"""Patient Notes document upload / download (NOTE-DOC-1..5).

Backs ``docs/patient_note_documents_backend_devreport.md``. The binary store was
already correct; what these tests pin is everything that was missing around it:

* **NOTE-DOC-1** a note can reference an uploaded document, and only one that
  belongs to the same patient — the whole point is that re-opening the note finds
  the file, and a mis-pointed id would surface another patient's file in this
  patient's chart.
* **NOTE-DOC-3** no route serves a patient document without authentication. The
  public ``/uploads/**`` mount is gone, so this asserts on the *absence* of a
  route as much as on the presence of one.
* **NOTE-DOC-5** the size cap and content-type allow-list are enforced by the
  server, not just by the file picker, and are published so both agree.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.config import settings
from app.db.models import Patient, PatientNote


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="John", last_name="Smith",
                dob=date(1980, 1, 1), is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def other_patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Jane", last_name="Doe",
                dob=date(1975, 3, 4), is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _upload(client, patient, name="scan.pdf", payload=b"%PDF-1.4 scan",
            content_type="application/pdf", document_type="CF"):
    r = client.post(
        "/api/v1/patient-documents",
        data={"patient_id": str(patient.id), "document_type": document_type},
        files={"file": (name, payload, content_type)},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── NOTE-DOC-1: the note ↔ document link ─────────────────────────────────────
def test_note_carries_the_uploaded_document_and_renders_a_link(client, patient):
    """The blocker: upload, save the note with the id, re-open, get the file back."""
    doc = _upload(client, patient, name="consent.pdf")

    note = client.post("/api/v1/patient-notes", json={
        "patient_id": patient.id, "note_type": "DOC", "notes": "Signed consent",
        "note_date": "2026-08-20", "document_id": doc["id"],
    })
    assert note.status_code == 201, note.text
    body = note.json()
    assert body["document_id"] == doc["id"]
    assert body["document"]["file_name"] == "consent.pdf"
    assert body["document"]["content_type"] == "application/pdf"
    assert body["document"]["file_size"] == len(b"%PDF-1.4 scan")

    # Re-opening the note finds the file, and the link actually downloads.
    reopened = client.get(f"/api/v1/patient-notes/{body['id']}").json()
    url = reopened["document"]["file_url"]
    assert url.endswith(f"/patient-documents/{doc['id']}/content")
    content = client.get(url)
    assert content.status_code == 200
    assert content.content == b"%PDF-1.4 scan"


def test_the_full_notes_flow_files_the_document_under_documents_notes(client, patient):
    """End to end, the way the Notes screen does it: upload with context=note,
    save the note with the returned id, re-open, download."""
    doc = client.post(
        "/api/v1/patient-documents",
        data={"patient_id": str(patient.id), "document_type": "CF", "context": "note"},
        files={"file": ("consent.pdf", b"%PDF-1.4 note file", "application/pdf")},
    ).json()
    assert doc["storage_path"].startswith("documents/notes/")

    note = client.post("/api/v1/patient-notes", json={
        "patient_id": patient.id, "note_type": "DOC", "notes": "Uploaded from Notes",
        "document_id": doc["id"],
    }).json()
    reopened = client.get(f"/api/v1/patient-notes/{note['id']}").json()
    got = client.get(reopened["document"]["file_url"])
    assert got.status_code == 200 and got.content == b"%PDF-1.4 note file"


def test_notes_list_embeds_the_document_without_a_per_row_fetch(client, patient):
    doc = _upload(client, patient)
    client.post("/api/v1/patient-notes", json={
        "patient_id": patient.id, "note_type": "DOC", "notes": "with file",
        "document_id": doc["id"],
    })
    client.post("/api/v1/patient-notes", json={
        "patient_id": patient.id, "note_type": "GEN", "notes": "plain note",
    })
    items = client.get(f"/api/v1/patient-notes?patient_id={patient.id}").json()["items"]
    by_notes = {i["notes"]: i for i in items}
    assert by_notes["with file"]["document"]["id"] == doc["id"]
    # A note type that carries no file reports null rather than an empty object.
    assert by_notes["plain note"]["document"] is None


def test_note_cannot_reference_another_patients_document(client, patient, other_patient):
    """A note is displayed inside one patient's chart; a mis-pointed id would put
    someone else's file there."""
    doc = _upload(client, other_patient)
    r = client.post("/api/v1/patient-notes", json={
        "patient_id": patient.id, "note_type": "DOC", "notes": "x", "document_id": doc["id"],
    })
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "document_patient_mismatch"


def test_note_cannot_reference_a_missing_or_deleted_document(client, patient):
    doc = _upload(client, patient)
    assert client.delete(f"/api/v1/patient-documents/{doc['id']}").status_code == 204
    for bad_id in (doc["id"], 999999):
        r = client.post("/api/v1/patient-notes", json={
            "patient_id": patient.id, "note_type": "DOC", "notes": "x", "document_id": bad_id,
        })
        assert r.status_code == 404, r.text


def test_patch_with_only_document_id_validates_against_the_stored_patient(
    client, patient, other_patient,
):
    """A PATCH carrying just the touched field must still reach the note's patient."""
    note = client.post("/api/v1/patient-notes", json={
        "patient_id": patient.id, "note_type": "DOC", "notes": "n",
    }).json()

    theirs = _upload(client, other_patient)
    bad = client.patch(f"/api/v1/patient-notes/{note['id']}", json={"document_id": theirs["id"]})
    assert bad.status_code == 422

    mine = _upload(client, patient)
    ok = client.patch(f"/api/v1/patient-notes/{note['id']}", json={"document_id": mine["id"]})
    assert ok.status_code == 200
    assert ok.json()["document"]["id"] == mine["id"]


def test_document_id_can_be_cleared(client, patient):
    doc = _upload(client, patient)
    note = client.post("/api/v1/patient-notes", json={
        "patient_id": patient.id, "note_type": "DOC", "notes": "n", "document_id": doc["id"],
    }).json()
    cleared = client.patch(f"/api/v1/patient-notes/{note['id']}", json={"document_id": None})
    assert cleared.status_code == 200
    assert cleared.json()["document_id"] is None and cleared.json()["document"] is None


def test_deleting_a_note_keeps_the_document(client, db_session, patient):
    """The documented answer to the dev report's cascade-vs-orphan question: the
    document is a patient-level record and survives; only the link goes."""
    doc = _upload(client, patient)
    note = client.post("/api/v1/patient-notes", json={
        "patient_id": patient.id, "note_type": "DOC", "notes": "n", "document_id": doc["id"],
    }).json()

    assert client.delete(f"/api/v1/patient-notes/{note['id']}").status_code == 204
    assert db_session.get(PatientNote, note["id"]).is_deleted is True
    assert client.get(f"/api/v1/patient-documents/{doc['id']}").status_code == 200
    assert client.get(f"/api/v1/patient-documents/{doc['id']}/content").status_code == 200


# ── NOTE-DOC-3: nothing serves a patient document unauthenticated ────────────
def test_patient_documents_are_not_reachable_through_the_public_uploads_route(client, patient):
    """The reported vulnerability: ``GET /uploads/patient_documents/...`` returned
    the file with no Authorization header at all. There is no such route now."""
    doc = _upload(client, patient)
    # Nothing in the response points at /uploads any more...
    assert not doc["file_url"].startswith("/uploads")
    assert doc["file_url"].endswith(f"/patient-documents/{doc['id']}/content")
    # ...and the path the reporter used is not routed.
    leaked = client.get(f"/uploads/{doc['storage_path']}")
    assert leaked.status_code == 404, leaked.text


def test_only_branding_subdirs_stay_publicly_mounted(client):
    """Logos must keep working — the fix is targeted, not a blanket unmount."""
    mounted = {r.name for r in client.app.routes if getattr(r, "name", "").startswith("uploads")}
    assert mounted == {f"uploads_{s}" for s in settings.UPLOAD_PUBLIC_SUBDIRS}
    assert "uploads" not in mounted
    assert not any("patient" in s for s in settings.UPLOAD_PUBLIC_SUBDIRS)


def test_progress_note_attachment_url_is_the_authenticated_route(client, db_session, patient):
    from app.db.models import ProgressNote

    # progress_notes carries no tenant_id — tenancy resolves through the patient.
    note = ProgressNote(patient_id=patient.id, note_date=date.today(), notes="chairside")
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)

    att = client.post(
        f"/api/v1/progress-notes/{note.id}/attachments",
        files={"file": ("photo.png", b"\x89PNG payload", "image/png")},
    )
    assert att.status_code == 201, att.text
    url = att.json()["file_url"]
    assert not url.startswith("/uploads")
    assert url.endswith(f"/progress-notes/{note.id}/attachments/{att.json()['id']}/content")
    got = client.get(url)
    assert got.status_code == 200 and got.content == b"\x89PNG payload"


# ── NOTE-DOC-5: server-side validation ───────────────────────────────────────
def test_upload_rejects_a_disallowed_type(client, patient):
    """The reporter uploaded ``text/plain`` and the API took it happily."""
    r = client.post(
        "/api/v1/patient-documents",
        data={"patient_id": str(patient.id)},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_file_type"


def test_upload_rejects_a_good_extension_with_a_disallowed_type(client, patient):
    r = client.post(
        "/api/v1/patient-documents",
        data={"patient_id": str(patient.id)},
        files={"file": ("payload.pdf", b"%PDF", "text/html")},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_content_type"


def test_upload_accepts_an_octet_stream_scan(client, patient):
    """Scanners and older browsers send octet-stream for a real PDF; rejecting
    those would break Document (Scan) for no security gain."""
    r = client.post(
        "/api/v1/patient-documents",
        data={"patient_id": str(patient.id)},
        files={"file": ("scan.pdf", b"%PDF-1.4", "application/octet-stream")},
    )
    assert r.status_code == 201, r.text


def test_upload_rejects_a_file_over_the_cap(client, patient, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_MAX_BYTES", 1024)
    r = client.post(
        "/api/v1/patient-documents",
        data={"patient_id": str(patient.id)},
        files={"file": ("big.pdf", b"x" * 2048, "application/pdf")},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "file_too_large"
    # The message names the actual limit so the UI can show it verbatim.
    assert "MB" in r.json()["error"]["message"]


def test_limits_endpoint_publishes_what_the_server_enforces(client):
    body = client.get("/api/v1/patient-documents/limits").json()
    assert body["max_bytes"] == settings.DOCUMENT_MAX_BYTES
    assert body["allowed_content_types"] == settings.DOCUMENT_ALLOWED_TYPES
    assert ".pdf" in body["allowed_extensions"] and ".png" in body["allowed_extensions"]
    # The picker also learns which context values the upload accepts, rather than
    # hardcoding "note" and finding out at runtime that it was rejected.
    assert body["allowed_contexts"] == ["note"]


# ── NOTE-DOC-4: the document_type vocabulary ─────────────────────────────────
def test_document_type_definitions_group_is_seeded(client, db_session):
    from scripts.seed_account_definitions import seed_for_tenant

    seed_for_tenant(db_session, db_session._tenant_id)
    db_session.commit()
    items = client.get("/api/v1/definitions?group_code=document_type").json()["items"]
    codes = {i["key1"]: i["description"] for i in items}
    assert codes["CF"] == "Consent Form"
    assert "OT" in codes


def test_cf_is_a_recognised_consent_type():
    """The Notes screen sends ``CF``. Outside a note it files with the practice's
    consents; *inside* a note the note context wins — pinned in
    ``test_document_storage.py::test_note_context_beats_the_consent_document_type``."""
    from app.services import document_store

    assert document_store.is_consent_type("CF") is True
    assert document_store.object_key(1, 42, "CF", "c.pdf").startswith(
        "documents/consent-forms/"
    )
