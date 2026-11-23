"""TX-MAX-1..6 — the treatment-plan estimate respects the annual maximum.

Repro shape from the devreport: a plan with $1,000 max / $50 deductible got
three lines each split against the *full* remaining benefit (deductible taken
three times, 1,689.20 insurance on a $1,000 max).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import (
    InsuranceCarrier,
    InsuranceClaim,
    InsuranceCoverageRule,
    InsurancePlan,
    Office,
    Patient,
    PatientInsurance,
    ProcedureCode,
    TreatmentPlan,
    TreatmentPlanInsuranceDetail,
    TreatmentPlanItem,
)
from app.services import benefit_usage_service as bus
from app.services import estimate_service, treatment_service
from app.services.treatment_service import TreatmentPlanItemCRUD

D = Decimal
PREFIX = "/api/v1"

item_crud = TreatmentPlanItemCRUD(
    TreatmentPlanItem, soft_delete_field="is_archived", soft_delete_value=True,
    default_sort="created_at",
)


@pytest.fixture(autouse=True)
def engine_on(monkeypatch):
    monkeypatch.setattr(settings, "PRICING_ENGINE_V2", True)
    monkeypatch.setattr(settings, "TX_PLAN_AUTO_RENET", True)


@pytest.fixture
def setup(db_session):
    t = db_session._tenant_id
    office = Office(tenant_id=t, office_code="TXM", name="TxMax Office", short_id="TXM")
    db_session.add(office)
    db_session.add_all([
        ProcedureCode(code="D2740", description="Crown", category="Rest",
                      coverage_category="03A", default_fee=D("0")),
        ProcedureCode(code="D2950", description="Core buildup", category="Rest",
                      coverage_category="03A", default_fee=D("0")),
        ProcedureCode(code="D3330", description="Molar RCT", category="Endo",
                      coverage_category="04", default_fee=D("0")),
        ProcedureCode(code="D0150", description="Comp exam", category="Diag",
                      coverage_category="01", default_fee=D("0"),
                      exempt_from_dental_max=True),
    ])
    carrier = InsuranceCarrier(tenant_id=t, name="MaxCo")
    db_session.add(carrier)
    db_session.commit()
    plan = InsurancePlan(tenant_id=t, carrier_id=carrier.id, group_number="G-1",
                         is_active=True, individual_max=D("1000"),
                         individual_deductible=D("50"), anniversary_month=1, anniversary_day=1)
    db_session.add(plan)
    db_session.commit()
    for cat, pct in (("03A", "50"), ("04", "80"), ("01", "100")):
        db_session.add(InsuranceCoverageRule(ins_plan_id=plan.id, start_code=cat, end_code=cat,
                                             category="0", coverage_pct=D(pct), ded_waived=False))
    pat = Patient(tenant_id=t, first_name="Kris", last_name="Max", chart_no="TXM-1",
                  home_office_id=office.id, is_active=True)
    db_session.add(pat)
    db_session.commit()
    slot = PatientInsurance(patient_id=pat.id, ins_plan_id=plan.id, legacy_plan_type="D",
                            insurance_type="primary", is_active=True,
                            max_remaining=D("1000"), deductible_remaining=D("50"))
    db_session.add(slot)
    tp = TreatmentPlan(id="TP-TXM", patient_id=pat.id, name="Plan 1", office_id=office.id,
                       status="active")
    db_session.add(tp)
    db_session.commit()
    return {"office": office, "carrier": carrier, "plan": plan, "patient": pat,
            "slot": slot, "tp": tp}


def _add(db, plan_id, item_id, code, fee, **extra):
    return item_crud.create(
        db, {"id": item_id, "plan_id": plan_id, "procedure_code": code, "fee": D(fee), **extra},
        tenant_id=db._tenant_id,
    )


def _items(db, plan_id="TP-TXM"):
    db.expire_all()
    return {i.id: i for i in db.query(TreatmentPlanItem).filter_by(plan_id=plan_id, is_archived=False)}


def _add_repro_lines(db):
    _add(db, "TP-TXM", "L1", "D2740", "1102.00", priority=1)
    _add(db, "TP-TXM", "L2", "D2950", "204.00", priority=2)
    _add(db, "TP-TXM", "L3", "D3330", "1114.00", priority=3)


# ── TX-MAX-1: item create nets the plan ──────────────────────────────────────
def test_item_creates_net_deductible_once_and_cap_at_max(db_session, setup):
    _add_repro_lines(db_session)
    items = _items(db_session)
    total = sum(i.insurance_estimate for i in items.values())
    assert total <= D("1000.00")
    assert total == D("1000.00")
    # Deductible taken once, on the first line.
    assert [items[k].estimated_deductible for k in ("L1", "L2", "L3")] == [D("50.00"), D("0.00"), D("0.00")]
    assert items["L1"].insurance_estimate == D("526.00")      # (1102-50) x 50%
    assert items["L2"].insurance_estimate == D("102.00")      # 204 x 50%
    assert items["L3"].insurance_estimate == D("372.00")      # 891.20 capped at what is left


def test_manual_est_ins_patch_is_not_renetted(db_session, setup):
    _add_repro_lines(db_session)
    item_crud.update(db_session, "L2", {"insurance_estimate": D("10.00")},
                     tenant_id=db_session._tenant_id)
    assert _items(db_session)["L2"].insurance_estimate == D("10.00")


def test_delete_frees_benefit_for_later_lines(db_session, setup):
    _add_repro_lines(db_session)
    item_crud.delete(db_session, "L1", tenant_id=db_session._tenant_id)
    items = _items(db_session)
    assert items["L2"].estimated_deductible == D("50.00")
    assert items["L2"].insurance_estimate == D("77.00")       # (204-50) x 50%
    assert items["L3"].insurance_estimate == D("891.20")


def test_fee_patch_renets(db_session, setup):
    _add_repro_lines(db_session)
    item_crud.update(db_session, "L1", {"fee": D("100.00")}, tenant_id=db_session._tenant_id)
    items = _items(db_session)
    assert items["L1"].insurance_estimate == D("25.00")       # (100-50) x 50%
    assert items["L3"].insurance_estimate == D("873.00")      # 1000 - 25 - 102


def test_kill_switch_leaves_provisional_split(db_session, setup, monkeypatch):
    monkeypatch.setattr(settings, "TX_PLAN_AUTO_RENET", False)
    _add_repro_lines(db_session)
    items = _items(db_session)
    # The old per-line behaviour: each line against the full benefit.
    assert [items[k].estimated_deductible for k in ("L1", "L2", "L3")] == [D("50.00")] * 3


# ── TX-MAX-2: one engine ─────────────────────────────────────────────────────
def test_re_estimate_matches_charge_engine_and_honours_exemption(db_session, setup):
    _add(db_session, "TP-TXM", "X1", "D0150", "72.00", priority=0)
    _add_repro_lines(db_session)
    res = treatment_service.re_estimate(db_session, "TP-TXM", db_session._tenant_id)
    by_code = {line.procedure_code: line for line in res.lines}
    # Exempt from the dental max: paid in full and does not consume it, so the
    # three restorative lines still get the whole $1,000.
    assert by_code["D0150"].insurance_estimate == D("22.00")  # (72-50) x 100%, ded taken here
    restorative = sum(by_code[c].insurance_estimate for c in ("D2740", "D2950", "D3330"))
    assert restorative == D("1000.00")
    # Same figure the charge-side estimate gives for the first line alone.
    est = estimate_service.estimate(
        db_session, setup["patient"].id, db_session._tenant_id,
        lines=[{"procedure_code": "D0150", "fee": D("72.00")}],
    )
    assert est["lines"][0]["insurance_estimate"] == by_code["D0150"].insurance_estimate


def test_exhausted_max_burns_no_deductible(db_session, setup):
    setup["slot"].max_remaining = D("0")
    db_session.commit()
    _add(db_session, "TP-TXM", "L1", "D2740", "1102.00")
    item = _items(db_session)["L1"]
    assert item.insurance_estimate == D("0.00")
    assert item.estimated_deductible == D("0.00")


# ── TX-MAX-3: effective remaining max ────────────────────────────────────────
def _claim(db, setup, cid, *, paid="0", est="0", status="paid", dos=None, plan_id=True,
           preauth=False):
    db.add(InsuranceClaim(
        id=cid, patient_id=setup["patient"].id, claim_number=cid, status=status,
        claim_type="primary", total_paid=D(paid), est_insurance=D(est),
        date_of_service_from=dos or date.today(), is_preauth=preauth,
        ins_plan_id=setup["plan"].id if plan_id else None,
        carrier_id=setup["carrier"].id,
    ))
    db.commit()


def test_claims_in_benefit_year_reduce_remaining(db_session, setup):
    setup["slot"].max_remaining = None
    db_session.commit()
    _claim(db_session, setup, "C1", paid="300")                         # settled
    _claim(db_session, setup, "C2", est="150", status="submitted")      # open -> estimate
    _claim(db_session, setup, "C3", paid="999", status="void")          # never counts
    _claim(db_session, setup, "C4", est="999", preauth=True)            # never counts
    _claim(db_session, setup, "C5", paid="999",
           dos=date.today().replace(month=1, day=1) - timedelta(days=1))  # last year
    _claim(db_session, setup, "C6", paid="25", plan_id=False)           # carrier match
    b = bus.slot_benefits(db_session, [setup["slot"]])[setup["slot"].id]
    assert b.benefits_used_ytd == D("475.00")
    assert b.max_remaining_effective == D("525.00")
    assert b.max_remaining_source == "claims"
    assert sorted(b.claim_ids) == ["C1", "C2", "C6"]


def test_slot_column_caps_derived_figure(db_session, setup):
    setup["slot"].max_remaining = D("200")
    db_session.commit()
    _claim(db_session, setup, "C1", paid="300")
    b = bus.slot_benefits(db_session, [setup["slot"]])[setup["slot"].id]
    assert b.max_remaining_effective == D("200.00")
    assert b.max_remaining_source == "claims_capped_by_slot"


def test_stale_slot_column_resets_with_benefit_year(db_session, setup):
    slot = setup["slot"]
    slot.max_remaining = D("0")
    slot.deductible_remaining = D("0")
    db_session.commit()
    last_year = datetime(date.today().year - 1, 6, 1)
    db_session.query(PatientInsurance).filter_by(id=slot.id).update(
        {"created_at": last_year, "updated_at": last_year})
    db_session.commit()
    db_session.refresh(slot)
    b = bus.slot_benefits(db_session, [slot])[slot.id]
    assert b.slot_values_stale is True
    assert b.max_remaining_effective == D("1000.00")
    assert b.max_remaining_source == "plan"
    assert b.deductible_remaining_effective == D("50.00")


def test_benefit_year_window_follows_anniversary():
    plan = InsurancePlan(anniversary_month=7, anniversary_day=1)
    assert bus.benefit_year_window(plan, date(2026, 11, 21)) == (date(2026, 7, 1), date(2027, 7, 1))
    assert bus.benefit_year_window(plan, date(2026, 3, 1)) == (date(2025, 7, 1), date(2026, 7, 1))
    assert bus.benefit_year_window(None, date(2026, 3, 1)) == (date(2026, 1, 1), date(2027, 1, 1))


def test_patient_insurance_read_exposes_effective_figures(client, db_session, setup):
    _claim(db_session, setup, "C1", paid="300")
    r = client.get(f"{PREFIX}/patient-insurance/{setup['slot'].id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["benefits_used_ytd"]) == 300
    assert float(body["max_remaining_effective"]) == 700
    assert body["max_remaining_source"] == "claims"
    assert body["benefit_year_start"] == f"{date.today().year}-01-01"
    assert float(body["max_remaining"]) == 1000  # stored column untouched


# ── TX-MAX-4: which lines consume ────────────────────────────────────────────
def test_completed_and_alternative_lines_do_not_consume(db_session, setup):
    _add(db_session, "TP-TXM", "A1", "D2740", "1102.00", priority=0, status="alternative")
    _add_repro_lines(db_session)
    res = treatment_service.re_estimate(db_session, "TP-TXM", db_session._tenant_id)
    by_id = {line.item_id: line for line in res.lines}
    assert by_id["A1"].consumes_benefit is False
    assert by_id["A1"].insurance_estimate == D("526.00")  # estimated, against what is left
    # ... but the real lines still get the deductible + the whole max.
    assert by_id["L1"].deductible_applied == D("50.00")
    assert sum(by_id[k].insurance_estimate for k in ("L1", "L2", "L3")) == D("1000.00")


# ── TX-MAX-5: cross-plan + benefit year ──────────────────────────────────────
def test_older_open_plan_is_netted_first(db_session, setup):
    older = TreatmentPlan(id="TP-OLD", patient_id=setup["patient"].id, name="Older",
                          office_id=setup["office"].id, status="active",
                          created_at=datetime(2020, 1, 1))
    db_session.add(older)
    db_session.commit()
    _add(db_session, "TP-OLD", "O1", "D3330", "1114.00")   # ded 50 + 851.20 of the max
    _add_repro_lines(db_session)
    res = treatment_service.re_estimate(db_session, "TP-TXM", db_session._tenant_id)
    assert res.netted_plan_ids == ["TP-OLD"]
    assert res.total_insurance_estimate == D("148.80")      # 1000 - 851.20
    assert all(line.deductible_applied == D("0.00") for line in res.lines)
    assert res.annual_max_remaining_after == D("0.00")
    # A closed plan no longer competes.
    older.status = "completed"
    db_session.commit()
    res = treatment_service.re_estimate(db_session, "TP-TXM", db_session._tenant_id)
    assert res.netted_plan_ids == []
    assert res.total_insurance_estimate == D("1000.00")


def test_line_booked_in_next_benefit_year_gets_fresh_benefit(db_session, setup):
    _add_repro_lines(db_session)
    next_year = date(date.today().year + 1, 2, 1)
    _add(db_session, "TP-TXM", "N1", "D3330", "1114.00", priority=9, start_date=next_year)
    line = {ln.item_id: ln for ln in treatment_service.re_estimate(
        db_session, "TP-TXM", db_session._tenant_id).lines}["N1"]
    assert line.benefit_year_start == date(next_year.year, 1, 1)
    assert line.deductible_applied == D("50.00")
    assert line.insurance_estimate == D("851.20")           # (1114-50) x 80%, fresh max


# ── TX-MAX-6: report payload ─────────────────────────────────────────────────
def test_report_carries_primary_insurance_and_remaining_max(db_session, setup):
    _add(db_session, "TP-TXM", "L1", "D2740", "1102.00")
    rep = treatment_service.plan_report(db_session, "TP-TXM", db_session._tenant_id)
    assert rep.primary_insurance is not None
    assert rep.primary_insurance.carrier_name == "MaxCo"
    assert rep.primary_insurance.label == "MaxCo #G-1"
    assert rep.annual_max_remaining_after == D("474.00")    # 1000 - 526
    assert rep.deductible_remaining_after == D("0.00")


def test_uninsured_line_grows_no_insurance_detail(db_session, setup):
    setup["slot"].is_active = False
    db_session.commit()
    _add(db_session, "TP-TXM", "U1", "D2740", "1102.00")
    assert db_session.query(TreatmentPlanInsuranceDetail).filter_by(plan_item_id="U1").count() == 0
    assert _items(db_session)["U1"].insurance_estimate == D("0.00")
