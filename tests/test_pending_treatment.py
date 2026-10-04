"""SCHED-PT-1..5: the scheduler "PT" (pending treatment) badge.

One rule (``treatment_service.pending_item_clauses``) read three ways: the
scheduler feed's ``pending_tx_*``, ``?pending=true`` on the patient items list
and ``GET /treatment-plan-items/pending-summary``.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from app.db.models import (
    Appointment,
    Office,
    Operatory,
    Patient,
    PatientProcedure,
    ProcedureCode,
    Provider,
    TreatmentPlan,
    TreatmentPlanItem,
)

PREFIX = "/api/v1"


@pytest.fixture
def pt(db_session):
    tid = db_session._tenant_id
    office = Office(tenant_id=tid, office_code="MAIN", name="Main")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    db_session.add_all([
        Provider(id="PRV-1", tenant_id=tid, office_id=office.id, name="Dr. Adams"),
        ProcedureCode(code="D2330", description="Resin", category="Restorative"),
    ])
    db_session.flush()
    db_session.add(Operatory(id="OPR-1", office_id=office.id, name="Op 1", provider_id="PRV-1"))
    a = Patient(tenant_id=tid, first_name="Pend", last_name="Ing", chart_no="PT-A")
    b = Patient(tenant_id=tid, first_name="None", last_name="Open", chart_no="PT-B")
    db_session.add_all([a, b])
    db_session.commit()
    db_session.refresh(a)
    db_session.refresh(b)
    db_session.add_all([TreatmentPlan(id="TP-A", patient_id=a.id, name="A"),
                        TreatmentPlan(id="TP-B", patient_id=b.id, name="B")])
    db_session.flush()

    def item(iid, plan, status, fee, **kw):
        return TreatmentPlanItem(id=iid, plan_id=plan, procedure_code="D2330", fee=Decimal(fee),
                                 status=status, priority=1, **kw)

    db_session.add_all([
        # pending for A: diagnosed, hold, alternative, scheduled, internal_referral
        item("I-1", "TP-A", "diagnosed", "85.00"),
        item("I-2", "TP-A", "hold", "10.00"),
        item("I-3", "TP-A", "alternative", "5.00"),
        item("I-4", "TP-A", "scheduled", "100.00"),
        item("I-5", "TP-A", "internal_referral", "1.00"),
        # not pending
        item("I-6", "TP-A", "completed", "999.00"),
        item("I-7", "TP-A", "referred_out", "999.00"),
        item("I-8", "TP-A", "external_referral", "999.00"),
        item("I-9", "TP-A", "accepted", "999.00", is_archived=True),
        item("I-10", "TP-A", "accepted", "999.00", end_date=date(2026, 5, 1)),
        item("I-11", "TP-A", "accepted", "999.00"),  # has a live charge below
        item("I-12", "TP-A", "accepted", "20.00"),   # charge is void -> still pending
        # B: only treated work
        item("I-20", "TP-B", "completed", "50.00"),
    ])
    db_session.flush()
    common = dict(patient_id=a.id, procedure_code="D2330", date_of_service=date(2026, 5, 1),
                  provider_id="PRV-1", office_id=office.id, fee=Decimal("1"))
    db_session.add_all([
        PatientProcedure(id="PP-1", treatment_plan_item_id="I-11", **common),
        PatientProcedure(id="PP-2", treatment_plan_item_id="I-12", is_void=True, **common),
    ])
    for appt_id, pid in (("APPT-A", a.id), ("APPT-B", b.id)):
        db_session.add(Appointment(
            id=appt_id, patient_id=pid, provider_id="PRV-1", operatory_id="OPR-1",
            office_id=office.id, date=date(2026, 6, 10), start_time=time(9, 0),
            end_time=time(9, 30), duration=30, status="Scheduled",
        ))
    db_session.commit()
    return {"a": a, "b": b}


EXPECTED_A = {"count": 6, "scheduled_count": 1, "total_fee": "221.00"}


def test_scheduler_feed_carries_pending_treatment(client, pt):
    rows = client.get(f"{PREFIX}/appointments/scheduler?date_from=2026-06-01&date_to=2026-06-30").json()
    by_patient = {r["patient_id"]: r for r in rows}
    a, b = by_patient[pt["a"].id], by_patient[pt["b"].id]
    assert a["pending_tx_count"] == EXPECTED_A["count"]
    assert a["pending_tx_scheduled_count"] == EXPECTED_A["scheduled_count"]
    assert Decimal(str(a["pending_tx_fee"])) == Decimal(EXPECTED_A["total_fee"])
    assert b["pending_tx_count"] == 0
    assert Decimal(str(b["pending_tx_fee"])) == 0


def test_pending_filter_on_patient_items(client, pt):
    r = client.get(f"{PREFIX}/patients/{pt['a'].id}/treatment-plan-items?pending=true")
    assert r.status_code == 200, r.text
    ids = {i["id"] for i in r.json()["items"]}
    assert ids == {"I-1", "I-2", "I-3", "I-4", "I-5", "I-12"}
    assert r.json()["meta"]["total"] == 6
    # include_completed=false keeps its old (narrower) meaning — non-breaking.
    loose = client.get(f"{PREFIX}/patients/{pt['a'].id}/treatment-plan-items?include_completed=false")
    assert "I-11" in {i["id"] for i in loose.json()["items"]}


def test_pending_summary_batch(client, pt):
    a, b = pt["a"].id, pt["b"].id
    r = client.get(f"{PREFIX}/treatment-plan-items/pending-summary?patient_ids={a},{b},999999")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["patient_id"] for i in items] == [a]  # B has none; 999999 is not ours
    assert items[0]["count"] == 6 and items[0]["scheduled_count"] == 1
    assert Decimal(str(items[0]["total_fee"])) == Decimal("221.00")


def test_pending_summary_rejects_too_many_ids(client, pt):
    ids = ",".join(str(i) for i in range(1, 202))
    r = client.get(f"{PREFIX}/treatment-plan-items/pending-summary?patient_ids={ids}")
    assert r.status_code == 422


def test_status_is_typed_and_legacy_codes_fold(client, pt, db_session):
    db_session.add(TreatmentPlanItem(id="I-L", plan_id="TP-B", procedure_code="D2330",
                                     fee=Decimal("1"), status="D", priority=1))
    db_session.commit()
    r = client.get(f"{PREFIX}/treatment-plan-items/I-L")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "diagnosed"
    spec = client.get(f"{PREFIX}/openapi.json").json()
    status = spec["components"]["schemas"]["TreatmentPlanItemRead"]["properties"]["status"]
    assert "enum" in status and "referred_out" in status["enum"]


def test_rules_metadata_publishes_pending_rule(client):
    rule = client.get(f"{PREFIX}/metadata/treatment-plan-rules").json()["pending_rule"]
    assert set(rule["excluded_statuses"]) == {"completed", "referred_out", "external_referral"}
    assert rule["scheduled_counts_as_pending"] is True
