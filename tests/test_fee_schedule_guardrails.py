"""Fee Schedule / Assignment / Entry write guardrails (§3.6, R1 step 4).

These fire on every write path regardless of ``PRICING_ENGINE_V2`` — they are
data-integrity rules for the three Setup maintainers, not pricing behaviour.
"""

from __future__ import annotations

import pytest

from app.db.models import (
    FeeSchedule,
    InsuranceCarrier,
    Office,
    OfficeGroup,
    Patient,
    ProcedureCode,
)

PREFIX = "/api/v1"


@pytest.fixture
def carrier(db_session) -> InsuranceCarrier:
    c = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Guard Carrier")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def schedule(db_session) -> FeeSchedule:
    fs = FeeSchedule(tenant_id=db_session._tenant_id, name="Guard Sched", is_active=True)
    db_session.add(fs)
    db_session.commit()
    db_session.refresh(fs)
    return fs


@pytest.fixture
def code(db_session) -> None:
    db_session.add(ProcedureCode(code="D0120", description="Exam", category="Diag"))
    db_session.commit()


# ── assignments ──────────────────────────────────────────────────────────────


def test_assignment_needs_a_payer_or_person(client, schedule):
    r = client.post(f"{PREFIX}/fee-schedule-assignments",
                    json={"fee_schedule_id": schedule.id})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "assignment_needs_target"


def test_assignment_duplicate_target_is_409(client, schedule, carrier, db_session):
    first = client.post(f"{PREFIX}/fee-schedule-assignments",
                        json={"fee_schedule_id": schedule.id, "carrier_id": carrier.id})
    assert first.status_code == 201, first.text
    # A second binding of the *same* target (carrier, all other keys blank) — even
    # to a different schedule — is the accidental duplicate the guard refuses.
    other = FeeSchedule(tenant_id=db_session._tenant_id, name="Other", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    dup = client.post(f"{PREFIX}/fee-schedule-assignments",
                      json={"fee_schedule_id": other.id, "carrier_id": carrier.id})
    assert dup.status_code == 409, dup.text
    assert dup.json()["error"]["details"]["code"] == "assignment_duplicate_target"


def test_assignment_to_inactive_schedule_is_422(client, carrier, db_session):
    dead = FeeSchedule(tenant_id=db_session._tenant_id, name="Dead", is_active=False)
    db_session.add(dead)
    db_session.commit()
    db_session.refresh(dead)
    r = client.post(f"{PREFIX}/fee-schedule-assignments",
                    json={"fee_schedule_id": dead.id, "carrier_id": carrier.id})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "assignment_schedule_invalid"


def test_assignment_to_foreign_schedule_is_422(client, carrier, db_session):
    from app.db.models import Tenant

    other = Tenant(name="OtherT", code="guard-other", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    foreign = FeeSchedule(tenant_id=other.id, name="Foreign", is_active=True)
    db_session.add(foreign)
    db_session.commit()
    db_session.refresh(foreign)
    r = client.post(f"{PREFIX}/fee-schedule-assignments",
                    json={"fee_schedule_id": foreign.id, "carrier_id": carrier.id})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "assignment_schedule_invalid"


# ── entries ──────────────────────────────────────────────────────────────────


def test_plan_pays_on_a_percentage_list_is_422(client, schedule, code):
    r = client.post(f"{PREFIX}/fee-schedule-entries", json={
        "fee_schedule_id": schedule.id, "procedure_code": "D0120",
        "patient_fee": "0.00", "insurance_fee": "26.16",
    })
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "insurance_fee_not_allowed"


def test_plan_pays_on_a_copay_list_is_allowed(client, code):
    fs = client.post(f"{PREFIX}/fee-schedules", json={
        "name": "MCO", "fee_type": "plan", "pricing_model": "copay",
    })
    assert fs.status_code == 201, fs.text
    r = client.post(f"{PREFIX}/fee-schedule-entries", json={
        "fee_schedule_id": fs.json()["id"], "procedure_code": "D0120",
        "insurance_fee": "26.16",
    })
    assert r.status_code == 201, r.text


def test_negative_fee_is_422(client, schedule, code):
    r = client.post(f"{PREFIX}/fee-schedule-entries", json={
        "fee_schedule_id": schedule.id, "procedure_code": "D0120", "patient_fee": "-5.00",
    })
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "fee_entry_negative"


# ── schedule header ──────────────────────────────────────────────────────────


def test_copay_model_requires_a_payer_type(client):
    r = client.post(f"{PREFIX}/fee-schedules", json={
        "name": "Bad", "fee_type": "standard", "pricing_model": "copay",
    })
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "pricing_model_requires_payer_type"


def test_fee_type_is_canonicalised_on_write(client):
    r = client.post(f"{PREFIX}/fee-schedules", json={"name": "Legacy", "fee_type": "office"})
    assert r.status_code == 201, r.text
    assert r.json()["fee_type"] == "standard"   # folded from the legacy spelling


def test_schedule_in_use_cannot_be_retired(client, schedule, carrier):
    ok = client.post(f"{PREFIX}/fee-schedule-assignments",
                     json={"fee_schedule_id": schedule.id, "carrier_id": carrier.id})
    assert ok.status_code == 201, ok.text
    # DELETE is a soft-retire; while an assignment references it, that is a 409.
    r = client.delete(f"{PREFIX}/fee-schedules/{schedule.id}")
    assert r.status_code == 409, r.text
    body = r.json()["error"]["details"]
    assert body["code"] == "fee_schedule_in_use"
    assert "assignments" in body["referenced_by"]


def test_schedule_referenced_by_patient_cannot_be_retired(client, schedule, db_session):
    office = Office(tenant_id=db_session._tenant_id, office_code="GRD",
                    name="Guard Office", short_id="GRD")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    pat = Patient(tenant_id=db_session._tenant_id, first_name="P", last_name="Q",
                  chart_no="GRD-1", home_office_id=office.id, is_active=True,
                  fee_schedule_id=schedule.id)
    db_session.add(pat)
    db_session.commit()
    r = client.delete(f"{PREFIX}/fee-schedules/{schedule.id}")
    assert r.status_code == 409, r.text
    assert "patients" in r.json()["error"]["details"]["referenced_by"]


# ── patient pointer ──────────────────────────────────────────────────────────


def test_patient_fee_schedule_pointer_must_be_valid(client, db_session):
    office = Office(tenant_id=db_session._tenant_id, office_code="GRP",
                    name="PP Office", short_id="GRP")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    r = client.post(f"{PREFIX}/patients", json={
        "first_name": "Bad", "last_name": "Pointer", "home_office_id": office.id,
        "fee_schedule_id": 999999,
    })
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "patient_schedule_invalid"
