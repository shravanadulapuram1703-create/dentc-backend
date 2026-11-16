"""Responsible Party / Family Accounts (RP-1 … RP-16).

docs: dentc-frontend/docs/patients/responsible_party_backend_devreport.md
response: docs/patients/responsible_party_backend_response.md
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.db.models import (
    Account,
    AccountChangeEvent,
    Office,
    Patient,
    PatientPayment,
    PatientProcedure,
    ProcedureCode,
    Provider,
    ResponsibleParty,
)

pytestmark = pytest.mark.enforce_fks

API = "/api/v1"


def _patient(db, first="Pat", last="Smith", **kw) -> Patient:
    p = Patient(tenant_id=db._tenant_id, first_name=first, last_name=last, **kw)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _provider(db) -> tuple[str, int]:
    prov = db.get(Provider, "PRV-RP")
    if prov is None:
        office = Office(tenant_id=db._tenant_id, office_code="OFF-RP", name="RP Office", short_id="RP")
        db.add(office)
        db.commit()
        prov = Provider(id="PRV-RP", tenant_id=db._tenant_id, office_id=office.id, name="Dr RP")
        db.add(prov)
        db.add(ProcedureCode(code="D1110", description="Prophylaxis", category="Preventive"))
        db.commit()
    return prov.id, prov.office_id


def _charge(db, patient_id, fee, pid=None, dos=None):
    db.add(PatientProcedure(
        id=pid or f"PP-{patient_id}-{fee}", patient_id=patient_id, procedure_code="D1110",
        fee=Decimal(str(fee)), date_of_service=dos or date(2026, 1, 1),
        provider_id=_provider(db)[0], office_id=_provider(db)[1],
    ))
    db.commit()


# ── RP-4: every patient has an account; default Self ─────────────────────────
def test_orm_insert_gets_self_account(db_session):
    p = _patient(db_session)
    assert p.account_id is not None
    assert p.guarantor_patient_id == p.id
    assert p.responsible_party_id == str(p.id)
    assert p.responsible_party_relationship == "S"
    acc = db_session.get(Account, p.account_id)
    assert acc.primary_guarantor_patient_id == p.id
    assert acc.account_no == str(acc.id)


def test_post_patients_defaults_self(client):
    r = client.post(f"{API}/patients", json={"first_name": "New", "last_name": "Self"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["guarantor"]["kind"] == "self"
    assert body["account_id"] and body["account_no"]


def test_register_without_rp_is_self(client):
    r = client.post(f"{API}/patients/register",
                    json={"patient": {"first_name": "Reg", "last_name": "Self"}})
    assert r.status_code == 201, r.text
    assert r.json()["guarantor"]["kind"] == "self"


# ── RP-1/RP-2: self key never resolves to an RP row with the same number ──────
def test_self_guarantor_not_confused_with_rp_row(client, db_session):
    p = _patient(db_session)
    # An unrelated RP row that happens to share the patient's id.
    rp = ResponsibleParty(id=p.id, tenant_id=db_session._tenant_id, first_name="Other",
                          last_name="Family")
    db_session.add(rp)
    db_session.commit()
    ctx = client.get(f"{API}/patients/{p.id}").json()
    assert ctx["guarantor"]["kind"] == "self"
    assert ctx["guarantor"]["name"] == "Smith, Pat"
    ov = client.get(f"{API}/patients/{p.id}/overview").json()
    assert ov["guarantor"]["kind"] == "self"
    assert ov["responsible_party"] is None


# ── RP-5: link to an existing patient / account ──────────────────────────────
def test_register_child_under_guarantor_patient(client, db_session):
    mom = _patient(db_session, "Mom", "Jones")
    r = client.post(f"{API}/patients/register", json={
        "patient": {"first_name": "Kid", "last_name": "Jones"},
        "responsible_party": {"guarantor_patient_id": mom.id, "relationship": "Child"},
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["account_id"] == mom.account_id
    assert body["guarantor"] == {**body["guarantor"], "kind": "patient", "patient_id": mom.id}
    assert body["responsible_party_id"] == str(mom.id)
    kid = db_session.get(Patient, body["patient_id"])
    db_session.refresh(kid)
    assert kid.responsible_party_relationship == "C"

    acct = client.get(f"{API}/accounts/{mom.account_id}").json()
    assert acct["member_count"] == 2
    guarantors = [m for m in acct["members"] if m["is_guarantor"]]
    assert [g["patient_id"] for g in guarantors] == [mom.id]


def test_register_join_account(client, db_session):
    mom = _patient(db_session, "Mom", "Lee")
    r = client.post(f"{API}/patients/register", json={
        "patient": {"first_name": "Kid", "last_name": "Lee"},
        "responsible_party": {"account_id": mom.account_id},
    })
    assert r.status_code == 201, r.text
    assert r.json()["guarantor"]["patient_id"] == mom.id


def test_register_inline_person_creates_party_account(client):
    r = client.post(f"{API}/patients/register", json={
        "patient": {"first_name": "Kid", "last_name": "Poe"},
        "responsible_party": {"person": {"first_name": "Gran", "last_name": "Poe"},
                              "relationship": "G"},
    })
    assert r.status_code == 201, r.text
    g = r.json()["guarantor"]
    assert g["kind"] == "responsible_party" and g["name"] == "Poe, Gran"


def test_register_inactive_guarantor_422(client, db_session):
    mom = _patient(db_session, "Gone", "Away", is_active=False)
    r = client.post(f"{API}/patients/register", json={
        "patient": {"first_name": "Kid", "last_name": "Away"},
        "responsible_party": {"guarantor_patient_id": mom.id},
    })
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "guarantor_patient_inactive"


# ── RP-7 / RP-4: PATCH validation ────────────────────────────────────────────
def test_patch_unknown_rp_key_422(client, db_session):
    p = _patient(db_session)
    r = client.patch(f"{API}/patients/{p.id}", json={"responsible_party_id": "typo-999"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "responsible_party_not_found"


def test_patch_null_rp_422(client, db_session):
    p = _patient(db_session)
    r = client.patch(f"{API}/patients/{p.id}", json={"responsible_party_id": None})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "guarantor_required"


def test_patch_same_alias_is_noop_and_other_fields_save(client, db_session):
    p = _patient(db_session)
    r = client.patch(f"{API}/patients/{p.id}",
                     json={"responsible_party_id": str(p.id), "first_name": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["first_name"] == "Renamed"
    assert r.json()["guarantor"]["kind"] == "self"


def test_patch_guarantor_patient_moves_account(client, db_session):
    mom = _patient(db_session, "Mom", "Ng")
    kid = _patient(db_session, "Kid", "Ng")
    old = kid.account_id
    r = client.patch(f"{API}/patients/{kid.id}", json={"guarantor_patient_id": mom.id})
    assert r.status_code == 200, r.text
    assert r.json()["account_id"] == mom.account_id
    assert db_session.get(Account, old).is_active is False  # emptied → retired


# ── RP-6: change guarantor ───────────────────────────────────────────────────
def test_change_guarantor_moves_balance_by_default(client, db_session):
    mom = _patient(db_session, "Mom", "Ray")
    kid = _patient(db_session, "Kid", "Ray")
    _charge(db_session, kid.id, 100)
    r = client.post(f"{API}/patients/{kid.id}/change-guarantor",
                    json={"guarantor_patient_id": mom.id, "relationship": "C"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["new_account_id"] == mom.account_id
    assert body["moved_balance"] == 100.0 and body["transfer_payment_ids"] == []
    log = client.get(f"{API}/patients/{kid.id}/change-log").json()
    assert log[0]["action"] == "change_guarantor"
    assert log[0]["old_account_id"] == body["old_account_id"]


def test_change_guarantor_leave_balance_posts_transfer(client, db_session):
    mom = _patient(db_session, "Mom", "Kay")
    kid = client.post(f"{API}/patients/register", json={
        "patient": {"first_name": "Kid", "last_name": "Kay"},
        "responsible_party": {"guarantor_patient_id": mom.id}}).json()["patient_id"]
    dad = _patient(db_session, "Dad", "Kay")
    _charge(db_session, kid, 80)
    r = client.post(f"{API}/patients/{kid}/change-guarantor",
                    json={"guarantor_patient_id": dad.id, "move_open_balance": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["balance_left_with_old_account"] is True
    assert len(body["transfer_payment_ids"]) == 2
    assert client.get(f"{API}/patients/{kid}/balance").json()["balance"] == 0.0
    assert client.get(f"{API}/patients/{mom.id}/balance").json()["balance"] == 80.0


def test_change_guarantor_with_dependents_409_then_moves(client, db_session):
    mom = _patient(db_session, "Mom", "Fox")
    kid = client.post(f"{API}/patients/register", json={
        "patient": {"first_name": "Kid", "last_name": "Fox"},
        "responsible_party": {"guarantor_patient_id": mom.id}}).json()["patient_id"]
    other = _patient(db_session, "New", "Spouse")
    r = client.post(f"{API}/patients/{mom.id}/change-guarantor",
                    json={"guarantor_patient_id": other.id})
    assert r.status_code == 409
    assert r.json()["error"]["details"]["code"] == "guarantor_has_dependents"
    r = client.post(f"{API}/patients/{mom.id}/change-guarantor",
                    json={"guarantor_patient_id": other.id, "include_dependents": True})
    assert r.status_code == 200, r.text
    assert set(r.json()["moved_patient_ids"]) == {mom.id, kid}
    db_session.expire_all()
    assert db_session.get(Patient, kid).account_id == other.account_id


def test_change_to_self_splits_out(client, db_session):
    mom = _patient(db_session, "Mom", "Ito")
    kid = client.post(f"{API}/patients/register", json={
        "patient": {"first_name": "Adult", "last_name": "Ito"},
        "responsible_party": {"guarantor_patient_id": mom.id}}).json()["patient_id"]
    r = client.post(f"{API}/patients/{kid}/change-guarantor", json={"is_self": True})
    assert r.status_code == 200, r.text
    assert r.json()["guarantor"]["kind"] == "self"
    assert r.json()["new_account_id"] != mom.account_id


def test_merge_accounts(client, db_session):
    a = _patient(db_session, "A", "One")
    b = _patient(db_session, "B", "Two")
    target, source = a.account_id, b.account_id  # the shared session re-points b in place
    r = client.post(f"{API}/accounts/{target}/merge", json={"source_account_id": source})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account"]["member_count"] == 2
    assert body["parties_added"] == 1  # B's primary becomes a secondary party
    src = client.get(f"{API}/accounts/{source}").json()
    assert src["is_active"] is False and src["merged_into_account_id"] == target


# ── RP-8: parties ────────────────────────────────────────────────────────────
def test_parties_crud_and_limit(client, db_session):
    a = _patient(db_session, "A", "Party")
    acc = a.account_id
    p2 = client.post(f"{API}/accounts/{acc}/parties", json={
        "person": {"first_name": "Dad", "last_name": "Party"}, "responsibility_pct": "50",
        "receives_statements": True})
    assert p2.status_code == 201, p2.text
    p3 = client.post(f"{API}/accounts/{acc}/parties", json={
        "person": {"first_name": "Bill", "last_name": "To"}, "role": "billing_contact"})
    assert p3.status_code == 201, p3.text
    p4 = client.post(f"{API}/accounts/{acc}/parties", json={
        "person": {"first_name": "Too", "last_name": "Many"}})
    assert p4.status_code == 409
    assert p4.json()["error"]["details"]["code"] == "account_parties_limit"
    parties = client.get(f"{API}/accounts/{acc}/parties").json()
    assert [x["role"] for x in parties] == ["primary", "secondary", "billing_contact"]
    bad = client.post(f"{API}/accounts/{acc}/parties", json={"role": "primary", "patient_id": a.id})
    assert bad.status_code in (409, 422)
    r = client.patch(f"{API}/accounts/{acc}/parties/{p2.json()['id']}", json={"responsibility_pct": "120"})
    assert r.status_code == 422
    assert client.delete(f"{API}/accounts/{acc}/parties/{p3.json()['id']}").status_code == 204
    swapped = client.post(f"{API}/accounts/{acc}/parties/{p2.json()['id']}/make-primary").json()
    assert swapped["primary_guarantor"]["kind"] == "responsible_party"
    assert swapped["parties"][1]["patient_id"] == a.id


# ── RP-9: account payment + statement ────────────────────────────────────────
def _family(client, db_session):
    mom = _patient(db_session, "Mom", "Bay")
    kid = client.post(f"{API}/patients/register", json={
        "patient": {"first_name": "Kid", "last_name": "Bay"},
        "responsible_party": {"guarantor_patient_id": mom.id}}).json()["patient_id"]
    _charge(db_session, mom.id, 40, dos=date(2026, 3, 1))
    _charge(db_session, kid, 100, dos=date(2026, 1, 1))
    return mom, kid


def test_account_payment_oldest_first(client, db_session):
    mom, kid = _family(client, db_session)
    r = client.post(f"{API}/accounts/{mom.account_id}/payments",
                    json={"amount": "120.00", "tender": "cash"})
    assert r.status_code == 201, r.text
    split = {p["patient_id"]: p["amount"] for p in r.json()["payments"]}
    assert split == {kid: 100.0, mom.id: 20.0}
    rows = db_session.query(PatientPayment).filter(
        PatientPayment.account_payment_id == r.json()["account_payment_id"]).all()
    assert {x.account_id for x in rows} == {mom.account_id}
    bal = client.get(f"{API}/patients/{mom.id}/balance").json()
    assert bal["patient_balance_total"] == 20.0
    assert bal["account_balance"] == 20.0  # true account total (RP-10)


def test_account_payment_by_member_reconciles(client, db_session):
    mom, kid = _family(client, db_session)
    bad = client.post(f"{API}/accounts/{mom.account_id}/payments", json={
        "amount": "50", "distribute": "by_member",
        "allocations": [{"patient_id": kid, "amount": "40"}]})
    assert bad.status_code == 422
    assert bad.json()["error"]["details"]["code"] == "allocations_not_reconciled"
    stranger = _patient(db_session, "No", "Member")
    bad2 = client.post(f"{API}/accounts/{mom.account_id}/payments", json={
        "amount": "10", "distribute": "by_member",
        "allocations": [{"patient_id": stranger.id, "amount": "10"}]})
    assert bad2.json()["error"]["details"]["code"] == "patient_not_on_account"


def test_account_statement_and_batch(client, db_session):
    mom, kid = _family(client, db_session)
    r = client.post(f"{API}/accounts/{mom.account_id}/statements", json={})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["statement_scope"] == "account" and s["patient_id"] == mom.id
    assert {m["patient_id"] for m in s["snapshot"]["members"]} == {mom.id, kid}
    assert float(s["closing_balance"]) == 140.0
    pdf = client.get(f"{API}/patients/{mom.id}/statements/{s['id']}/pdf")
    assert pdf.status_code == 200


# ── RP-10/RP-11: payloads ────────────────────────────────────────────────────
def test_account_balance_carries_guarantor(client, db_session):
    mom, kid = _family(client, db_session)
    body = client.get(f"{API}/patients/{kid}/account-balance").json()
    assert body["account_id"] == mom.account_id and body["member_count"] == 2
    assert body["guarantor"]["kind"] == "patient"
    assert client.get(f"{API}/patients/{kid}/balance").json()["account_balance"] == 140.0
    roster = client.get(f"{API}/responsible-parties/{mom.id}/patients").json()
    assert {r["patient_id"] for r in roster} == {mom.id, kid}
    assert [r["is_guarantor"] for r in roster if r["patient_id"] == mom.id] == [True]


# ── RP-12: search ────────────────────────────────────────────────────────────
def test_search_by_guarantor_and_account(client, db_session):
    mom = _patient(db_session, "Maria", "Zebulon")
    kid = client.post(f"{API}/patients/register", json={
        "patient": {"first_name": "Kid", "last_name": "Other"},
        "responsible_party": {"guarantor_patient_id": mom.id}}).json()["patient_id"]
    ids = {p["id"] for p in client.get(f"{API}/patients?guarantor_name=Zebulon").json()["items"]}
    assert ids == {kid}
    ids = {p["id"] for p in client.get(f"{API}/patients?search=Zebulon").json()["items"]}
    assert ids == {mom.id, kid}
    acc_no = db_session.get(Account, mom.account_id).account_no
    ids = {p["id"] for p in client.get(f"{API}/patients?account_no={acc_no}").json()["items"]}
    assert ids == {mom.id, kid}
    accs = client.get(f"{API}/accounts?search=zebulon").json()
    assert accs["total"] == 1


# ── RP-13 / RP-15 / RP-16 ────────────────────────────────────────────────────
def test_account_insurance_empty_and_rules(client, db_session):
    p = _patient(db_session)
    assert client.get(f"{API}/accounts/{p.account_id}/insurance").json() == []
    rules = client.get(f"{API}/metadata/account-rules").json()
    assert rules["max_account_parties"] == 3
    assert rules["spec_precedence"][0] == "is_self"


def test_legacy_key_groups_into_one_account(db_session):
    a = _patient(db_session, "Leg", "One", legacy_id="L1", responsible_party_id="9001")
    b = _patient(db_session, "Leg", "Two", legacy_id="L2", responsible_party_id="9001")
    assert a.account_id == b.account_id
    acc = db_session.get(Account, a.account_id)
    assert acc.legacy_key == "9001" and acc.account_no == "9001"
    assert a.guarantor_patient_id is None and a.guarantor_party_id is None  # unresolved
    assert a.responsible_party_id == "9001"


def test_update_account_flags_logged(client, db_session):
    p = _patient(db_session)
    r = client.patch(f"{API}/accounts/{p.account_id}", json={"send_statements": False})
    assert r.status_code == 200 and r.json()["send_statements"] is False
    ev = db_session.query(AccountChangeEvent).filter_by(action="account_updated").one()
    assert ev.details["changes"]["send_statements"]["after"] is False
