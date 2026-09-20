"""``apply_split`` — the single write-path pricing/split helper (R1, §3.3/§3.4).

Splits into two halves:

* **flag-off parity** — with ``PRICING_ENGINE_V2`` off the write path must behave
  exactly as it shipped: a fee-less create is priced (fee only, no split), and a
  PATCH is never re-priced.
* **flag-on** — a create fills the insurance/patient/deductible split from the
  patient's coverage through the same arithmetic the estimate endpoint uses
  (self-pay / percentage / copay), honours the override discipline in
  ``client_legacy`` compatibility mode, a PATCH re-splits only on a fee change to
  an unclaimed charge, and a single posted line equals the one-line ``/estimate``.
"""

from __future__ import annotations

from datetime import date
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
    PatientProcedure,
    ProcedureCode,
    Provider,
)
from app.services import estimate_service
from app.services.patient_procedure_service import patient_procedure_crud

D = Decimal
TODAY = date.today()


@pytest.fixture
def engine_on(monkeypatch):
    monkeypatch.setattr(settings, "PRICING_ENGINE_V2", True)


@pytest.fixture
def engine_off(monkeypatch):
    monkeypatch.setattr(settings, "PRICING_ENGINE_V2", False)


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="AS1",
               name="ApplySplit Office", short_id="AS1")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    prov = Provider(id="ASPRV", tenant_id=db_session._tenant_id, office_id=office.id,
                    name="Dr AS")
    db_session.add(prov)
    db_session.commit()
    db_session.refresh(prov)
    return prov


@pytest.fixture
def codes(db_session) -> None:
    db_session.add(ProcedureCode(code="D0120", description="Exam", category="Diag",
                                 coverage_category="01", default_fee=D("0")))
    db_session.commit()


def _plan(db_session, *, pct="80", cat="01", deductible="0", annual_max=None, name="AS"):
    c = InsuranceCarrier(tenant_id=db_session._tenant_id, name=name + " Carrier")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    p = InsurancePlan(
        tenant_id=db_session._tenant_id, carrier_id=c.id, group_number="G", is_active=True,
        individual_deductible=D(deductible),
        individual_max=(D(annual_max) if annual_max is not None else None),
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    db_session.add(InsuranceCoverageRule(ins_plan_id=p.id, start_code=cat, end_code=cat,
                                         category="0", coverage_pct=D(pct), ded_waived=False))
    db_session.commit()
    return p


def _patient(db_session, office, plan=None) -> Patient:
    pat = Patient(tenant_id=db_session._tenant_id, first_name="A", last_name="S",
                  chart_no="AS-1", home_office_id=office.id, is_active=True)
    db_session.add(pat)
    db_session.commit()
    db_session.refresh(pat)
    if plan is not None:
        db_session.add(PatientInsurance(patient_id=pat.id, ins_plan_id=plan.id,
                                        legacy_plan_type="D", insurance_type="primary",
                                        is_active=True))
        db_session.commit()
    return pat


def _schedule(db_session, name, code, patient_fee, *, fee_type="standard",
              pricing_model="percentage", insurance_fee=None) -> FeeSchedule:
    s = FeeSchedule(tenant_id=db_session._tenant_id, name=name, fee_type=fee_type,
                    pricing_model=pricing_model, is_active=True)
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    kw = dict(fee_schedule_id=s.id, tenant_id=db_session._tenant_id, procedure_code=code,
              effective_date=TODAY,
              patient_fee=(D(str(patient_fee)) if patient_fee is not None else None))
    if insurance_fee is not None:
        kw["insurance_fee"] = D(str(insurance_fee))
    db_session.add(FeeScheduleEntry(**kw))
    db_session.commit()
    return s


def _split(db_session, payload, current=None):
    return estimate_service.apply_split(db_session, dict(payload), db_session._tenant_id,
                                        current=current)


# ── flag-off parity ──────────────────────────────────────────────────────────


def test_flag_off_create_prices_fee_but_writes_no_split(db_session, office, codes, engine_off):
    pat = _patient(db_session, office)
    s = _schedule(db_session, "Office default", "D0120", "44.00")
    office.default_fee_schedule_id = s.id
    db_session.commit()

    out = _split(db_session, {"patient_id": pat.id, "procedure_code": "D0120",
                              "office_id": office.id})
    assert out["fee"] == D("44.00")
    assert out.get("fee_schedule_id") == s.id
    # No split columns are written while the engine is dark.
    for k in ("insurance_estimate", "patient_estimate", "coverage_pct", "fee_source"):
        assert k not in out


def test_flag_off_explicit_fee_is_untouched(db_session, office, codes, engine_off):
    pat = _patient(db_session, office)
    out = _split(db_session, {"patient_id": pat.id, "procedure_code": "D0120",
                              "office_id": office.id, "fee": D("77.00")})
    assert out["fee"] == D("77.00")
    assert "patient_estimate" not in out


def test_flag_off_update_never_reprices(db_session, office, codes, engine_off):
    pat = _patient(db_session, office)
    current = PatientProcedure(patient_id=pat.id, procedure_code="D0120",
                               office_id=office.id, fee=D("50.00"), claim_id=None)
    out = _split(db_session, {"fee": D("60.00")}, current=current)
    assert out == {"fee": D("60.00")}


# ── flag-on: create ────────────────────────────────────────────────────────────


def test_create_self_pay(db_session, office, codes, engine_on):
    pat = _patient(db_session, office)  # no coverage
    s = _schedule(db_session, "Office default", "D0120", "44.00")
    office.default_fee_schedule_id = s.id
    db_session.commit()

    out = _split(db_session, {"patient_id": pat.id, "procedure_code": "D0120",
                              "office_id": office.id})
    assert out["fee"] == D("44.00")
    assert out["fee_source"] == "office_default"
    assert out["insurance_estimate"] == D("0.00")
    assert out["patient_estimate"] == D("44.00")
    assert out["coverage_pct"] == D("0")


def test_create_percentage_split(db_session, office, codes, engine_on):
    plan = _plan(db_session, pct="80", cat="01")
    pat = _patient(db_session, office, plan)
    s = _schedule(db_session, "Office default", "D0120", "100.00")
    office.default_fee_schedule_id = s.id
    db_session.commit()

    out = _split(db_session, {"patient_id": pat.id, "procedure_code": "D0120",
                              "office_id": office.id})
    assert out["fee"] == D("100.00")
    assert out["coverage_pct"] == D("80.00")
    assert out["insurance_estimate"] == D("80.00")
    assert out["patient_estimate"] == D("20.00")
    assert out["coverage_rule_id"] is not None


def test_create_copay_split(db_session, office, codes, engine_on):
    plan = _plan(db_session, pct="0", cat="01")
    pat = _patient(db_session, office, plan)
    copay = _schedule(db_session, "Medicaid", "D0120", None, fee_type="plan",
                      pricing_model="copay", insurance_fee="26.16")
    db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id,
                                         ins_plan_id=plan.id, fee_schedule_id=copay.id))
    db_session.commit()

    out = _split(db_session, {"patient_id": pat.id, "procedure_code": "D0120",
                              "office_id": office.id})
    assert out["fee"] == D("26.16")
    assert out["insurance_estimate"] == D("26.16")
    assert out["patient_estimate"] == D("0.00")


def test_create_client_legacy_fee_honoured_split_recomputed(db_session, office, codes, engine_on):
    plan = _plan(db_session, pct="50", cat="01")
    pat = _patient(db_session, office, plan)
    s = _schedule(db_session, "Office default", "D0120", "100.00")
    office.default_fee_schedule_id = s.id
    db_session.commit()

    out = _split(db_session, {"patient_id": pat.id, "procedure_code": "D0120",
                              "office_id": office.id, "fee": D("200.00")})
    assert out["fee"] == D("200.00")                 # the client's fee is honoured
    assert out["fee_source"] == "client_legacy"
    assert out["insurance_estimate"] == D("100.00")  # 50 % of 200, recomputed
    assert out["patient_estimate"] == D("100.00")
    assert out.get("fee_schedule_id") == s.id        # provenance still recorded


def test_create_override_carries_no_schedule_but_still_splits(db_session, office, codes, engine_on):
    plan = _plan(db_session, pct="50", cat="01")
    pat = _patient(db_session, office, plan)
    s = _schedule(db_session, "Office default", "D0120", "100.00")
    office.default_fee_schedule_id = s.id
    db_session.commit()

    out = _split(db_session, {"patient_id": pat.id, "procedure_code": "D0120",
                              "office_id": office.id, "fee": D("200.00"),
                              "fee_override": True})
    assert out["fee_source"] == "override"
    assert out.get("fee_schedule_id") is None        # an override is off-schedule
    assert "fee_override" not in out                 # the transient flag is consumed
    assert out["insurance_estimate"] == D("100.00")  # split still computed


# ── flag-on: update ─────────────────────────────────────────────────────────


def test_update_reprices_split_on_fee_change_unclaimed(db_session, office, codes, engine_on):
    plan = _plan(db_session, pct="80", cat="01")
    pat = _patient(db_session, office, plan)
    current = PatientProcedure(patient_id=pat.id, procedure_code="D0120", office_id=office.id,
                               fee=D("100.00"), claim_id=None, date_of_service=None,
                               provider_id=None)
    out = _split(db_session, {"fee": D("200.00")}, current=current)
    assert out["fee"] == D("200.00")
    assert out["insurance_estimate"] == D("160.00")  # 80 % of the new fee
    assert out["patient_estimate"] == D("40.00")


def test_update_on_claimed_charge_does_not_resplit(db_session, office, codes, engine_on):
    plan = _plan(db_session, pct="80", cat="01")
    pat = _patient(db_session, office, plan)
    current = PatientProcedure(patient_id=pat.id, procedure_code="D0120", office_id=office.id,
                               fee=D("100.00"), claim_id="CLM1")
    out = _split(db_session, {"fee": D("200.00")}, current=current)
    assert out == {"fee": D("200.00")}               # untouched — a claimed charge is frozen


def test_update_without_fee_change_is_noop(db_session, office, codes, engine_on):
    pat = _patient(db_session, office)
    current = PatientProcedure(patient_id=pat.id, procedure_code="D0120", office_id=office.id,
                               fee=D("100.00"), claim_id=None)
    out = _split(db_session, {"provider_id": "X"}, current=current)
    assert out == {"provider_id": "X"}


# ── integration through the real CRUD write path + estimate parity ───────────


def test_posted_charge_persists_the_split(db_session, office, codes, provider, engine_on):
    plan = _plan(db_session, pct="80", cat="01")
    pat = _patient(db_session, office, plan)
    s = _schedule(db_session, "Office default", "D0120", "100.00")
    office.default_fee_schedule_id = s.id
    db_session.commit()

    obj = patient_procedure_crud.create(
        db_session, {"id": "ASPLIT-1", "patient_id": pat.id, "procedure_code": "D0120",
                     "office_id": office.id, "provider_id": provider.id,
                     "date_of_service": TODAY},
        tenant_id=db_session._tenant_id,
    )
    assert obj.fee == D("100.00")
    assert obj.insurance_estimate == D("80.00")
    assert obj.patient_estimate == D("20.00")
    assert obj.coverage_pct == D("80.00")
    assert obj.fee_source == "office_default"


def test_single_post_equals_one_line_estimate(db_session, office, codes, provider, engine_on):
    plan = _plan(db_session, pct="80", cat="01", deductible="50", annual_max="1000")
    pat = _patient(db_session, office, plan)
    s = _schedule(db_session, "Office default", "D0120", "100.00")
    office.default_fee_schedule_id = s.id
    db_session.commit()

    est = estimate_service.estimate(
        db_session, pat.id, db_session._tenant_id,
        lines=[{"procedure_code": "D0120"}], office_id=office.id,
    )["lines"][0]
    obj = patient_procedure_crud.create(
        db_session, {"id": "ASPLIT-2", "patient_id": pat.id, "procedure_code": "D0120",
                     "office_id": office.id, "provider_id": provider.id,
                     "date_of_service": TODAY},
        tenant_id=db_session._tenant_id,
    )
    assert obj.fee == est["fee"]
    assert obj.insurance_estimate == est["insurance_estimate"]
    assert obj.patient_estimate == est["patient_estimate"]
    assert obj.estimated_deductible == est["estimated_deductible"]
