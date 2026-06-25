"""Progress-notes backend-gap tests (progress-notes dev-report PN-1..7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import hash_password
from app.db.models import Patient, ProgressNote, User

PREFIX = "/api/v1"
PWD = "test1234"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Note", last_name="Taker",
                chart_no="PN-1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def provider(db_session) -> User:
    u = User(tenant_id=db_session._tenant_id, email="dr@test.local", username="drwho",
             password_hash=hash_password(PWD), first_name="Doctor", last_name="Who",
             role="provider", is_active=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _make_note(client, patient_id: int, **extra) -> dict:
    body = {"patient_id": patient_id, "notes": "initial", **extra}
    r = client.post(f"{PREFIX}/progress-notes", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── PN-1: per-user signature store ───────────────────────────────────────────
def test_my_signature_round_trip(client, db_session):
    missing = client.get(f"{PREFIX}/users/me/signature")
    assert missing.status_code == 404  # nothing on file yet

    saved = client.put(f"{PREFIX}/users/me/signature",
                       json={"signature_data": "data:image/png;base64,AAAA", "signature_len": 42})
    assert saved.status_code == 200, saved.text
    assert saved.json()["user_id"] == db_session._admin.id
    assert saved.json()["signature_len"] == 42

    got = client.get(f"{PREFIX}/users/me/signature")
    assert got.status_code == 200
    assert got.json()["signature_data"] == "data:image/png;base64,AAAA"
    assert got.json()["updated_at"] is not None


# ── PN-2: sign as caller / verified provider ─────────────────────────────────
def test_sign_as_caller(client, patient, db_session):
    note = _make_note(client, patient.id)
    r = client.post(f"{PREFIX}/progress-notes/{note['id']}/sign")
    assert r.status_code == 200, r.text
    assert r.json()["signed_by"] == db_session._admin.id
    assert r.json()["signed_at"] is not None


def test_sign_as_provider_with_credentials(client, patient, provider):
    note = _make_note(client, patient.id)
    r = client.post(f"{PREFIX}/progress-notes/{note['id']}/sign",
                    json={"username": "drwho", "password": PWD})
    assert r.status_code == 200, r.text
    assert r.json()["signed_by"] == provider.id
    assert r.json()["signed_by_name"] == "Doctor Who"


def test_sign_bad_credentials_401(client, patient, provider):
    note = _make_note(client, patient.id)
    r = client.post(f"{PREFIX}/progress-notes/{note['id']}/sign",
                    json={"username": "drwho", "password": "wrong"})
    assert r.status_code == 401


def test_sign_incomplete_credentials_422(client, patient):
    note = _make_note(client, patient.id)
    r = client.post(f"{PREFIX}/progress-notes/{note['id']}/sign",
                    json={"username": "drwho"})
    assert r.status_code == 422


# ── PN-3: per-note attachments ───────────────────────────────────────────────
def test_attachment_lifecycle(client, patient):
    note = _make_note(client, patient.id)
    nid = note["id"]

    up = client.post(f"{PREFIX}/progress-notes/{nid}/attachments",
                     files={"file": ("scan.pdf", b"%PDF-1.4 fake", "application/pdf")},
                     data={"description": "x-ray"})
    assert up.status_code == 201, up.text
    att_id = up.json()["id"]
    assert up.json()["file_name"] == "scan.pdf"

    listed = client.get(f"{PREFIX}/progress-notes/{nid}/attachments")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # attachment_count surfaces on the note read (PN-3 📎 indicator)
    read = client.get(f"{PREFIX}/progress-notes/{nid}")
    assert read.json()["attachment_count"] == 1

    # not visible on a different note
    other = _make_note(client, patient.id)
    assert client.get(f"{PREFIX}/progress-notes/{other['id']}/attachments").json() == []

    deleted = client.delete(f"{PREFIX}/progress-notes/{nid}/attachments/{att_id}")
    assert deleted.status_code == 204
    assert client.get(f"{PREFIX}/progress-notes/{nid}/attachments").json() == []
    assert client.get(f"{PREFIX}/progress-notes/{nid}").json()["attachment_count"] == 0


# ── PN-4: strike-off audit ───────────────────────────────────────────────────
def test_strike_off_stamps_and_restore_clears(client, patient, db_session):
    note = _make_note(client, patient.id)
    nid = note["id"]

    off = client.patch(f"{PREFIX}/progress-notes/{nid}", json={"is_struck_off": True})
    assert off.status_code == 200, off.text
    assert off.json()["is_struck_off"] is True
    assert off.json()["struck_off_at"] is not None
    assert off.json()["struck_off_by"] == db_session._admin.id

    restored = client.patch(f"{PREFIX}/progress-notes/{nid}", json={"is_struck_off": False})
    assert restored.status_code == 200
    assert restored.json()["struck_off_at"] is None
    assert restored.json()["struck_off_by"] is None


# ── PN-5: resolved actor names ───────────────────────────────────────────────
def test_read_exposes_actor_names(client, patient, db_session):
    note = _make_note(client, patient.id)
    client.post(f"{PREFIX}/progress-notes/{note['id']}/sign")
    read = client.get(f"{PREFIX}/progress-notes/{note['id']}").json()
    assert read["created_by_name"] == db_session._admin.username
    assert read["signed_by_name"] == db_session._admin.username


# ── PN-6: macro categories ───────────────────────────────────────────────────
def test_macro_categories(client, db_session):
    for name, cat in [("M1", "Exam"), ("M2", "Exam"), ("M3", "Hygiene")]:
        client.post(f"{PREFIX}/note-macros", json={"name": name, "content": "...", "category": cat})
    r = client.get(f"{PREFIX}/note-macros/categories")
    assert r.status_code == 200, r.text
    by_cat = {c["category"]: c["macro_count"] for c in r.json()}
    assert by_cat == {"Exam": 2, "Hygiene": 1}


# ── PN-7: server-side lock enforcement ───────────────────────────────────────
def test_signed_note_rejects_text_edit(client, patient):
    note = _make_note(client, patient.id)
    nid = note["id"]
    client.post(f"{PREFIX}/progress-notes/{nid}/sign")

    blocked = client.patch(f"{PREFIX}/progress-notes/{nid}", json={"notes": "tampered"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "conflict"

    # strike-off is still permitted on a locked note
    ok = client.patch(f"{PREFIX}/progress-notes/{nid}", json={"is_struck_off": True})
    assert ok.status_code == 200


def test_prior_day_note_locked(client, patient, db_session):
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    note = ProgressNote(patient_id=patient.id, notes="old", created_at=yesterday,
                        created_by=db_session._admin.id)
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)

    read = client.get(f"{PREFIX}/progress-notes/{note.id}").json()
    assert read["is_locked"] is True

    blocked = client.patch(f"{PREFIX}/progress-notes/{note.id}", json={"notes": "edit"})
    assert blocked.status_code == 409
