"""Insurance Setup tests (carriers & employers) — dev-report gaps INS-1..INS-8."""

from __future__ import annotations

import pytest

from app.db.models import (
    Employer,
    InsuranceCarrier,
    InsurancePlan,
    InsuranceSubscriber,
)
from scripts.seed_account_definitions import seed_for_tenant


def _carrier(db_session, name: str, carrier_type: str | None) -> int:
    c = InsuranceCarrier(tenant_id=db_session._tenant_id, name=name, carrier_type=carrier_type)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c.id


def test_carrier_type_filter_and_is_dental(client, db_session):
    # INS-1 + INS-2: server-side carrier_type filter and typed is_dental discriminator.
    _carrier(db_session, "Delta Dental", "True")
    _carrier(db_session, "Aetna Medical", "False")

    dental = client.get("/api/v1/insurance-carriers", params={"carrier_type": "True"}).json()
    assert {c["name"] for c in dental["items"]} == {"Delta Dental"}
    assert dental["items"][0]["is_dental"] is True

    medical = client.get("/api/v1/insurance-carriers", params={"carrier_type": "False"}).json()
    assert {c["name"] for c in medical["items"]} == {"Aetna Medical"}
    assert medical["items"][0]["is_dental"] is False
    # meta.total gives a per-type count without scanning the whole list.
    assert medical["meta"]["total"] == 1


def test_carrier_capability_and_contact_fields(client, db_session):
    # INS-3 + INS-4: capability flags, insurance_type, fax, email round-trip.
    cid = _carrier(db_session, "MedCo", "False")
    r = client.patch(f"/api/v1/insurance-carriers/{cid}", json={
        "fax": "555-1212", "email": "claims@medco.test",
        "supports_realtime_eligibility": True, "supports_claim_status": False,
        "supports_dxc_attachment": True, "insurance_type": "PPO",
    })
    assert r.status_code == 200
    g = client.get(f"/api/v1/insurance-carriers/{cid}").json()
    assert g["fax"] == "555-1212"
    assert g["email"] == "claims@medco.test"
    assert g["supports_realtime_eligibility"] is True
    assert g["supports_claim_status"] is False
    assert g["supports_dxc_attachment"] is True
    assert g["insurance_type"] == "PPO"


def test_carrier_update_stamps_updated_by(client, db_session):
    # INS-6: server-maintained modified actor on PATCH.
    cid = _carrier(db_session, "AuditCo", "True")
    r = client.patch(f"/api/v1/insurance-carriers/{cid}", json={"phone": "555-0000"})
    assert r.status_code == 200
    body = r.json()
    assert body["updated_by"] == db_session._admin.id
    assert body["updated_at"] is not None


def test_employer_extra_fields_and_audit(client, db_session):
    # INS-5 + INS-6: salesrep/contact_person + created_by/updated_by audit.
    c = client.post("/api/v1/employers", json={
        "name": "Acme Corp", "salesrep": "Jane Rep", "contact_person": "Bob HR",
    })
    assert c.status_code == 201
    created = c.json()
    eid = created["id"]
    assert created["salesrep"] == "Jane Rep"
    assert created["contact_person"] == "Bob HR"
    assert created["created_by"] == db_session._admin.id

    u = client.patch(f"/api/v1/employers/{eid}", json={"city": "Springfield"})
    assert u.status_code == 200
    assert u.json()["updated_by"] == db_session._admin.id
    assert u.json()["updated_at"] is not None


def test_pagination_stable_tiebreaker(client, db_session):
    # INS-8: non-unique sort column must not drop/duplicate rows across pages.
    ids = [_carrier(db_session, "SameName", "True") for _ in range(5)]
    seen: list[int] = []
    for page in range(1, 4):  # 5 rows, size 2 -> 3 pages
        body = client.get("/api/v1/insurance-carriers", params={
            "sort": "name", "order": "asc", "page": page, "size": 2,
        }).json()
        seen.extend(c["id"] for c in body["items"])
    # All five distinct ids returned exactly once, in ascending id order.
    assert seen == sorted(ids)
    assert len(seen) == len(set(seen)) == 5


def test_plans_search_by_carrier_and_employer_name(client, db_session):
    # INS-9: a plan (no name, stores only ids) is findable by carrier/employer name.
    cigna_id = _carrier(db_session, "Cigna Dental", "True")
    other_id = _carrier(db_session, "Aetna", "True")
    emp = Employer(tenant_id=db_session._tenant_id, name="Acme Industries")
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=cigna_id,
                         employer_id=emp.id, group_number="GRP-1")
    decoy = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=other_id, group_number="GRP-2")
    db_session.add_all([plan, decoy])
    db_session.commit()

    by_carrier = client.get("/api/v1/insurance-plans", params={"search": "Cigna"}).json()
    assert [p["group_number"] for p in by_carrier["items"]] == ["GRP-1"]

    by_employer = client.get("/api/v1/insurance-plans", params={"search": "Acme"}).json()
    assert [p["group_number"] for p in by_employer["items"]] == ["GRP-1"]

    # Own-column search still works (group_number).
    by_group = client.get("/api/v1/insurance-plans", params={"search": "GRP-2"}).json()
    assert [p["group_number"] for p in by_group["items"]] == ["GRP-2"]


def test_coverage_code_definitions_seeded(client, db_session):
    # INS-10: coverage_type / coverage_category labels exposed via /definitions.
    seed_for_tenant(db_session, db_session._tenant_id)

    cats = client.get("/api/v1/definitions", params={"group_code": "coverage_category"}).json()
    by_code = {d["key1"]: d["description"] for d in cats["items"]}
    assert by_code["1"] == "Diagnostic"
    assert by_code["11"] == "Orthodontics"
    assert by_code["0"] == "Other"

    types = client.get("/api/v1/definitions", params={"group_code": "coverage_type"}).json()
    type_map = {d["key1"]: d["description"] for d in types["items"]}
    assert type_map["I"] == "Indemnity"


def _subscriber(db_session, plan_id: int, elig_status, member: str, active: bool = True):
    s = InsuranceSubscriber(tenant_id=db_session._tenant_id, ins_plan_id=plan_id,
                            sub_member_id=member, elig_status=elig_status, is_active=active)
    db_session.add(s)
    db_session.commit()


def test_subscriber_elig_status_filter_and_summary(client, db_session):
    # INS-11: elig_status list filter + cheap verification-status summary.
    cid = _carrier(db_session, "Cigna", "True")
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=cid, group_number="G")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    _subscriber(db_session, plan.id, "unknown", "M1")
    _subscriber(db_session, plan.id, None, "M2")
    _subscriber(db_session, plan.id, "verified", "M3")
    _subscriber(db_session, plan.id, "pending", "M4")
    _subscriber(db_session, plan.id, "verified", "M5", active=False)  # inactive → excluded

    # Filter: count one status cheaply via meta.total.
    pending = client.get("/api/v1/insurance-subscribers", params={"elig_status": "pending"}).json()
    assert pending["meta"]["total"] == 1

    # Summary: GROUP BY, NULL/blank → "unknown"; pending = active total − verified.
    s = client.get("/api/v1/reports/insurance-verification-summary").json()
    assert s["total"] == 4  # inactive excluded
    assert s["by_status"]["unknown"] == 2  # explicit "unknown" + NULL
    assert s["by_status"]["verified"] == 1  # inactive verified not counted
    assert s["verified"] == 1
    assert s["pending"] == 3
