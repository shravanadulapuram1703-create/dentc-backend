"""Insurance Payment window backend gaps (INS-PAY-1 … INS-PAY-8).

Reply to ``docs/patient-insurance/insurance_payment_backend_devreport.md``.

INS-PAY-2 is the critical one and gets the most coverage: a posted remittance
could not be backed out, and ``recalculate`` echoed ``total_paid`` instead of
deriving it, so a mis-keyed payment overstated the carrier's money permanently.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import Office, Patient, Provider

PREFIX = "/api/v1"
TODAY = date.today().isoformat()


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="IP1", name="Ins Pay Office",
               short_id="IP1")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def patient(db_session, office) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ins", last_name="Payee",
                chart_no="IP-PAT", home_office_id=office.id, is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def provider(db_session, office) -> Provider:
    pr = Provider(id="IPPRV", tenant_id=db_session._tenant_id, office_id=office.id,
                  name="Dr Pay", short_id="DRIP")
    db_session.add(pr)
    db_session.commit()
    db_session.refresh(pr)
    return pr


@pytest.fixture
def proc_code(client):
    r = client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D0150", "description": "Comprehensive exam", "category": "Diagnostic",
        "default_fee": 77})
    assert r.status_code == 201, r.text
    return "D0150"


def _claim(client, patient, office, claim_id="CLM-IP", status="sent", **extra):
    r = client.post(f"{PREFIX}/insurance-claims", json={
        "id": claim_id, "patient_id": patient.id, "office_id": office.id,
        "claim_number": claim_id, "status": status, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _proc(client, patient, office, provider, code, fee, item_id, claim_id=None, **extra):
    body = {"id": item_id, "patient_id": patient.id, "office_id": office.id,
            "provider_id": provider.id, "procedure_code": code, "fee": fee,
            "date_of_service": TODAY, **extra}
    if claim_id:
        body["claim_id"] = claim_id
    r = client.post(f"{PREFIX}/patient-procedures", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _paid(client, claim_id) -> float:
    return float(client.get(f"{PREFIX}/insurance-claims/{claim_id}").json()["total_paid"])


def _post(client, patient, claim_id, office, **amounts):
    r = client.post(f"{PREFIX}/ledger-insurance-details/payment", json={
        "patient_id": patient.id, "claim_id": claim_id, "office_id": office.id,
        "payment_method": "check", "check_number": "CHK-77012", **amounts})
    assert r.status_code == 201, r.text
    return r.json()


# ── INS-PAY-1: the remittance note has a home ────────────────────────────────
def test_remittance_notes_persist_on_the_coverage_row(client, patient, office):
    claim = _claim(client, patient, office)
    body = _post(client, patient, claim["id"], office,
                 prim_ins_paid=100, notes="Short-paid, see EOB page 2")
    assert body["notes"] == "Short-paid, see EOB page 2"

    # …and reads back off the row, not off the claim's own notes.
    row = client.get(f"{PREFIX}/ledger-insurance-details/{body['id']}").json()
    assert row["notes"] == "Short-paid, see EOB page 2"
    assert client.get(f"{PREFIX}/insurance-claims/{claim['id']}").json()["notes"] is None


# ── INS-PAY-2: total_paid is derived, and a payment can be reversed ──────────
def test_recalculate_derives_total_paid_from_live_rows(
    client, patient, office, provider, proc_code,
):
    claim = _claim(client, patient, office)
    _proc(client, patient, office, provider, proc_code, 224, "IP-P1",
          claim_id=claim["id"], insurance_estimate=224)

    for amount in (51.56, 46.88, 51.56):
        _post(client, patient, claim["id"], office, prim_ins_paid=amount)
    assert _paid(client, claim["id"]) == 150.0

    # The exact scenario from the report: delete the rows, then recalculate.
    for row in client.get(f"{PREFIX}/ledger-insurance-details",
                          params={"claim_id": claim["id"]}).json()["items"]:
        assert client.delete(f"{PREFIX}/ledger-insurance-details/{row['id']}").status_code == 204

    recalc = client.post(f"{PREFIX}/insurance-claims/{claim['id']}/recalculate")
    assert recalc.status_code == 200, recalc.text
    body = recalc.json()
    # It used to still report 150.00 with zero coverage rows behind it.
    assert float(body["total_paid"]) == 0.0
    assert body["coverage_row_count"] == 0
    assert float(body["total_billed"]) == 224.0


def test_migrated_paid_total_survives_derivation(client, patient, office):
    """The regression deriving ``total_paid`` would otherwise have caused.

    79,038 migrated claims carry a paid total that came from the Denticon export
    with no coverage row behind it. Deriving from rows alone zeroes every one of
    them the first time someone hits Recalculate, so the legacy money is held in
    ``opening_paid`` and **added** to what this system posts.
    """
    claim = _claim(client, patient, office)
    # Stand in for a migrated claim: money on the claim, nothing backing it.
    client.patch(f"{PREFIX}/insurance-claims/{claim['id']}",
                 json={"total_paid": 500, "opening_paid": 500})

    recalc = client.post(f"{PREFIX}/insurance-claims/{claim['id']}/recalculate").json()
    assert float(recalc["total_paid"]) == 500.0
    assert float(recalc["opening_paid"]) == 500.0
    assert float(recalc["posted_paid"]) == 0.0

    # A payment posted now *adds* to the legacy total rather than replacing it.
    row = _post(client, patient, claim["id"], office, prim_ins_paid=150)
    assert _paid(client, claim["id"]) == 650.0

    # …and reversing that payment returns to the legacy baseline, not to zero.
    client.post(f"{PREFIX}/ledger-insurance-details/{row['id']}/reverse",
                json={"reason": "keyed twice"})
    assert _paid(client, claim["id"]) == 500.0


def test_delete_is_a_void_that_keeps_the_row_and_fixes_the_claim(client, patient, office):
    claim = _claim(client, patient, office)
    row = _post(client, patient, claim["id"], office, prim_ins_paid=150)

    assert client.delete(f"{PREFIX}/ledger-insurance-details/{row['id']}").status_code == 204
    # The claim is corrected immediately — no recalculate needed.
    assert _paid(client, claim["id"]) == 0.0
    # The evidence survives its own correction.
    assert client.get(f"{PREFIX}/ledger-insurance-details/{row['id']}").json()["is_void"] is True
    listed = client.get(f"{PREFIX}/ledger-insurance-details",
                        params={"claim_id": claim["id"]}).json()
    assert listed["meta"]["total"] == 0
    voided = client.get(f"{PREFIX}/ledger-insurance-details",
                        params={"claim_id": claim["id"], "is_void": True}).json()
    assert voided["meta"]["total"] == 1


def test_reverse_insurance_payment(client, patient, office):
    claim = _claim(client, patient, office)
    row = _post(client, patient, claim["id"], office, prim_ins_paid=150, sec_ins_paid=25)
    assert _paid(client, claim["id"]) == 175.0

    r = client.post(f"{PREFIX}/ledger-insurance-details/{row['id']}/reverse",
                    json={"reason": "Posted against the wrong claim"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["reversed_amount"]) == 175.0
    assert float(body["claim"]["total_paid"]) == 0.0

    stored = client.get(f"{PREFIX}/ledger-insurance-details/{row['id']}").json()
    assert stored["is_void"] is True
    assert stored["void_reason"] == "Posted against the wrong claim"
    # A claim nobody has paid must not still say "paid".
    assert client.get(f"{PREFIX}/insurance-claims/{claim['id']}").json()["status"] != "paid"


def test_reverse_is_idempotent_guarded_and_needs_a_reason(client, patient, office):
    claim = _claim(client, patient, office)
    row = _post(client, patient, claim["id"], office, prim_ins_paid=50)

    blank = client.post(f"{PREFIX}/ledger-insurance-details/{row['id']}/reverse",
                        json={"reason": "   "})
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "reason_required"

    assert client.post(f"{PREFIX}/ledger-insurance-details/{row['id']}/reverse",
                       json={"reason": "keyed twice"}).status_code == 200
    again = client.post(f"{PREFIX}/ledger-insurance-details/{row['id']}/reverse",
                        json={"reason": "keyed twice"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_reversed"


def test_reversing_one_line_leaves_the_others_standing(client, patient, office):
    claim = _claim(client, patient, office)
    rows = [_post(client, patient, claim["id"], office, prim_ins_paid=a)
            for a in (51.56, 46.88, 51.56)]
    client.post(f"{PREFIX}/ledger-insurance-details/{rows[1]['id']}/reverse",
                json={"reason": "duplicate line"})
    assert float(
        client.get(f"{PREFIX}/insurance-claims/{claim['id']}").json()["total_paid"]
    ) == 103.12


# ── INS-PAY-3: a multi-line remittance is one transaction ────────────────────
def test_batch_post_is_atomic_and_reconciles(client, patient, office, provider, proc_code):
    claim = _claim(client, patient, office)
    for i, fee in enumerate((77, 70, 77), start=1):
        _proc(client, patient, office, provider, proc_code, fee, f"IP-B{i}",
              claim_id=claim["id"], insurance_estimate=fee)

    r = client.post(f"{PREFIX}/ledger-insurance-details/payment-batch", json={
        "patient_id": patient.id, "claim_id": claim["id"], "office_id": office.id,
        "payment_method": "check", "check_number": "CHK-77012", "bank_number": "021000021",
        "eob_number": "EOB-55123", "notes": "cheque covers three lines",
        "payment_amount": 150.00,
        "lines": [
            {"procedure_id": "IP-B1", "prim_ins_paid": 51.56, "prim_ins_adjust": 7.70},
            {"procedure_id": "IP-B2", "prim_ins_paid": 46.88, "prim_ins_adjust": 7.00},
            {"procedure_id": "IP-B3", "prim_ins_paid": 51.56, "prim_ins_adjust": 7.70},
        ],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["lines"]) == 3
    assert float(body["allocated"]) == 150.0
    assert float(body["claim"]["total_paid"]) == 150.0
    # Header identifiers apply to every line without being repeated.
    assert {line["check_number"] for line in body["lines"]} == {"CHK-77012"}
    assert {line["eob_number"] for line in body["lines"]} == {"EOB-55123"}


def test_batch_rejects_an_unbalanced_remittance_before_writing(client, patient, office):
    claim = _claim(client, patient, office)
    r = client.post(f"{PREFIX}/ledger-insurance-details/payment-batch", json={
        "patient_id": patient.id, "claim_id": claim["id"],
        "payment_amount": 150.00,
        "lines": [{"prim_ins_paid": 100.00}],
    })
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "remittance_not_reconciled"
    assert err["details"]["unallocated"] == "50.00"
    # Nothing was written.
    assert client.get(f"{PREFIX}/ledger-insurance-details",
                      params={"claim_id": claim["id"]}).json()["meta"]["total"] == 0
    assert _paid(client, claim["id"]) == 0.0


def test_batch_rolls_back_when_a_later_line_is_invalid(
    client, patient, office, provider, proc_code,
):
    """The failure the window could not recover from: line 3 of 3 rejected."""
    claim = _claim(client, patient, office)
    _proc(client, patient, office, provider, proc_code, 77, "IP-R1", claim_id=claim["id"])

    r = client.post(f"{PREFIX}/ledger-insurance-details/payment-batch", json={
        "patient_id": patient.id, "claim_id": claim["id"],
        "lines": [
            {"procedure_id": "IP-R1", "prim_ins_paid": 50},
            {"procedure_id": "IP-R1", "prim_ins_paid": 25},
            {"procedure_id": "NOT-ON-THIS-CLAIM", "prim_ins_paid": 25},
        ],
    })
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "procedure_not_on_claim"
    # No half-paid claim: the first two lines are gone too.
    assert client.get(f"{PREFIX}/ledger-insurance-details",
                      params={"claim_id": claim["id"]}).json()["meta"]["total"] == 0
    assert _paid(client, claim["id"]) == 0.0


def test_negative_amounts_are_refused(client, patient, office):
    claim = _claim(client, patient, office)
    r = client.post(f"{PREFIX}/ledger-insurance-details/payment", json={
        "patient_id": patient.id, "claim_id": claim["id"], "prim_ins_paid": -50})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "negative_remittance_amount"


def test_batch_can_close_the_claim(client, patient, office):
    claim = _claim(client, patient, office)
    r = client.post(f"{PREFIX}/ledger-insurance-details/payment-batch", json={
        "patient_id": patient.id, "claim_id": claim["id"], "close_claim": True,
        "lines": [{"prim_ins_paid": 100}],
    })
    assert r.status_code == 201, r.text
    assert r.json()["claim"]["status"] == "closed"


# ── INS-PAY-4: the claim-level write-off intent is recorded ──────────────────
def test_claim_write_off_intent_survives_the_distribution(client, patient, office):
    claim = _claim(client, patient, office)
    r = client.post(f"{PREFIX}/ledger-insurance-details/payment-batch", json={
        "patient_id": patient.id, "claim_id": claim["id"],
        "write_off_mode": "percent", "write_off_value": 10,
        "lines": [
            {"prim_ins_paid": 51.56, "prim_ins_adjust": 7.70},
            {"prim_ins_paid": 46.88, "prim_ins_adjust": 7.00},
            {"prim_ins_paid": 51.56, "prim_ins_adjust": 7.70},
        ],
    })
    assert r.status_code == 201, r.text
    claim_out = r.json()["claim"]
    # "a 10% claim write-off" is still readable after being split across lines.
    assert claim_out["write_off_mode"] == "percent"
    assert float(claim_out["write_off_value"]) == 10.0
    assert float(claim_out["write_off_amount"]) == 22.40


# ── INS-PAY-5: the secondary and tertiary tiers post like the primary ────────
def test_all_three_tiers_are_writable(client, patient, office):
    claim = _claim(client, patient, office)
    body = _post(
        client, patient, claim["id"], office,
        prim_ins_paid=100, prim_deductible=50,
        sec_ins_paid=30, sec_ins_adjust=5, sec_deductible=10,
        ter_ins_paid=20, ter_ins_adjust=2, ter_deductible=5,
    )
    assert float(body["sec_deductible"]) == 10.0
    assert float(body["ter_ins_paid"]) == 20.0
    assert float(body["ter_ins_adjust"]) == 2.0
    assert float(body["ter_deductible"]) == 5.0
    # All three tiers count toward what the carrier has paid.
    assert _paid(client, claim["id"]) == 150.0


# ── INS-PAY-6: EOB / EFT identifiers on a patient-side payment ───────────────
def test_patient_payment_carries_eob_and_eft_trace(client, patient, office):
    """"Insurance Check to Previous Balance" posts an unallocated carrier cheque
    here, so it needs the same reconciliation identifiers."""
    r = client.post(f"{PREFIX}/patient-payments", json={
        "id": "PAY-IP1", "patient_id": patient.id, "office_id": office.id,
        "amount": 150, "payment_date": TODAY, "payment_type": "insurance",
        "payment_method": "eft", "eob_number": "EOB-55123", "eft_trace_number": "TRACE-9",
        "bank_number": "021000021",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["eob_number"] == "EOB-55123"
    assert body["eft_trace_number"] == "TRACE-9"


# ── INS-PAY-7: the outstanding-claims picker ─────────────────────────────────
def test_outstanding_claims_rollups(client, patient, office, provider, proc_code):
    open_claim = _claim(client, patient, office, claim_id="CLM-OPEN")
    _proc(client, patient, office, provider, proc_code, 224, "IP-O1",
          claim_id="CLM-OPEN", insurance_estimate=200)
    _post(client, patient, "CLM-OPEN", office, prim_ins_paid=80, prim_ins_adjust=20,
          prim_deductible=25)
    _claim(client, patient, office, claim_id="CLM-DONE", status="closed")

    r = client.get(f"{PREFIX}/patients/{patient.id}/outstanding-claims")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [row["claim_id"] for row in rows] == [open_claim["id"]]
    row = rows[0]
    assert float(row["total_charges"]) == 224.0
    assert float(row["est_insurance"]) == 200.0
    assert float(row["ins_paid"]) == 80.0
    assert float(row["ins_adjusted"]) == 20.0
    assert float(row["deductible_used"]) == 25.0
    assert float(row["remaining"]) == 100.0
    assert row["procedure_count"] == 1

    # Closed claims are opt-in.
    everything = client.get(f"{PREFIX}/patients/{patient.id}/outstanding-claims",
                            params={"include_closed": True}).json()
    assert {r_["claim_id"] for r_ in everything} == {"CLM-OPEN", "CLM-DONE"}


def test_outstanding_claims_excludes_voided_coverage(client, patient, office):
    _claim(client, patient, office, claim_id="CLM-VOID")
    row = _post(client, patient, "CLM-VOID", office, prim_ins_paid=90)
    client.post(f"{PREFIX}/ledger-insurance-details/{row['id']}/reverse",
                json={"reason": "wrong claim"})
    rows = client.get(f"{PREFIX}/patients/{patient.id}/outstanding-claims").json()
    assert float(rows[0]["ins_paid"]) == 0.0


def test_outstanding_claims_is_tenant_scoped(client, db_session, office):
    from app.db.models import Tenant

    other = Tenant(name="Other", code="oth", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    stranger = Patient(tenant_id=other.id, first_name="Not", last_name="Mine", is_active=True)
    db_session.add(stranger)
    db_session.commit()
    db_session.refresh(stranger)

    assert client.get(f"{PREFIX}/patients/{stranger.id}/outstanding-claims").status_code == 404


# ── INS-PAY-8: the attachment-type vocabulary ────────────────────────────────
def test_attachment_type_is_normalised_to_the_catalog(client, patient, office):
    from app.services.patient_extra_service import CLAIM_ATTACHMENT_TYPES

    claim = _claim(client, patient, office)
    r = client.post(
        f"{PREFIX}/insurance-claims/{claim['id']}/attachments",
        files={"file": ("eob.pdf", b"%PDF-1.4 eob", "application/pdf")},
        data={"attachment_type": "Explanation of Benefits"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["attachment_type"] == "EOB"
    assert "EOB" in CLAIM_ATTACHMENT_TYPES

    # An unrecognised type is stored as written rather than blocking the upload.
    odd = client.post(
        f"{PREFIX}/insurance-claims/{claim['id']}/attachments",
        files={"file": ("x.pdf", b"%PDF-1.4 x", "application/pdf")},
        data={"attachment_type": "Carrier-specific form 27B"},
    )
    assert odd.status_code == 201, odd.text
    assert odd.json()["attachment_type"] == "Carrier-specific form 27B"
