"""KAN-108 — duplicate-patient detection on Quick Save.

Quick Save posts straight to ``POST /patients/register``, which used to create
the row unconditionally. The guard has to hold server-side, and the matcher has
to see the contact details Quick Save actually collects.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import Patient


@pytest.fixture
def existing(db_session) -> Patient:
    p = Patient(
        tenant_id=db_session._tenant_id, first_name="Maria", last_name="Delgado",
        dob=date(1984, 3, 11), phone="(555) 240-8891", email="Maria.Delgado@example.com",
        ssn="222-33-4444", chart_no="CH-DUP1", is_active=True,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _register(client, patient: dict, **extra):
    return client.post("/api/v1/patients/register", json={"patient": patient, **extra})


# ── matcher ──────────────────────────────────────────────────────────────────
def test_check_duplicate_matches_on_phone_despite_name_spelling(client, existing):
    """The repeat-patient case a name-only matcher misses entirely."""
    r = client.post("/api/v1/patients/check-duplicate",
                    json={"first_name": "Marai", "last_name": "Delgado",
                          "phone": "555-240-8891"})
    assert r.status_code == 200, r.text
    cand = next(c for c in r.json()["candidates"] if c["id"] == existing.id)
    # Phone stored as "(555) 240-8891" — separators must not defeat the compare.
    assert "phone" in cand["match_on"]


def test_check_duplicate_matches_on_email_case_insensitively(client, existing):
    r = client.post("/api/v1/patients/check-duplicate",
                    json={"email": "maria.delgado@EXAMPLE.com"})
    assert r.status_code == 200, r.text
    cand = next(c for c in r.json()["candidates"] if c["id"] == existing.id)
    assert "email" in cand["match_on"]


def test_shared_surname_alone_is_not_strong(client, existing):
    """A household sharing a surname must stay creatable."""
    r = client.post("/api/v1/patients/check-duplicate",
                    json={"first_name": "Tomas", "last_name": "Delgado"})
    assert r.status_code == 200, r.text
    for c in r.json()["candidates"]:
        assert c["is_strong"] is False


def test_full_name_plus_dob_is_strong(client, existing):
    r = client.post("/api/v1/patients/check-duplicate",
                    json={"first_name": "Maria", "last_name": "Delgado",
                          "dob": "1984-03-11"})
    cand = next(c for c in r.json()["candidates"] if c["id"] == existing.id)
    assert cand["is_strong"] is True


# ── register guard ───────────────────────────────────────────────────────────
def test_quick_save_refuses_duplicate_and_returns_candidates(client, existing):
    r = _register(client, {
        "first_name": "Maria", "last_name": "Delgado", "dob": "1984-03-11",
        "phone": "555-240-8891",
    })
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "duplicate_patient"
    assert [c["id"] for c in err["details"]["candidates"]] == [existing.id]


def test_force_create_overrides_after_user_confirms(client, existing):
    r = _register(client, {
        "first_name": "Maria", "last_name": "Delgado", "dob": "1984-03-11",
        "phone": "555-240-8891",
    }, force_create=True)
    assert r.status_code == 201, r.text
    assert r.json()["patient_id"] != existing.id


def test_genuinely_new_patient_still_registers(client, existing):
    r = _register(client, {
        "first_name": "Priya", "last_name": "Raman", "dob": "1990-07-02",
        "phone": "555-777-0000",
    })
    assert r.status_code == 201, r.text


def test_ssn_match_alone_blocks(client, existing):
    """SSN is unique per person — it needs no corroboration."""
    r = _register(client, {"first_name": "M", "last_name": "D", "ssn": "222-33-4444"})
    assert r.status_code == 409, r.text
