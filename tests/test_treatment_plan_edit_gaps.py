"""Edit Treatment window + Tx Plan -> New Appt backend gaps.

Covers the 2026-09-08 re-audit of ``treatment_plan_backend_devreport.md``
(PLAN-9/11/16/17/18/19/20/24/25/26/27/28/29, PLAN-3 matcher fix) and
``tx_plan_new_appointment_backend_devreport.md`` (PLAN-APPT-1..5, 7).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.models import (
    FeeSchedule,
    IcdCode,
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    Office,
    Operatory,
    Patient,
    PatientInsurance,
    Provider,
    Referral,
    Tenant,
    TreatmentPlan,
    TreatmentPlanInsuranceDetail,
    TreatmentPlanItem,
)

PREFIX = "/api/v1"


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, name="Main", office_code="TPE", is_active=True)
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    p = Provider(id="PRV-TPE", tenant_id=db_session._tenant_id, office_id=office.id,
                 name="Dr. Plan", legacy_id="7409", is_active=True)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def operatory(db_session, office, provider) -> Operatory:
    op = Operatory(id="OPR-TPE", office_id=office.id, name="Op 1", provider_id=provider.id, is_active=True)
    db_session.add(op)
    db_session.commit()
    return op


@pytest.fixture
def patient(db_session, office) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Edit", last_name="Tx",
                chart_no="TPE-1", home_office_id=office.id, is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def codes(client):
    for row in (
        {"code": "D1110", "description": "Prophylaxis", "category": "Preventive",
         "default_fee": 200, "default_duration_minutes": 40},
        {"code": "D2740", "description": "Crown", "category": "Restorative", "default_fee": 900},
        {"code": "D0120", "description": "Periodic exam", "category": "Diagnostic", "default_fee": 50},
    ):
        r = client.post(f"{PREFIX}/procedure-codes", json=row)
        assert r.status_code == 201, r.text
    return True


@pytest.fixture
def plan(client, patient, office, codes) -> str:
    r = client.post(f"{PREFIX}/treatment-plans", json={
        "id": "TP-EDIT", "patient_id": patient.id, "name": "Plan", "office_id": office.id,
    })
    assert r.status_code == 201, r.text
    return "TP-EDIT"


def _item(client, plan_id: str, item_id: str, code: str = "D1110", **extra) -> dict:
    body = {"id": item_id, "plan_id": plan_id, "procedure_code": code, "fee": 200, **extra}
    r = client.post(f"{PREFIX}/treatment-plan-items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _get(client, item_id: str) -> dict:
    r = client.get(f"{PREFIX}/treatment-plan-items/{item_id}")
    assert r.status_code == 200, r.text
    return r.json()


# ── PLAN-17/18/19/25/27/28/29/11: the Edit Treatment fields ──────────────────
def test_edit_treatment_fields_round_trip(client, db_session, plan, provider):
    ref = Referral(tenant_id=db_session._tenant_id, first_name="Ref", last_name="Dentist",
                   referral_type="out")
    fs = FeeSchedule(tenant_id=db_session._tenant_id, name="UCR 2026")
    db_session.add_all([ref, fs])
    db_session.commit()
    admin_id = db_session._admin.id

    item = _item(client, plan, "E-1", notes="Watch #3", accepted_date="2026-09-01",
                 scheduled_date="2026-09-15", duration_minutes=45,
                 referral_id=ref.id, referral_type="OUT",
                 update_end_date_at_posting=True, re_estimate_at_posting=True,
                 fee_schedule_id=fs.id, counselor_user_id=admin_id, provider_id=provider.id)
    assert item["notes"] == "Watch #3"
    assert item["accepted_date"] == "2026-09-01"
    assert item["scheduled_date"] == "2026-09-15"
    assert item["duration_minutes"] == 45
    assert item["referral_id"] == ref.id
    assert item["referral_type"] == "out"  # normalised
    assert item["referral_name"] == "Ref Dentist"
    assert item["update_end_date_at_posting"] is True
    assert item["re_estimate_at_posting"] is True
    assert item["fee_schedule_id"] == fs.id
    assert item["fee_schedule_name"] == "UCR 2026"
    assert item["counselor_user_id"] == admin_id
    assert item["counselor_name"] == "admin"
    # PLAN-25: stamped by the engine from the token, names resolved on read.
    assert item["created_by"] == admin_id
    assert item["created_by_name"] == "admin"
    assert item["updated_by"] is None

    r = client.patch(f"{PREFIX}/treatment-plan-items/E-1", json={"notes": "Changed"})
    assert r.status_code == 200, r.text
    assert r.json()["updated_by"] == admin_id
    assert r.json()["updated_by_name"] == "admin"


def test_item_references_are_tenant_checked(client, db_session, plan):
    other = Tenant(name="Other", code="other", is_active=True)
    db_session.add(other)
    db_session.commit()
    ref = Referral(tenant_id=other.id, first_name="Foreign", last_name="Ref")
    db_session.add(ref)
    db_session.commit()
    r = client.post(f"{PREFIX}/treatment-plan-items", json={
        "id": "E-bad", "plan_id": plan, "procedure_code": "D1110", "fee": 1, "referral_id": ref.id,
    })
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "referral_not_found"
    r = client.post(f"{PREFIX}/treatment-plan-items", json={
        "id": "E-bad2", "plan_id": plan, "procedure_code": "D1110", "fee": 1, "referral_type": "sideways",
    })
    assert r.status_code == 422


def test_accepted_date_is_stamped_on_first_acceptance(client, plan):
    item = _item(client, plan, "E-2")
    assert item["accepted_date"] is None
    r = client.patch(f"{PREFIX}/treatment-plan-items/E-2", json={"status": "accepted"})
    assert r.status_code == 200, r.text
    assert r.json()["accepted_date"] is not None
    first = r.json()["accepted_date"]
    # Re-accepting later keeps the original date; an explicit value always wins.
    client.patch(f"{PREFIX}/treatment-plan-items/E-2", json={"status": "hold"})
    r = client.patch(f"{PREFIX}/treatment-plan-items/E-2", json={"status": "accepted"})
    assert r.json()["accepted_date"] == first
    r = client.patch(f"{PREFIX}/treatment-plan-items/E-2", json={"accepted_date": "2020-01-01"})
    assert r.json()["accepted_date"] == "2020-01-01"


# ── PLAN-20: the last two STATUS boxes ────────────────────────────────────────
@pytest.mark.parametrize("status", ["internal_referral", "external_referral", "scheduled"])
def test_referral_statuses_are_accepted(client, plan, status):
    item = _item(client, plan, f"E-{status}", status=status)
    assert item["status"] == status


def test_completed_still_requires_a_charge(client, plan):
    _item(client, plan, "E-3")
    r = client.patch(f"{PREFIX}/treatment-plan-items/E-3", json={"status": "completed"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "status_requires_charge"


# ── PLAN-29: omitted fee is priced server-side ────────────────────────────────
def test_omitted_fee_is_priced_from_the_resolver(client, plan):
    r = client.post(f"{PREFIX}/treatment-plan-items",
                    json={"id": "E-4", "plan_id": plan, "procedure_code": "D2740"})
    assert r.status_code == 201, r.text
    assert float(r.json()["fee"]) == 900  # code default_fee, no schedule -> no schedule id
    assert r.json()["fee_schedule_id"] is None


# ── PLAN-26: ICD-10 links ─────────────────────────────────────────────────────
def test_icd_code_links(client, db_session, plan):
    a = IcdCode(code="K02.9", description="Dental caries, unspecified", icd10="K02.9")
    b = IcdCode(code="K04.0", description="Pulpitis", icd10="K04.0")
    db_session.add_all([a, b])
    db_session.commit()

    item = _item(client, plan, "E-5", icd_code_ids=[b.id, a.id])
    assert item["icd_code_ids"] == [b.id, a.id]
    assert [c["icd10"] for c in item["icd_codes"]] == ["K04.0", "K02.9"]
    assert item["icd_codes"][0]["ordinal"] == 1

    # PATCH replaces the set (and re-orders).
    r = client.patch(f"{PREFIX}/treatment-plan-items/E-5", json={"icd_code_ids": [a.id]})
    assert r.status_code == 200, r.text
    assert r.json()["icd_code_ids"] == [a.id]
    # PUT with [] is "clear all".
    r = client.put(f"{PREFIX}/treatment-plan-items/E-5/icd-codes", json={"icd_code_ids": []})
    assert r.status_code == 200, r.text
    assert r.json()["icd_code_ids"] == []
    # Unknown id -> 422 naming it.
    r = client.patch(f"{PREFIX}/treatment-plan-items/E-5", json={"icd_code_ids": [999999]})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["missing"] == [999999]


# ── PLAN-24: archived items / details hidden by default ──────────────────────
def test_archived_items_hidden_from_default_listing(client, plan):
    _item(client, plan, "E-6")
    _item(client, plan, "E-7")
    assert client.delete(f"{PREFIX}/treatment-plan-items/E-7").status_code == 204
    default = client.get(f"{PREFIX}/treatment-plan-items?plan_id={plan}").json()
    assert [r["id"] for r in default["items"]] == ["E-6"]
    tombstones = client.get(f"{PREFIX}/treatment-plan-items?plan_id={plan}&is_archived=true").json()
    assert [r["id"] for r in tombstones["items"]] == ["E-7"]


def test_archived_insurance_details_hidden_from_default_listing(client, plan):
    _item(client, plan, "E-8")
    det = client.post(f"{PREFIX}/treatment-plan-insurance-details",
                      json={"plan_item_id": "E-8", "estimated_ins": 10, "estimated_pat": 190})
    assert det.status_code == 201, det.text
    assert client.delete(f"{PREFIX}/treatment-plan-insurance-details/{det.json()['id']}").status_code == 204
    listed = client.get(f"{PREFIX}/treatment-plan-insurance-details?plan_item_id=E-8").json()
    assert listed["meta"]["total"] == 0
    assert client.get(
        f"{PREFIX}/treatment-plan-insurance-details?plan_item_id=E-8&is_archived=true"
    ).json()["meta"]["total"] == 1


# ── PLAN-9: pre-auth status ───────────────────────────────────────────────────
def test_preauth_status_normalised_and_stamped(client, plan):
    _item(client, plan, "E-9")
    r = client.post(f"{PREFIX}/treatment-plan-insurance-details",
                    json={"plan_item_id": "E-9", "preauth_number": "PA-1", "preauth_status": "Sent"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["preauth_status"] == "sent"
    assert body["preauth_status_at"] is not None
    sent_at = body["preauth_status_at"]
    # No change -> no re-stamp; change -> re-stamp.
    r = client.patch(f"{PREFIX}/treatment-plan-insurance-details/{body['id']}",
                     json={"preauth_status": "sent", "preauth_amount": 100})
    assert r.json()["preauth_status_at"] == sent_at
    r = client.patch(f"{PREFIX}/treatment-plan-insurance-details/{body['id']}",
                     json={"preauth_status": "closed"})
    assert r.json()["preauth_status"] == "closed"
    r = client.patch(f"{PREFIX}/treatment-plan-insurance-details/{body['id']}",
                     json={"preauth_status": "pending"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "invalid_preauth_status"


def test_insurance_details_are_tenant_scoped(client, db_session, plan):
    """The table has no tenant_id; before this any tenant could read any row by id."""
    other = Tenant(name="Other2", code="other2", is_active=True)
    db_session.add(other)
    db_session.commit()
    foreign_patient = Patient(tenant_id=other.id, first_name="F", last_name="P")
    db_session.add(foreign_patient)
    db_session.commit()
    fplan = TreatmentPlan(id="TP-FOREIGN", patient_id=foreign_patient.id, name="F")
    fitem = TreatmentPlanItem(id="FI-1", plan_id="TP-FOREIGN", procedure_code="D1110", fee=Decimal("1"))
    db_session.add_all([fplan, fitem])
    db_session.commit()
    det = TreatmentPlanInsuranceDetail(plan_item_id="FI-1", estimated_ins=Decimal("1"))
    db_session.add(det)
    db_session.commit()
    assert client.get(f"{PREFIX}/treatment-plan-insurance-details/{det.id}").status_code == 404
    assert client.get(f"{PREFIX}/treatment-plan-items/FI-1").status_code == 404
    # A foreign item is "not found" from this tenant's point of view.
    r = client.post(f"{PREFIX}/treatment-plan-insurance-details", json={"plan_item_id": "FI-1"})
    assert r.status_code in (404, 422)


# ── PLAN-3: the coverage-category matcher (FEE-1) ────────────────────────────
def _coverage(db_session, patient_id, *, band: str, pct=80, deductible=0, annual_max=5000):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Acme", is_active=True)
    db_session.add(carrier)
    db_session.commit()
    ins_plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                             individual_deductible=Decimal(deductible),
                             individual_max=Decimal(annual_max), is_active=True)
    db_session.add(ins_plan)
    db_session.commit()
    db_session.add(InsuranceCoverageRule(ins_plan_id=ins_plan.id, start_code=band, end_code=band,
                                         coverage_pct=Decimal(pct), ded_waived=False))
    db_session.add(PatientInsurance(patient_id=patient_id, ins_plan_id=ins_plan.id,
                                    insurance_type="primary", is_active=True,
                                    deductible_remaining=Decimal(deductible),
                                    max_remaining=Decimal(annual_max)))
    db_session.commit()
    return ins_plan.id


def test_re_estimate_matches_category_bands(client, db_session, patient, plan):
    """A Denticon plan bands on ``02`` (Preventive), not ``D1000``–``D1999``; the
    lexical matcher returned 0 % here on every migrated plan."""
    _coverage(db_session, patient.id, band="02", pct=100)
    _item(client, plan, "RE-1")  # D1110 = category 02, fee 200
    _item(client, plan, "RE-2", code="D2740", fee=900)  # 03A, not banded -> 0 %
    r = client.post(f"{PREFIX}/treatment-plans/{plan}/re-estimate")
    assert r.status_code == 200, r.text
    lines = {ln["item_id"]: ln for ln in r.json()["lines"]}
    assert float(lines["RE-1"]["insurance_estimate"]) == 200
    assert lines["RE-1"]["coverage_category"] == "02"
    assert lines["RE-1"]["rule_start_code"] == "02"
    assert float(lines["RE-2"]["insurance_estimate"]) == 0
    # PLAN-3 confirmation: the per-item insurance-detail row is written.
    det = client.get(f"{PREFIX}/treatment-plan-insurance-details?plan_item_id=RE-1").json()
    assert det["meta"]["total"] == 1
    assert float(det["items"][0]["estimated_ins"]) == 200
    assert float(det["items"][0]["coverage_pct"]) == 100


def test_re_estimate_use_new_fees_reprices(client, db_session, patient, plan):
    _coverage(db_session, patient.id, band="02", pct=50)
    _item(client, plan, "RE-3", fee=999)  # hand-typed, off-schedule
    r = client.post(f"{PREFIX}/treatment-plans/{plan}/re-estimate?use_new_fees=true")
    assert r.status_code == 200, r.text
    line = r.json()["lines"][0]
    assert float(line["fee"]) == 200  # code default_fee
    assert line["fee_source"] is not None
    assert float(line["insurance_estimate"]) == 100
    assert float(_get(client, "RE-3")["fee"]) == 200


# ── PLAN-28: posting flags ────────────────────────────────────────────────────
def test_posting_flags_are_honoured(client, db_session, patient, plan, provider):
    _coverage(db_session, patient.id, band="02", pct=50)
    _item(client, plan, "PF-1", provider_id=provider.id, end_date="2026-01-01",
          update_end_date_at_posting=True, re_estimate_at_posting=True)
    r = client.post(f"{PREFIX}/treatment-plan-items/PF-1/post", json={"date_of_service": "2026-09-02"})
    assert r.status_code == 201, r.text
    assert float(r.json()["insurance_estimate"]) == 100  # re-estimated at posting
    item = _get(client, "PF-1")
    assert item["end_date"] == "2026-09-02"  # overwritten, not just filled
    assert item["status"] == "completed"
    assert float(item["insurance_estimate"]) == 100


def test_posting_without_flags_keeps_end_date(client, plan, provider):
    _item(client, plan, "PF-2", provider_id=provider.id, end_date="2026-01-01", insurance_estimate=7)
    r = client.post(f"{PREFIX}/treatment-plan-items/PF-2/post", json={"date_of_service": "2026-09-02"})
    assert r.status_code == 201, r.text
    assert float(r.json()["insurance_estimate"]) == 7
    assert _get(client, "PF-2")["end_date"] == "2026-01-01"


# ── PLAN-APPT-5/1/2/3/4/7: book from plan ─────────────────────────────────────
def test_book_from_plan_is_atomic_and_schedules_items(client, plan, provider, operatory, office):
    _item(client, plan, "B-1", provider_id=provider.id, status="accepted", duration_minutes=20)
    _item(client, plan, "B-2", code="D2740", fee=900)  # no duration -> code default -> 30
    r = client.post(f"{PREFIX}/treatment-plans/{plan}/book", json={
        "item_ids": ["B-1", "B-2"], "date": "2026-10-01", "start_time": "09:00:00",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider_id"] == provider.id and body["provider_source"] == "item"
    assert body["operatory_id"] == operatory.id and body["operatory_source"] == "provider_column"
    assert body["office_id"] == office.id
    assert body["duration"] == 50 and body["end_time"] == "09:50:00"
    assert [p["treatment_plan_item_id"] for p in body["procedures"]] == ["B-1", "B-2"]
    assert body["procedures"][1]["duration_minutes"] == 30
    appt_id = body["appointment_id"]

    # PLAN-APPT-1: both items are scheduled, remembering where they came from.
    b1, b2 = _get(client, "B-1"), _get(client, "B-2")
    assert b1["status"] == "scheduled" and b1["status_before_scheduled"] == "accepted"
    assert b2["status"] == "scheduled" and b2["status_before_scheduled"] == "diagnosed"
    assert b1["scheduled_date"] == "2026-10-01"
    # PLAN-APPT-2: the read points back at the appointment.
    assert b1["appointment_id"] == appt_id and b1["appointment_ids"] == [appt_id]
    # PLAN-APPT-3: the provider-less item adopted the appointment's provider.
    assert b2["provider_id"] == provider.id
    # The line carries the item id and is filterable by it.
    lines = client.get(f"{PREFIX}/appointment-procedures?treatment_plan_item_id=B-1").json()
    assert lines["meta"]["total"] == 1

    # Booking again -> 409 naming the live booking.
    r = client.post(f"{PREFIX}/treatment-plans/{plan}/book", json={
        "item_ids": ["B-1"], "date": "2026-10-02", "start_time": "09:00:00",
    })
    assert r.status_code == 409
    assert r.json()["error"]["details"]["bookings"]["B-1"] == [appt_id]

    # Cancel via the status endpoint -> items revert to what they were.
    r = client.patch(f"{PREFIX}/appointments/{appt_id}/status", json={"status": "cancelled"})
    assert r.status_code == 200, r.text
    b1, b2 = _get(client, "B-1"), _get(client, "B-2")
    assert b1["status"] == "accepted" and b1["status_before_scheduled"] is None
    assert b2["status"] == "diagnosed" and b1["scheduled_date"] is None
    assert b1["appointment_id"] is None
    # Un-cancel -> scheduled again.
    client.patch(f"{PREFIX}/appointments/{appt_id}/status", json={"status": "Scheduled"})
    assert _get(client, "B-1")["status"] == "scheduled"


def test_book_from_plan_uses_provider_default_operatory(client, db_session, plan, provider, office):
    op_a = Operatory(id="OPR-A", office_id=office.id, name="A", is_active=True)
    op_b = Operatory(id="OPR-B", office_id=office.id, name="B", is_active=True)
    db_session.add_all([op_a, op_b])
    db_session.commit()
    r = client.patch(f"{PREFIX}/providers/{provider.id}", json={"default_operatory_id": "OPR-B"})
    assert r.status_code == 200, r.text
    assert r.json()["default_operatory_id"] == "OPR-B"
    _item(client, plan, "B-3", provider_id=provider.id)
    r = client.post(f"{PREFIX}/treatment-plans/{plan}/book", json={
        "item_ids": ["B-3"], "date": "2026-10-01", "start_time": "10:00:00",
    })
    assert r.status_code == 201, r.text
    assert r.json()["operatory_id"] == "OPR-B"
    assert r.json()["operatory_source"] == "provider_default"


def test_default_operatory_must_be_in_a_provider_office(client, db_session, provider):
    other_office = Office(tenant_id=db_session._tenant_id, name="Far", office_code="FAR")
    db_session.add(other_office)
    db_session.commit()
    db_session.add(Operatory(id="OPR-FAR", office_id=other_office.id, name="Far 1"))
    db_session.commit()
    r = client.patch(f"{PREFIX}/providers/{provider.id}", json={"default_operatory_id": "OPR-FAR"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "operatory_not_in_provider_office"


def test_book_rejects_completed_and_needs_a_provider(client, plan, provider):
    _item(client, plan, "B-4", provider_id=provider.id)
    assert client.post(f"{PREFIX}/treatment-plan-items/B-4/post", json={}).status_code == 201
    r = client.post(f"{PREFIX}/treatment-plans/{plan}/book", json={
        "item_ids": ["B-4"], "date": "2026-10-01", "start_time": "09:00:00",
    })
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "item_completed"


def test_deleting_the_appointment_releases_items(client, plan, provider):
    _item(client, plan, "B-5", provider_id=provider.id, status="hold")
    r = client.post(f"{PREFIX}/treatment-plans/{plan}/book", json={
        "item_ids": ["B-5"], "date": "2026-10-01", "start_time": "09:00:00",
    })
    appt_id = r.json()["appointment_id"]
    assert _get(client, "B-5")["status"] == "scheduled"
    assert client.delete(f"{PREFIX}/appointments/{appt_id}").status_code == 204
    assert _get(client, "B-5")["status"] == "hold"
    # SCHED-DEL-2 restore books it again.
    assert client.post(f"{PREFIX}/appointments/{appt_id}/restore").status_code == 200
    assert _get(client, "B-5")["status"] == "scheduled"


def test_generic_appointment_procedure_line_books_the_item(client, plan, provider, office, patient):
    """The FE's existing POST /appointments + POST /appointment-procedures path."""
    _item(client, plan, "B-6", provider_id=provider.id, tooth="14", duration_minutes=25)
    r = client.post(f"{PREFIX}/appointments", json={
        "id": "APPT-GEN", "patient_id": patient.id, "provider_id": provider.id,
        "office_id": office.id, "date": "2026-10-03", "start_time": "09:00:00",
        "end_time": "09:30:00", "duration": 30, "status": "Scheduled",
    })
    assert r.status_code == 201, r.text
    r = client.post(f"{PREFIX}/appointment-procedures", json={
        "appointment_id": "APPT-GEN", "procedure_code": "D1110", "treatment_plan_item_id": "B-6",
    })
    assert r.status_code == 201, r.text
    line = r.json()
    # Inherited from the item where the payload left it blank.
    assert line["treatment_plan_id"] == plan and line["tooth"] == "14"
    assert float(line["fee"]) == 200 and line["duration_minutes"] == 25
    assert _get(client, "B-6")["status"] == "scheduled"
    # Wrong patient -> 422, nothing written.
    r = client.post(f"{PREFIX}/appointment-procedures", json={
        "appointment_id": "APPT-GEN", "procedure_code": "D1110", "treatment_plan_item_id": "NOPE",
    })
    assert r.status_code == 422
    # Removing the line releases the item.
    assert client.delete(f"{PREFIX}/appointment-procedures/{line['id']}").status_code == 204
    assert _get(client, "B-6")["status"] == "diagnosed"


# ── PLAN-APPT-3: provider defaults from diagnosed_by (legacy id) ──────────────
def test_new_item_defaults_provider_from_diagnosed_by(client, plan, provider):
    item = _item(client, plan, "P-1", diagnosed_by="7409")  # providers.legacy_id
    assert item["provider_id"] == provider.id
    # The rest of the plan then supplies the default for a provider-less line.
    assert _item(client, plan, "P-2")["provider_id"] == provider.id


# ── PLAN-16: eligibility, batched ─────────────────────────────────────────────
def test_procedure_code_eligibility(client, db_session, provider, office, codes):
    other = Provider(id="PRV-OTHER", tenant_id=db_session._tenant_id, office_id=office.id, name="Dr. B")
    db_session.add(other)
    db_session.commit()
    r = client.get(f"{PREFIX}/procedure-codes/eligibility?codes=D1110,D2740")
    assert r.status_code == 200, r.text
    assert r.json()["eligible_for_all"] is None  # nothing restricted yet
    assert all(c["restricted"] is False for c in r.json()["codes"])

    r = client.put(f"{PREFIX}/providers/{provider.id}/procedure-codes", json={"codes": ["D2740"]})
    assert r.status_code == 200, r.text
    r = client.get(f"{PREFIX}/procedure-codes/eligibility?codes=D1110,D2740").json()
    by_code = {c["procedure_code"]: c for c in r["codes"]}
    assert by_code["D1110"]["restricted"] is False
    assert by_code["D2740"] == {"procedure_code": "D2740", "restricted": True, "provider_ids": [provider.id]}
    assert r["eligible_for_all"] == [provider.id]
    assert r["restricted_provider_ids"] == [provider.id]
    r = client.get(f"{PREFIX}/procedure-codes/D2740/providers").json()
    assert [p["id"] for p in r] == [provider.id]
    assert client.get(f"{PREFIX}/procedure-codes/D1110/providers").json() == []


def test_treatment_plan_rules_metadata(client):
    r = client.get(f"{PREFIX}/metadata/treatment-plan-rules")
    assert r.status_code == 200
    assert "internal_referral" in r.json()["item_statuses"]
    assert r.json()["preauth_statuses"] == ["sent", "closed"]
