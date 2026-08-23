"""Account Ledger second pass — AL-6 / AL-8 / AL-9 / AL-10 / AL-11 / AL-12.

AL-9 is the one worth spelling out. ``patient_payments.amount`` carries two sign
conventions (migrated rows are negative, app-created rows positive), and the old
arithmetic double-negated the migrated half: a payment made the running balance go
*up* and ``/balance`` overstated the account by twice the payments. These tests pin
the settled rule from both directions, so a future refactor cannot quietly
reintroduce it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.db.models import (
    InsuranceClaim,
    Office,
    Patient,
    PatientPayment,
    PatientProcedure,
    ProcedureCode,
    Provider,
    ResponsibleParty,
)
from app.services import balance_service, ledger_service, procedure_totals_service
from app.services.ledger_sign import payment_credit, payment_debit, payment_delta

PREFIX = "/api/v1"
RP_KEY = "RP-LEDGER-1"


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="ALX", name="Ledger Office",
               short_id="ALX")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    pr = Provider(id="PRV-AL", tenant_id=db_session._tenant_id, office_id=office.id,
                  name="Dr Ledger", short_id="LDGR")
    db_session.add(pr)
    db_session.commit()
    db_session.refresh(pr)
    return pr


@pytest.fixture(autouse=True)
def proc_code(db_session) -> str:
    code = ProcedureCode(code="D2750", description="Crown", category="Restorative")
    db_session.add(code)
    db_session.commit()
    return code.code


@pytest.fixture
def anchor(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ada", last_name="Anchor",
                chart_no="AL-A", is_active=True, responsible_party_id=RP_KEY)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def sibling(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Bob", last_name="Sibling",
                chart_no="AL-B", is_active=True, responsible_party_id=RP_KEY)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _charge(db_session, patient, office, provider, *, fee, dos, row_id, **extra):
    defaults = {
        "insurance_estimate": Decimal("0"), "patient_estimate": Decimal("0"),
        "billing_status": "not_billed", "hold_claim": False,
    }
    row = PatientProcedure(
        id=row_id, patient_id=patient.id, office_id=office.id, provider_id=provider.id,
        procedure_code="D2750", fee=Decimal(str(fee)), date_of_service=dos,
        is_void=False, is_archived=False, **{**defaults, **extra},
    )
    db_session.add(row)
    db_session.commit()
    return row


def _payment(db_session, patient, office, *, amount, pdate, row_id, payment_type="patient"):
    row = PatientPayment(
        id=row_id, patient_id=patient.id, office_id=office.id, amount=Decimal(str(amount)),
        payment_date=pdate, payment_type=payment_type, is_void=False, is_archived=False,
    )
    db_session.add(row)
    db_session.commit()
    return row


# ── AL-9: the sign convention ────────────────────────────────────────────────
def test_payment_sign_rule_is_direction_not_magnitude():
    # A payment credits the account whichever sign it is stored with.
    assert payment_delta("-266.25", "patient") == Decimal("-266.25")
    assert payment_delta("266.25", "patient") == Decimal("-266.25")
    assert payment_credit("-266.25", "insurance") == Decimal("266.25")
    assert payment_debit("-266.25", "insurance") == Decimal("0")
    # An adjustment is genuinely two-way, so its stored sign is the intent.
    assert payment_delta("-50", "adjustment") == Decimal("-50")
    assert payment_delta("50", "adjustment") == Decimal("50")
    assert payment_debit("50", "adjustment") == Decimal("50")
    assert payment_credit("50", "adjustment") == Decimal("0")


@pytest.mark.parametrize("stored", ["-417.50", "417.50"])
def test_balance_is_charges_minus_payments_under_either_sign(
    db_session, anchor, office, provider, stored
):
    """The report's case: charged 1093.00, paid 417.50 → 675.50, never 1510.50."""
    _charge(db_session, anchor, office, provider, fee=1093, dos=date(2025, 1, 1), row_id="ALC1")
    _payment(db_session, anchor, office, amount=stored, pdate=date(2025, 2, 1), row_id="ALP1")

    balance = balance_service.get_patient_balance(db_session, anchor.id, db_session._tenant_id)
    assert balance["total_charged"] == 1093.0
    assert balance["total_paid"] == 417.5      # reported positive, not signed
    assert balance["balance"] == 675.5


@pytest.mark.parametrize("stored", ["-500.00", "500.00"])
def test_feed_amount_is_signed_and_payment_lowers_the_running_balance(
    db_session, anchor, office, provider, stored
):
    _charge(db_session, anchor, office, provider, fee=1000, dos=date(2025, 3, 1), row_id="ALC2")
    _payment(db_session, anchor, office, amount=stored, pdate=date(2025, 3, 2), row_id="ALP2")

    feed = ledger_service.get_account_ledger(db_session, anchor.id, db_session._tenant_id)
    charge, payment = feed["rows"]
    assert charge["amount"] == Decimal("1000.00")
    assert charge["running_balance"] == Decimal("1000.00")
    # credit is a magnitude; amount is signed; the balance goes DOWN.
    assert payment["credit"] == Decimal("500.00")
    assert payment["amount"] == Decimal("-500.00")
    assert payment["running_balance"] == Decimal("500.00")
    assert payment["transaction_kind"] == "C"
    assert feed["grand_total"] == Decimal("500.00")


def test_debit_adjustment_posted_as_payment_is_a_charge(db_session, anchor, office, provider):
    _charge(db_session, anchor, office, provider, fee=100, dos=date(2025, 4, 1), row_id="ALC3")
    _payment(db_session, anchor, office, amount="40", pdate=date(2025, 4, 2),
             row_id="ALP3", payment_type="adjustment")

    feed = ledger_service.get_account_ledger(db_session, anchor.id, db_session._tenant_id)
    assert feed["grand_total"] == Decimal("140.00")
    assert feed["rows"][1]["transaction_kind"] == "P"

    balance = balance_service.get_patient_balance(db_session, anchor.id, db_session._tenant_id)
    assert balance["total_charged"] == 140.0
    assert balance["total_paid"] == 0.0
    assert balance["balance"] == 140.0
    assert balance["total_payment_debits"] == 40.0


# ── AL-8: claim rows ─────────────────────────────────────────────────────────
def test_claim_events_are_interleaved_and_do_not_move_the_balance(
    db_session, anchor, office, provider
):
    _charge(db_session, anchor, office, provider, fee=200, dos=date(2025, 5, 1), row_id="ALC4")
    db_session.add(InsuranceClaim(
        id="CLM-AL1", patient_id=anchor.id, office_id=office.id, claim_number="AL1",
        status="closed", claim_type="primary", billing_order="primary",
        total_billed=Decimal("70.00"), total_paid=Decimal("70.00"),
        submitted_date=date(2025, 5, 2), close_date=date(2025, 5, 20),
    ))
    db_session.commit()

    plain = ledger_service.get_account_ledger(db_session, anchor.id, db_session._tenant_id)
    assert plain["total"] == 1  # opt-in — an existing caller sees no new rows

    feed = ledger_service.get_account_ledger(
        db_session, anchor.id, db_session._tenant_id, include_claims=True
    )
    claims = [r for r in feed["rows"] if r["source_type"] == "claim"]
    assert [c["claim_event"] for c in claims] == ["submitted", "closed"]
    assert {c["code"] for c in claims} == {"CLM-P"}
    assert claims[0]["description"] == "Pri Claim - Sent"
    assert claims[0]["claim_number"] == "AL1"
    assert claims[0]["transaction_kind"] == "I"
    # Informational: the money arrived as an insurance payment, not here.
    assert all(c["amount"] == Decimal("0") for c in claims)
    assert feed["grand_total"] == Decimal("200.00")

    only = ledger_service.get_account_ledger(
        db_session, anchor.id, db_session._tenant_id,
        include_claims=True, transaction_type="claim",
    )
    assert only["total"] == 2 and all(r["source_type"] == "claim" for r in only["rows"])


# ── AL-10: user attribution ──────────────────────────────────────────────────
def test_user_label_falls_back_to_the_legacy_login(db_session, anchor, office, provider):
    _charge(db_session, anchor, office, provider, fee=10, dos=date(2025, 6, 1),
            row_id="ALC5", created_by_legacy="AUDRAG")
    feed = ledger_service.get_account_ledger(db_session, anchor.id, db_session._tenant_id)
    assert feed["rows"][0]["user_label"] == "AUDRAG"


# ── AL-6: duration + unbilled ────────────────────────────────────────────────
def test_duration_and_unbilled_reflect_the_backfilled_columns(
    db_session, anchor, office, provider
):
    db_session.add(InsuranceClaim(
        id="CLM-AL2", patient_id=anchor.id, office_id=office.id, claim_number="AL2",
        status="closed", claim_type="primary", billing_order="primary",
    ))
    db_session.commit()
    _charge(db_session, anchor, office, provider, fee=10, dos=date(2025, 7, 1),
            row_id="ALC6", duration_minutes=45, claim_id="CLM-AL2")
    _charge(db_session, anchor, office, provider, fee=10, dos=date(2025, 7, 2), row_id="ALC7")

    rows = ledger_service.get_account_ledger(
        db_session, anchor.id, db_session._tenant_id)["rows"]
    billed, unbilled = rows
    assert billed["duration_minutes"] == 45
    assert billed["unbilled"] is False and billed["claim_id"] == "CLM-AL2"
    # Null duration means "not recorded" — never coerced to 0.
    assert unbilled["duration_minutes"] is None
    assert unbilled["unbilled"] is True


# ── AL-11: account (family) scope ────────────────────────────────────────────
def test_account_scope_merges_members_and_pages_server_side(
    db_session, anchor, sibling, office, provider
):
    _charge(db_session, anchor, office, provider, fee=100, dos=date(2025, 8, 1), row_id="ALC8")
    _charge(db_session, sibling, office, provider, fee=300, dos=date(2025, 8, 2), row_id="ALC9")
    _payment(db_session, sibling, office, amount="-50", pdate=date(2025, 8, 3), row_id="ALP4")

    patient_only = ledger_service.get_account_ledger(
        db_session, anchor.id, db_session._tenant_id)
    assert patient_only["total"] == 1
    assert patient_only["scope"] == "patient"

    account = ledger_service.get_account_ledger(
        db_session, anchor.id, db_session._tenant_id, scope="account")
    assert account["total"] == 3
    assert sorted(account["patient_ids"]) == sorted([anchor.id, sibling.id])
    assert account["responsible_party_id"] == RP_KEY
    # The running balance is recomputed across the merged multi-patient feed.
    assert [r["running_balance"] for r in account["rows"]] == [
        Decimal("100.00"), Decimal("400.00"), Decimal("350.00")]
    assert account["grand_total"] == Decimal("350.00")
    assert account["rows"][1]["patient_id"] == sibling.id
    assert account["rows"][1]["patient_name"] == "Bob Sibling"

    paged = ledger_service.get_account_ledger(
        db_session, anchor.id, db_session._tenant_id, scope="account", page=2, size=2)
    assert paged["pages"] == 2 and len(paged["rows"]) == 1


def test_account_balance_aggregates_members(db_session, anchor, sibling, office, provider):
    _charge(db_session, anchor, office, provider, fee=100, dos=date(2025, 9, 1), row_id="ALC10")
    _charge(db_session, sibling, office, provider, fee=300, dos=date(2025, 9, 2), row_id="ALC11")
    _payment(db_session, sibling, office, amount="-50", pdate=date(2025, 9, 3), row_id="ALP5")

    out = balance_service.get_account_balance(db_session, anchor.id, db_session._tenant_id)
    assert out["member_count"] == 2
    assert out["total_charged"] == 400.0
    assert out["total_paid"] == 50.0
    assert out["balance"] == 350.0
    assert {m["patient_id"] for m in out["members"]} == {anchor.id, sibling.id}
    assert out["members"][0]["patient_name"] == "Ada Anchor"


def test_account_ledger_scope_endpoint(client, anchor, sibling, office, provider, db_session):
    _charge(db_session, sibling, office, provider, fee=25, dos=date(2025, 10, 1), row_id="ALC12")
    r = client.get(f"{PREFIX}/patients/{anchor.id}/account-ledger?scope=account")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"] == "account"
    assert body["rows"][0]["patient_id"] == sibling.id


# ── AL-12: responsible party / primary insurance in the patient context ──────
def test_patient_context_carries_responsible_party(client, db_session, anchor):
    rp = ResponsibleParty(tenant_id=db_session._tenant_id, legacy_id=RP_KEY,
                          first_name="Rita", last_name="Payer")
    db_session.add(rp)
    db_session.commit()

    r = client.get(f"{PREFIX}/patients/{anchor.id}/context")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["responsible_party_id"] == RP_KEY
    assert body["responsible_party"]["name"] == "Rita Payer"
    assert body["responsible_party"]["legacy_id"] == RP_KEY
    assert body["primary_insurance"] is None  # no active plan on this patient


# ── AL-14: descriptions are plain text, never money-prefixed ─────────────────
def test_migrated_money_prefix_is_stripped_from_descriptions(
    db_session, anchor, office, provider
):
    """Some migrated notes arrive as "$-89 Payment - Insurance Check No: …", which
    the grid then prefixed again into "$0 $-89 Payment - …"."""
    _payment(db_session, anchor, office, amount="-89", pdate=date(2026, 1, 5), row_id="ALP6")
    row = db_session.get(PatientPayment, "ALP6")
    row.notes = "$-89 Payment - Insurance Check No: 78687655 Notes:"
    db_session.commit()

    feed = ledger_service.get_account_ledger(db_session, anchor.id, db_session._tenant_id)
    assert feed["rows"][0]["description"] == "Payment - Insurance Check No: 78687655 Notes:"


def test_a_description_that_is_only_an_amount_is_kept(db_session, anchor, office, provider):
    _payment(db_session, anchor, office, amount="-5", pdate=date(2026, 1, 6), row_id="ALP7")
    row = db_session.get(PatientPayment, "ALP7")
    row.notes = "$25.00"
    db_session.commit()
    feed = ledger_service.get_account_ledger(db_session, anchor.id, db_session._tenant_id)
    # Stripping would leave an empty cell, which is worse than the prefix.
    assert feed["rows"][0]["description"] == "$25.00"


# ── AL-17: hold_claim ────────────────────────────────────────────────────────
def test_hold_claim_is_on_the_feed_and_filterable(client, db_session, anchor, office, provider):
    _charge(db_session, anchor, office, provider, fee=10, dos=date(2026, 2, 1),
            row_id="ALC13", hold_claim=True)
    _charge(db_session, anchor, office, provider, fee=10, dos=date(2026, 2, 2), row_id="ALC14")

    rows = ledger_service.get_account_ledger(
        db_session, anchor.id, db_session._tenant_id)["rows"]
    assert [r["hold_claim"] for r in rows] == [True, False]

    r = client.get(f"{PREFIX}/patient-procedures?patient_id={anchor.id}&hold_claim=true")
    assert r.status_code == 200, r.text
    assert [i["id"] for i in r.json()["items"]] == ["ALC13"]


# ── AL-15: the roll-ups and the outstanding line ─────────────────────────────
def test_outstanding_uses_the_legacy_pat_amounts(client, db_session, anchor, office, provider):
    """`payment_allocations` cannot supply these — the source export's AMOUNT is
    0.0000 on every row (AL-16) — so the LEDGER scalars are the only record."""
    _charge(db_session, anchor, office, provider, fee=75, dos=date(2026, 3, 1),
            row_id="ALC15", insurance_estimate=Decimal("25"),
            pat_paid=Decimal("20"), pat_adjust=Decimal("5"))

    r = client.get(f"{PREFIX}/patient-procedures/ALC15/allocations-summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(body["paid_to_date"]) == Decimal("20")
    assert Decimal(body["adjusted_to_date"]) == Decimal("5")
    # patient share = fee − insurance_estimate (no patient_estimate was recorded)
    assert Decimal(body["remaining_amount"]) == Decimal("25")
    assert Decimal(body["outstanding_amount"]) == Decimal("50")  # 75 − 20 − 0 − 5


def test_remaining_amount_is_not_zero_when_no_estimate_was_recorded(
    client, db_session, anchor, office, provider
):
    """The reported symptom: fee 75.00, nothing paid, remaining_amount "0"."""
    _charge(db_session, anchor, office, provider, fee=75, dos=date(2026, 3, 2),
            row_id="ALC16", insurance_estimate=Decimal("25"))
    body = client.get(f"{PREFIX}/patient-procedures/ALC16/allocations-summary").json()
    assert Decimal(body["remaining_amount"]) == Decimal("50")
    assert Decimal(body["outstanding_amount"]) == Decimal("75")


def test_an_allocation_still_beats_the_legacy_scalar(db_session, anchor, office, provider):
    from app.db.models import PaymentAllocation

    _charge(db_session, anchor, office, provider, fee=100, dos=date(2026, 3, 3),
            row_id="ALC17", pat_paid=Decimal("10"))
    _payment(db_session, anchor, office, amount="-40", pdate=date(2026, 3, 3), row_id="ALP8")
    db_session.add(PaymentAllocation(
        patient_id=anchor.id, procedure_id="ALC17", payment_id="ALP8",
        alloc_date=date(2026, 3, 3), amount=Decimal("40"),
    ))
    db_session.commit()

    totals = procedure_totals_service.applied_totals(db_session, ["ALC17"])["ALC17"]
    assert totals["paid_to_date"] == Decimal("40")  # the split wins, not the scalar


# ── AL-13: the Modified By/On pair ───────────────────────────────────────────
def test_modified_audit_pair_is_stamped_and_exposed(client, db_session, anchor, office, provider):
    _charge(db_session, anchor, office, provider, fee=10, dos=date(2026, 4, 1), row_id="ALC18")
    r = client.patch(f"{PREFIX}/patient-procedures/ALC18", json={"fee": 20})
    assert r.status_code == 200, r.text
    assert r.json()["updated_at"] is not None

    db_session.expire_all()
    row = ledger_service.get_account_ledger(
        db_session, anchor.id, db_session._tenant_id)["rows"][0]
    assert row["updated_at"] is not None


# ── AL-17: Hold Claim is enforced on every write path, not just in the grid ──
def test_a_held_charge_cannot_be_claimed(client, db_session, anchor, office, provider):
    db_session.add(InsuranceClaim(
        id="CLM-AL3", patient_id=anchor.id, office_id=office.id, claim_number="AL3",
        status="draft", claim_type="primary", billing_order="primary",
    ))
    db_session.commit()
    _charge(db_session, anchor, office, provider, fee=10, dos=date(2026, 5, 1),
            row_id="ALC19", hold_claim=True)

    r = client.patch(f"{PREFIX}/patient-procedures/ALC19", json={"claim_id": "CLM-AL3"})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "procedure_on_hold_claim"

    # Lifting the hold in the same call is a normal thing to do, and works.
    r = client.patch(
        f"{PREFIX}/patient-procedures/ALC19",
        json={"claim_id": "CLM-AL3", "hold_claim": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["claim_id"] == "CLM-AL3"


def test_the_guard_only_blocks_claim_assignment(client, db_session, anchor, office, provider):
    _charge(db_session, anchor, office, provider, fee=10, dos=date(2026, 5, 2),
            row_id="ALC20", hold_claim=True)
    # Editing a held charge is untouched — only stamping a claim on it is refused.
    assert client.patch(f"{PREFIX}/patient-procedures/ALC20", json={"fee": 30}).status_code == 200
    assert client.patch(
        f"{PREFIX}/patient-procedures/ALC20", json={"claim_id": None}
    ).status_code == 200
