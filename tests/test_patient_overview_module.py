"""Patient Overview backend gaps (docs/patients/patient_overview_backend_devreport.md, PO-1..12)."""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app.db.models import (
    Appointment,
    Office,
    Patient,
    PatientRecall,
    Provider,
    Referral,
    ResponsibleParty,
)


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="OFF-PO", name="PO Office", short_id="PO")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    p = Provider(id="PRV-PO", tenant_id=db_session._tenant_id, office_id=office.id, name="Dr PO")
    db_session.add(p)
    db_session.commit()
    return p


def _appt(db_session, office, provider, patient_id, appt_id, d, archived=False):
    db_session.add(Appointment(
        id=appt_id, patient_id=patient_id, provider_id=provider.id, office_id=office.id,
        date=d, start_time=time(9, 0), end_time=time(9, 30), duration=30, is_archived=archived,
    ))
    db_session.commit()


# ── PO-5: is_archived filter on /appointments ─────────────────────────────────
def test_appointments_is_archived_filter(client, db_session, office, provider):
    p = Patient(tenant_id=db_session._tenant_id, first_name="Appt", last_name="Filter")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    _appt(db_session, office, provider, p.id, "APPT-PO-A", date.today())
    _appt(db_session, office, provider, p.id, "APPT-PO-B", date.today(), archived=True)

    active = client.get(f"/api/v1/appointments?patient_id={p.id}&is_archived=false").json()
    assert active["meta"]["total"] == 1
    archived = client.get(f"/api/v1/appointments?patient_id={p.id}&is_archived=true").json()
    assert archived["meta"]["total"] == 1


# ── PO-3: roster accepts raw string id + extended columns ─────────────────────
def test_roster_raw_string_and_extended(client, db_session, office, provider):
    tid = db_session._tenant_id
    for i in (1, 2):
        pt = Patient(tenant_id=tid, first_name=f"Mem{i}", last_name="Legacy",
                     responsible_party_id="LEGACY-9999", home_office_id=office.id, dob=date(1990, 1, 1))
        db_session.add(pt)
    db_session.commit()
    member = db_session.execute(
        __import__("sqlalchemy").select(Patient).where(Patient.responsible_party_id == "LEGACY-9999")
    ).scalars().first()
    _appt(db_session, office, provider, member.id, "APPT-PO-F", date.today() + timedelta(days=7))

    # No 404 for a migrated (non-numeric-RP) account, and rows carry the new block.
    r = client.get("/api/v1/responsible-parties/LEGACY-9999/patients")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 2
    row = next(x for x in rows if x["patient_id"] == member.id)
    for key in ("aging", "next_visit", "last_visit", "scheduled_recall",
                "estimated_patient", "estimated_insurance", "is_active"):
        assert key in row
    assert row["next_visit"] == (date.today() + timedelta(days=7)).isoformat()


# ── PO-4: family appointments ─────────────────────────────────────────────────
def test_family_appointments(client, db_session, office, provider):
    tid = db_session._tenant_id
    p = Patient(tenant_id=tid, first_name="Fam", last_name="Member", responsible_party_id="ACC-1")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    _appt(db_session, office, provider, p.id, "APPT-PO-FAM", date.today() + timedelta(days=3))

    r = client.get("/api/v1/appointments/family?responsible_party_id=ACC-1&upcoming_only=true")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1


# ── PO-1: overview aggregate ──────────────────────────────────────────────────
def test_patient_overview_aggregate(client, db_session, office, provider):
    tid = db_session._tenant_id
    p = Patient(tenant_id=tid, first_name="Over", last_name="View", home_office_id=office.id,
                responsible_party_id="ACC-OV")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    p.responsible_party_id = str(p.id)  # self-linked account
    db_session.add(PatientRecall(patient_id=p.id, recall_type="prophy", due_date=date(2027, 1, 1)))
    _appt(db_session, office, provider, p.id, "APPT-PO-OV", date.today() + timedelta(days=5))
    db_session.commit()

    r = client.get(f"/api/v1/patients/{p.id}/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("patient", "balance", "visit", "responsible_party", "account_members",
                "appointments", "recalls", "insurance", "referrals", "contracts"):
        assert key in body
    assert body["patient"]["home_office_name"] == "PO Office"
    assert body["visit"]["next_visit"] == (date.today() + timedelta(days=5)).isoformat()
    assert len(body["appointments"]) == 1 and len(body["recalls"]) == 1
    assert len(body["account_members"]) == 1  # self-linked


# ── PO-2b / PO-11: responsible-party legacy_id + home_office_id ───────────────
def test_responsible_party_legacy_and_office_filters(client, db_session, office):
    rp = ResponsibleParty(tenant_id=db_session._tenant_id, first_name="Guar", last_name="Antor",
                          legacy_id="13002496", home_office_id=office.id)
    db_session.add(rp)
    db_session.commit()
    by_legacy = client.get("/api/v1/responsible-parties?legacy_id=13002496").json()
    assert by_legacy["meta"]["total"] == 1
    assert by_legacy["items"][0]["home_office_id"] == office.id


# ── PO-6: referrals legacy_id filter ─────────────────────────────────────────
def test_referral_legacy_id_filter(client, db_session):
    db_session.add(Referral(tenant_id=db_session._tenant_id, legacy_id="13000412",
                            referral_type="1", last_name="Practice"))
    db_session.commit()
    got = client.get("/api/v1/referrals?legacy_id=13000412").json()
    assert got["meta"]["total"] == 1


# ── PO-10: patient photo_document_id ─────────────────────────────────────────
def test_patient_photo_document_id(client, db_session):
    p = Patient(tenant_id=db_session._tenant_id, first_name="Photo", last_name="Pat")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    upd = client.patch(f"/api/v1/patients/{p.id}", json={"photo_document_id": 12345})
    assert upd.status_code == 200, upd.text
    assert upd.json()["photo_document_id"] == 12345


# ── PO-12: insurance-plans alias ─────────────────────────────────────────────
def test_insurance_plans_alias(client, db_session):
    p = Patient(tenant_id=db_session._tenant_id, first_name="Alias", last_name="Pat")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    assert client.get(f"/api/v1/patients/{p.id}/insurance-plans").status_code == 200
    assert client.get(f"/api/v1/patients/{p.id}/account-plans").status_code == 200
