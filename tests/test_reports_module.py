"""Tests for the Reports module aggregation endpoints (FE dev-report gaps 1/2/3).

Exercises tenant-scoped roll-ups over seeded procedures/payments/adjustments/
claims/appointments, plus office scoping and the gap-6 office_id list filters.
"""

from __future__ import annotations

PREFIX = "/api/v1"


def _patient(client, **kw) -> int:
    body = {"first_name": "Re", "last_name": "Port", **kw}
    r = client.post(f"{PREFIX}/patients", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _proc(client, pid, pid_str, fee, dos, *, office_id=1, ins_est=0):
    r = client.post(f"{PREFIX}/patient-procedures", json={
        "id": pid_str, "patient_id": pid, "procedure_code": "D1110",
        "date_of_service": dos, "provider_id": "PR1", "office_id": office_id,
        "fee": fee, "insurance_estimate": ins_est,
    })
    assert r.status_code == 201, r.text


def _payment(client, pid, pid_str, amount, pdate, *, office_id=1, ptype="patient"):
    r = client.post(f"{PREFIX}/patient-payments", json={
        "id": pid_str, "patient_id": pid, "payment_date": pdate,
        "amount": amount, "payment_type": ptype, "office_id": office_id,
    })
    assert r.status_code == 201, r.text


def test_summary_production_and_collections(client):
    pid = _patient(client)
    _proc(client, pid, "PRC-1", 200, "2026-03-10")
    _proc(client, pid, "PRC-2", 100, "2026-03-20")
    _proc(client, pid, "PRC-3", 999, "2026-01-01")  # outside window
    _payment(client, pid, "PAY-1", 120, "2026-03-15")

    r = client.get(f"{PREFIX}/reports/summary",
                   params={"date_from": "2026-03-01", "date_to": "2026-03-31"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["production"] == 300.0
    assert body["collections"] == 120.0
    # Patient was created "today" (not in March) — proves new_patients is windowed.
    assert body["new_patients"] == 0
    assert body["active_patients"] >= 1
    # AR is cumulative (≤ date_to): 200+100+999 charged − 120 paid = 1179
    assert body["outstanding_ar"] == 1179.0

    # A window that includes "today" picks the newly-created patient up.
    wide = client.get(f"{PREFIX}/reports/summary",
                      params={"date_from": "2026-01-01", "date_to": "2026-12-31"})
    assert wide.json()["new_patients"] >= 1


def test_office_scoping(client):
    pid = _patient(client)
    _proc(client, pid, "O-1", 500, "2026-03-05", office_id=1)
    _proc(client, pid, "O-2", 300, "2026-03-06", office_id=2)

    r = client.get(f"{PREFIX}/reports/summary",
                   params={"date_from": "2026-03-01", "date_to": "2026-03-31", "office_id": 1})
    assert r.json()["production"] == 500.0
    r2 = client.get(f"{PREFIX}/reports/summary",
                    params={"date_from": "2026-03-01", "date_to": "2026-03-31", "office_id": 2})
    assert r2.json()["production"] == 300.0


def test_accounts_receivable(client):
    pid = _patient(client)
    _proc(client, pid, "AR-1", 400, "2026-02-01", ins_est=150)
    _payment(client, pid, "ARP-1", 100, "2026-02-05")
    client.post(f"{PREFIX}/patient-adjustments", json={
        "patient_id": pid, "adjustment_date": "2026-02-10", "amount": 50, "office_id": 1,
    })

    r = client.get(f"{PREFIX}/reports/accounts-receivable", params={"as_of": "2026-12-31"})
    assert r.status_code == 200, r.text
    body = r.json()
    # 400 charged − (100 paid + 50 adjusted) = 250
    assert body["total_ar"] == 250.0
    assert body["insurance_ar"] == 150.0
    assert body["patient_ar"] == 100.0


def test_aging_buckets(client):
    pid = _patient(client)
    _proc(client, pid, "AG-1", 100, "2026-06-05")   # 2 days -> current
    _proc(client, pid, "AG-2", 200, "2026-04-01")   # ~67 days -> d60
    r = client.get(f"{PREFIX}/reports/aging", params={"as_of": "2026-06-07"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current"] == 100.0
    assert body["d60"] == 200.0
    assert body["total"] == 300.0


def test_trends_monthly(client):
    pid = _patient(client)
    _proc(client, pid, "T-1", 100, "2026-01-10")
    _proc(client, pid, "T-2", 50, "2026-01-20")
    _proc(client, pid, "T-3", 70, "2026-02-15")
    _payment(client, pid, "TP-1", 30, "2026-02-16")

    r = client.get(f"{PREFIX}/reports/trends", params={
        "date_from": "2026-01-01", "date_to": "2026-02-28", "interval": "month",
    })
    assert r.status_code == 200, r.text
    buckets = {b["period"]: b for b in r.json()["buckets"]}
    assert buckets["2026-01-01"]["production"] == 150.0
    assert buckets["2026-02-01"]["production"] == 70.0
    assert buckets["2026-02-01"]["collections"] == 30.0


def test_insurance_receivables_excludes_settled(client):
    pid = _patient(client)
    client.post(f"{PREFIX}/insurance-claims", json={
        "id": "CL-1", "patient_id": pid, "claim_number": "C1", "office_id": 1,
        "status": "submitted", "total_billed": 500, "total_paid": 100,
    })
    client.post(f"{PREFIX}/insurance-claims", json={
        "id": "CL-2", "patient_id": pid, "claim_number": "C2", "office_id": 1,
        "status": "paid", "total_billed": 300, "total_paid": 300,
    })
    r = client.get(f"{PREFIX}/reports/summary",
                   params={"date_from": "2026-01-01", "date_to": "2026-12-31"})
    # only the submitted claim's remainder (500 − 100 = 400) counts
    assert r.json()["insurance_receivables"] == 400.0


def test_office_id_list_filter(client):
    """Gap 6: office_id is now an OpenAPI-visible filter on procedures/payments/claims."""
    pid = _patient(client)
    _proc(client, pid, "F-1", 100, "2026-03-01", office_id=1)
    _proc(client, pid, "F-2", 100, "2026-03-01", office_id=2)
    r = client.get(f"{PREFIX}/patient-procedures", params={"office_id": 2})
    assert r.status_code == 200, r.text
    ids = [row["id"] for row in r.json()["items"]]
    assert ids == ["F-2"]
