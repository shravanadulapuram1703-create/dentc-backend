"""Letters-module backend-gap tests (LTR-1..12)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from app.db.models import (
    AccountSettings,
    Appointment,
    LetterTemplate,
    Office,
    OfficeLetterTemplate,
    Patient,
    PatientConsent,
    Provider,
    ResponsibleParty,
    TreatmentPlan,
    TreatmentPlanItem,
)
from app.services import letter_service


@pytest.fixture
def office(db_session) -> Office:
    o = Office(
        tenant_id=db_session._tenant_id, office_code="O-T1", name="Test Dental",
        corporate_name="Test Dental Group LLC",
        address_line1="1 Main St", city="Pittsburgh", state="PA", zip="15201",
        phone="412-555-0100", email="front@test.local", is_active=True,
    )
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    p = Provider(
        id="PRV-T1", tenant_id=db_session._tenant_id, office_id=office.id,
        name="Dr. Jane Rivera", last_name="Rivera", role="dentist",
        address_line1="9 Provider Way", city="Wexford", state="PA", zip="15090",
        phone="412-555-0199",
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def patient(db_session, office, provider) -> Patient:
    p = Patient(
        tenant_id=db_session._tenant_id, home_office_id=office.id,
        first_name="John", last_name="Smith", middle_initial="Q",
        dob=date(1980, 3, 4), address_line1="22 Oak Ave", city="Moon",
        state="PA", zip="15108", email="john@test.local", phone="412-555-0123",
        preferred_provider_id=provider.id, is_active=True,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def template(db_session) -> LetterTemplate:
    t = LetterTemplate(
        tenant_id=db_session._tenant_id, legacy_id="TPL1",
        name="AP002 - Missed Appt with Fee Letter", letter_type="A", channel="L",
        body_html=(
            "<div>#TODAY_DATE#</div>"
            "<div>Dear #PAT_FIRST_NAME# #PAT_LAST_NAME#,</div>"
            "<div>#PAT_ADDRESS#, #PAT_CITY# #PAT_STATE# #PAT_ZIP#</div>"
            "<div>#OFFICE_CNAME# / #OFFICE_NAME# — #OFFICE_PHONE1#</div>"
            "<div>#PAT_PREF_PROV#, #PAT_PREF_PROV_Address#, #PAT_PREF_PROV_PHONE#</div>"
            "<div>#MARKET_NAME#, #MARKET_CITY#</div>"
        ),
        is_active=True,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


# ── LTR-5: merge catalog + render ────────────────────────────────────────────
def test_merge_field_catalog_is_the_full_56_token_corpus(client):
    body = client.get("/api/v1/letters/merge-fields").json()
    tokens = {f["token"] for f in body["fields"]}
    assert len(tokens) == 56
    # The three blocks the dev report called out as having no backend source.
    assert {"PAT_PREF_PROV_Address", "MARKET_NAME", "OFFICE_CNAME"} <= tokens
    balance_tokens = {f["token"] for f in body["fields"] if f["requires_balance"]}
    assert balance_tokens == {"RP_TOTAL_BAL"}


def test_render_merges_every_token(client, patient, template):
    r = client.post("/api/v1/letters/render",
                    json={"template_id": template.id, "patient_id": patient.id})
    assert r.status_code == 200, r.text
    body = r.json()
    html = body["rendered_html"]
    assert "#PAT_FIRST_NAME#" not in html and "John" in html and "Smith" in html
    # LTR-3: the corporate name, the provider letterhead and the marketing block
    # all resolve rather than silently printing the office address.
    assert "Test Dental Group LLC" in html
    assert "9 Provider Way" in html and "412-555-0199" in html
    assert body["merge_fields"]["MARKET_NAME"] == "Test Dental Group LLC"
    assert body["unknown_tokens"] == []
    # title is null on most migrated rows -> name is the heading (LTR-9).
    assert body["title"] == template.name


def test_render_escapes_merged_values(client, db_session, patient, template):
    patient.last_name = "<script>alert(1)</script>"
    db_session.commit()
    html = client.post("/api/v1/letters/render",
                       json={"template_id": template.id, "patient_id": patient.id}).json()["rendered_html"]
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_render_reports_unresolved_tokens_blank(client, db_session, patient, template):
    template.body_html = "Hello #PAT_FIRST_NAME#, tooth #TX_PLAN_TH_NUMBER# / #PAT_CELLPHONE#"
    db_session.commit()
    body = client.post("/api/v1/letters/render",
                       json={"template_id": template.id, "patient_id": patient.id}).json()
    assert set(body["unresolved_tokens"]) == {"TX_PLAN_TH_NUMBER", "PAT_CELLPHONE"}
    # A token with no data prints blank — never "#TOKEN#" at the patient.
    assert "#" not in body["rendered_html"]


# ── LTR-4: treatment-plan tooth number ───────────────────────────────────────
def test_treatment_plan_binds_tooth_number(client, db_session, patient, template):
    plan = TreatmentPlan(id="TP-T1", patient_id=patient.id, name="Plan A")
    db_session.add(plan)
    db_session.add_all([
        TreatmentPlanItem(id="TPI-1", plan_id=plan.id, procedure_code="D2740",
                          tooth="14", fee=1200, priority=1),
        TreatmentPlanItem(id="TPI-2", plan_id=plan.id, procedure_code="D2750",
                          tooth="19", fee=1100, priority=2),
    ])
    template.body_html = "Tooth #TX_PLAN_TH_NUMBER#"
    db_session.commit()

    without = client.post("/api/v1/letters/render",
                          json={"template_id": template.id, "patient_id": patient.id}).json()
    assert without["unresolved_tokens"] == ["TX_PLAN_TH_NUMBER"]

    with_plan = client.post("/api/v1/letters/render", json={
        "template_id": template.id, "patient_id": patient.id, "treatment_plan_id": plan.id,
    }).json()
    assert with_plan["rendered_html"] == "Tooth 14, 19"
    assert with_plan["unresolved_tokens"] == []


# ── LTR-5: batch runs ────────────────────────────────────────────────────────
def test_batch_run_records_a_job_and_survives_a_bad_row(client, db_session, patient, template):
    other = Patient(tenant_id=db_session._tenant_id, first_name="Ann", last_name="Lee",
                    is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    r = client.post("/api/v1/letters/render-batch", json={
        "template_id": template.id,
        "patient_ids": [patient.id, other.id, 999999],  # last one does not exist
        "store_html": True,
    })
    assert r.status_code == 200, r.text
    batch = r.json()["batch"]
    assert batch["requested"] == 3 and batch["succeeded"] == 2 and batch["failed"] == 1

    fetched = client.get(f"/api/v1/letters/batches/{batch['id']}").json()
    statuses = sorted(i["status"] for i in fetched["items"])
    assert statuses == ["failed", "rendered", "rendered"]
    assert any(i["rendered_html"] for i in fetched["items"])
    assert client.get("/api/v1/letters/batches").json()["meta"]["total"] == 1


def test_batch_rejects_an_empty_list(client, template):
    r = client.post("/api/v1/letters/render-batch",
                    json={"template_id": template.id, "patient_ids": []})
    assert r.status_code == 422  # min_length=1 on the request model


# ── LTR-6: aggregate letter context ──────────────────────────────────────────
def test_letter_context_is_one_round_trip(client, db_session, patient, office, provider):
    rp = ResponsibleParty(tenant_id=db_session._tenant_id, first_name="Mary",
                          last_name="Smith", address_line1="22 Oak Ave", city="Moon",
                          state="PA", zip="15108", email="mary@test.local")
    db_session.add(rp)
    db_session.commit()
    db_session.refresh(rp)
    patient.responsible_party_id = str(rp.id)
    db_session.add(Appointment(
        id="APPT-T1", patient_id=patient.id, provider_id=provider.id,
        office_id=office.id, date=date.today() + timedelta(days=7),
        start_time=time(9, 0), end_time=time(10, 0), duration=60,
    ))
    db_session.commit()

    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    assert body["patient"]["id"] == patient.id
    assert body["office"]["corporate_name"] == "Test Dental Group LLC"
    assert body["responsible_party"]["first_name"] == "Mary"
    assert body["next_appointment"]["id"] == "APPT-T1"
    assert body["merge_fields"]["RP_FIRST_NAME"] == "Mary"
    assert body["merge_fields"]["APPT_PRDR"] == "Dr. Jane Rivera"
    # The slow aggregate is opt-in.
    assert body["balance"] is None
    assert body["merge_fields"]["RP_TOTAL_BAL"] == ""

    with_bal = client.get(
        f"/api/v1/patients/{patient.id}/letter-context?include_balance=true"
    ).json()
    assert with_bal["balance"] is not None
    assert with_bal["merge_fields"]["RP_TOTAL_BAL"].startswith("$")


def test_render_pulls_balance_only_when_the_template_needs_it(client, db_session, patient, template):
    template.body_html = "You owe #RP_TOTAL_BAL#"
    db_session.commit()
    body = client.post("/api/v1/letters/render",
                       json={"template_id": template.id, "patient_id": patient.id}).json()
    assert body["merge_fields"]["RP_TOTAL_BAL"].startswith("$")
    assert body["unresolved_tokens"] == []


# ── LTR-7: office assignment semantics ───────────────────────────────────────
def test_effective_letter_templates_falls_back_to_the_whole_catalog(
    client, db_session, office, template,
):
    other = LetterTemplate(tenant_id=db_session._tenant_id, name="CS001 - Batch Coll 1",
                           letter_type="F", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    # Unassigned office -> the full tenant catalog.
    unassigned = client.get(f"/api/v1/offices/{office.id}/letter-templates/effective").json()
    assert {t["id"] for t in unassigned} == {template.id, other.id}
    # The assignment grid itself stays empty (it is what PUT replaces).
    assert client.get(f"/api/v1/offices/{office.id}/letter-templates").json() == []

    db_session.add(OfficeLetterTemplate(
        tenant_id=db_session._tenant_id, office_id=office.id, letter_template_id=other.id,
    ))
    db_session.commit()
    assigned = client.get(f"/api/v1/offices/{office.id}/letter-templates/effective").json()
    assert [t["id"] for t in assigned] == [other.id]


# ── LTR-10: consent signing ──────────────────────────────────────────────────
def test_consent_status_vocabulary_is_published(client):
    body = client.get("/api/v1/patient-consents/statuses").json()
    assert body["statuses"] == ["pending", "printed", "signed", "declined", "voided"]
    assert "scanned" in body["signature_methods"]


def test_sign_consent_with_a_drawn_signature(client, db_session, patient, template):
    consent = PatientConsent(tenant_id=db_session._tenant_id, patient_id=patient.id,
                             template_id=template.id, status="printed")
    db_session.add(consent)
    db_session.commit()
    db_session.refresh(consent)

    r = client.post(f"/api/v1/patient-consents/{consent.id}/sign", json={
        "signature_data": "data:image/png;base64,iVBORw0KGgo=",
        "signer_name": "John Smith", "signer_relationship": "self",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "signed" and body["signature_method"] == "drawn"
    assert body["signed_by"] == db_session._admin.id and body["signed_at"]

    # Re-signing is a conflict: the first signature is the record.
    again = client.post(f"/api/v1/patient-consents/{consent.id}/sign",
                        json={"signature_data": "data:image/png;base64,AAAA"})
    assert again.status_code == 409


def test_sign_consent_with_a_scanned_document(client, db_session, patient, template):
    consent = PatientConsent(tenant_id=db_session._tenant_id, patient_id=patient.id,
                             template_id=template.id, status="printed")
    db_session.add(consent)
    db_session.commit()
    db_session.refresh(consent)

    doc = client.post("/api/v1/patient-documents",
                      data={"patient_id": str(patient.id), "document_type": "consent-form"},
                      files={"file": ("signed.pdf", b"%PDF-1.4 signed", "application/pdf")}).json()

    r = client.post(f"/api/v1/patient-consents/{consent.id}/sign",
                    json={"document_id": doc["id"], "signer_name": "John Smith"})
    assert r.status_code == 200, r.text
    assert r.json()["document_id"] == doc["id"]
    assert r.json()["signature_method"] == "scanned"


def test_sign_requires_a_signature(client, db_session, patient, template):
    consent = PatientConsent(tenant_id=db_session._tenant_id, patient_id=patient.id,
                             template_id=template.id, status="pending")
    db_session.add(consent)
    db_session.commit()
    db_session.refresh(consent)
    assert client.post(f"/api/v1/patient-consents/{consent.id}/sign", json={}).status_code == 422


def test_declining_a_consent_needs_no_signature(client, db_session, patient, template):
    consent = PatientConsent(tenant_id=db_session._tenant_id, patient_id=patient.id,
                             template_id=template.id, status="printed")
    db_session.add(consent)
    db_session.commit()
    db_session.refresh(consent)
    r = client.post(f"/api/v1/patient-consents/{consent.id}/sign",
                    json={"status": "declined", "declined_reason": "wants to think it over"})
    assert r.status_code == 200
    assert r.json()["status"] == "declined" and r.json()["signed_at"]


# ── LTR-1 / LTR-12: document storage + listing ───────────────────────────────
def test_document_records_its_storage_provenance(client, patient):
    doc = client.post("/api/v1/patient-documents",
                      data={"patient_id": str(patient.id), "document_type": "consent-form"},
                      files={"file": ("c.pdf", b"%PDF-1.4 x", "application/pdf")}).json()
    # No bucket configured in tests -> local, but the provenance columns are populated.
    assert doc["storage_backend"] == "local"
    assert doc["storage_path"] and doc["storage_bucket"] is None
    assert "file_path" not in doc


def test_document_content_proxy_streams_the_bytes(client, patient):
    payload = b"%PDF-1.4 hello letters"
    doc = client.post("/api/v1/patient-documents",
                      data={"patient_id": str(patient.id), "document_type": "consent-form"},
                      files={"file": ("c.pdf", payload, "application/pdf")}).json()
    r = client.get(f"/api/v1/patient-documents/{doc['id']}/content")
    assert r.status_code == 200
    assert r.content == payload
    assert r.headers["content-type"].startswith("application/pdf")


def test_document_list_filters_by_type_and_pages(client, patient):
    for name, kind in (("a.pdf", "consent-form"), ("b.pdf", "consent-form"), ("c.pdf", "xray")):
        client.post("/api/v1/patient-documents",
                    data={"patient_id": str(patient.id), "document_type": kind},
                    files={"file": (name, b"%PDF-1.4", "application/pdf")})
    all_docs = client.get(f"/api/v1/patient-documents?patient_id={patient.id}").json()
    assert all_docs["meta"]["total"] == 3
    consents = client.get(
        f"/api/v1/patient-documents?patient_id={patient.id}&document_type=consent-form"
    ).json()
    assert consents["meta"]["total"] == 2
    paged = client.get(
        f"/api/v1/patient-documents?patient_id={patient.id}&size=1&page=2"
    ).json()
    assert paged["meta"]["pages"] == 3 and len(paged["items"]) == 1


def test_consent_forms_listing_is_safe_without_a_bucket(client):
    body = client.get("/api/v1/consent-forms").json()
    assert body["is_configured"] is False and body["items"] == []


# ── LTR-11: timezone-aware timestamps ────────────────────────────────────────
def test_created_at_carries_an_offset(client, patient):
    doc = client.post("/api/v1/patient-documents",
                      data={"patient_id": str(patient.id)},
                      files={"file": ("c.pdf", b"%PDF-1.4", "application/pdf")}).json()
    stamp = doc["created_at"]
    assert stamp.endswith("Z") or "+" in stamp[10:], stamp
    # And it round-trips as an aware datetime.
    assert datetime.fromisoformat(stamp.replace("Z", "+00:00")).tzinfo is not None


# ── LTR-2: the letter_type lookup group ──────────────────────────────────────
def test_lettertype_definition_group_is_seeded(client, db_session):
    from scripts.seed_account_definitions import seed_for_tenant

    seed_for_tenant(db_session, db_session._tenant_id)
    body = client.get("/api/v1/definitions?group_code=LETTERTYPE").json()
    codes = {d["key1"]: d["description"] for d in body["items"]}
    assert set(codes) == set("ACDEFIMS")
    assert codes["C"] == "Patient Consent"


# ── LTR-8/9: the migration repair rules ──────────────────────────────────────
@pytest.mark.parametrize(("broken", "fixed"), [
    ("If you?re concerned", "If you’re concerned"),
    ("It?s been several months", "It’s been several months"),
    ("attorney?s fees", "attorney’s fees"),
    ("also known as ?bleaching?.", "also known as “bleaching”."),
    # A genuine question mark is left alone.
    ("what are its benefits? <br />", "what are its benefits? <br />"),
])
def test_mojibake_repair_rules(broken, fixed):
    from scripts.repair_letter_templates import repair_body

    assert repair_body(broken, [])[0] == fixed


def test_mojibake_trademark_rule_is_opt_in():
    from scripts.repair_letter_templates import repair_body

    assert repair_body("RADIESSE? filler", [])[0] == "RADIESSE? filler"
    assert repair_body("RADIESSE? filler", ["RADIESSE"])[0] == "RADIESSE® filler"


def test_account_settings_marketing_block_is_writable(client, db_session, office):
    db_session.add(AccountSettings(tenant_id=db_session._tenant_id))
    db_session.commit()
    r = client.patch(f"/api/v1/tenants/{db_session._tenant_id}/account-settings",
                     json={"marketing_name": "Excel Dental Group",
                           "marketing_city": "Wexford", "marketing_phone": "412-555-0000"})
    assert r.status_code == 200, r.text
    assert r.json()["marketing_name"] == "Excel Dental Group"
