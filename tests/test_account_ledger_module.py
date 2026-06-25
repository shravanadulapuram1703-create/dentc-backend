"""Account Ledger backend-gap tests (account-ledger dev-report AL-1..7)."""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import Office, Patient, Provider

PREFIX = "/api/v1"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Led", last_name="Ger",
                chart_no="AL-PAT", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="MOON", name="Moon Office",
               short_id="MOON")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    pr = Provider(id="PRV-1", tenant_id=db_session._tenant_id, office_id=office.id,
                  name="Dr Strange", short_id="STRG")
    db_session.add(pr)
    db_session.commit()
    db_session.refresh(pr)
    return pr


def _proc(client, patient_id, office_id, provider_id, code, fee, dos, item_id, **extra):
    body = {"id": item_id, "patient_id": patient_id, "office_id": office_id,
            "provider_id": provider_id, "procedure_code": code, "fee": fee,
            "date_of_service": dos, **extra}
    r = client.post(f"{PREFIX}/patient-procedures", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _pay(client, patient_id, amount, pdate, pay_id):
    r = client.post(f"{PREFIX}/patient-payments", json={
        "id": pay_id, "patient_id": patient_id, "amount": amount,
        "payment_date": pdate, "payment_type": "patient"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def proc_code(client):
    r = client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D2740", "description": "Crown", "category": "Restorative", "default_fee": 1000})
    assert r.status_code == 201, r.text
    return "D2740"


# ── AL-1/2: denormalised feed + running balance + pagination ──────────────────
def test_account_ledger_running_balance_and_denorm(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 1000, "2026-01-01", "P1",
          tooth="3", surface="MO", apply_to="P", insurance_estimate=600, patient_estimate=400)
    _pay(client, patient.id, 250, "2026-01-05", "PAY1")

    r = client.get(f"{PREFIX}/patients/{patient.id}/account-ledger")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert float(body["grand_total"]) == 750.0  # 1000 charge − 250 payment

    rows = body["rows"]  # chronological asc
    charge, payment = rows[0], rows[1]
    assert charge["source_type"] == "charge"
    assert charge["code"] == "D2740" and charge["description"] == "Crown"
    assert charge["office_short_id"] == "MOON"        # AL-7
    assert charge["provider_name"] == "Dr Strange"
    assert charge["transaction_kind"] == "P"
    assert charge["unbilled"] is True                 # AL-6 "N" (no claim)
    assert float(charge["running_balance"]) == 1000.0
    assert float(charge["insurance_estimate"]) == 600.0
    assert payment["source_type"] == "payment" and payment["code"] == "PMT"
    assert payment["transaction_kind"] == "C"
    assert float(payment["running_balance"]) == 750.0


def test_account_ledger_pagination(client, patient, office, provider, proc_code):
    for i in range(5):
        _proc(client, patient.id, office.id, provider.id, proc_code, 100, f"2026-02-0{i+1}", f"PG{i}")
    r = client.get(f"{PREFIX}/patients/{patient.id}/account-ledger?page=1&size=2")
    body = r.json()
    assert body["total"] == 5 and body["pages"] == 3 and len(body["rows"]) == 2
    # running balance accumulates across the full window, not just the page
    assert float(body["rows"][0]["running_balance"]) == 100.0
    assert float(body["rows"][1]["running_balance"]) == 200.0
    assert float(body["grand_total"]) == 500.0


# ── AL-4: type filter (running balance stays account-level) ───────────────────
def test_account_ledger_type_filter(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 1000, "2026-03-01", "TP1")
    _pay(client, patient.id, 250, "2026-03-05", "TPAY1")

    pays = client.get(f"{PREFIX}/patients/{patient.id}/account-ledger?transaction_type=payment").json()
    assert pays["total"] == 1
    assert pays["rows"][0]["source_type"] == "payment"
    assert float(pays["rows"][0]["running_balance"]) == 750.0   # account-level, not -250
    assert float(pays["grand_total"]) == 750.0                  # full-account total


# ── AL-5: server-side sort ────────────────────────────────────────────────────
def test_account_ledger_sort_by_amount(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 100, "2026-04-01", "S1")
    _proc(client, patient.id, office.id, provider.id, proc_code, 900, "2026-04-02", "S2")
    r = client.get(f"{PREFIX}/patients/{patient.id}/account-ledger?sort_by=amount&order=desc").json()
    amounts = [float(row["amount"]) for row in r["rows"]]
    assert amounts == sorted(amounts, reverse=True)


# ── AL-3: payment-plan fields + plan_type discriminator ───────────────────────
def test_ortho_payment_plan_type_and_filter(client, patient):
    reg = client.post(f"{PREFIX}/patient-payment-plans", json={
        "patient_id": patient.id, "plan_type": "regular", "amt_financed": 1000})
    assert reg.status_code == 201, reg.text
    ortho = client.post(f"{PREFIX}/patient-payment-plans", json={
        "patient_id": patient.id, "plan_type": "ortho", "amt_financed": 5000})
    assert ortho.status_code == 201, ortho.text
    assert ortho.json()["plan_type"] == "ortho"

    only_ortho = client.get(
        f"{PREFIX}/patient-payment-plans?patient_id={patient.id}&plan_type=ortho").json()
    assert only_ortho["meta"]["total"] == 1


def test_ins_payment_plan_financial_fields(client, patient):
    r = client.post(f"{PREFIX}/patient-ins-payment-plans", json={
        "patient_id": patient.id, "plan_amount": 2000, "down_payment": 200,
        "rem_total_amt": 1800, "rem_payments": 9, "periodic_amt": 200})
    assert r.status_code == 201, r.text
    body = r.json()
    assert float(body["plan_amount"]) == 2000.0
    assert body["rem_payments"] == 9
