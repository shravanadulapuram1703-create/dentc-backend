"""Persistent default-patient selection tests (dev-report PDP-1..4)."""

from __future__ import annotations

import pytest

from app.core.security import hash_password
from app.db.models import Patient, Tenant, User

PREFIX = "/api/v1"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Def", last_name="Pat", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


# ── PDP-1/2: round-trip ───────────────────────────────────────────────────────
def test_last_patient_round_trip(client, patient):
    # none initially
    assert client.get(f"{PREFIX}/users/me/last-patient").json()["patient_id"] is None

    saved = client.put(f"{PREFIX}/users/me/last-patient", json={"patient_id": patient.id})
    assert saved.status_code == 200, saved.text
    assert saved.json()["patient_id"] == patient.id

    assert client.get(f"{PREFIX}/users/me/last-patient").json()["patient_id"] == patient.id


def test_last_patient_in_me_full(client, patient):
    client.put(f"{PREFIX}/users/me/last-patient", json={"patient_id": patient.id})
    me = client.get(f"{PREFIX}/auth/me-full")
    assert me.status_code == 200, me.text
    assert me.json()["last_patient_id"] == patient.id


def test_clear_last_patient(client, patient):
    client.put(f"{PREFIX}/users/me/last-patient", json={"patient_id": patient.id})
    # clear via null body
    assert client.put(f"{PREFIX}/users/me/last-patient", json={"patient_id": None}).json()["patient_id"] is None
    # set again, clear via DELETE
    client.put(f"{PREFIX}/users/me/last-patient", json={"patient_id": patient.id})
    assert client.delete(f"{PREFIX}/users/me/last-patient").status_code == 204
    assert client.get(f"{PREFIX}/users/me/last-patient").json()["patient_id"] is None


# ── PDP-4: validation / isolation ─────────────────────────────────────────────
def test_set_unknown_patient_404(client):
    assert client.put(f"{PREFIX}/users/me/last-patient", json={"patient_id": 999999}).status_code == 404


def test_cross_tenant_patient_rejected(client, db_session):
    other_tenant = Tenant(name="Other", code="other", is_active=True)
    db_session.add(other_tenant)
    db_session.commit()
    db_session.refresh(other_tenant)
    foreign = Patient(tenant_id=other_tenant.id, first_name="X", last_name="Y", is_active=True)
    db_session.add(foreign)
    db_session.commit()
    db_session.refresh(foreign)

    r = client.put(f"{PREFIX}/users/me/last-patient", json={"patient_id": foreign.id})
    assert r.status_code == 404  # not leaked across tenants


def test_archived_patient_reads_as_null(client, db_session, patient):
    client.put(f"{PREFIX}/users/me/last-patient", json={"patient_id": patient.id})
    # patient becomes inactive (soft-deleted)
    patient.is_active = False
    db_session.commit()

    # read returns null and clears the stale reference
    assert client.get(f"{PREFIX}/users/me/last-patient").json()["patient_id"] is None
    assert db_session.get(User, db_session._admin.id).last_patient_id is None
