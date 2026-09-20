"""Treatment-plan-item split wiring (R1 step 3c).

``apply_split`` in **split-only** mode fills the item's coverage split behind
``PRICING_ENGINE_V2`` while leaving the fee / ``fee_schedule_id`` set by
``_price_item`` (PLAN-29) untouched, and never writes a ``patient_estimate``
(the item has no such column — the detail row carries the patient portion).

* flag off — an item created/edited through ``TreatmentPlanItemCRUD`` carries no
  split (owned by the plan-level ``re_estimate``), exactly as today.
* flag on — a created line carries a per-line split immediately, an edit that
  changes the fee re-splits in place, and an edit that does not touch the fee
  leaves the split alone.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import (
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    Office,
    Patient,
    PatientInsurance,
    ProcedureCode,
    TreatmentPlan,
    TreatmentPlanItem,
)
from app.services.treatment_service import TreatmentPlanItemCRUD

D = Decimal

item_crud = TreatmentPlanItemCRUD(
    TreatmentPlanItem, soft_delete_field="is_archived", soft_delete_value=True,
    default_sort="created_at",
)


@pytest.fixture
def engine_on(monkeypatch):
    monkeypatch.setattr(settings, "PRICING_ENGINE_V2", True)


@pytest.fixture
def engine_off(monkeypatch):
    monkeypatch.setattr(settings, "PRICING_ENGINE_V2", False)


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="TI1",
               name="TxItem Office", short_id="TI1")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def codes(db_session) -> None:
    db_session.add(ProcedureCode(code="D0120", description="Exam", category="Diag",
                                 coverage_category="01", default_fee=D("0")))
    db_session.commit()


def _covered_patient(db_session, office, *, pct="80", cat="01"):
    c = InsuranceCarrier(tenant_id=db_session._tenant_id, name="TI Carrier")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=c.id, group_number="G",
                         is_active=True, individual_deductible=D("0"))
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(InsuranceCoverageRule(ins_plan_id=plan.id, start_code=cat, end_code=cat,
                                         category="0", coverage_pct=D(pct), ded_waived=False))
    pat = Patient(tenant_id=db_session._tenant_id, first_name="Tx", last_name="Item",
                  chart_no="TI-1", home_office_id=office.id, is_active=True)
    db_session.add(pat)
    db_session.commit()
    db_session.refresh(pat)
    db_session.add(PatientInsurance(patient_id=pat.id, ins_plan_id=plan.id,
                                    legacy_plan_type="D", insurance_type="primary", is_active=True))
    db_session.commit()
    return pat


def _plan(db_session, patient, office) -> str:
    tp = TreatmentPlan(id="TP-TI", patient_id=patient.id, name="Plan", office_id=office.id)
    db_session.add(tp)
    db_session.commit()
    return tp.id


def _create(db_session, plan_id, item_id, **extra):
    return item_crud.create(
        db_session,
        {"id": item_id, "plan_id": plan_id, "procedure_code": "D0120", **extra},
        tenant_id=db_session._tenant_id,
    )


# ── flag off ─────────────────────────────────────────────────────────────────


def test_flag_off_item_create_writes_no_split(db_session, office, codes, engine_off):
    pat = _covered_patient(db_session, office)
    plan_id = _plan(db_session, pat, office)
    item = _create(db_session, plan_id, "TI-A", fee=D("100.00"))
    assert item.fee == D("100.00")
    # ``insurance_estimate`` has always defaulted to 0.00 (owned by the plan-level
    # re_estimate); ``coverage_pct`` is the R1 split column the engine writes, so
    # its being NULL is the real "no split written while dark" signal.
    assert item.insurance_estimate == D("0.00")
    assert item.coverage_pct is None


# ── flag on ─────────────────────────────────────────────────────────────────


def test_item_create_fills_split(db_session, office, codes, engine_on):
    pat = _covered_patient(db_session, office, pct="80")
    plan_id = _plan(db_session, pat, office)
    item = _create(db_session, plan_id, "TI-B", fee=D("100.00"))
    assert item.fee == D("100.00")                 # PLAN-29 fee untouched
    assert item.insurance_estimate == D("80.00")
    assert item.coverage_pct == D("80.00")
    assert item.coverage_rule_id is not None


def test_item_create_self_pay(db_session, office, codes, engine_on):
    pat = Patient(tenant_id=db_session._tenant_id, first_name="No", last_name="Ins",
                  chart_no="TI-2", home_office_id=office.id, is_active=True)
    db_session.add(pat)
    db_session.commit()
    db_session.refresh(pat)
    plan_id = _plan(db_session, pat, office)
    item = _create(db_session, plan_id, "TI-C", fee=D("100.00"))
    assert item.insurance_estimate == D("0.00")
    assert item.coverage_pct == D("0")


def test_item_update_reprices_split_on_fee_change(db_session, office, codes, engine_on):
    pat = _covered_patient(db_session, office, pct="80")
    plan_id = _plan(db_session, pat, office)
    item = _create(db_session, plan_id, "TI-D", fee=D("100.00"))
    assert item.insurance_estimate == D("80.00")

    updated = item_crud.update(db_session, "TI-D", {"fee": D("200.00")},
                               tenant_id=db_session._tenant_id)
    assert updated.fee == D("200.00")
    assert updated.insurance_estimate == D("160.00")  # 80 % of the new fee


def test_item_update_without_fee_change_keeps_split(db_session, office, codes, engine_on):
    pat = _covered_patient(db_session, office, pct="80")
    plan_id = _plan(db_session, pat, office)
    item = _create(db_session, plan_id, "TI-E", fee=D("100.00"))
    # Simulate an authoritative plan-level re_estimate having set a different value.
    item.insurance_estimate = D("55.00")
    db_session.commit()

    updated = item_crud.update(db_session, "TI-E", {"notes": "watch #3"},
                               tenant_id=db_session._tenant_id)
    assert updated.insurance_estimate == D("55.00")   # untouched — no fee change
