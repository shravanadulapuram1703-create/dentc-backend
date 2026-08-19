"""Second-pass Transactions gaps: ADJ-1, CHG-5 rollups, PROV-1 office scoping.

Backs ``docs/transactions_backend_devreport.md``:

- ADJ-1  split one adjustment across specific outstanding procedures.
- CHG-5  per-procedure Pat Paid / Pat Adj / Rem Amt on the procedure read.
- PROV-1 ``?office_id=`` spans provider_offices ∪ the home-office scalar, and the
  backfill reconstructs the join from historical usage.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import Office, Patient, PatientProcedure, Provider, ProviderOffice
from scripts.backfill_provider_offices import backfill

PREFIX = "/api/v1"
TODAY = date.today().isoformat()


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="PV1", name="Main", short_id="PV1")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def other_office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="PV2", name="Satellite", short_id="PV2")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def patient(db_session, office) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Al", last_name="Loc",
                chart_no="PV-PAT", home_office_id=office.id, is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def provider(db_session, office) -> Provider:
    pr = Provider(id="PVPRV", tenant_id=db_session._tenant_id, office_id=office.id,
                  name="Dr Home", short_id="DRH")
    db_session.add(pr)
    db_session.commit()
    db_session.refresh(pr)
    return pr


@pytest.fixture
def proc_code(client):
    r = client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D2740", "description": "Crown", "category": "Restorative", "default_fee": 900})
    assert r.status_code == 201, r.text
    return "D2740"


def _proc(client, patient_id, office_id, provider_id, code, item_id, fee=900, **extra):
    body = {"id": item_id, "patient_id": patient_id, "office_id": office_id,
            "provider_id": provider_id, "procedure_code": code, "fee": fee,
            "date_of_service": TODAY, **extra}
    r = client.post(f"{PREFIX}/patient-procedures", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _adjustment(client, patient_id, office_id, amount, **extra):
    r = client.post(f"{PREFIX}/patient-adjustments", json={
        "patient_id": patient_id, "office_id": office_id, "amount": amount,
        "adjustment_date": TODAY, "adjustment_type": "writeoff", **extra})
    assert r.status_code == 201, r.text
    return r.json()


# ── ADJ-1: per-procedure adjustment allocation ───────────────────────────────
def test_allocate_adjustment_splits_across_procedures(
    client, patient, office, provider, proc_code
):
    _proc(client, patient.id, office.id, provider.id, proc_code, "AP1", patient_estimate=900)
    _proc(client, patient.id, office.id, provider.id, proc_code, "AP2", patient_estimate=900)
    adj = _adjustment(client, patient.id, office.id, 300)
    adj_id = adj["id"]

    r = client.post(f"{PREFIX}/patient-adjustments/{adj_id}/allocate", json={
        "allocations": [
            {"procedure_id": "AP1", "amount": 200},
            {"procedure_id": "AP2", "amount": 100},
        ]})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [row["procedure_id"] for row in rows] == ["AP1", "AP2"]
    assert all(row["adjustment_id"] == adj_id for row in rows)

    listed = client.get(f"{PREFIX}/patient-adjustments/{adj_id}/allocations").json()
    assert sum(float(row["amount"]) for row in listed) == 300.0


def test_allocate_adjustment_guards_over_allocation(
    client, patient, office, provider, proc_code
):
    _proc(client, patient.id, office.id, provider.id, proc_code, "AG1")
    adj_id = _adjustment(client, patient.id, office.id, 50)["id"]
    r = client.post(f"{PREFIX}/patient-adjustments/{adj_id}/allocate", json={
        "allocations": [{"procedure_id": "AG1", "amount": 80}]})
    assert r.status_code == 422, r.text
    assert "exceed" in r.json()["error"]["message"].lower()


def test_allocate_adjustment_rejects_foreign_procedure(
    client, db_session, patient, office, provider, proc_code
):
    other = Patient(tenant_id=db_session._tenant_id, first_name="Other", last_name="Pat",
                    chart_no="PV-OTH", home_office_id=office.id, is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    _proc(client, other.id, office.id, provider.id, proc_code, "AF1")
    adj_id = _adjustment(client, patient.id, office.id, 100)["id"]
    r = client.post(f"{PREFIX}/patient-adjustments/{adj_id}/allocate", json={
        "allocations": [{"procedure_id": "AF1", "amount": 10}]})
    assert r.status_code == 422, r.text


def test_allocate_adjustment_replace_reissues_the_split(
    client, patient, office, provider, proc_code
):
    _proc(client, patient.id, office.id, provider.id, proc_code, "AR1")
    adj_id = _adjustment(client, patient.id, office.id, 100)["id"]
    client.post(f"{PREFIX}/patient-adjustments/{adj_id}/allocate", json={
        "allocations": [{"procedure_id": "AR1", "amount": 100}]})
    r = client.post(f"{PREFIX}/patient-adjustments/{adj_id}/allocate", json={
        "replace": True, "allocations": [{"procedure_id": "AR1", "amount": 40}]})
    assert r.status_code == 200, r.text
    listed = client.get(f"{PREFIX}/patient-adjustments/{adj_id}/allocations").json()
    assert len(listed) == 1
    assert float(listed[0]["amount"]) == 40.0


# ── CHG-5: Pat Paid / Pat Adj / Rem Amt on the procedure read ────────────────
def test_procedure_read_carries_applied_totals(
    client, patient, office, provider, proc_code
):
    _proc(client, patient.id, office.id, provider.id, proc_code, "T1", patient_estimate=900)
    pay = client.post(f"{PREFIX}/patient-payments", json={
        "id": "TPAY1", "patient_id": patient.id, "amount": 300,
        "payment_date": TODAY, "payment_type": "patient"})
    assert pay.status_code == 201, pay.text
    r = client.post(f"{PREFIX}/patient-payments/TPAY1/allocate", json={
        "allocations": [{"procedure_id": "T1", "amount": 300}]})
    assert r.status_code == 200, r.text

    adj = _adjustment(client, patient.id, office.id, 100, procedure_id="T1")
    assert adj["procedure_id"] == "T1"

    row = client.get(f"{PREFIX}/patient-procedures/T1").json()
    assert float(row["paid_to_date"]) == 300.0
    assert float(row["adjusted_to_date"]) == 100.0
    assert float(row["remaining_amount"]) == 500.0

    listed = client.get(f"{PREFIX}/patient-procedures?patient_id={patient.id}").json()
    grid_row = next(x for x in listed["items"] if x["id"] == "T1")
    assert float(grid_row["paid_to_date"]) == 300.0
    assert float(grid_row["remaining_amount"]) == 500.0


def test_split_adjustment_is_not_double_counted(
    client, patient, office, provider, proc_code
):
    """An adjustment carrying both a scalar procedure_id and an ADJ-1 split must
    count once — through the split."""
    _proc(client, patient.id, office.id, provider.id, proc_code, "D1", patient_estimate=900)
    adj_id = _adjustment(client, patient.id, office.id, 200, procedure_id="D1")["id"]
    client.post(f"{PREFIX}/patient-adjustments/{adj_id}/allocate", json={
        "allocations": [{"procedure_id": "D1", "amount": 200}]})
    row = client.get(f"{PREFIX}/patient-procedures/D1").json()
    assert float(row["adjusted_to_date"]) == 200.0


def test_procedure_allocations_summary(client, patient, office, provider, proc_code):
    _proc(client, patient.id, office.id, provider.id, proc_code, "S1", patient_estimate=900)
    client.post(f"{PREFIX}/patient-payments", json={
        "id": "SPAY1", "patient_id": patient.id, "amount": 150,
        "payment_date": TODAY, "payment_type": "patient"})
    client.post(f"{PREFIX}/patient-payments/SPAY1/allocate", json={
        "allocations": [{"procedure_id": "S1", "amount": 150}]})
    _adjustment(client, patient.id, office.id, 50, procedure_id="S1")

    out = client.get(f"{PREFIX}/patient-procedures/S1/allocations-summary")
    assert out.status_code == 200, out.text
    body = out.json()
    assert float(body["paid_to_date"]) == 150.0
    assert float(body["adjusted_to_date"]) == 50.0
    assert float(body["remaining_amount"]) == 700.0
    assert len(body["allocations"]) == 1
    assert len(body["adjustments"]) == 1


def test_insurance_payment_counts_as_insurance_not_patient(
    client, patient, office, provider, proc_code
):
    _proc(client, patient.id, office.id, provider.id, proc_code, "I1", patient_estimate=300)
    r = client.post(f"{PREFIX}/ledger-insurance-details/payment", json={
        "patient_id": patient.id, "procedure_id": "I1", "prim_ins_paid": 600,
        "payment_date": TODAY, "check_number": "CHK-9"})
    assert r.status_code == 201, r.text
    row = client.get(f"{PREFIX}/patient-procedures/I1").json()
    assert float(row["insurance_paid_to_date"]) == 600.0
    assert float(row["paid_to_date"]) == 0.0
    assert float(row["remaining_amount"]) == 300.0


# ── PROV-1: office scoping spans the M:N join ────────────────────────────────
def test_provider_office_filter_unions_assignment_and_home_office(
    client, db_session, office, other_office, provider
):
    visitor = Provider(id="PVVIS", tenant_id=db_session._tenant_id, office_id=other_office.id,
                       name="Dr Visitor", short_id="DRV")
    db_session.add(visitor)
    db_session.commit()

    # Home-office scalar only: the main office sees just its own provider.
    listed = client.get(f"{PREFIX}/providers?office_id={office.id}").json()
    assert {p["id"] for p in listed["items"]} == {"PVPRV"}

    # Assign the visitor to the main office — now both come back.
    r = client.put(f"{PREFIX}/offices/{office.id}/providers", json={"ids": ["PVVIS"]})
    assert r.status_code == 200, r.text
    listed = client.get(f"{PREFIX}/providers?office_id={office.id}").json()
    assert {p["id"] for p in listed["items"]} == {"PVPRV", "PVVIS"}
    assert listed["meta"]["total"] == 2

    # The assignment grid itself still returns only what its PUT set.
    assigned = client.get(f"{PREFIX}/offices/{office.id}/providers").json()
    assert {p["id"] for p in assigned} == {"PVVIS"}

    # …and the effective list is the union.
    effective = client.get(f"{PREFIX}/offices/{office.id}/providers/effective").json()
    assert {p["id"] for p in effective} == {"PVPRV", "PVVIS"}


def test_effective_providers_hides_inactive_by_default(
    client, db_session, office, provider
):
    retired = Provider(id="PVOLD", tenant_id=db_session._tenant_id, office_id=office.id,
                       name="Dr Retired", is_active=False)
    db_session.add(retired)
    db_session.commit()
    active = client.get(f"{PREFIX}/offices/{office.id}/providers/effective").json()
    assert {p["id"] for p in active} == {"PVPRV"}
    everyone = client.get(
        f"{PREFIX}/offices/{office.id}/providers/effective?include_inactive=true"
    ).json()
    assert {p["id"] for p in everyone} == {"PVPRV", "PVOLD"}


def test_backfill_provider_offices_reconstructs_the_join(
    client, db_session, office, other_office, provider, patient, proc_code
):
    """A provider who produced at another office gets a link from history."""
    db_session.add(PatientProcedure(
        id="BF1", patient_id=patient.id, office_id=other_office.id, provider_id=provider.id,
        procedure_code=proc_code, fee=100, date_of_service=date.today()))
    db_session.commit()

    added, present = backfill(db_session, db_session._tenant_id)
    assert added == 2  # home office + the satellite where they produced
    assert present == 0

    links = {
        (link.provider_id, link.office_id)
        for link in db_session.query(ProviderOffice).all()
    }
    assert links == {(provider.id, office.id), (provider.id, other_office.id)}

    # Idempotent: a second run adds nothing.
    added_again, present_again = backfill(db_session, db_session._tenant_id)
    assert added_again == 0
    assert present_again == 2
