"""The v2 fee resolver — the precedence card, dated entries, copay lists (R1).

Every test flips ``settings.PRICING_ENGINE_V2`` on; the last one pins that with
the flag **off** the resolver is unchanged, because that is what makes shipping the
engine dark safe. The order under test is the card in ``fee_vocab``:

    override > plan asg > carrier asg > patient list > provider asg > office default > office UCR

with the rules that make it deterministic: a plan-keyed assignment beats a
carrier+office one (rank vector, not key count), a 0.00 fee on a percentage list is
"not priced", a payer list that lacks the code is a flagged gap rather than a silent
fall-through, and a fee that starts after the service date is never used.
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
    InsurancePlan,
    Office,
    Patient,
    PatientInsurance,
    Provider,
    ProcedureCode,
)
from app.services import pricing_service

TODAY = date.today()


@pytest.fixture(autouse=True)
def _engine_on(monkeypatch):
    """Every test in this module exercises the v2 resolver."""
    monkeypatch.setattr(settings, "PRICING_ENGINE_V2", True)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="PH1", name="Pricing Office",
               short_id="PH1", timezone="America/New_York")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def carrier(db_session) -> InsuranceCarrier:
    c = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Acme Dental")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def plan(db_session, carrier) -> InsurancePlan:
    p = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                      group_number="G1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def codes(db_session) -> None:
    for code, desc in [("D0120", "Periodic exam"), ("D2740", "Crown")]:
        db_session.add(ProcedureCode(code=code, description=desc, category="X",
                                     default_fee=Decimal("10.00")))
    db_session.commit()


@pytest.fixture
def patient(db_session, office, plan, codes) -> Patient:
    pat = Patient(tenant_id=db_session._tenant_id, first_name="Pat", last_name="Ient",
                  chart_no="PH-1", home_office_id=office.id, is_active=True)
    db_session.add(pat)
    db_session.commit()
    db_session.refresh(pat)
    db_session.add(PatientInsurance(patient_id=pat.id, ins_plan_id=plan.id,
                                    legacy_plan_type="D", insurance_type="primary", is_active=True))
    db_session.commit()
    return pat


@pytest.fixture
def provider(db_session, office) -> Provider:
    prov = Provider(id="PHPRV", tenant_id=db_session._tenant_id, office_id=office.id,
                    name="Dr Ph")
    db_session.add(prov)
    db_session.commit()
    db_session.refresh(prov)
    return prov


def _schedule(db_session, name, entries, *, fee_type="standard", pricing_model="percentage",
              is_active=True) -> FeeSchedule:
    """``entries`` maps code -> patient_fee, or code -> dict(patient_fee=, insurance_fee=,
    effective_date=, is_no_charge=) for the rarer shapes."""
    sched = FeeSchedule(tenant_id=db_session._tenant_id, name=name, fee_type=fee_type,
                        pricing_model=pricing_model, is_active=is_active)
    db_session.add(sched)
    db_session.commit()
    db_session.refresh(sched)
    for code, spec in entries.items():
        kw = dict(fee_schedule_id=sched.id, tenant_id=db_session._tenant_id,
                  procedure_code=code, effective_date=TODAY)
        if isinstance(spec, dict):
            kw.update(spec)
        else:
            kw["patient_fee"] = Decimal(str(spec))
        db_session.add(FeeScheduleEntry(**kw))
    db_session.commit()
    return sched


def _assign(db_session, schedule, **keys) -> None:
    db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id,
                                         fee_schedule_id=schedule.id, **keys))
    db_session.commit()


def _quote(db_session, office, code="D0120", patient=None, **kw):
    return pricing_service.resolve_procedure_fee(
        db_session, db_session._tenant_id, code,
        patient_id=patient.id if patient else None, office_id=office.id, **kw,
    )


# ── the precedence card ──────────────────────────────────────────────────────


def test_tier_order_plan_beats_patient_beats_office_default_beats_ucr(
    db_session, office, patient, plan
):
    plan_list = _schedule(db_session, "Plan rate", {"D0120": "30.00"}, fee_type="carrier")
    patient_list = _schedule(db_session, "Patient rate", {"D0120": "40.00"})
    office_default = _schedule(db_session, "Office default", {"D0120": "50.00"})
    ucr = _schedule(db_session, "UCR", {"D0120": "150.00"}, fee_type="ucr")
    _assign(db_session, plan_list, ins_plan_id=plan.id)
    patient.fee_schedule_id = patient_list.id
    office.default_fee_schedule_id = office_default.id
    office.default_ucr_fee_schedule_id = ucr.id
    db_session.commit()

    q = _quote(db_session, office, patient=patient)
    assert q["fee"] == Decimal("30.00")
    assert q["fee_source"] == "assignment_plan"
    assert q["ucr_fee"] == Decimal("150.00")
    # UCR minus the contracted fee is the write-off, whatever tier priced the fee.
    assert q["expected_write_off"] == Decimal("120.00")


def test_patient_list_used_when_no_payer_assignment(db_session, office, patient):
    patient_list = _schedule(db_session, "Patient rate", {"D0120": "40.00"})
    office_default = _schedule(db_session, "Office default", {"D0120": "50.00"})
    patient.fee_schedule_id = patient_list.id
    office.default_fee_schedule_id = office_default.id
    db_session.commit()

    q = _quote(db_session, office, patient=patient)
    assert q["fee"] == Decimal("40.00")
    assert q["fee_source"] == "patient_schedule"


def test_office_default_then_ucr(db_session, office, patient):
    office_default = _schedule(db_session, "Office default", {"D0120": "50.00"})
    ucr = _schedule(db_session, "UCR", {"D0120": "150.00"}, fee_type="ucr")
    office.default_fee_schedule_id = office_default.id
    office.default_ucr_fee_schedule_id = ucr.id
    db_session.commit()

    q = _quote(db_session, office, patient=patient)
    assert q["fee"] == Decimal("50.00")
    assert q["fee_source"] == "office_default"

    # Remove the default: UCR becomes the priced tier and there is no write-off.
    office.default_fee_schedule_id = None
    db_session.commit()
    q = _quote(db_session, office, patient=patient)
    assert q["fee"] == Decimal("150.00")
    assert q["fee_source"] == "office_ucr"
    assert q["expected_write_off"] is None


def test_plan_assignment_beats_carrier_plus_office(db_session, office, patient, plan, carrier):
    plan_list = _schedule(db_session, "Plan", {"D0120": "30.00"}, fee_type="carrier")
    carrier_office_list = _schedule(db_session, "Carrier+office", {"D0120": "20.00"}, fee_type="carrier")
    _assign(db_session, plan_list, ins_plan_id=plan.id)
    _assign(db_session, carrier_office_list, carrier_id=carrier.id, office_id=office.id)

    q = _quote(db_session, office, patient=patient)
    # Key-count would pick carrier+office (2 keys); the rank vector picks the plan.
    assert q["fee"] == Decimal("30.00")
    assert q["fee_source"] == "assignment_plan"


def test_unpriced_when_no_tier_prices_the_code(db_session, office, patient):
    q = _quote(db_session, office, patient=patient)
    assert q["is_unpriced"] is True
    assert q["fee_source"] == "unpriced"
    assert q["fee"] == Decimal("0")
    assert "unpriced" in q["warnings"]
    # default_fee is NOT a pricing tier in v2.
    assert q["fee_schedule_id"] is None


# ── dated entries ────────────────────────────────────────────────────────────


def test_date_of_service_selects_the_entry_in_force(db_session, office, patient):
    sched = _schedule(db_session, "Dated", {
        "D0120": {"patient_fee": Decimal("40.00"), "effective_date": date(2024, 1, 1)},
    })
    db_session.add(FeeScheduleEntry(
        fee_schedule_id=sched.id, tenant_id=db_session._tenant_id, procedure_code="D0120",
        patient_fee=Decimal("55.00"), effective_date=date(2025, 6, 1)))
    office.default_fee_schedule_id = sched.id
    db_session.commit()

    old = _quote(db_session, office, patient=patient, date_of_service=date(2024, 6, 1))
    assert old["fee"] == Decimal("40.00")
    assert old["fee_effective_date"] == "2024-01-01"
    new = _quote(db_session, office, patient=patient, date_of_service=date(2025, 12, 1))
    assert new["fee"] == Decimal("55.00")
    assert new["fee_effective_date"] == "2025-06-01"


def test_back_dated_service_before_all_entries_uses_earliest_and_warns(db_session, office, patient):
    sched = _schedule(db_session, "Loaded 2024", {
        "D0120": {"patient_fee": Decimal("40.00"), "effective_date": date(2024, 1, 1)},
    })
    office.default_fee_schedule_id = sched.id
    db_session.commit()
    q = _quote(db_session, office, patient=patient, date_of_service=date(2019, 3, 1))
    assert q["fee"] == Decimal("40.00")
    assert "entry_predates_service_date" in q["warnings"]


def test_future_only_entries_are_not_priced_today(db_session, office, patient):
    future = TODAY + timedelta(days=60)
    sched = _schedule(db_session, "Next quarter", {
        "D0120": {"patient_fee": Decimal("40.00"), "effective_date": future},
    })
    office.default_fee_schedule_id = sched.id
    db_session.commit()
    q = _quote(db_session, office, patient=patient, date_of_service=TODAY)
    # Pricing today at next quarter's fee is exactly what the date logic prevents.
    assert q["is_unpriced"] is True
    assert "entry_not_yet_effective" in q["warnings"]


# ── zero / no-charge ─────────────────────────────────────────────────────────


def test_zero_fee_entry_on_a_percentage_list_is_skipped(db_session, office, patient):
    zero_list = _schedule(db_session, "Has a 0.00", {"D0120": "0.00"})
    real_list = _schedule(db_session, "Office default", {"D0120": "44.00"})
    patient.fee_schedule_id = zero_list.id       # tier 3, but its fee is 0.00
    office.default_fee_schedule_id = real_list.id  # tier 5
    db_session.commit()
    q = _quote(db_session, office, patient=patient)
    # The 0.00 is treated as "not priced", so the walk continues to the office list.
    assert q["fee"] == Decimal("44.00")
    assert q["fee_source"] == "office_default"


def test_explicit_no_charge_entry_prices_at_zero(db_session, office, patient):
    free_list = _schedule(db_session, "No charge", {
        "D0120": {"patient_fee": Decimal("0.00"), "is_no_charge": True},
    })
    patient.fee_schedule_id = free_list.id
    db_session.commit()
    q = _quote(db_session, office, patient=patient)
    assert q["fee"] == Decimal("0")
    assert q["fee_source"] == "patient_schedule"
    assert q["is_unpriced"] is False


# ── copay lists ──────────────────────────────────────────────────────────────


def test_copay_list_prices_from_the_plan_pays_amount(db_session, office, patient, plan):
    copay = _schedule(db_session, "Medicaid MCO", {
        "D0120": {"patient_fee": None, "insurance_fee": Decimal("26.16")},
    }, fee_type="plan", pricing_model="copay")
    _assign(db_session, copay, ins_plan_id=plan.id)
    q = _quote(db_session, office, patient=patient)
    # patient_fee is blank, so the charge amount is the plan-pays figure — never summed.
    assert q["fee"] == Decimal("26.16")
    assert q["pricing_model"] == "copay"
    assert q["payer_amount"] == Decimal("26.16")


def test_copay_list_never_sums_both_columns(db_session, office, patient, plan):
    copay = _schedule(db_session, "Both columns", {
        "D0120": {"patient_fee": Decimal("10.00"), "insurance_fee": Decimal("26.16")},
    }, fee_type="plan", pricing_model="copay")
    _assign(db_session, copay, ins_plan_id=plan.id)
    q = _quote(db_session, office, patient=patient)
    # patient copay present -> that is the charge; the two are never added to 36.16.
    assert q["fee"] == Decimal("10.00")
    assert q["payer_amount"] == Decimal("26.16")


# ── payer gap and legacy rows ────────────────────────────────────────────────


def test_payer_list_missing_the_code_is_flagged_not_silently_skipped(
    db_session, office, patient, plan
):
    plan_list = _schedule(db_session, "Plan (no D2740)", {"D0120": "30.00"}, fee_type="carrier")
    office_default = _schedule(db_session, "Office", {"D2740": "800.00"})
    _assign(db_session, plan_list, ins_plan_id=plan.id)
    office.default_fee_schedule_id = office_default.id
    db_session.commit()
    q = _quote(db_session, office, code="D2740", patient=patient)
    # The plan's list applies but does not price the crown: it falls through to the
    # office list, and the gap is surfaced for the fee-schedule owner.
    assert q["fee"] == Decimal("800.00")
    assert q["fee_source"] == "office_default"
    assert "code_missing_on_bound_schedule" in q["warnings"]
    assert any(s["fee_schedule_id"] == plan_list.id for s in q["skipped"])


def test_legacy_targetless_assignment_is_ignored(db_session, office, patient):
    practice_wide = _schedule(db_session, "Legacy practice-wide", {"D0120": "999.00"})
    office_default = _schedule(db_session, "Office", {"D0120": "44.00"})
    _assign(db_session, practice_wide)  # every key NULL — a legacy row
    office.default_fee_schedule_id = office_default.id
    db_session.commit()
    q = _quote(db_session, office, patient=patient)
    # v2 ignores the all-NULL row; the office default wins.
    assert q["fee"] == Decimal("44.00")
    assert q["fee_source"] == "office_default"


def test_inactive_schedule_is_skipped(db_session, office, patient):
    retired = _schedule(db_session, "Retired", {"D0120": "60.00"}, is_active=False)
    live = _schedule(db_session, "Office", {"D0120": "44.00"})
    patient.fee_schedule_id = retired.id
    office.default_fee_schedule_id = live.id
    db_session.commit()
    q = _quote(db_session, office, patient=patient)
    assert q["fee"] == Decimal("44.00")
    assert q["fee_source"] == "office_default"


# ── the flag itself ──────────────────────────────────────────────────────────


def test_flag_off_uses_the_v1_resolver(db_session, office, patient, monkeypatch):
    monkeypatch.setattr(settings, "PRICING_ENGINE_V2", False)
    office_default = _schedule(db_session, "Office", {"D0120": "44.00"})
    office.default_fee_schedule_id = office_default.id
    db_session.commit()
    q = _quote(db_session, office, patient=patient)
    # v1 prices the office default too, but reports specificity and no v2 keys.
    assert q["fee"] == Decimal("44.00")
    assert q["fee_source"] == "office_default"
    assert "is_unpriced" not in q
    assert "warnings" not in q
