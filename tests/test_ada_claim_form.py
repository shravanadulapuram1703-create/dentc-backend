"""ADA Dental Claim Form (2024) — docs/claims/ada_claim_form_2024_backend_devreport.md.

ADA-BE-1 the JSON assembler + PDF (form / overlay / batch) + PRINT audit,
ADA-BE-2 the three 2024 boxes (+ derived date_last_srp), ADA-BE-3/4 the line
pointer / quantity rules, ADA-BE-5 other fees, ADA-BE-6 missing teeth
(derived, overridden, tooth-status), ADA-BE-7 claim_consent signature,
ADA-BE-8 entity NPI, ADA-BE-9 other coverage captured at creation, ADA-BE-10
suffixes, ADA-BE-11 area codes, ADA-BE-12 provider defaults on create and on
per-line attach, ADA-BE-13 treatment address, ADA-BE-14 taxonomy, and the
fill-out vocabulary (CLM-FO-1..4) + submit snapshot (CLM-FO-5).
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import select

from app.db.models import (
    AuditLog,
    ChartCondition,
    ClaimSubmission,
    InsuranceCarrier,
    InsurancePlan,
    InsuranceSubscriber,
    Office,
    Patient,
    PatientInsurance,
    PatientSignature,
    Provider,
    ProviderInsuranceId,
    Tenant,
)

PREFIX = "/api/v1"


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="ADA1", name="Smile Dental", short_id="ADA",
               corporate_name="Smile Dental Group PC", address_line1="PO Box 900", city="Austin", state="TX",
               zip="78701", phone="512-555-0100", tax_id="12-3456789", timezone="America/Chicago")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    p = Provider(id="DR1", tenant_id=db_session._tenant_id, office_id=office.id, name="Dr Endo", short_id="DR1",
                 npi="1234567893", license="TX-111", specialty="Endodontist", phone="512-555-0111")
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def provider2(db_session, office) -> Provider:
    p = Provider(id="DR2", tenant_id=db_session._tenant_id, office_id=office.id, name="Dr Two", short_id="DR2",
                 npi="1987654321", print_separate_claim_form=True)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def patient(db_session, office, provider) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Pat", last_name="Claimant", middle_initial="J",
                suffix="Jr", chart_no="ADA-001", home_office_id=office.id, dob=date(1990, 1, 2), gender="F",
                address_line1="5 Elm St", city="Austin", state="TX", zip="78702", assign_benefits=True,
                preferred_provider_id=provider.id, is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def coverage(db_session, patient, office):
    """Primary + secondary dental slots on two carriers."""
    tid = db_session._tenant_id
    out = {}
    for rank, cname, payer_id, member in (("primary", "Delta", "PAY1", "MEM-1"), ("secondary", "Cigna", "PAY2", "MEM-2")):
        carrier = InsuranceCarrier(tenant_id=tid, name=cname, carrier_type="dental", payer_id=payer_id,
                                   address="1 Payer Way", city="Dallas", state="TX", zip="75001")
        db_session.add(carrier)
        db_session.flush()
        plan = InsurancePlan(tenant_id=tid, carrier_id=carrier.id, group_number=f"GRP-{rank}", plan_type="PPO")
        db_session.add(plan)
        db_session.flush()
        sub = InsuranceSubscriber(tenant_id=tid, ins_plan_id=plan.id, sub_first_name="Sub", sub_last_name=cname,
                                  sub_mi="Q", sub_suffix="Sr", sub_member_id=member, sub_dob=date(1985, 5, 5),
                                  sub_gender="M", sub_address="9 Sub Rd", sub_city="Austin", sub_state="TX",
                                  sub_zip="78703")
        db_session.add(sub)
        db_session.flush()
        slot = PatientInsurance(patient_id=patient.id, ins_plan_id=plan.id, subscriber_id=sub.id,
                                legacy_plan_type="D", insurance_type=rank, relationship="Child", is_active=True)
        db_session.add(slot)
        out[rank] = {"carrier": carrier, "plan": plan, "subscriber": sub, "slot": slot}
    db_session.commit()
    return out


@pytest.fixture
def codes(client):
    for code, desc, extra in (
        ("D2750", "Crown PFM", {}), ("D4341", "SRP 4+ teeth", {}), ("D7140", "Extraction", {}),
        ("D0120", "Periodic eval", {}),
    ):
        r = client.post(f"{PREFIX}/procedure-codes", json={"code": code, "description": desc,
                                                          "category": "Test", "default_fee": 100, **extra})
        assert r.status_code == 201, r.text
    return True


def _proc(client, patient_id, office_id, provider_id, code, fee, dos, item_id, **extra):
    body = {"id": item_id, "patient_id": patient_id, "office_id": office_id, "provider_id": provider_id,
            "procedure_code": code, "fee": fee, "date_of_service": dos, **extra}
    r = client.post(f"{PREFIX}/patient-procedures", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _claim(client, patient_id, office_id, claim_id="CLM-ADA", **extra):
    r = client.post(f"{PREFIX}/insurance-claims", json={
        "id": claim_id, "patient_id": patient_id, "office_id": office_id, "claim_number": claim_id,
        "status": "draft", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _assert_pdf(resp, name_part: str) -> None:
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
    assert name_part in resp.headers["content-disposition"]


# ── ADA-BE-12 / 9: creation defaults ─────────────────────────────────────────
def test_claim_create_defaults_providers_dates_plan_and_other_plan(client, db_session, patient, office, provider, coverage, codes):
    office.billing_provider_id = provider.id
    db_session.commit()
    p1 = _proc(client, patient.id, office.id, provider.id, "D2750", 900, "2026-03-01", "P-1", tooth="3",
               quantity=1, diagnosis_pointers="a,b")
    p2 = _proc(client, patient.id, office.id, provider.id, "D0120", 60, "2026-02-10", "P-2")
    assert p1["diagnosis_pointers"] == "AB"
    assert p2["quantity"] == 1
    claim = _claim(client, patient.id, office.id, procedure_ids=["P-1", "P-2"])
    assert claim["treating_provider_id"] == provider.id
    assert claim["billing_provider_id"] == provider.id
    assert claim["ins_plan_id"] == coverage["primary"]["plan"].id
    assert claim["carrier_id"] == coverage["primary"]["carrier"].id
    # ADA-BE-9: the *other* plan is captured at creation.
    assert claim["other_ins_plan_id"] == coverage["secondary"]["plan"].id
    assert claim["date_of_service_from"] == "2026-02-10"
    assert claim["date_of_service_to"] == "2026-03-01"
    assert float(claim["total_billed"]) == 960.0
    # the lines are attached in the same transaction
    r = client.get(f"{PREFIX}/patient-procedures", params={"claim_id": "CLM-ADA"})
    assert {row["id"] for row in r.json()["items"]} == {"P-1", "P-2"}


def test_claim_create_rejects_separate_form_provider_mix(client, db_session, patient, office, provider, provider2, codes):
    _proc(client, patient.id, office.id, provider.id, "D2750", 900, "2026-03-01", "P-1", tooth="3")
    _proc(client, patient.id, office.id, provider2.id, "D0120", 60, "2026-03-01", "P-2")
    r = client.post(f"{PREFIX}/insurance-claims", json={
        "id": "CLM-MIX", "patient_id": patient.id, "office_id": office.id, "claim_number": "CLM-MIX",
        "procedure_ids": ["P-1", "P-2"]})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "claim_provider_mismatch"
    # unknown / foreign procedure ids are refused too
    r = client.post(f"{PREFIX}/insurance-claims", json={
        "id": "CLM-NF", "patient_id": patient.id, "office_id": office.id, "claim_number": "CLM-NF",
        "procedure_ids": ["nope"]})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "procedure_not_found"


def test_per_line_attach_fills_claim_providers(client, db_session, patient, office, provider, provider2, codes):
    """The ledger's POST-then-PATCH shape (ADA-BE-12): the first line that lands
    on a provider-less claim fills treating/billing; a separate-form provider
    cannot be attached alongside."""
    claim = _claim(client, patient.id, office.id, claim_id="CLM-PATCH")
    # preferred provider seeds treating at creation; clear it to test the attach path
    client.patch(f"{PREFIX}/insurance-claims/CLM-PATCH", json={"treating_provider_id": None,
                                                              "billing_provider_id": None})
    _proc(client, patient.id, office.id, provider.id, "D2750", 900, "2026-03-01", "P-1", tooth="3")
    r = client.patch(f"{PREFIX}/patient-procedures/P-1", json={"claim_id": "CLM-PATCH"})
    assert r.status_code == 200, r.text
    claim = client.get(f"{PREFIX}/insurance-claims/CLM-PATCH").json()
    assert claim["treating_provider_id"] == provider.id
    assert claim["billing_provider_id"] == provider.id
    assert claim["date_of_service_from"] == "2026-03-01"
    _proc(client, patient.id, office.id, provider2.id, "D0120", 60, "2026-03-02", "P-2")
    r = client.patch(f"{PREFIX}/patient-procedures/P-2", json={"claim_id": "CLM-PATCH"})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "claim_provider_mismatch"


# ── ADA-BE-3/4: line rules ───────────────────────────────────────────────────
def test_line_pointer_and_quantity_rules(client, patient, office, provider, codes):
    r = client.post(f"{PREFIX}/patient-procedures", json={
        "id": "P-BAD", "patient_id": patient.id, "office_id": office.id, "provider_id": provider.id,
        "procedure_code": "D0120", "fee": 60, "date_of_service": "2026-03-01", "diagnosis_pointers": "AE"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "invalid_diagnosis_pointer"
    r = client.post(f"{PREFIX}/patient-procedures", json={
        "id": "P-BAD2", "patient_id": patient.id, "office_id": office.id, "provider_id": provider.id,
        "procedure_code": "D0120", "fee": 60, "date_of_service": "2026-03-01", "quantity": 0})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "invalid_quantity"
    row = _proc(client, patient.id, office.id, provider.id, "D0120", 60, "2026-03-01", "P-OK",
                quantity=3, diagnosis_pointers="b, a b")
    assert row["quantity"] == 3 and row["diagnosis_pointers"] == "BA"
    r = client.patch(f"{PREFIX}/patient-procedures/P-OK", json={"diagnosis_pointers": None, "quantity": 2})
    assert r.status_code == 200 and r.json()["diagnosis_pointers"] is None and r.json()["quantity"] == 2


# ── fill-out vocabulary (CLM-FO-1..4) ────────────────────────────────────────
def test_claim_fillout_validation(client, patient, office):
    _claim(client, patient.id, office.id, claim_id="CLM-FO")
    bad = [
        ({"accident_type": "bicycle"}, "invalid_accident_type"),
        ({"accident_state": "T1"}, "invalid_accident_state"),
        ({"icd_qualifier": "ZZ"}, "invalid_icd_qualifier"),
        ({"icd_1": "K02.9!"}, "invalid_icd_code"),
        ({"place_of_treatment": "1A"}, "invalid_place_of_treatment"),
        ({"missing_teeth": "1,99"}, "invalid_missing_tooth"),
        ({"other_fees": -1}, "invalid_other_fees"),
    ]
    for body, code in bad:
        r = client.patch(f"{PREFIX}/insurance-claims/CLM-FO", json=body)
        assert r.status_code == 422, (body, r.text)
        assert r.json()["error"]["details"]["code"] == code, body
    r = client.patch(f"{PREFIX}/insurance-claims/CLM-FO", json={
        "accident_type": "Auto", "accident_state": "tx", "accident_date": "2026-01-05", "icd_qualifier": "ab",
        "icd_1": "k02.9", "icd_2": "K04.7", "place_of_treatment": "1", "missing_teeth": " 32, 1,1 ",
        "predetermination_number": " PRE-77 ", "remarks": "Tooth 3 fractured", "is_epsdt": True,
        "is_locum_tenens": True, "date_last_srp": "2025-11-01", "other_fees": 12.5, "is_ortho": True,
        "ortho_appliance_date": "2025-06-01", "ortho_months_remaining": 12, "prosthesis_replacement": True,
        "prosthesis_prior_date": "2019-01-01", "signature_on_file": True, "has_other_coverage": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accident_type"] == "auto" and body["accident_state"] == "TX"
    assert body["icd_qualifier"] == "AB" and body["icd_1"] == "K02.9"
    assert body["place_of_treatment"] == "01"
    assert body["missing_teeth"] == "1,32"
    assert body["predetermination_number"] == "PRE-77"
    assert body["is_epsdt"] is True and body["is_locum_tenens"] is True and body["date_last_srp"] == "2025-11-01"


# ── ADA-BE-1: the assembled form ─────────────────────────────────────────────
def test_assembled_form_resolves_every_section(client, db_session, patient, office, provider, coverage, codes):
    tid = db_session._tenant_id
    office.npi = "1112223334"
    office.billing_provider_id = provider.id
    office.treatment_address_line1 = "500 Clinic Blvd"
    office.treatment_city, office.treatment_state, office.treatment_zip = "Austin", "TX", "78705"
    db_session.add(ProviderInsuranceId(tenant_id=tid, provider_id=provider.id,
                                       carrier_id=coverage["primary"]["carrier"].id, ins_id="DELTA-77"))
    db_session.add(ChartCondition(patient_id=patient.id, tooth="17", condition_code="MISSING",
                                  activity_date=date(2020, 1, 1)))
    db_session.commit()
    _proc(client, patient.id, office.id, provider.id, "D4341", 200, "2025-09-01", "P-SRP", quadrant="UR")
    _proc(client, patient.id, office.id, provider.id, "D7140", 150, "2025-10-01", "P-EXT", tooth="1")
    _proc(client, patient.id, office.id, provider.id, "D2750", 900, "2026-03-01", "P-1", tooth="3",
          surface="MOD", diagnosis_pointers="AC")
    _proc(client, patient.id, office.id, provider.id, "D0120", 60, "2026-03-01", "P-2", quadrant="LL")
    _claim(client, patient.id, office.id, procedure_ids=["P-1", "P-2"], icd_1="K02.9", remarks="Fractured cusp",
           other_fees=10)

    r = client.get(f"{PREFIX}/insurance-claims/CLM-ADA/ada-claim-form")
    assert r.status_code == 200, r.text
    form = r.json()
    assert form["form_version"] == "2024" and form["pages"] == 1
    assert form["header"]["transaction_type"] == "statement"
    # Item 3 / 3a
    assert form["payer"]["name"] == "Delta" and form["payer"]["payer_id"] == "PAY1"
    # Items 4–11 from the secondary slot, derived (nothing stored says otherwise)
    oc = form["other_coverage"]
    assert oc["has_other_coverage"] is True and oc["plan_source"] == "stored"
    assert oc["subscriber"]["last_name"] == "Cigna" and oc["carrier"]["payer_id"] == "PAY2"
    assert oc["coverage_type"] == "dental"
    # Items 12–18 incl. the suffix (ADA-BE-10)
    assert form["subscriber"]["last_name"] == "Delta" and form["subscriber"]["suffix"] == "Sr"
    assert form["subscriber"]["group_number"] == "GRP-primary"
    assert form["patient"]["relationship_to_subscriber"] == "dependent"
    # Items 20–23
    assert form["patient"]["suffix"] == "Jr" and form["patient"]["chart_no"] == "ADA-001"
    assert form["patient"]["sex"] == "F"
    # service lines: area code (ADA-BE-11), pointers, quantity, description
    lines = {ln["procedure_code"]: ln for ln in form["service_lines"]}
    assert lines["D2750"]["tooth"] == "3" and lines["D2750"]["surface"] == "MOD"
    assert lines["D2750"]["diagnosis_pointers"] == "AC" and lines["D2750"]["quantity"] == 1
    assert lines["D2750"]["description"] == "Crown PFM"
    assert lines["D0120"]["area_of_oral_cavity"] == "30"
    assert float(form["fees"]["lines_total"]) == 960.0
    assert float(form["fees"]["other_fees"]) == 10.0 and float(form["fees"]["total_fee"]) == 970.0
    # Item 33 derived from the chart + the extraction charge (ADA-BE-6)
    assert form["missing_teeth"] == {"teeth": ["1", "17"], "source": "chart"}
    # Item 34/34a + dangling pointer warning (C is blank)
    assert form["diagnosis"]["qualifier"] == "AB" and form["diagnosis"]["codes"]["A"] == "K02.9"
    assert any(w["code"] == "pointer_without_diagnosis" for w in form["warnings"])
    assert form["remarks"] == "Fractured cusp"
    # Items 36/37
    assert form["authorizations"]["signature_on_file"] is False
    assert form["authorizations"]["assignment_of_benefits"] is True
    # Item 38 default, 39a derived (ADA-BE-2)
    assert form["ancillary"]["place_of_treatment"] == "11"
    assert form["ancillary"]["date_last_srp"] == "2025-09-01"
    assert form["ancillary"]["date_last_srp_source"] == "derived"
    # Items 48–52a: the entity NPI (ADA-BE-8), corporate name, office TIN/phone, legacy ins id
    b = form["billing"]
    assert b["name"] == "Smile Dental Group PC" and b["npi"] == "1112223334" and b["npi_type"] == "2"
    assert b["license"] is None  # the entity bills; use_billing_license is off
    assert b["tax_id"] == "12-3456789" and b["additional_provider_id"] == "DELTA-77"
    # Items 53–58: treating from the claim, physical location (ADA-BE-13), taxonomy (ADA-BE-14)
    t = form["treating"]
    assert t["provider_id"] == provider.id and t["provider_source"] == "claim"
    assert t["npi"] == "1234567893" and t["license"] == "TX-111"
    assert t["location"]["address_line1"] == "500 Clinic Blvd" and t["location_source"] == "treatment_address"
    assert t["specialty_code"] == "1223E0200X" and t["specialty_code_source"] == "specialty"
    assert t["additional_provider_id"] == "DELTA-77"
    assert not any(w["code"] == "billing_entity_npi_missing" for w in form["warnings"])


def test_form_warns_on_corporate_office_without_entity_npi_and_po_box(client, db_session, patient, office, provider, coverage, codes):
    _proc(client, patient.id, office.id, provider.id, "D0120", 60, "2026-03-01", "P-2")
    _claim(client, patient.id, office.id, procedure_ids=["P-2"])
    form = client.get(f"{PREFIX}/insurance-claims/CLM-ADA/ada-claim-form").json()
    codes_ = {w["code"] for w in form["warnings"]}
    assert "billing_entity_npi_missing" in codes_
    assert "treatment_location_is_po_box" in codes_
    assert form["billing"]["npi"] == provider.npi and form["billing"]["npi_type"] == "1"
    assert form["billing"]["license"] == "TX-111"


def test_stored_overrides_beat_derivations(client, db_session, patient, office, provider, coverage, codes):
    """date_last_srp / missing_teeth / has_other_coverage / other_ins_plan_id
    stored on the claim win over the chart-derived answers."""
    tid = db_session._tenant_id
    db_session.add(PatientSignature(patient_id=patient.id, signature_type="claim_consent", is_active=True,
                                    signature_data="x"))
    db_session.commit()
    _proc(client, patient.id, office.id, provider.id, "D4341", 200, "2025-09-01", "P-SRP")
    _proc(client, patient.id, office.id, provider.id, "D0120", 60, "2026-03-01", "P-2")
    _claim(client, patient.id, office.id, procedure_ids=["P-2"], date_last_srp="2024-01-15",
           missing_teeth="8,9", has_other_coverage=False, other_ins_plan_id=None)
    form = client.get(f"{PREFIX}/insurance-claims/CLM-ADA/ada-claim-form").json()
    assert form["ancillary"]["date_last_srp"] == "2024-01-15"
    assert form["ancillary"]["date_last_srp_source"] == "claim"
    assert form["missing_teeth"] == {"teeth": ["8", "9"], "source": "claim"}
    assert form["other_coverage"]["has_other_coverage"] is False
    assert form["other_coverage"]["has_other_coverage_source"] == "stored"
    assert form["other_coverage"]["subscriber"] is None
    # ADA-BE-7: the captured consent asserts Item 36 without the checkbox
    assert form["authorizations"]["signature_on_file"] is True
    assert form["authorizations"]["signature_source"] == "claim_consent_signature"
    # ...and surfaces on PatientRead
    assert client.get(f"{PREFIX}/patients/{patient.id}").json()["has_claim_consent"] is True


# ── ADA-BE-1: PDF + audit ────────────────────────────────────────────────────
def test_pdf_form_overlay_batch_and_audit(client, db_session, patient, office, provider, coverage, codes):
    for n in range(12):  # 12 lines -> two forms (rule E)
        _proc(client, patient.id, office.id, provider.id, "D0120", 60, "2026-03-01", f"P-{n}")
    _claim(client, patient.id, office.id, procedure_ids=[f"P-{n}" for n in range(12)])
    form = client.get(f"{PREFIX}/insurance-claims/CLM-ADA/ada-claim-form").json()
    assert form["pages"] == 2
    assert form["service_lines"][10]["page_no"] == 2

    r = client.get(f"{PREFIX}/insurance-claims/CLM-ADA/reports/ada-claim-form")
    _assert_pdf(r, "ada-claim-CLM-ADA")
    r = client.get(f"{PREFIX}/insurance-claims/CLM-ADA/reports/ada-claim-form",
                   params={"mode": "overlay", "offset_x": 3, "offset_y": -2})
    _assert_pdf(r, "ada-claim-CLM-ADA")
    assert client.get(f"{PREFIX}/insurance-claims/CLM-ADA/reports/ada-claim-form",
                      params={"mode": "poster"}).status_code == 422

    _claim(client, patient.id, office.id, claim_id="CLM-B")
    r = client.post(f"{PREFIX}/insurance-claims/reports/ada-claim-form",
                    json={"claim_ids": ["CLM-ADA", "CLM-B", "CLM-ADA"], "mode": "form"})
    _assert_pdf(r, "ada-claims-batch-2")

    audits = db_session.execute(
        select(AuditLog).where(AuditLog.action == "PRINT", AuditLog.resource_type == "claim_report")
    ).scalars().all()
    assert len(audits) == 4  # single ×2 + batch ×2
    assert {a.resource_id for a in audits} == {"CLM-ADA", "CLM-B"}
    assert all(a.patient_id == patient.id for a in audits)
    assert audits[0].details["params"]["form_version"] == "2024"
    assert audits[1].details["params"]["mode"] == "overlay"


def test_form_is_tenant_scoped(client, db_session, patient, office):
    _claim(client, patient.id, office.id)
    other = Tenant(name="Other", code="other", is_active=True)
    db_session.add(other)
    db_session.commit()
    stranger = Patient(tenant_id=other.id, first_name="S", last_name="T", is_active=True)
    db_session.add(stranger)
    db_session.commit()
    from app.db.models import InsuranceClaim

    db_session.add(InsuranceClaim(id="CLM-X", patient_id=stranger.id, claim_number="CLM-X"))
    db_session.commit()
    assert client.get(f"{PREFIX}/insurance-claims/CLM-X/ada-claim-form").status_code == 404
    assert client.get(f"{PREFIX}/insurance-claims/CLM-X/reports/ada-claim-form").status_code == 404
    r = client.post(f"{PREFIX}/insurance-claims/reports/ada-claim-form", json={"claim_ids": ["CLM-ADA", "CLM-X"]})
    assert r.status_code == 404
    assert client.get(f"{PREFIX}/patients/{stranger.id}/tooth-status").status_code == 404


# ── ADA-BE-6: tooth status ───────────────────────────────────────────────────
def test_tooth_status_is_uncapped_and_ranked(client, db_session, patient, office, provider, codes):
    for t in range(1, 33):  # far more rows than the old size=200 page could have held per patient, per kind
        db_session.add(ChartCondition(patient_id=patient.id, tooth=str(t), condition_code="MISSING"))
    db_session.add(ChartCondition(patient_id=patient.id, tooth="30", condition_code="IMPLANT"))
    db_session.add(ChartCondition(patient_id=patient.id, tooth="A", condition_code="MISSING"))  # primary: ignored
    db_session.commit()
    _proc(client, patient.id, office.id, provider.id, "D7140", 150, "2025-10-01", "P-EXT", tooth="5")
    r = client.get(f"{PREFIX}/patients/{patient.id}/tooth-status")
    assert r.status_code == 200, r.text
    body = r.json()
    by = {t["tooth"]: t for t in body["teeth"]}
    assert len(body["teeth"]) == 32 and len(body["missing_teeth"]) == 32
    assert by["30"]["status"] == "implant"
    assert by["5"]["status"] == "extracted" and by["5"]["procedure_code"] == "D7140" and by["5"]["date"] == "2025-10-01"
    assert by["7"]["status"] == "missing" and by["7"]["source"] == "chart_condition"


# ── ADA-BE-14 / 8 / 13: office + provider reads ──────────────────────────────
def test_provider_taxonomy_and_office_entity_fields(client, provider, office):
    r = client.get(f"{PREFIX}/providers/{provider.id}")
    assert r.json()["effective_taxonomy_code"] == "1223E0200X"
    assert r.json()["effective_taxonomy_source"] == "specialty"
    r = client.patch(f"{PREFIX}/providers/{provider.id}", json={"taxonomy_code": "1223G0001X"})
    assert r.status_code == 200 and r.json()["taxonomy_code"] == "1223G0001X"
    assert r.json()["effective_taxonomy_code"] == "1223G0001X" and r.json()["effective_taxonomy_source"] == "stored"
    r = client.patch(f"{PREFIX}/offices/{office.id}", json={
        "npi": "1112223334", "taxonomy_code": "122300000X", "treatment_address_line1": "500 Clinic Blvd"})
    assert r.status_code == 200, r.text
    assert r.json()["npi"] == "1112223334" and r.json()["treatment_address_line1"] == "500 Clinic Blvd"
    r = client.get(f"{PREFIX}/metadata/provider-taxonomy-codes")
    assert r.status_code == 200 and any(c["code"] == "1223E0200X" for c in r.json())


def test_rules_metadata_published(client):
    r = client.get(f"{PREFIX}/metadata/ada-claim-form-rules")
    assert r.status_code == 200
    body = r.json()
    assert body["form_version"] == "2024" and body["lines_per_page"] == 10
    assert {"token": "UR", "code": "10"} in body["area_of_oral_cavity"]
    assert body["signature_on_file"]["signature_type"] == "claim_consent"
    r = client.get(f"{PREFIX}/metadata/procedure-entry-rules")
    assert {"token": "FM", "code": "00"} in r.json()["area_of_oral_cavity"]


# ── CLM-FO-5: submit freezes the form ────────────────────────────────────────
def test_submit_snapshots_form_and_reports_warnings(client, db_session, patient, office, provider, coverage, codes):
    _proc(client, patient.id, office.id, provider.id, "D0120", 60, "2026-03-01", "P-2", diagnosis_pointers="B")
    _claim(client, patient.id, office.id, procedure_ids=["P-2"])
    r = client.post(f"{PREFIX}/insurance-claims/CLM-ADA/submit", json={"send_method": "paper"})
    assert r.status_code == 200, r.text
    assert any(w["code"] == "pointer_without_diagnosis" for w in r.json()["form_warnings"])
    sub = db_session.execute(select(ClaimSubmission).where(ClaimSubmission.claim_id == "CLM-ADA")).scalar_one()
    snapshot = json.loads(sub.claim_text)
    assert snapshot["form_version"] == "2024" and snapshot["service_lines"][0]["procedure_id"] == "P-2"
    assert sub.num_lines == 1
