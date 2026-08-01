"""Payment Plans (Ortho + Regular) — docs/payment-plans/payment_plans_backend_devreport.md.

Covers PP-1..8, OPP-1..11 and RPP-1..6: soft-delete visibility, the periodic
billing posting path, the patient-side instalment store, server-side
amortisation, the contract documents, and every new persisted column.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

API = "/api/v1"


# ── fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture
def office(client):
    r = client.post(f"{API}/offices", json={"name": "Main", "office_code": "MAIN"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def provider(client, office):
    r = client.post(f"{API}/providers", json={
        "id": "736TC", "name": "Jinna, Dhileep DMD", "office_id": office,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def patient(client, office, provider):
    r = client.post(f"{API}/patients", json={
        "first_name": "Leo", "last_name": "Rob", "home_office_id": office,
        "preferred_provider_id": provider,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def codes(client):
    for code, desc in (("D8080", "Comprehensive ortho tx"), ("D8670", "Periodic ortho visit"),
                       ("ACBIL", "Periodic Contract Billing")):
        r = client.post(f"{API}/procedure-codes", json={
            "code": code, "description": desc, "category": "Ortho", "default_fee": 0,
        })
        assert r.status_code == 201, r.text
    return ("D8080", "D8670", "ACBIL")


def _ortho_plan(client, patient, office, provider, **extra):
    body = {
        "patient_id": patient, "office_id": office,
        "procedure_code": "D8670", "initial_procedure_code": "D8080",
        "pref_provider_id": provider,
        "pat_amt_financed": 2400, "pat_down_pay": 400, "pat_apr": 0,
        "pat_num_payments": 24, "pat_interval": "monthly",
        "pat_first_due_date": "2026-08-01",
        **extra,
    }
    r = client.post(f"{API}/ortho-plans", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _regular_plan(client, patient, office, **extra):
    body = {
        "patient_id": patient, "office_id": office, "plan_type": "regular",
        "plan_bal_amt": 500, "tx_plan_amt": 1000, "billing_code": "ACBIL",
        "amt_financed": 1200, "down_payment": 300, "apr": 0,
        "num_payments": 12, "interval_type": "monthly", "first_due_date": "2026-08-01",
        **extra,
    }
    r = client.post(f"{API}/patient-payment-plans", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── PP-1: a deleted contract must not come back ──────────────────────────────
def test_pp1_soft_deleted_ortho_plan_is_hidden_by_default(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider)
    assert client.delete(f"{API}/ortho-plans/{plan['id']}").status_code == 204

    default = client.get(f"{API}/ortho-plans", params={"patient_id": patient}).json()
    assert default["items"] == []

    params = {"patient_id": patient, "is_active": True}
    active = client.get(f"{API}/ortho-plans", params=params).json()
    assert active["items"] == []

    # An explicit is_active=false still surfaces them (audit / undelete screens).
    params = {"patient_id": patient, "is_active": False}
    deleted = client.get(f"{API}/ortho-plans", params=params).json()
    assert [i["id"] for i in deleted["items"]] == [plan["id"]]


def test_pp1_applies_to_regular_and_reg_plans(client, patient, office, codes):
    plan = _regular_plan(client, patient, office)
    assert client.delete(f"{API}/patient-payment-plans/{plan['id']}").status_code == 204
    listed = client.get(f"{API}/patient-payment-plans", params={"patient_id": patient})
    assert listed.json()["items"] == []

    r = client.post(f"{API}/patient-reg-plans", json={"patient_id": patient, "amt_financed": 100})
    reg_id = r.json()["id"]
    assert client.delete(f"{API}/patient-reg-plans/{reg_id}").status_code == 204
    listed = client.get(f"{API}/patient-reg-plans", params={"patient_id": patient})
    assert listed.json()["items"] == []


def test_pp1_does_not_leak_into_other_resources(client, office):
    """The default-hide is opt-in: inactive providers still list by default."""
    client.post(f"{API}/providers", json={"id": "P9", "name": "Retired", "office_id": office})
    assert client.delete(f"{API}/providers/P9").status_code == 204
    items = client.get(f"{API}/providers").json()["items"]
    assert "P9" in [i["id"] for i in items]


# ── OPP-1..11 · RPP-1..6: every previously-dropped column round-trips ────────
def test_opp_columns_persist(client, patient, office, provider, codes):
    plan = _ortho_plan(
        client, patient, office, provider,
        insert_class="NONE", pat_setup_date="2026-07-01", pat_notes="patient column note",
        remarks="REMARKS pop-out", financial_disclosure="STD",
        payment_code="credit_card", payment_token_id="tok_abc123",
        card_holder_name="Leo Rob", card_last4="4242", card_exp_month=9, card_exp_year=2029,
        post_down_payment_with_card=True,
        ins_mon_claim_print_fee=5, ins_suppress_periodic_printing=True,
        sec_ins_mon_claim_print_fee=3, sec_ins_suppress_periodic_printing=True,
        sec_ins_setup_date="2026-07-02", sec_ins_down_pay=100, sec_ins_interval="monthly",
        sec_ins_num_payments=18, sec_ins_rem_payments=18, sec_ins_rem_amt=900,
        sec_ins_first_due_date="2026-08-15", sec_ins_months_remaining=18,
        tx_duration_months=24, months_remaining=20, created_office_id=office,
    )
    got = client.get(f"{API}/ortho-plans/{plan['id']}").json()

    assert got["initial_procedure_code"] == "D8080"     # OPP-1
    assert got["procedure_code"] == "D8670"             # (periodic, unchanged name)
    assert got["pref_provider_id"] == provider          # OPP-2
    assert got["pref_provider_name"] == "Jinna, Dhileep DMD"
    assert got["insert_class"] == "NONE"                # OPP-3
    assert got["pat_setup_date"] == "2026-07-01"        # OPP-4
    assert got["pat_notes"] == "patient column note"
    assert got["remarks"] == "REMARKS pop-out"
    assert got["financial_disclosure"] == "STD"         # OPP-5
    assert got["payment_token_id"] == "tok_abc123"      # OPP-6
    assert got["card_last4"] == "4242"
    assert got["post_down_payment_with_card"] is True
    assert float(got["ins_mon_claim_print_fee"]) == 5   # OPP-7
    assert got["sec_ins_suppress_periodic_printing"] is True
    assert got["sec_ins_num_payments"] == 18            # OPP-8
    assert float(got["sec_ins_rem_amt"]) == 900
    assert got["tx_duration_months"] == 24              # OPP-10
    assert got["months_remaining"] == 20
    assert got["created_office_code"] == "MAIN"         # OPP-11
    assert got["created_by_name"]                       # resolvable actor


def test_opp6_never_exposes_a_pan_or_cvv_column(client):
    """OPP-6: card data must live in a vault — the table stores only a token."""
    schema = client.get("/api/v1/openapi.json").json()["components"]["schemas"]["OrthoPlanRead"]
    banned = {"card_number", "pan", "cvv", "cvc", "security_code"}
    assert not banned & set(schema["properties"])


def test_rpp_columns_persist(client, patient, office, codes):
    tp = client.post(f"{API}/treatment-plans", json={
        "id": "TP-1", "patient_id": patient, "name": "Plan A",
    })
    assert tp.status_code == 201, tp.text

    plan = _regular_plan(
        client, patient, office,
        treatment_plan_id="TP-1", tx_plan_number="TP-1",
        financial_disclosure="STD", total_of_payments=1200,
        payment_code="credit_card", payment_token_id="tok_xyz", card_last4="1111",
    )
    got = client.get(f"{API}/patient-payment-plans/{plan['id']}").json()
    assert float(got["tx_plan_amt"]) == 1000          # RPP-1
    assert got["treatment_plan_id"] == "TP-1"
    assert got["billing_code"] == "ACBIL"             # RPP-2
    assert got["financial_disclosure"] == "STD"       # RPP-3
    assert got["payment_token_id"] == "tok_xyz"       # RPP-4
    assert float(got["total_of_payments"]) == 1200    # RPP-6
    assert got["created_by_name"]                     # PP-7

    # RPP-1: the typed FK is filterable.
    listed = client.get(f"{API}/patient-payment-plans", params={"treatment_plan_id": "TP-1"}).json()
    assert [i["id"] for i in listed["items"]] == [plan["id"]]


def test_pp7_updated_by_is_stamped(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider)
    assert plan["updated_by"] is None
    got = client.patch(f"{API}/ortho-plans/{plan['id']}", json={"remarks": "re-amortised"}).json()
    assert got["updated_by"] is not None
    assert got["updated_by_name"]


def test_pp8_plan_type_is_constrained(client, patient, office, codes):
    bad = client.post(f"{API}/patient-payment-plans", json={
        "patient_id": patient, "plan_type": "whatever",
    })
    assert bad.status_code == 422

    # Casing is normalised rather than rejected.
    ok = client.post(f"{API}/patient-payment-plans", json={
        "patient_id": patient, "plan_type": "Ortho",
    })
    assert ok.status_code == 201, ok.text
    assert ok.json()["plan_type"] == "ortho"


# ── PP-6: an instalment row knows which contract made it ────────────────────
def test_pp6_installments_link_to_their_ortho_plan(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider)
    other = _ortho_plan(client, patient, office, provider)
    for plan_id, amount in ((plan["id"], 100), (other["id"], 200)):
        r = client.post(f"{API}/patient-ins-payment-plans", json={
            "patient_id": patient, "ortho_plan_id": plan_id,
            "periodic_order": 1, "periodic_date": "2026-08-01",
            "periodic_amt": amount, "billing_code": "D8670",
        })
        assert r.status_code == 201, r.text

    rows = client.get(
        f"{API}/patient-ins-payment-plans", params={"ortho_plan_id": plan["id"]}
    ).json()
    assert len(rows["items"]) == 1
    assert float(rows["items"][0]["periodic_amt"]) == 100


# ── OPP-9 / RPP-5: patient-side schedule + server-side amortisation ─────────
def test_generate_schedule_amortises_the_contract(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider)
    r = client.post(f"{API}/payment-plans/ortho/{plan['id']}/installments/generate", json={})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["terms"]["num_payments"] == 24
    assert Decimal(body["terms"]["periodic_amt"]) == Decimal("100.00")  # 2400 / 24, 0% APR
    assert Decimal(body["terms"]["total_of_payments"]) == Decimal("2400.00")
    assert Decimal(body["terms"]["finance_charge"]) == Decimal("0.00")
    assert len(body["rows"]) == 24
    assert body["rows"][0]["periodic_date"] == "2026-08-01"
    assert body["rows"][1]["periodic_date"] == "2026-09-01"
    assert body["rows"][-1]["periodic_date"] == "2028-07-01"  # 24 monthly steps
    # Rows sum exactly to the total of payments (no per-instalment rounding drift).
    assert sum(Decimal(r["periodic_amt"]) for r in body["rows"]) == Decimal("2400.00")
    assert Decimal(body["rows"][-1]["rem_total_amt"]) == Decimal("0.00")


def test_generate_schedule_with_interest(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider, pat_apr=12, pat_num_payments=12,
                       pat_amt_financed=1200)
    body = client.post(
        f"{API}/payment-plans/ortho/{plan['id']}/installments/generate", json={}
    ).json()
    # 1200 @ 12% APR over 12 monthly payments ≈ 106.62/mo.
    assert Decimal(body["terms"]["periodic_amt"]) == Decimal("106.62")
    assert Decimal(body["terms"]["finance_charge"]) > 0
    assert Decimal(body["terms"]["total_of_payments"]) > Decimal("1200")


def test_generate_schedule_preview_does_not_persist(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider)
    body = client.post(
        f"{API}/payment-plans/ortho/{plan['id']}/installments/generate", json={"persist": False}
    ).json()
    assert body["persisted"] is False
    stored = client.get(f"{API}/payment-plans/ortho/{plan['id']}/installments").json()
    assert stored["rows"] == []


def test_generate_schedule_requires_terms(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider, pat_num_payments=None)
    r = client.post(f"{API}/payment-plans/ortho/{plan['id']}/installments/generate", json={})
    assert r.status_code == 422
    assert "number of payments" in r.json()["error"]["message"]


def test_replace_schedule_keeps_posted_rows(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider)
    client.post(f"{API}/payment-plans/ortho/{plan['id']}/installments/generate", json={})
    rows = client.get(f"{API}/payment-plans/ortho/{plan['id']}/installments").json()["rows"]

    first = rows[0]["installment_id"]
    assert client.post(f"{API}/patient-plan-installments/{first}/post").status_code == 201

    r = client.put(f"{API}/payment-plans/ortho/{plan['id']}/installments", json={
        "installments": [
            {"periodic_order": 1, "periodic_date": "2026-08-01", "periodic_amt": 999},
            {"periodic_order": 2, "periodic_date": "2026-09-01", "periodic_amt": 50},
        ]
    })
    assert r.status_code == 200, r.text
    out = {row["periodic_order"]: row for row in r.json()["rows"]}
    # The posted instalment is ledger history — it survives untouched.
    assert out[1]["is_billed"] is True
    assert Decimal(out[1]["periodic_amt"]) == Decimal("100.00")
    assert Decimal(out[2]["periodic_amt"]) == Decimal("50.00")
    assert len(out) == 2


def test_regular_contract_schedule(client, patient, office, codes):
    plan = _regular_plan(client, patient, office)
    body = client.post(
        f"{API}/payment-plans/regular/{plan['id']}/installments/generate", json={}
    ).json()
    assert len(body["rows"]) == 12
    assert Decimal(body["terms"]["periodic_amt"]) == Decimal("100.00")
    assert body["rows"][0]["billing_code"] == "ACBIL"


# ── PP-2: posting a periodic instalment to the ledger ───────────────────────
def test_pp2_post_installment_writes_a_real_charge(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider)
    client.post(f"{API}/payment-plans/ortho/{plan['id']}/installments/generate", json={})
    row = client.get(f"{API}/payment-plans/ortho/{plan['id']}/installments").json()["rows"][0]

    before = client.get(f"{API}/patients/{patient}/balance").json()["balance"]

    r = client.post(f"{API}/patient-plan-installments/{row['installment_id']}/post")
    assert r.status_code == 201, r.text
    posted = r.json()
    assert posted["procedure_code"] == "D8670"
    assert Decimal(posted["amount"]) == Decimal("100.00")
    assert posted["provider_id"] == provider
    assert posted["office_id"] == office
    assert posted["post_date"] == "2026-08-01"

    # The charge exists in the ledger and the cached balance moved.
    proc = client.get(f"{API}/patient-procedures/{posted['ledger_id']}")
    assert proc.status_code == 200
    assert float(proc.json()["fee"]) == 100.0
    after = client.get(f"{API}/patients/{patient}/balance").json()["balance"]
    assert after == before + 100.0

    # is_billed / ledger_id are stamped (they were dead columns before PP-2).
    stored = client.get(f"{API}/patient-plan-installments/{row['installment_id']}").json()
    assert stored["is_billed"] is True
    assert stored["ledger_id"] == posted["ledger_id"]


def test_pp2_post_is_not_repeatable(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider)
    client.post(f"{API}/payment-plans/ortho/{plan['id']}/installments/generate", json={})
    row_id = client.get(
        f"{API}/payment-plans/ortho/{plan['id']}/installments"
    ).json()["rows"][0]["installment_id"]

    assert client.post(f"{API}/patient-plan-installments/{row_id}/post").status_code == 201
    again = client.post(f"{API}/patient-plan-installments/{row_id}/post")
    assert again.status_code == 409
    assert "already been posted" in again.json()["error"]["message"]


def test_pp2_post_insurance_installment(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider)
    r = client.post(f"{API}/patient-ins-payment-plans", json={
        "patient_id": patient, "ortho_plan_id": plan["id"], "periodic_order": 1,
        "periodic_date": "2026-08-01", "periodic_amt": 75, "billing_code": "D8670",
    })
    row_id = r.json()["id"]

    posted = client.post(f"{API}/patient-ins-payment-plans/{row_id}/post")
    assert posted.status_code == 201, posted.text
    assert posted.json()["source"] == "ins"
    # An insurance instalment is owed by the carrier, not the patient.
    proc = client.get(f"{API}/patient-procedures/{posted.json()['ledger_id']}").json()
    assert float(proc["insurance_estimate"]) == 75.0
    assert float(proc["patient_estimate"]) == 0.0


def test_pp2_post_reports_why_it_cannot_post(client, patient, office, codes):
    """No provider anywhere on the contract or the patient → an explicit 422."""
    r = client.post(f"{API}/patients", json={"first_name": "No", "last_name": "Provider"})
    orphan = r.json()["id"]
    row = client.post(f"{API}/patient-plan-installments", json={
        "patient_id": orphan, "periodic_order": 1, "periodic_date": "2026-08-01",
        "periodic_amt": 50, "billing_code": "ACBIL",
    }).json()

    failed = client.post(f"{API}/patient-plan-installments/{row['id']}/post")
    assert failed.status_code == 422
    assert "provider" in failed.json()["error"]["message"]


def test_pp2_post_due_batch(client, patient, office, provider, codes):
    # 4 monthly instalments starting 60 days ago → exactly 2 are due today.
    plan = _ortho_plan(client, patient, office, provider,
                       pat_first_due_date=str(date.today() - timedelta(days=60)),
                       pat_num_payments=4)
    client.post(f"{API}/payment-plans/ortho/{plan['id']}/installments/generate", json={})

    dry = client.post(f"{API}/payment-plans/post-due", json={
        "patient_id": patient, "dry_run": True,
    })
    assert dry.status_code == 200, dry.text
    assert len(dry.json()["posted"]) == 2
    assert dry.json()["dry_run"] is True
    # Nothing was actually written.
    rows = client.get(f"{API}/payment-plans/ortho/{plan['id']}/installments").json()["rows"]
    assert all(not r["is_billed"] for r in rows)

    real = client.post(f"{API}/payment-plans/post-due", json={"patient_id": patient})
    assert len(real.json()["posted"]) == 2
    assert Decimal(real.json()["total_posted_amount"]) == Decimal("1200.00")  # 2 × 2400/4
    rows = client.get(f"{API}/payment-plans/ortho/{plan['id']}/installments").json()["rows"]
    assert [r["is_billed"] for r in rows] == [True, True, False, False]

    # Re-running is a no-op: nothing is double-charged.
    rerun = client.post(f"{API}/payment-plans/post-due", json={"patient_id": patient})
    assert rerun.json()["posted"] == []


def test_pp2_post_due_skips_without_aborting(client, patient, office, provider, codes):
    """A row that cannot post lands in `skipped`; the rest of the sweep continues."""
    good = _ortho_plan(client, patient, office, provider)
    client.post(f"{API}/payment-plans/ortho/{good['id']}/installments/generate", json={
        "num_payments": 1, "first_due_date": "2026-01-01", "amount_financed": 100,
    })
    client.post(f"{API}/patient-plan-installments", json={
        "patient_id": patient, "periodic_order": 1, "periodic_date": "2026-01-01",
        "periodic_amt": 50, "billing_code": "NOSUCHCODE",
    })

    out = client.post(f"{API}/payment-plans/post-due", json={"patient_id": patient}).json()
    assert len(out["posted"]) == 1
    assert len(out["skipped"]) == 1
    assert "NOSUCHCODE" in out["skipped"][0]["reason"]


# ── PP-3: server-rendered contract / coupons ────────────────────────────────
def test_pp3_contract_payload(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider, financial_disclosure="STD")
    client.post(f"{API}/definitions", json={
        "group_code": "financial_disclosure", "key1": "STD",
        "description": "Standard Truth-in-Lending disclosure",
    })
    client.post(f"{API}/payment-plans/ortho/{plan['id']}/installments/generate", json={})

    r = client.get(f"{API}/payment-plans/ortho/{plan['id']}/contract")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["party"]["patient_name"] == "Rob, Leo"
    assert body["provider_name"] == "Jinna, Dhileep DMD"
    assert body["office_name"] == "Main"
    assert body["initial_billing_code"] == "D8080"
    assert body["disclosure_text"] == "Standard Truth-in-Lending disclosure"
    assert Decimal(body["terms"]["total_of_payments"]) == Decimal("2400.00")
    assert len(body["rows"]) == 24


def test_pp3_contract_falls_back_to_a_projection(client, patient, office, codes):
    """No persisted schedule yet → the contract still prints the amortisation."""
    plan = _regular_plan(client, patient, office)
    body = client.get(f"{API}/payment-plans/regular/{plan['id']}/contract").json()
    assert len(body["rows"]) == 12


def test_pp3_contract_and_coupon_pdfs(client, patient, office, provider, codes):
    pytest.importorskip("reportlab")
    plan = _ortho_plan(client, patient, office, provider)
    client.post(f"{API}/payment-plans/ortho/{plan['id']}/installments/generate", json={})

    for path in ("contract.pdf", "coupons.pdf"):
        r = client.get(f"{API}/payment-plans/ortho/{plan['id']}/{path}")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")
        assert len(r.content) > 1000


def test_contract_404s_for_another_tenant(client, patient, office, provider, codes):
    plan = _ortho_plan(client, patient, office, provider)
    assert client.get(f"{API}/payment-plans/ortho/{plan['id'] + 999}/contract").status_code == 404
    assert client.get(f"{API}/payment-plans/regular/{plan['id']}/contract").status_code == 404
