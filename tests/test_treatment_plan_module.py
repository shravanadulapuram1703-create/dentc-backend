"""Treatment-plan backend-gap tests (treatment-plan dev-report PLAN-1..14)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.models import (
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    Patient,
    PatientInsurance,
)

PREFIX = "/api/v1"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Plan", last_name="Ner",
                chart_no="TP-PAT", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def proc(client):
    r = client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D1110", "description": "Prophylaxis", "category": "Preventive", "default_fee": 200,
    })
    assert r.status_code == 201, r.text
    return "D1110"


def _plan(client, patient_id: int, pid: str = "TP-A") -> str:
    r = client.post(f"{PREFIX}/treatment-plans",
                    json={"id": pid, "patient_id": patient_id, "name": "Plan A"})
    assert r.status_code == 201, r.text
    return pid


def _item(client, plan_id: str, proc: str, item_id: str, **extra) -> dict:
    body = {"id": item_id, "plan_id": plan_id, "procedure_code": proc, "fee": 200, **extra}
    r = client.post(f"{PREFIX}/treatment-plan-items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── PLAN-1/2/5/10: new item fields persist ───────────────────────────────────
def test_new_item_fields_persist(client, patient, proc):
    plan = _plan(client, patient.id)
    item = _item(client, plan, proc, "I-1", phase_id=2, discount=15.5,
                 provider_id=None, diagnosed_date="2026-06-01",
                 start_date="2026-07-01", end_date="2026-08-01", status="accepted")
    assert item["phase_id"] == 2
    assert float(item["discount"]) == 15.5
    assert item["diagnosed_date"] == "2026-06-01"
    assert item["start_date"] == "2026-07-01"
    assert item["status"] == "accepted"
    assert item["is_archived"] is False


# ── status enum (LOW) ─────────────────────────────────────────────────────────
def test_invalid_status_rejected(client, patient, proc):
    plan = _plan(client, patient.id)
    r = client.post(f"{PREFIX}/treatment-plan-items", json={
        "id": "I-bad", "plan_id": plan, "procedure_code": proc, "fee": 100, "status": "bogus",
    })
    assert r.status_code == 422


# ── PLAN-14: soft-delete + filter ─────────────────────────────────────────────
def test_item_soft_delete(client, patient, proc):
    plan = _plan(client, patient.id)
    _item(client, plan, proc, "I-2")
    d = client.delete(f"{PREFIX}/treatment-plan-items/I-2")
    assert d.status_code == 204
    # archived row retained, flagged
    assert client.get(f"{PREFIX}/treatment-plan-items/I-2").json()["is_archived"] is True
    active = client.get(f"{PREFIX}/treatment-plan-items?plan_id={plan}&is_archived=false").json()
    assert active["meta"]["total"] == 0


# ── PLAN-13: item with insurance-detail is still deletable ────────────────────
def test_item_with_insurance_detail_deletable(client, patient, proc):
    plan = _plan(client, patient.id)
    _item(client, plan, proc, "I-3")
    det = client.post(f"{PREFIX}/treatment-plan-insurance-details",
                      json={"plan_item_id": "I-3", "estimated_ins": 50, "estimated_pat": 150})
    assert det.status_code == 201, det.text
    det_id = det.json()["id"]

    d = client.delete(f"{PREFIX}/treatment-plan-items/I-3")
    assert d.status_code == 204  # not 409

    # the detail was archived alongside the item
    assert client.get(f"{PREFIX}/treatment-plan-insurance-details/{det_id}").json()["is_archived"] is True
    excluded = client.get(
        f"{PREFIX}/treatment-plan-insurance-details?plan_item_id=I-3&is_archived=false"
    ).json()
    assert excluded["meta"]["total"] == 0


# ── PLAN-12: patient-scoped items, no N+1, no cross-patient ───────────────────
def test_patient_items_endpoint(client, db_session, patient, proc):
    plan_a = _plan(client, patient.id, "TP-A")
    plan_b = _plan(client, patient.id, "TP-B")
    _item(client, plan_a, proc, "PA-1")
    _item(client, plan_b, proc, "PB-1")

    other = Patient(tenant_id=db_session._tenant_id, first_name="Other", last_name="Pat")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    plan_c = _plan(client, other.id, "TP-C")
    _item(client, plan_c, proc, "PC-1")

    rows = client.get(f"{PREFIX}/patients/{patient.id}/treatment-plan-items")
    assert rows.status_code == 200, rows.text
    ids = {r["id"] for r in rows.json()}
    assert ids == {"PA-1", "PB-1"}  # both plans, no cross-patient row


# ── PLAN-3: insurance re-estimate ─────────────────────────────────────────────
def _setup_coverage(db_session, patient_id, *, pct=80, deductible=50, annual_max=1000):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Acme Dental", is_active=True)
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                         individual_deductible=Decimal(deductible), individual_max=Decimal(annual_max),
                         is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(InsuranceCoverageRule(ins_plan_id=plan.id, start_code="D0000",
                                         end_code="D9999", coverage_pct=Decimal(pct), ded_waived=False))
    db_session.add(PatientInsurance(patient_id=patient_id, ins_plan_id=plan.id,
                                    insurance_type="primary", is_active=True,
                                    deductible_remaining=Decimal(deductible),
                                    max_remaining=Decimal(annual_max)))
    db_session.commit()
    return plan.id


def test_re_estimate_with_coverage(client, db_session, patient, proc):
    ins_plan_id = _setup_coverage(db_session, patient.id)
    plan = _plan(client, patient.id)
    _item(client, plan, proc, "RE-1", priority=1)  # fee 200

    r = client.post(f"{PREFIX}/treatment-plans/{plan}/re-estimate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["insured"] is True
    assert body["ins_plan_id"] == ins_plan_id
    line = body["lines"][0]
    # deductible 50 applied → base 150 → 80% = 120 ins, 80 patient
    assert float(line["deductible_applied"]) == 50
    assert float(line["insurance_estimate"]) == 120
    assert float(line["patient_estimate"]) == 80
    # written back to the item
    assert float(client.get(f"{PREFIX}/treatment-plan-items/RE-1").json()["insurance_estimate"]) == 120


def test_re_estimate_no_insurance(client, patient, proc):
    plan = _plan(client, patient.id)
    _item(client, plan, proc, "RE-2")
    r = client.post(f"{PREFIX}/treatment-plans/{plan}/re-estimate")
    assert r.status_code == 200, r.text
    assert r.json()["insured"] is False
    assert float(r.json()["lines"][0]["insurance_estimate"]) == 0
    assert float(r.json()["lines"][0]["patient_estimate"]) == 200


# ── PLAN-6: report payload ────────────────────────────────────────────────────
def test_plan_report(client, patient, proc):
    plan = _plan(client, patient.id)
    _item(client, plan, proc, "R-1", insurance_estimate=120)
    rep = client.get(f"{PREFIX}/treatment-plans/{plan}/report")
    assert rep.status_code == 200, rep.text
    body = rep.json()
    assert body["patient"]["id"] == patient.id
    assert body["item_count"] == 1
    assert float(body["total_fee"]) == 200
    assert float(body["total_patient_estimate"]) == 80


# ── PLAN-7: per-patient consent capture ───────────────────────────────────────
def test_patient_consent_crud(client, patient):
    r = client.post(f"{PREFIX}/patient-consents", json={
        "patient_id": patient.id, "title": "Crown consent",
        "rendered_html": "<p>I consent</p>", "status": "pending",
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    listed = client.get(f"{PREFIX}/patient-consents?patient_id={patient.id}").json()
    assert listed["meta"]["total"] == 1
    signed = client.patch(f"{PREFIX}/patient-consents/{cid}",
                          json={"status": "signed", "signature_data": "base64xyz"})
    assert signed.status_code == 200
    assert signed.json()["status"] == "signed"
