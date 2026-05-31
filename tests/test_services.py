"""Tests for the Phase 2 service overrides (non-CRUD business logic)."""

from __future__ import annotations

PREFIX = "/api/v1"


def _make_patient(client) -> int:
    r = client.post(f"{PREFIX}/patients", json={"first_name": "Pay", "last_name": "Tient"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_treatment_plan_summary(client):
    pid = _make_patient(client)
    client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D1110", "description": "Prophylaxis", "category": "Preventive", "default_fee": 100,
    })
    plan = client.post(f"{PREFIX}/treatment-plans", json={
        "id": "TP-1", "patient_id": pid, "name": "Plan A",
    })
    assert plan.status_code == 201, plan.text
    for fee, ins in [(200, 120), (100, 0)]:
        item = client.post(f"{PREFIX}/treatment-plan-items", json={
            "id": f"TPI-{fee}", "plan_id": "TP-1", "procedure_code": "D1110",
            "fee": fee, "insurance_estimate": ins,
        })
        assert item.status_code == 201, item.text

    summary = client.get(f"{PREFIX}/treatment-plans/TP-1/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["item_count"] == 2
    assert float(body["total_fee"]) == 300
    assert float(body["total_insurance_estimate"]) == 120
    assert float(body["total_patient_estimate"]) == 180


def test_payment_over_allocation_rejected(client):
    pid = _make_patient(client)
    pay = client.post(f"{PREFIX}/patient-payments", json={
        "id": "PAY-1", "patient_id": pid, "payment_date": "2026-01-01",
        "amount": 100, "payment_type": "patient",
    })
    assert pay.status_code == 201, pay.text

    ok = client.post(f"{PREFIX}/patient-payments/PAY-1/allocate", json={
        "allocations": [{"amount": 60}, {"amount": 40}],
    })
    assert ok.status_code == 200, ok.text
    assert len(ok.json()) == 2

    over = client.post(f"{PREFIX}/patient-payments/PAY-1/allocate", json={
        "allocations": [{"amount": 10}],
    })
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "validation_error"
