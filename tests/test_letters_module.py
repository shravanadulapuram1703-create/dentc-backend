"""Letters-module backend-gap tests (LTR-1..17)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

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


# The 56 distinct #TOKEN#s extracted from the 153 seeded letter_templates bodies.
# Kept here verbatim so the catalog is checked against the *corpus*, not against
# itself — if a template ever uses a token the backend cannot resolve, this fails.
CORPUS_TOKENS = frozenset("""
APPT_DATE APPT_PRDR DOC_LAST_NAME LASTVISIT_DATE
MARKET_ADDRESS MARKET_CITY MARKET_NAME MARKET_PHONE MARKET_STATE MARKET_ZIP
OFFICE_ADDRESS OFFICE_CITY OFFICE_CNAME OFFICE_EMAIL OFFICE_NAME OFFICE_PHONE1
OFFICE_STATE OFFICE_ZIP
PAT_ADDRESS PAT_BIRTHDATE PAT_CELLPHONE PAT_CITY PAT_EMAIL PAT_FIRST_NAME
PAT_HOMEPHONE PAT_ID PAT_LAST_NAME PAT_MID_INITIAL PAT_NAME_FIRST PAT_STATE
PAT_WORKPHONE PAT_ZIP
PAT_PREF_PROV PAT_PREF_PROV_Address PAT_PREF_PROV_CITY PAT_PREF_PROV_PHONE
PAT_PREF_PROV_STATE PAT_PREF_PROV_ZIP
PAT_REF_BY PAT_REF_BY_ADDRESS PAT_REF_BY_CITY PAT_REF_BY_STATE PAT_REF_BY_ZIP
PAT_REF_TO PAT_REF_TO_DATE
RP_ADDRESS RP_CITY RP_EMAIL RP_FIRST_NAME RP_LAST_NAME RP_MID_INITIAL RP_STATE
RP_TOTAL_BAL RP_ZIP
TODAY_DATE TX_PLAN_TH_NUMBER
""".split())


# ── LTR-5: merge catalog + render ────────────────────────────────────────────
def test_merge_field_catalog_covers_the_whole_seeded_corpus(client):
    body = client.get("/api/v1/letters/merge-fields").json()
    tokens = {f["token"] for f in body["fields"]}
    assert len(CORPUS_TOKENS) == 56
    # Every token a real migrated template can contain must be resolvable.
    assert CORPUS_TOKENS <= tokens
    # The catalog may extend beyond the corpus, but only deliberately: APPT_DATETIME
    # is the one addition the frontend asked for (LTR-13).
    assert tokens - CORPUS_TOKENS == {"APPT_DATETIME"}
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
    rendered = client.post(
        "/api/v1/letters/render",
        json={"template_id": template.id, "patient_id": patient.id},
    ).json()
    html = rendered["rendered_html"]
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


def test_render_pulls_balance_only_when_needed(client, db_session, patient, template):
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


# ── LTR-13: the appointment block falls back to the last visit ───────────────
def _appointment(db_session, patient, office, provider, *, appt_id, day, hour=9):
    db_session.add(Appointment(
        id=appt_id, patient_id=patient.id, provider_id=provider.id,
        office_id=office.id, date=day,
        start_time=time(hour, 0), end_time=time(hour + 1, 0), duration=60,
    ))
    db_session.commit()


def test_appt_provider_falls_back_to_the_last_appointment(
    client, db_session, patient, office, provider,
):
    """The consent-form case: no upcoming visit, so the token used to print blank
    on a signed legal document ("I hereby authorize Dr. ___")."""
    other = Provider(id="PRV-T2", tenant_id=db_session._tenant_id, office_id=office.id,
                     name="Dr. Arjun Mehta", last_name="Mehta", role="dentist")
    db_session.add(other)
    db_session.commit()
    _appointment(db_session, patient, office, other,
                 appt_id="APPT-PAST", day=date.today() - timedelta(days=3))

    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    assert body["last_appointment"]["id"] == "APPT-PAST"
    assert body["last_appointment_provider"]["id"] == "PRV-T2"
    assert body["merge_fields"]["APPT_PRDR"] == "Dr. Arjun Mehta"
    assert body["merge_fields"]["APPT_DATE"] != ""
    assert "APPT_PRDR" not in body["unresolved_tokens"]
    assert "APPT_DATE" not in body["unresolved_tokens"]


def test_upcoming_appointment_still_wins_over_the_last_one(
    client, db_session, patient, office, provider,
):
    past = Provider(id="PRV-PAST", tenant_id=db_session._tenant_id, office_id=office.id,
                    name="Dr. Past", role="dentist")
    db_session.add(past)
    db_session.commit()
    _appointment(db_session, patient, office, past,
                 appt_id="APPT-OLD", day=date.today() - timedelta(days=3))
    _appointment(db_session, patient, office, provider,
                 appt_id="APPT-NEW", day=date.today() + timedelta(days=5), hour=14)

    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    assert body["merge_fields"]["APPT_PRDR"] == "Dr. Jane Rivera"
    assert body["merge_fields"]["APPT_DATETIME"].endswith("2:00 PM")


def test_appt_provider_last_resort_is_the_preferred_provider(client, patient):
    """No appointments at all. 15 templates use #APPT_PRDR#, and a blank doctor
    on a consent form is worse than naming the patient's own dentist."""
    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    assert body["last_appointment"] is None
    assert body["merge_fields"]["APPT_PRDR"] == "Dr. Jane Rivera"


def test_appt_prdr_renders_in_a_consent_body(client, db_session, patient, office, template):
    doc = Provider(id="PRV-T3", tenant_id=db_session._tenant_id, office_id=office.id,
                   name="Dr. Arjun Mehta", last_name="Mehta", role="dentist")
    db_session.add(doc)
    db_session.commit()
    _appointment(db_session, patient, office, doc,
                 appt_id="APPT-CHAIR", day=date.today() - timedelta(days=1))
    template.body_html = "I hereby authorize Dr. #APPT_PRDR# to perform the extraction."
    db_session.commit()

    body = client.post("/api/v1/letters/render",
                       json={"template_id": template.id, "patient_id": patient.id}).json()
    assert "Dr. Arjun Mehta" in body["rendered_html"]
    assert body["unresolved_tokens"] == []


# ── LTR-14: TODAY_DATE is the office's date, not UTC ─────────────────────────
def test_today_date_uses_the_office_timezone(client, db_session, patient, office):
    """22:05 US-Eastern on the 18th is already the 19th in UTC. A consent form
    signed that evening must still be dated the 18th."""
    office.timezone = "America/New_York"
    db_session.commit()

    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    assert body["timezone"] == "America/New_York"
    expected = datetime.now(ZoneInfo("America/New_York")).date()
    assert body["today"] == expected.isoformat()
    assert body["merge_fields"]["TODAY_DATE"] == expected.strftime("%m/%d/%Y")


def test_today_date_differs_from_utc_for_a_far_west_office(client, db_session, patient, office):
    # UTC-10, no DST: for 10 hours of every UTC day these two dates disagree, and
    # the office's is the one a printed letter has to carry.
    office.timezone = "Pacific/Honolulu"
    db_session.commit()
    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    assert body["today"] == datetime.now(ZoneInfo("Pacific/Honolulu")).date().isoformat()
    assert body["timezone"] == "Pacific/Honolulu"


def test_a_broken_office_timezone_does_not_500(client, db_session, patient, office):
    office.timezone = "Not/AZone"
    db_session.commit()
    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    # Degraded to the default zone rather than 500-ing one office's letters.
    assert body["merge_fields"]["TODAY_DATE"]


def test_render_reports_the_clock_it_used(client, db_session, patient, office, template):
    office.timezone = "America/Chicago"
    db_session.commit()
    body = client.post("/api/v1/letters/render",
                       json={"template_id": template.id, "patient_id": patient.id}).json()
    assert body["timezone"] == "America/Chicago"
    assert body["today"] == datetime.now(ZoneInfo("America/Chicago")).date().isoformat()


def test_office_today_helper_is_not_the_utc_date_when_they_differ():
    from app.core.datetimes import office_today

    utc_now = datetime.now(timezone.utc)
    honolulu = office_today("Pacific/Honolulu")
    # Between 00:00 and 10:00 UTC the two calendar dates genuinely differ.
    if utc_now.hour < 10:
        assert honolulu == (utc_now.date() - timedelta(days=1))
    else:
        assert honolulu == utc_now.date()


# ── LTR-15: caller-supplied values ──────────────────────────────────────────
def test_render_accepts_token_overrides(client, db_session, patient, template):
    template.body_html = "Dear #PAT_FIRST_NAME#, #APPT_PRDR# will see you."
    db_session.commit()
    body = client.post("/api/v1/letters/render", json={
        "template_id": template.id, "patient_id": patient.id,
        "overrides": {"APPT_PRDR": "Dr. Arjun Mehta"},
    }).json()
    assert body["rendered_html"] == "Dear John, Dr. Arjun Mehta will see you."
    assert body["applied_overrides"] == ["APPT_PRDR"]
    assert body["merge_fields"]["APPT_PRDR"] == "Dr. Arjun Mehta"


def test_overrides_are_escaped_like_every_other_value(client, db_session, patient, template):
    template.body_html = "Dr. #APPT_PRDR#"
    db_session.commit()
    body = client.post("/api/v1/letters/render", json={
        "template_id": template.id, "patient_id": patient.id,
        "overrides": {"APPT_PRDR": "<img src=x onerror=alert(1)>"},
    }).json()
    assert "<img" not in body["rendered_html"] and "&lt;img" in body["rendered_html"]


def test_unknown_override_keys_are_reported_not_merged(client, patient, template):
    body = client.post("/api/v1/letters/render", json={
        "template_id": template.id, "patient_id": patient.id,
        "overrides": {"PAT_FIRST_NAME": "Jonathan", "NOT_A_TOKEN": "x"},
    }).json()
    assert body["rejected_overrides"] == ["NOT_A_TOKEN"]
    assert body["applied_overrides"] == ["PAT_FIRST_NAME"]
    assert "Jonathan" in body["rendered_html"]


def test_signing_provider_repoints_the_doctor_tokens(client, db_session, patient, office, template):
    signer = Provider(id="PRV-SIGN", tenant_id=db_session._tenant_id, office_id=office.id,
                      name="Dr. Arjun Mehta", last_name="Mehta", role="dentist")
    db_session.add(signer)
    template.body_html = "#APPT_PRDR# / #DOC_LAST_NAME# / #PAT_PREF_PROV#"
    db_session.commit()

    body = client.post("/api/v1/letters/render", json={
        "template_id": template.id, "patient_id": patient.id,
        "signing_provider_id": "PRV-SIGN",
    }).json()
    # The doctor named in the body moves...
    assert body["rendered_html"].startswith("Dr. Arjun Mehta / Mehta")
    # ...the letterhead block does not.
    assert body["merge_fields"]["PAT_PREF_PROV"] == "Dr. Jane Rivera"


def test_an_explicit_override_beats_signing_provider(client, db_session, patient, office, template):
    db_session.add(Provider(id="PRV-SIGN2", tenant_id=db_session._tenant_id,
                            office_id=office.id, name="Dr. Signer", role="dentist"))
    template.body_html = "#APPT_PRDR#"
    db_session.commit()
    body = client.post("/api/v1/letters/render", json={
        "template_id": template.id, "patient_id": patient.id,
        "signing_provider_id": "PRV-SIGN2",
        "overrides": {"APPT_PRDR": "Dr. Override"},
    }).json()
    assert body["rendered_html"] == "Dr. Override"


def test_unknown_signing_provider_is_a_404(client, patient, template):
    r = client.post("/api/v1/letters/render", json={
        "template_id": template.id, "patient_id": patient.id,
        "signing_provider_id": "PRV-NOPE",
    })
    assert r.status_code == 404


def test_batch_applies_the_signing_provider_to_every_letter(
    client, db_session, patient, office, template,
):
    db_session.add(Provider(id="PRV-BATCH", tenant_id=db_session._tenant_id,
                            office_id=office.id, name="Dr. Batch", role="dentist"))
    other = Patient(tenant_id=db_session._tenant_id, first_name="Ann", last_name="Lee",
                    is_active=True)
    db_session.add(other)
    template.body_html = "#PAT_FIRST_NAME# sees #APPT_PRDR#"
    db_session.commit()
    db_session.refresh(other)

    r = client.post("/api/v1/letters/render-batch", json={
        "template_id": template.id, "patient_ids": [patient.id, other.id],
        "signing_provider_id": "PRV-BATCH", "store_html": True,
    }).json()
    assert r["batch"]["succeeded"] == 2
    assert all("Dr. Batch" in i["rendered_html"] for i in r["items"])


# ── LTR-17: which tier of the fallback chain answered ───────────────────────
def test_source_is_next_when_an_upcoming_appointment_exists(
    client, db_session, patient, office, provider,
):
    _appointment(db_session, patient, office, provider,
                 appt_id="APPT-FUTURE", day=date.today() + timedelta(days=4))
    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    assert body["appointment_source"] == "next"
    assert body["appointment_provider_source"] == "next"
    # The ideal case is not a fallback and must not be annotated.
    assert body["fallback_tokens"] == {}


def test_source_is_last_when_only_a_past_appointment_exists(
    client, db_session, patient, office, provider,
):
    _appointment(db_session, patient, office, provider,
                 appt_id="APPT-DONE", day=date.today() - timedelta(days=2))
    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    assert body["appointment_source"] == "last"
    assert body["appointment_provider_source"] == "last"
    assert body["fallback_tokens"] == {
        "APPT_DATE": "last", "APPT_DATETIME": "last", "APPT_PRDR": "last",
    }


def test_source_is_preferred_when_there_is_no_appointment_at_all(client, patient):
    """The case the preview has to warn about: the name printed has no
    connection to any visit."""
    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    assert body["appointment_source"] is None
    assert body["appointment_provider_source"] == "preferred"
    assert body["fallback_tokens"] == {"APPT_PRDR": "preferred"}


def test_source_is_null_when_nothing_can_answer(client, db_session, office):
    bare = Patient(tenant_id=db_session._tenant_id, home_office_id=office.id,
                   first_name="Nan", last_name="Obody", is_active=True)
    db_session.add(bare)
    db_session.commit()
    db_session.refresh(bare)
    body = client.get(f"/api/v1/patients/{bare.id}/letter-context").json()
    assert body["appointment_source"] is None
    assert body["appointment_provider_source"] is None
    assert body["fallback_tokens"] == {}  # nothing resolved, so nothing to annotate
    assert "APPT_PRDR" in body["unresolved_tokens"]


def test_appointment_and_provider_tiers_can_disagree(
    client, db_session, patient, office, provider,
):
    """A past appointment whose provider_id no longer resolves: the date comes
    from 'last', the name from 'preferred'."""
    db_session.add(Appointment(
        id="APPT-ORPHAN", patient_id=patient.id, provider_id="prov-deleted",
        office_id=office.id, date=date.today() - timedelta(days=5),
        start_time=time(9, 0), end_time=time(10, 0), duration=60,
    ))
    db_session.commit()
    body = client.get(f"/api/v1/patients/{patient.id}/letter-context").json()
    assert body["appointment_source"] == "last"
    assert body["appointment_provider_source"] == "preferred"
    assert body["fallback_tokens"]["APPT_DATE"] == "last"
    assert body["fallback_tokens"]["APPT_PRDR"] == "preferred"


def test_render_only_reports_fallbacks_the_template_uses(
    client, db_session, patient, office, provider, template,
):
    _appointment(db_session, patient, office, provider,
                 appt_id="APPT-USED", day=date.today() - timedelta(days=2))
    template.body_html = "Dr. #APPT_PRDR# saw you."  # no #APPT_DATE#
    db_session.commit()
    body = client.post("/api/v1/letters/render",
                       json={"template_id": template.id, "patient_id": patient.id}).json()
    assert body["fallback_tokens"] == {"APPT_PRDR": "last"}
    assert body["appointment_provider_source"] == "last"


def test_an_overridden_token_is_not_reported_as_a_fallback(
    client, db_session, patient, template,
):
    """The value came from the dialog, so there is nothing to warn about."""
    template.body_html = "Dr. #APPT_PRDR#"
    db_session.commit()
    body = client.post("/api/v1/letters/render", json={
        "template_id": template.id, "patient_id": patient.id,
        "overrides": {"APPT_PRDR": "Dr. Chosen"},
    }).json()
    assert body["fallback_tokens"] == {}
    # The underlying tier is still reported, for anyone who wants it.
    assert body["appointment_provider_source"] == "preferred"


def test_signing_provider_also_clears_the_fallback_note(
    client, db_session, patient, office, template,
):
    db_session.add(Provider(id="PRV-S17", tenant_id=db_session._tenant_id,
                            office_id=office.id, name="Dr. Signer", role="dentist"))
    template.body_html = "Dr. #APPT_PRDR#"
    db_session.commit()
    body = client.post("/api/v1/letters/render", json={
        "template_id": template.id, "patient_id": patient.id,
        "signing_provider_id": "PRV-S17",
    }).json()
    assert body["fallback_tokens"] == {}
