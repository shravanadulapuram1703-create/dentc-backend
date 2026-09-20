"""Step-5 pricing/setup endpoints: metadata, usage, retire, fee-defaults,
fee-binding, /pricing/quote, /setup/pricing-health, and date_of_service passthrough.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import (
    FeeSchedule,
    FeeScheduleAssignment,
    FeeScheduleEntry,
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    Office,
    Patient,
    PatientInsurance,
    ProcedureCode,
)

PREFIX = "/api/v1"
D = Decimal
TODAY = date.today()


@pytest.fixture
def engine_on(monkeypatch):
    monkeypatch.setattr(settings, "PRICING_ENGINE_V2", True)


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="PE1", name="PE Office", short_id="PE1")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def code(db_session) -> None:
    db_session.add(ProcedureCode(code="D0120", description="Exam", category="Diag",
                                 coverage_category="01", default_fee=D("0")))
    db_session.commit()


def _schedule(db_session, name, *, active=True) -> FeeSchedule:
    fs = FeeSchedule(tenant_id=db_session._tenant_id, name=name, fee_type="standard",
                     pricing_model="percentage", is_active=active)
    db_session.add(fs)
    db_session.commit()
    db_session.refresh(fs)
    return fs


def _entry(db_session, fs, code, fee):
    db_session.add(FeeScheduleEntry(fee_schedule_id=fs.id, tenant_id=db_session._tenant_id,
                                    procedure_code=code, patient_fee=D(str(fee)),
                                    effective_date=TODAY))
    db_session.commit()


# ── metadata ─────────────────────────────────────────────────────────────────


def test_metadata_publishes_the_precedence_card(client):
    r = client.get(f"{PREFIX}/fee-schedules/metadata")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "precedence" in body        # the tier-ordered precedence card
    assert "error_codes" in body
    assert any(t["code"] == "ucr" for t in body["fee_types"])


# ── usage + retire ───────────────────────────────────────────────────────────


def test_usage_and_retire_when_unreferenced(client, db_session):
    fs = _schedule(db_session, "Retire Me")
    u = client.get(f"{PREFIX}/fee-schedules/{fs.id}/usage").json()
    assert u["can_retire"] is True
    assert u["counts"]["assignments"] == 0
    r = client.post(f"{PREFIX}/fee-schedules/{fs.id}/retire")
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False


def test_retire_refused_while_referenced(client, db_session):
    fs = _schedule(db_session, "In Use")
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="PE Carrier")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    client.post(f"{PREFIX}/fee-schedule-assignments",
                json={"fee_schedule_id": fs.id, "carrier_id": carrier.id})
    u = client.get(f"{PREFIX}/fee-schedules/{fs.id}/usage").json()
    assert u["can_retire"] is False
    assert u["counts"]["assignments"] == 1
    r = client.post(f"{PREFIX}/fee-schedules/{fs.id}/retire")
    assert r.status_code == 409, r.text
    assert r.json()["error"]["details"]["code"] == "fee_schedule_in_use"


# ── office fee-defaults ──────────────────────────────────────────────────────


def test_office_fee_defaults_set_and_validate(client, office, db_session):
    ucr = _schedule(db_session, "UCR list")
    r = client.patch(f"{PREFIX}/offices/{office.id}/fee-defaults", json={
        "default_ucr_fee_schedule_id": ucr.id, "unpriced_charge_policy": "refuse",
    })
    assert r.status_code == 200, r.text
    assert r.json()["default_ucr_fee_schedule_id"] == ucr.id
    assert r.json()["unpriced_charge_policy"] == "refuse"


def test_office_fee_defaults_reject_bad_schedule(client, office):
    r = client.patch(f"{PREFIX}/offices/{office.id}/fee-defaults",
                     json={"default_fee_schedule_id": 999999})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "office_schedule_invalid"


def test_office_fee_defaults_reject_bad_policy(client, office):
    r = client.patch(f"{PREFIX}/offices/{office.id}/fee-defaults",
                     json={"unpriced_charge_policy": "explode"})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "invalid_unpriced_policy"


# ── plan fee-binding ─────────────────────────────────────────────────────────


def test_plan_fee_binding_reports_the_assigned_schedule(client, db_session):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Bind Carrier")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                         group_number="G", is_active=True)
    fs = _schedule(db_session, "Plan Sched")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    client.post(f"{PREFIX}/fee-schedule-assignments",
                json={"fee_schedule_id": fs.id, "ins_plan_id": plan.id})
    b = client.get(f"{PREFIX}/insurance-plans/{plan.id}/fee-binding").json()
    assert b["bound"] is True
    assert b["via"] == "plan"
    assert b["fee_schedule_id"] == fs.id
    assert b["fee_source"] == "assignment_plan"


def test_plan_fee_binding_unbound(client, db_session):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="NoBind Carrier")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                         group_number="G2", is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    b = client.get(f"{PREFIX}/insurance-plans/{plan.id}/fee-binding").json()
    assert b["bound"] is False
    assert b["via"] is None


# ── /pricing/quote ───────────────────────────────────────────────────────────


def test_quote_without_patient_prices_from_office_default(client, office, code, db_session, engine_on):
    fs = _schedule(db_session, "Office default")
    _entry(db_session, fs, "D0120", "44.00")
    office.default_fee_schedule_id = fs.id
    db_session.commit()
    r = client.post(f"{PREFIX}/pricing/quote", json={
        "office_id": office.id, "lines": [{"procedure_code": "D0120"}],
    })
    assert r.status_code == 200, r.text
    line = r.json()["lines"][0]
    assert Decimal(str(line["fee"])) == D("44.00")
    assert line["fee_source"] == "office_default"


def test_quote_with_patient_returns_the_split(client, office, code, db_session, engine_on):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Q Carrier")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                         group_number="QG", is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(InsuranceCoverageRule(ins_plan_id=plan.id, start_code="01", end_code="01",
                                         category="0", coverage_pct=D("80"), ded_waived=False))
    fs = _schedule(db_session, "Off default")
    _entry(db_session, fs, "D0120", "100.00")
    office.default_fee_schedule_id = fs.id
    pat = Patient(tenant_id=db_session._tenant_id, first_name="Q", last_name="P",
                  chart_no="PE-Q", home_office_id=office.id, is_active=True)
    db_session.add(pat)
    db_session.commit()
    db_session.refresh(pat)
    db_session.add(PatientInsurance(patient_id=pat.id, ins_plan_id=plan.id,
                                    legacy_plan_type="D", insurance_type="primary", is_active=True))
    db_session.commit()
    r = client.post(f"{PREFIX}/pricing/quote", json={
        "office_id": office.id, "patient_id": pat.id, "lines": [{"procedure_code": "D0120"}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(str(body["insurance_estimate"])) == D("80.00")
    assert Decimal(str(body["patient_estimate"])) == D("20.00")


# ── /setup/pricing-health ────────────────────────────────────────────────────


def test_pricing_health_flags_office_without_ucr(client, office):
    r = client.get(f"{PREFIX}/setup/pricing-health", params={"office_id": office.id})
    assert r.status_code == 200, r.text
    codes = {f["code"] for f in r.json()["findings"]}
    assert "office_without_ucr" in codes


# ── date_of_service passthrough ──────────────────────────────────────────────


def test_fee_route_accepts_date_of_service(client, office, code, db_session, engine_on):
    fs = _schedule(db_session, "Dated")
    _entry(db_session, fs, "D0120", "44.00")
    office.default_fee_schedule_id = fs.id
    pat = Patient(tenant_id=db_session._tenant_id, first_name="D", last_name="S",
                  chart_no="PE-D", home_office_id=office.id, is_active=True)
    db_session.add(pat)
    db_session.commit()
    db_session.refresh(pat)
    r = client.get(f"{PREFIX}/patients/{pat.id}/fee", params={
        "procedure_code": "D0120", "office_id": office.id, "date_of_service": TODAY.isoformat(),
    })
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["fee"])) == D("44.00")


# ── bulk write ops (§3.5) ─────────────────────────────────────────────────────

FUTURE = (date.today() + timedelta(days=90))


def test_bulk_upsert_entries_creates_then_updates(client, code, db_session):
    fs = _schedule(db_session, "Bulk list")
    body = {"effective_date": FUTURE.isoformat(),
            "entries": [{"procedure_code": "D0120", "patient_fee": "50.00"}]}
    r = client.put(f"{PREFIX}/fee-schedules/{fs.id}/entries/bulk", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1
    # Same code + same effective_date again → an update, not a duplicate.
    body["entries"][0]["patient_fee"] = "55.00"
    r2 = client.put(f"{PREFIX}/fee-schedules/{fs.id}/entries/bulk", json=body)
    assert r2.json()["created"] == 0
    assert r2.json()["updated"] == 1


def test_bulk_upsert_rejects_plan_pays_on_percentage_list(client, code, db_session):
    fs = _schedule(db_session, "Bulk pct")
    r = client.put(f"{PREFIX}/fee-schedules/{fs.id}/entries/bulk", json={
        "entries": [{"procedure_code": "D0120", "insurance_fee": "26.16"}],
    })
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "insurance_fee_not_allowed"


def test_adjust_writes_a_new_dated_percentage_set(client, code, db_session):
    from app.db.models import FeeScheduleEntry

    fs = _schedule(db_session, "Adjust list")
    _entry(db_session, fs, "D0120", "100.00")
    r = client.post(f"{PREFIX}/fee-schedules/{fs.id}/adjust", json={
        "mode": "percent", "value": 10, "effective_date": FUTURE.isoformat(),
    })
    assert r.status_code == 200, r.text
    assert r.json()["adjusted"] == 1
    new = db_session.execute(
        FeeScheduleEntry.__table__.select().where(
            (FeeScheduleEntry.fee_schedule_id == fs.id)
            & (FeeScheduleEntry.effective_date == FUTURE)
        )
    ).mappings().first()
    assert new is not None
    assert Decimal(str(new["patient_fee"])) == Decimal("110.00")


def test_adjust_rejects_bad_mode(client, code, db_session):
    fs = _schedule(db_session, "Adjust bad")
    _entry(db_session, fs, "D0120", "100.00")
    r = client.post(f"{PREFIX}/fee-schedules/{fs.id}/adjust", json={
        "mode": "multiply", "value": 2, "effective_date": FUTURE.isoformat(),
    })
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "invalid_adjust_mode"


def test_reassign_patients_moves_them_and_unblocks_retire(client, office, db_session):
    source = _schedule(db_session, "Old list")
    target = _schedule(db_session, "New list")
    pat = Patient(tenant_id=db_session._tenant_id, first_name="Move", last_name="Me",
                  chart_no="PE-M", home_office_id=office.id, is_active=True,
                  fee_schedule_id=source.id)
    db_session.add(pat)
    db_session.commit()
    db_session.refresh(pat)
    # Referenced → cannot retire yet.
    assert client.post(f"{PREFIX}/fee-schedules/{source.id}/retire").status_code == 409
    r = client.post(f"{PREFIX}/fee-schedules/{source.id}/reassign-patients",
                    json={"to_fee_schedule_id": target.id})
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == 1
    db_session.expire_all()
    assert db_session.get(Patient, pat.id).fee_schedule_id == target.id
    # No longer referenced → retire now succeeds.
    assert client.post(f"{PREFIX}/fee-schedules/{source.id}/retire").status_code == 200


def test_reassign_patients_rejects_bad_target(client, db_session):
    source = _schedule(db_session, "Src")
    r = client.post(f"{PREFIX}/fee-schedules/{source.id}/reassign-patients",
                    json={"to_fee_schedule_id": 999999})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "patient_schedule_invalid"
