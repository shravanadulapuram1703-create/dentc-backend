"""Transactions-module backend-gap tests (transactions_backend_devreport).

Covers office dashboards (DASH-1..5), unified feed/search (SRCH-1/3), refunds &
reversals (REF-1..4), statements (STMT-1..3), insurance-payment remittance
(INS-1), claim submit (SVC-1) + status history (AUD-3), ledger sort/filter
(LED-1) + audit (AUD-1/2), estimate engine (CHG-1), explosion codes (CHG-4),
insurance summary (CHG-8) and today's appointment (CHG-9).
"""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import (
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    Office,
    Patient,
    PatientInsurance,
    Provider,
)

PREFIX = "/api/v1"
TODAY = date.today().isoformat()


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="TX1", name="Tx Office", short_id="TX1")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def patient(db_session, office) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Tran", last_name="Sax",
                chart_no="TX-PAT", home_office_id=office.id, email="pat@tx.local", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def provider(db_session, office) -> Provider:
    pr = Provider(id="TXPRV", tenant_id=db_session._tenant_id, office_id=office.id,
                  name="Dr Tx", short_id="DRTX")
    db_session.add(pr)
    db_session.commit()
    db_session.refresh(pr)
    return pr


@pytest.fixture
def proc_code(client):
    r = client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D2750", "description": "Crown PFM", "category": "Restorative", "default_fee": 1000})
    assert r.status_code == 201, r.text
    return "D2750"


def _proc(client, patient_id, office_id, provider_id, code, fee, dos, item_id, **extra):
    body = {"id": item_id, "patient_id": patient_id, "office_id": office_id,
            "provider_id": provider_id, "procedure_code": code, "fee": fee,
            "date_of_service": dos, **extra}
    r = client.post(f"{PREFIX}/patient-procedures", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _pay(client, patient_id, amount, pay_id, office_id=None, ptype="patient", pdate=TODAY):
    body = {"id": pay_id, "patient_id": patient_id, "amount": amount,
            "payment_date": pdate, "payment_type": ptype}
    if office_id:
        body["office_id"] = office_id
    r = client.post(f"{PREFIX}/patient-payments", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── DASH-1: office financial summary ─────────────────────────────────────────
def test_office_financial_summary(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 1000, TODAY, "F1",
          insurance_estimate=600)
    _pay(client, patient.id, 250, "FP1", office_id=office.id)

    r = client.get(f"{PREFIX}/offices/{office.id}/financial-summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["outstanding_balance"]) == 750.0
    assert float(body["insurance_receivable"]) == 600.0
    assert body["patient_count"] == 1


def test_financial_summary_office_scoped_to_tenant(client):
    r = client.get(f"{PREFIX}/offices/99999/financial-summary")
    assert r.status_code == 404


# ── DASH-2: collections ──────────────────────────────────────────────────────
def test_office_collections_today(client, patient, office, provider, proc_code):
    _pay(client, patient.id, 100, "C1", office_id=office.id, ptype="patient")
    _pay(client, patient.id, 300, "C2", office_id=office.id, ptype="insurance")
    r = client.get(f"{PREFIX}/offices/{office.id}/collections?period=today")
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["patient_payments"]) == 100.0
    assert float(body["insurance_payments"]) == 300.0
    assert float(body["total_collections"]) == 400.0


# ── DASH-3: insurance receivables ────────────────────────────────────────────
def test_insurance_receivables(client, patient, office):
    r = client.post(f"{PREFIX}/insurance-claims", json={
        "id": "CLM-1", "patient_id": patient.id, "office_id": office.id, "claim_number": "CLM-1",
        "status": "sent", "est_insurance": 500, "total_paid": 100})
    assert r.status_code == 201, r.text
    out = client.get(f"{PREFIX}/offices/{office.id}/insurance-receivables").json()
    assert float(out["total_outstanding"]) == 400.0
    assert out["open_claim_count"] == 1


# ── DASH-4: adjustment / write-off / refund totals ───────────────────────────
def test_adjustment_summary(client, patient, office, provider, proc_code):
    r = client.post(f"{PREFIX}/patient-adjustments", json={
        "patient_id": patient.id, "office_id": office.id, "amount": 80,
        "adjustment_date": TODAY, "adjustment_type": "writeoff", "write_off_type": "contractual"})
    assert r.status_code == 201, r.text
    out = client.get(f"{PREFIX}/offices/{office.id}/adjustment-summary?period=month").json()
    assert float(out["adjustment_total"]) == 80.0
    assert float(out["write_off_total"]) == 80.0
    assert float(out["write_off_by_type"]["contractual"]) == 80.0


# ── SRCH-1/3 · DASH-5: unified feed ──────────────────────────────────────────
def test_unified_transaction_feed(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 1000, TODAY, "U1")
    _pay(client, patient.id, 250, "UP1", office_id=office.id)
    r = client.get(f"{PREFIX}/transactions?type=all")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    types = {row["transaction_type"] for row in body["rows"]}
    assert types == {"charge", "payment"}
    names = {row["patient_name"] for row in body["rows"]}
    assert names == {"Sax, Tran"}


def test_unified_feed_type_and_amount_filter(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 1000, TODAY, "U2")
    _pay(client, patient.id, 250, "UP2", office_id=office.id)
    charges = client.get(f"{PREFIX}/transactions?type=charge").json()
    assert charges["total"] == 1 and charges["rows"][0]["transaction_type"] == "charge"
    ranged = client.get(f"{PREFIX}/transactions?amount_min=500").json()
    assert ranged["total"] == 1  # only the 1000 charge (payment is 250)


def test_search_by_transaction_number(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 1000, TODAY, "FINDME")
    r = client.get(f"{PREFIX}/transactions?transaction_number=FINDME").json()
    assert r["total"] == 1 and r["rows"][0]["source_id"] == "FINDME"


# ── REF-1/3: refund + refundable balance ─────────────────────────────────────
def test_refund_flow_and_balance(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 100, TODAY, "R1")
    _pay(client, patient.id, 150, "RP1", office_id=office.id)  # overpaid by 50

    refundable = client.get(f"{PREFIX}/patients/{patient.id}/refundable-balance").json()
    assert float(refundable["credit_balance"]) == 50.0
    assert float(refundable["refundable_amount"]) == 50.0

    r = client.post(f"{PREFIX}/patients/{patient.id}/refunds", json={
        "refund_amount": 50, "refund_method": "check", "reason_code": "overpayment"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert float(body["refund"]["amount"]) == 50.0
    # After refunding the credit, the balance is back to 0.
    assert float(body["balance"]["account_balance"]) == 0.0
    assert float(body["balance"]["total_refunded"]) == 50.0


def test_refund_over_credit_rejected(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 100, TODAY, "R2")
    _pay(client, patient.id, 110, "RP2", office_id=office.id)  # credit only 10
    r = client.post(f"{PREFIX}/patients/{patient.id}/refunds", json={
        "refund_amount": 50, "refund_method": "cash"})
    assert r.status_code == 422, r.text


# ── REF-2: reverse a payment ─────────────────────────────────────────────────
def test_reverse_payment(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 100, TODAY, "RV1")
    _pay(client, patient.id, 100, "RVP1", office_id=office.id)
    before = client.get(f"{PREFIX}/patients/{patient.id}/balance").json()
    assert float(before["balance"]) == 0.0

    r = client.post(f"{PREFIX}/patient-payments/RVP1/reverse", json={"reason": "posted in error"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reversed_type"] == "payment"
    # Voiding the payment restores the 100 charge to the balance.
    assert float(body["balance"]["balance"]) == 100.0


# ── REF-4: policy ────────────────────────────────────────────────────────────
def test_refund_policy(client, office):
    r = client.get(f"{PREFIX}/metadata/refund-policy?office_id={office.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "manager_approval_threshold" in body
    assert "admin" in body["approver_roles"]


# ── STMT-1/3: statement generate + PDF + deliver ─────────────────────────────
def test_statement_generation_and_pdf(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 400, TODAY, "S1")
    _pay(client, patient.id, 100, "SP1", office_id=office.id)

    r = client.post(f"{PREFIX}/patients/{patient.id}/statements", json={"office_id": office.id})
    assert r.status_code == 201, r.text
    stmt = r.json()
    assert float(stmt["closing_balance"]) == 300.0
    sid = stmt["id"]

    listed = client.get(f"{PREFIX}/patients/{patient.id}/statements").json()
    assert listed["meta"]["total"] == 1

    pdf = client.get(f"{PREFIX}/patients/{patient.id}/statements/{sid}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"

    delivered = client.post(
        f"{PREFIX}/patients/{patient.id}/statements/{sid}/deliver", json={"method": "email"})
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["delivery_status"] == "emailed"


def test_statement_batch(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 500, TODAY, "SB1")
    r = client.post(f"{PREFIX}/offices/{office.id}/statements/batch", json={"min_balance": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generated"] == 1
    assert body["statements"][0]["batch_id"] == body["batch_id"]


# ── INS-1: insurance payment with remittance identifiers ─────────────────────
def test_insurance_payment_remittance(client, patient, office):
    claim = client.post(f"{PREFIX}/insurance-claims", json={
        "id": "CLM-INS", "patient_id": patient.id, "office_id": office.id, "claim_number": "CLM-INS",
        "status": "sent", "est_insurance": 500}).json()
    r = client.post(f"{PREFIX}/ledger-insurance-details/payment", json={
        "patient_id": patient.id, "claim_id": claim["id"], "office_id": office.id,
        "payment_method": "eft", "eob_number": "EOB-9", "eft_trace_number": "TR-1",
        "check_number": "CK-7", "bank_number": "BK-2", "prim_ins_paid": 400})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["eob_number"] == "EOB-9"
    assert body["eft_trace_number"] == "TR-1"
    assert float(body["prim_ins_paid"]) == 400.0


# ── SVC-1 + AUD-3: submit claim + status history ─────────────────────────────
def test_submit_claim_and_status_history(client, patient, office):
    claim = client.post(f"{PREFIX}/insurance-claims", json={
        "id": "CLM-SVC", "patient_id": patient.id, "office_id": office.id, "claim_number": "CLM-SVC",
        "status": "draft", "total_billed": 800}).json()
    r = client.post(f"{PREFIX}/insurance-claims/{claim['id']}/submit",
                    json={"send_method": "electronic"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "sent"
    assert body["batch_id"].startswith("BATCH-")

    hist = client.get(f"{PREFIX}/insurance-claims/{claim['id']}/status-history")
    assert hist.status_code == 200, hist.text
    events = hist.json()["events"]
    assert any(e["source"] == "claim_field" and e["status"] == "submitted" for e in events)


# ── AUD-1: audit-log resource_id filter ──────────────────────────────────────
def test_audit_resource_id_filter(client, db_session):
    # The audit middleware writes via its own session, so seed rows directly to
    # exercise the new resource_id filter on the read endpoint.
    from app.db.models import AuditLog

    db_session.add_all([
        AuditLog(id=1, tenant_id=db_session._tenant_id, user_id=db_session._admin.id, action="POST",
                 resource_type="insurance-claims", resource_id="CLM-AUD", method="POST",
                 path="/api/v1/insurance-claims/CLM-AUD/submit", status_code=200),
        AuditLog(id=2, tenant_id=db_session._tenant_id, user_id=db_session._admin.id, action="POST",
                 resource_type="insurance-claims", resource_id="OTHER", method="POST",
                 path="/api/v1/insurance-claims/OTHER/submit", status_code=200),
    ])
    db_session.commit()

    r = client.get(f"{PREFIX}/audit-logs?resource_type=insurance-claims&resource_id=CLM-AUD")
    assert r.status_code == 200, r.text
    logs = r.json()["items"]
    assert logs and all(log["resource_id"] == "CLM-AUD" for log in logs)


# ── LED-1 + AUD-2: ledger sort/filter + creator columns ──────────────────────
def test_ledger_sort_filter_and_created_by(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, 100, "2026-01-01", "L1")
    _proc(client, patient.id, office.id, provider.id, proc_code, 900, "2026-01-02", "L2")
    _pay(client, patient.id, 50, "LP1", office_id=office.id, pdate="2026-01-03")

    only_charges = client.get(
        f"{PREFIX}/patients/{patient.id}/ledger?transaction_type=procedure").json()
    assert only_charges["total"] == 2
    assert all(e["entry_type"] == "procedure" for e in only_charges["entries"])
    # AUD-2: creator populated on the ledger row.
    assert only_charges["entries"][0]["created_by"] is not None
    assert only_charges["entries"][0]["created_by_name"]

    desc = client.get(
        f"{PREFIX}/patients/{patient.id}/ledger?sort_by=amount&sort_order=desc").json()
    amounts = [e["charge"] - e["credit"] for e in desc["entries"]]
    assert amounts == sorted(amounts, reverse=True)


# ── CHG-1/7: estimate engine ─────────────────────────────────────────────────
def test_estimate_with_coverage(client, db_session, patient, office, provider, proc_code):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Delta")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                         individual_deductible=0, individual_max=5000)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(InsuranceCoverageRule(
        ins_plan_id=plan.id, start_code="D2000", end_code="D2999", coverage_pct=50))
    db_session.add(PatientInsurance(
        patient_id=patient.id, ins_plan_id=plan.id, insurance_type="primary", is_active=True))
    db_session.commit()

    r = client.post(f"{PREFIX}/patients/{patient.id}/estimate",
                    json={"procedure_code": proc_code, "fee": 1000})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_active_coverage"] is True
    assert float(body["insurance_estimate"]) == 500.0
    assert float(body["patient_estimate"]) == 500.0


def test_estimate_no_coverage_is_all_patient(client, patient, proc_code):
    r = client.post(f"{PREFIX}/patients/{patient.id}/estimate",
                    json={"procedure_code": proc_code, "fee": 1000}).json()
    assert r["has_active_coverage"] is False
    assert float(r["insurance_estimate"]) == 0.0
    assert float(r["patient_estimate"]) == 1000.0


# ── CHG-4: explosion codes ───────────────────────────────────────────────────
def test_explosion_code_expand(client, office, proc_code):
    header = client.post(f"{PREFIX}/explosion-codes", json={
        "code": "NPEXAM", "description": "New patient exam"})
    assert header.status_code == 201, header.text
    hid = header.json()["id"]
    item = client.post(f"{PREFIX}/explosion-code-items", json={
        "explosion_code_id": hid, "procedure_code": proc_code, "display_order": 1})
    assert item.status_code == 201, item.text

    r = client.get(f"{PREFIX}/explosion-codes/NPEXAM/expand")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["explosion_code"] == "NPEXAM"
    assert body["procedures"][0]["procedure_code"] == proc_code
    assert body["procedures"][0]["description"] == "Crown PFM"


# ── CHG-8: insurance summary ─────────────────────────────────────────────────
def test_patient_insurance_summary(client, db_session, patient):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Aetna")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id, group_number="G1")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(PatientInsurance(
        patient_id=patient.id, ins_plan_id=plan.id, insurance_type="primary", is_active=True))
    db_session.commit()

    r = client.get(f"{PREFIX}/patients/{patient.id}/insurance-summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["primary"]["carrier_name"] == "Aetna"
    assert body["primary"]["group_number"] == "G1"


# ── CHG-9: today's appointment ───────────────────────────────────────────────
def test_todays_appointment(client, patient, office, provider):
    appt = client.post(f"{PREFIX}/appointments", json={
        "id": "APPT-TX", "patient_id": patient.id, "provider_id": provider.id,
        "office_id": office.id, "date": TODAY, "start_time": "09:00:00",
        "end_time": "09:30:00", "duration": 30, "status": "scheduled"})
    assert appt.status_code == 201, appt.text
    r = client.get(f"{PREFIX}/patients/{patient.id}/todays-appointment")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_appointment"] is True
    assert body["appointment_id"] == "APPT-TX"


def test_todays_appointment_none(client, patient):
    r = client.get(f"{PREFIX}/patients/{patient.id}/todays-appointment").json()
    assert r["has_appointment"] is False


# ── CHG-5/6: payment bank_number + procedure hygienist persisted ─────────────
def test_payment_bank_number_persisted(client, patient, office):
    r = client.post(f"{PREFIX}/patient-payments", json={
        "id": "BNK1", "patient_id": patient.id, "amount": 100, "payment_date": TODAY,
        "payment_type": "patient", "office_id": office.id, "bank_number": "BANK-9"})
    assert r.status_code == 201, r.text
    assert r.json()["bank_number"] == "BANK-9"


def test_procedure_hygienist_persisted(client, patient, office, provider, proc_code):
    out = _proc(client, patient.id, office.id, provider.id, proc_code, 100, TODAY, "HYG1",
                hygienist_id=provider.id)
    assert out["hygienist_id"] == provider.id
