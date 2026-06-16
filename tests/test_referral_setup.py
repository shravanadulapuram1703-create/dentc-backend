"""Referral Setup tests — dev-report gaps 1-5."""

from __future__ import annotations

from app.db.models import Referral, ReferralDemogDetail, ReferralDemogHeader
from scripts.seed_account_definitions import seed_for_tenant


def test_referral_info_fields_roundtrip(client, db_session):
    # Gaps 1-4: e_referral_id / practice_name / contact_name / cost round-trip.
    c = client.post("/api/v1/referrals", json={
        "first_name": "Jane", "last_name": "Doe", "referral_type": "1",
        "e_referral_id": "ERX-9", "practice_name": "Smile Dental",
        "contact_name": "Front Desk", "cost": "125.50",
    })
    assert c.status_code == 201, c.text
    rid = c.json()["id"]
    g = client.get(f"/api/v1/referrals/{rid}").json()
    assert g["e_referral_id"] == "ERX-9"
    assert g["practice_name"] == "Smile Dental"
    assert g["contact_name"] == "Front Desk"
    assert float(g["cost"]) == 125.50


def test_referral_direction_and_type_filters(client, db_session):
    # Left-rail SEARCH ON (referral_type) + TYPE (reason_code) server filters.
    db_session.add_all([
        Referral(tenant_id=db_session._tenant_id, first_name="By", referral_type="0", reason_code="R003"),
        Referral(tenant_id=db_session._tenant_id, first_name="To", referral_type="1", reason_code="RC01"),
    ])
    db_session.commit()
    by = client.get("/api/v1/referrals", params={"referral_type": "0"}).json()
    assert {r["first_name"] for r in by["items"]} == {"By"}
    typed = client.get("/api/v1/referrals", params={"reason_code": "RC01"}).json()
    assert {r["first_name"] for r in typed["items"]} == {"To"}


def test_referral_direction_definitions_seeded(client, db_session):
    # referral_type domain exposed as a /definitions enum (not hardcoded in the FE).
    seed_for_tenant(db_session, db_session._tenant_id)
    d = client.get("/api/v1/definitions", params={"group_code": "referral_direction"}).json()
    by_code = {x["key1"]: x["description"] for x in d["items"]}
    assert by_code == {"0": "Referred By", "1": "Referred To"}


def test_referral_demographics_feed(client, db_session):
    # Gap 5: demographics feed exists (now tagged Patients) — header catalog + per-referral values.
    ref = Referral(tenant_id=db_session._tenant_id, first_name="Demo")
    header = ReferralDemogHeader(tenant_id=db_session._tenant_id, description="Specialty Mix")
    db_session.add_all([ref, header])
    db_session.commit()
    db_session.refresh(ref)
    db_session.refresh(header)
    db_session.add(ReferralDemogDetail(
        tenant_id=db_session._tenant_id, referral_id=ref.id,
        demog_header_id=header.id, data="{\"perio\": 40}",
    ))
    db_session.commit()

    headers = client.get("/api/v1/referral-demog-headers").json()
    assert any(h["description"] == "Specialty Mix" for h in headers["items"])
    details = client.get("/api/v1/referral-demog-details", params={"referral_id": ref.id}).json()
    assert len(details["items"]) == 1
    assert details["items"][0]["demog_header_id"] == header.id
