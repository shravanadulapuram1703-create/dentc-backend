"""The v2 split engine — benefit models, cap-before-deductible, COB (R1).

Fees are supplied as line overrides so each test isolates the *split* arithmetic
from fee resolution (which ``test_pricing_hierarchy`` covers). The coverage
percentage comes from a real ``insurance_coverage_rules`` band on the plan.
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
    ProcedureCode,
)
from app.services import estimate_service

D = Decimal


@pytest.fixture(autouse=True)
def _engine_on(monkeypatch):
    monkeypatch.setattr(settings, "PRICING_ENGINE_V2", True)


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="EM1", name="Est Office", short_id="EM1")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def codes(db_session) -> None:
    # coverage_category is stored, so it drives the band match directly.
    db_session.add(ProcedureCode(code="D2393", description="Composite", category="Rest",
                                 coverage_category="03", default_fee=D("0")))
    db_session.add(ProcedureCode(code="D8080", description="Ortho", category="Ortho",
                                 coverage_category="10", default_fee=D("0"), is_ortho=True))
    db_session.commit()


def _plan(db_session, *, deductible="0", annual_max=None, ortho_max=None, non_dup=False,
          pct_by_cat=(("03", "80"),), name="Plan") -> InsurancePlan:
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name=name + " Carrier")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    p = InsurancePlan(
        tenant_id=db_session._tenant_id, carrier_id=carrier.id, group_number="G",
        is_active=True, individual_deductible=D(deductible),
        individual_max=(D(annual_max) if annual_max is not None else None),
        ortho_max=(D(ortho_max) if ortho_max is not None else None),
        is_non_dup_benefits=non_dup,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    for cat, pct in pct_by_cat:
        db_session.add(InsuranceCoverageRule(
            ins_plan_id=p.id, start_code=cat, end_code=cat, category="0",
            coverage_pct=D(pct), ded_waived=False))
    db_session.commit()
    return p


def _patient(db_session, office, *, slots) -> Patient:
    """``slots`` = list of dicts: plan, rank, plan_type, ded_remaining, max_remaining."""
    pat = Patient(tenant_id=db_session._tenant_id, first_name="Est", last_name="Pt",
                  chart_no="EM-1", home_office_id=office.id, is_active=True)
    db_session.add(pat)
    db_session.commit()
    db_session.refresh(pat)
    for s in slots:
        db_session.add(PatientInsurance(
            patient_id=pat.id, ins_plan_id=s["plan"].id, insurance_type=s.get("rank", "primary"),
            legacy_plan_type=s.get("plan_type", "D"), is_active=True,
            deductible_remaining=s.get("ded_remaining"), max_remaining=s.get("max_remaining"),
            ortho_remaining=s.get("ortho_remaining")))
    db_session.commit()
    return pat


def _est(db_session, patient, lines, **kw):
    return estimate_service.estimate(
        db_session, patient.id, db_session._tenant_id, lines=lines, **kw)


# ── Model A: percentage ──────────────────────────────────────────────────────


def test_percentage_split_no_deductible(db_session, office, codes):
    plan = _plan(db_session, deductible="0")
    pat = _patient(db_session, office, slots=[{"plan": plan}])
    line = _est(db_session, pat, [{"procedure_code": "D2393", "fee": "100.00"}])["lines"][0]
    assert line["coverage_pct"] == D("80")
    assert line["insurance_estimate"] == D("80.00")
    assert line["patient_estimate"] == D("20.00")
    assert line["benefit_model"] == "percentage"


def test_deductible_reduces_the_insured_base(db_session, office, codes):
    plan = _plan(db_session, deductible="50")
    pat = _patient(db_session, office, slots=[{"plan": plan}])  # slot ded NULL -> plan's 50
    line = _est(db_session, pat, [{"procedure_code": "D2393", "fee": "100.00"}])["lines"][0]
    assert line["estimated_deductible"] == D("50.00")
    assert line["insurance_estimate"] == D("40.00")   # 80% of (100 - 50)
    assert line["patient_estimate"] == D("60.00")


def test_annual_max_is_capped_before_deductible_is_burned(db_session, office, codes):
    # Benefit exhausted: the line must pay 0 AND not consume any deductible, so the
    # next line's math cannot depend on this one having burned it.
    plan = _plan(db_session, deductible="50", annual_max="1000")
    pat = _patient(db_session, office,
                   slots=[{"plan": plan, "max_remaining": "0", "ded_remaining": "50"}])
    line = _est(db_session, pat, [{"procedure_code": "D2393", "fee": "100.00"}])["lines"][0]
    assert line["insurance_estimate"] == D("0.00")
    assert line["estimated_deductible"] == D("0.00")
    assert line["patient_estimate"] == D("100.00")


def test_deductible_is_consumed_across_lines_in_one_estimate(db_session, office, codes):
    plan = _plan(db_session, deductible="50", annual_max="10000")
    pat = _patient(db_session, office, slots=[{"plan": plan}])
    out = _est(db_session, pat, [
        {"procedure_code": "D2393", "fee": "100.00"},
        {"procedure_code": "D2393", "fee": "100.00"},
    ])
    l1, l2 = out["lines"]
    assert l1["estimated_deductible"] == D("50.00")   # burns the whole deductible
    assert l1["insurance_estimate"] == D("40.00")
    assert l2["estimated_deductible"] == D("0.00")     # none left for line 2
    assert l2["insurance_estimate"] == D("80.00")
    assert out["insurance_estimate"] == D("120.00")


def test_annual_max_caps_the_insurance_estimate(db_session, office, codes):
    plan = _plan(db_session, deductible="0", annual_max="30")
    pat = _patient(db_session, office, slots=[{"plan": plan}])
    line = _est(db_session, pat, [{"procedure_code": "D2393", "fee": "100.00"}])["lines"][0]
    assert line["insurance_estimate"] == D("30.00")   # 80 would be 80, capped at 30
    assert line["patient_estimate"] == D("70.00")


def test_ortho_code_draws_on_the_ortho_maximum(db_session, office, codes):
    plan = _plan(db_session, deductible="0", annual_max="0", ortho_max="500",
                 pct_by_cat=(("10", "50"),))
    pat = _patient(db_session, office, slots=[{"plan": plan}])
    # annual max is 0 but ortho has its own bucket, so the ortho code still pays.
    line = _est(db_session, pat, [{"procedure_code": "D8080", "fee": "200.00"}])["lines"][0]
    assert line["insurance_estimate"] == D("100.00")   # 50% of 200, from the ortho max


# ── Model C: self-pay ────────────────────────────────────────────────────────


def test_no_active_coverage_is_self_pay(db_session, office, codes):
    pat = _patient(db_session, office, slots=[])
    line = _est(db_session, pat, [{"procedure_code": "D2393", "fee": "100.00"}])["lines"][0]
    assert line["insurance_estimate"] == D("0.00")
    assert line["patient_estimate"] == D("100.00")
    assert line["benefit_model"] == "self_pay"


def test_a_medical_slot_never_prices_dental(db_session, office, codes):
    plan = _plan(db_session)
    pat = _patient(db_session, office, slots=[{"plan": plan, "plan_type": "M"}])
    line = _est(db_session, pat, [{"procedure_code": "D2393", "fee": "100.00"}])["lines"][0]
    # The only slot is medical, so dental has no coverage: self-pay.
    assert line["insurance_estimate"] == D("0.00")
    assert line["benefit_model"] == "self_pay"


# ── NULL vs 0 remaining ──────────────────────────────────────────────────────


def test_zero_remaining_deductible_is_exhausted_not_unknown(db_session, office, codes):
    plan = _plan(db_session, deductible="50")
    pat = _patient(db_session, office, slots=[{"plan": plan, "ded_remaining": "0"}])
    line = _est(db_session, pat, [{"procedure_code": "D2393", "fee": "100.00"}])["lines"][0]
    # slot says 0 remaining -> no deductible applied, despite the plan's 50.
    assert line["estimated_deductible"] == D("0.00")
    assert line["insurance_estimate"] == D("80.00")


# ── secondary coordination of benefits ──────────────────────────────────────


def test_standard_cob_pays_the_remaining_balance(db_session, office, codes):
    primary = _plan(db_session, pct_by_cat=(("03", "80"),), name="Primary")
    secondary = _plan(db_session, pct_by_cat=(("03", "50"),), name="Secondary")
    pat = _patient(db_session, office, slots=[
        {"plan": primary, "rank": "primary"},
        {"plan": secondary, "rank": "secondary"},
    ])
    line = _est(db_session, pat, [{"procedure_code": "D2393", "fee": "100.00"}],
                include_secondary=True)["lines"][0]
    # primary 80; secondary normal 50 but capped at the 20 balance -> 20; patient 0.
    assert line["primary_insurance_estimate"] == D("80.00")
    assert line["sec_insurance_estimate"] == D("20.00")
    assert line["patient_estimate"] == D("0.00")


def test_non_duplication_secondary_pays_only_its_excess(db_session, office, codes):
    primary = _plan(db_session, pct_by_cat=(("03", "80"),), name="Primary")
    secondary = _plan(db_session, pct_by_cat=(("03", "50"),), non_dup=True, name="Secondary")
    pat = _patient(db_session, office, slots=[
        {"plan": primary, "rank": "primary"},
        {"plan": secondary, "rank": "secondary"},
    ])
    line = _est(db_session, pat, [{"procedure_code": "D2393", "fee": "100.00"}],
                include_secondary=True)["lines"][0]
    # non-dup: max(0, 50 - 80) = 0; patient owes the 20 the primary left.
    assert line["sec_insurance_estimate"] == D("0.00")
    assert line["patient_estimate"] == D("20.00")


def test_secondary_ignored_unless_requested(db_session, office, codes):
    primary = _plan(db_session, pct_by_cat=(("03", "80"),), name="Primary")
    secondary = _plan(db_session, pct_by_cat=(("03", "50"),), name="Secondary")
    pat = _patient(db_session, office, slots=[
        {"plan": primary, "rank": "primary"},
        {"plan": secondary, "rank": "secondary"},
    ])
    line = _est(db_session, pat, [{"procedure_code": "D2393", "fee": "100.00"}])["lines"][0]
    assert line["sec_insurance_estimate"] == D("0.00")
    assert line["insurance_estimate"] == D("80.00")


# ── Model B: copay list ──────────────────────────────────────────────────────


def test_copay_list_split_from_the_schedule(db_session, office, codes):
    plan = _plan(db_session, pct_by_cat=())   # a percentage rule would be ignored anyway
    copay = FeeSchedule(tenant_id=db_session._tenant_id, name="MCO", fee_type="plan",
                        pricing_model="copay", is_active=True)
    db_session.add(copay)
    db_session.commit()
    db_session.refresh(copay)
    # The Medicaid / MCO shape: patient fee blank, the plan-pays amount in the
    # insurance column (Denticon fs 147/148). The charge is that amount; the
    # patient owes nothing; the two columns are never summed.
    db_session.add(FeeScheduleEntry(fee_schedule_id=copay.id, tenant_id=db_session._tenant_id,
                                    procedure_code="D2393", patient_fee=None,
                                    insurance_fee=D("26.16"), effective_date=date(2020, 1, 1)))
    db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id,
                                         ins_plan_id=plan.id, fee_schedule_id=copay.id))
    db_session.commit()
    pat = _patient(db_session, office, slots=[{"plan": plan}])
    # No override: the copay schedule resolves the fee and states the split.
    line = _est(db_session, pat, [{"procedure_code": "D2393"}])["lines"][0]
    assert line["benefit_model"] == "copay"
    assert line["fee"] == D("26.16")                  # the plan-pays amount is the charge
    assert line["insurance_estimate"] == D("26.16")   # the plan pays it
    assert line["patient_estimate"] == D("0.00")


def test_copay_list_with_a_real_patient_copay(db_session, office, codes):
    """A DHMO copay: the patient owes a fixed amount and the plan pays the rest of
    the (small) charge — the two columns still are not summed."""
    plan = _plan(db_session, pct_by_cat=())
    copay = FeeSchedule(tenant_id=db_session._tenant_id, name="DHMO", fee_type="plan",
                        pricing_model="copay", is_active=True)
    db_session.add(copay)
    db_session.commit()
    db_session.refresh(copay)
    db_session.add(FeeScheduleEntry(fee_schedule_id=copay.id, tenant_id=db_session._tenant_id,
                                    procedure_code="D2393", patient_fee=D("15.00"),
                                    insurance_fee=D("0.00"), effective_date=date(2020, 1, 1)))
    db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id,
                                         ins_plan_id=plan.id, fee_schedule_id=copay.id))
    db_session.commit()
    pat = _patient(db_session, office, slots=[{"plan": plan}])
    line = _est(db_session, pat, [{"procedure_code": "D2393"}])["lines"][0]
    assert line["fee"] == D("15.00")                  # the patient copay is the charge
    assert line["insurance_estimate"] == D("0.00")
    assert line["patient_estimate"] == D("15.00")
