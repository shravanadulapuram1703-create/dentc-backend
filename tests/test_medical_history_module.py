"""Patient Medical History gaps MH-1..16.

MH-1 is a data task with tooling (``scripts/seed_medical_history_catalogs.py``);
what is covered here is the *server-side* half of it — the built-in catalog is
served, and reported as such, until a tenant seeds a real one.
"""

from __future__ import annotations

import pytest

from app.db.models import (
    Definition,
    DefinitionGroup,
    Patient,
    PatientAlert,
    PatientMedicalAlert,
    PatientSignature,
)
from app.services.medical_history_catalog import to_code

V1 = "/api/v1"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Leo", last_name="Rob",
                chart_no="C-1", cell_phone="9092221234", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def other_patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ann", last_name="Zeta",
                chart_no="C-2", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _seed_alert_catalog(db_session, *, flash_code: str | None = None) -> None:
    """A real tenant MEDALERT catalog (over the size guard)."""
    db_session.add(DefinitionGroup(tenant_id=db_session._tenant_id, group_code="MEDALERT",
                                   description="Medical Alerts", group_type="MEDALERT"))
    labels = [
        ("No Known Allergies", "Allergic To"),
        ("Penicillin", "Allergic To"),
        ("Latex Rubber", "Allergic To"),
        ("Aspirin", "Allergic To"),
        ("Codeine", "Allergic To"),
        ("Diabetes", "Medical Conditions"),
        ("Asthma", "Medical Conditions"),
        ("Cancer", "Medical Conditions"),
        ("Stroke", "Medical Conditions"),
        ("Pregnant", "Women Only"),
        ("No Change Since Last Recorded", "Other"),
    ]
    for index, (label, section) in enumerate(labels):
        code = to_code(label)
        db_session.add(Definition(
            tenant_id=db_session._tenant_id, group_code="MEDALERT", key1=code,
            description=label, section=section, sort_order=index, is_active=True,
            is_flash_alert=(code == flash_code),
        ))
    db_session.commit()


# ── MH-2: the composite read ─────────────────────────────────────────────────
def test_composite_read_returns_the_whole_document(client, patient):
    body = client.get(f"{V1}/patients/{patient.id}/medical-history").json()
    assert body["patient_id"] == patient.id
    assert body["patient"]["chart_no"] == "C-1"
    for key in ("alerts", "dental_responses", "medical_responses", "emergency_contacts",
                "signatures", "versions"):
        assert body[key] == []
    assert body["signature_status"] == "unsigned"
    assert set(body["catalogs"]) == {"alerts", "dental", "medical"}


def test_builtin_catalog_is_served_until_a_tenant_seeds_one(client, patient):
    """MH-1: the size guard lives server-side too, so a stray test group with one
    row never replaces the ~90-item legacy catalog."""
    body = client.get(f"{V1}/patients/{patient.id}/medical-history").json()
    assert body["catalog_sources"]["alerts"] == "builtin"
    assert len(body["catalogs"]["alerts"]) > 50
    assert any(i["code"] == "latex_rubber" for i in body["catalogs"]["alerts"])


def test_tenant_catalog_wins_once_it_is_real(client, patient, db_session):
    _seed_alert_catalog(db_session)
    body = client.get(f"{V1}/patients/{patient.id}/medical-history").json()
    assert body["catalog_sources"]["alerts"] == "tenant"
    assert len(body["catalogs"]["alerts"]) == 11


# ── MH-3: the composite write ────────────────────────────────────────────────
def test_composite_write_creates_updates_and_deletes_in_one_call(client, patient):
    saved = client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "comments": "Takes warfarin daily",
        "alerts": [
            {"alert_code": "penicillin", "alert_label": "Penicillin", "response": "yes"},
            {"alert_code": "aspirin", "alert_label": "Aspirin", "response": "no"},
        ],
        "dental_responses": [
            {"question_code": "do_you_have_loose_teeth", "answer": "yes"},
        ],
        "mark_completed": ["alerts", "dental"],
    })
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert {a["alert_code"] for a in body["alerts"]} == {"penicillin", "aspirin"}
    assert body["comments"] == "Takes warfarin daily"
    assert len(body["dental_responses"]) == 1
    # MH-16: a completion is asserted, never inferred from a row edit.
    assert body["completion"]["alerts"]["last_completed_at"] is not None
    assert body["completion"]["medical"]["last_completed_at"] is None

    # A null response is a reset to Not Answered: the row goes away (MH-5).
    body = client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [{"alert_code": "aspirin", "response": None}],
    }).json()
    assert {a["alert_code"] for a in body["alerts"]} == {"penicillin"}


def test_no_to_all_alerts_is_one_request(client, patient):
    """MH-3: the legacy button against the whole catalog used to be ~90 POSTs."""
    catalog = client.get(f"{V1}/patients/{patient.id}/medical-history").json()["catalogs"]["alerts"]
    payload = [
        {"alert_code": item["code"], "alert_label": item["label"], "response": "no"}
        for item in catalog
        if not item["input_kind"] and item["code"] != to_code("No Known Allergies")
    ]
    body = client.put(f"{V1}/patients/{patient.id}/medical-history",
                      json={"alerts": payload, "mark_completed": ["alerts"]}).json()
    assert len(body["alerts"]) == len(payload) > 50
    assert all(a["response"] == "no" for a in body["alerts"])


def test_replace_clears_the_codes_the_payload_omits(client, patient):
    client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [{"alert_code": "penicillin", "response": "yes"},
                   {"alert_code": "codeine", "response": "yes"}],
    })
    body = client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [{"alert_code": "penicillin", "response": "yes"}],
        "replace_alerts": True,
    }).json()
    assert {a["alert_code"] for a in body["alerts"]} == {"penicillin"}


# ── MH-13: comments are a first-class field ──────────────────────────────────
def test_comments_are_not_stored_as_a_magic_alert_row(client, patient, db_session):
    client.put(f"{V1}/patients/{patient.id}/medical-history",
               json={"comments": "Latex gloves only"})
    codes = {
        row.alert_code
        for row in db_session.query(PatientMedicalAlert).filter_by(patient_id=patient.id)
    }
    assert "ADDITIONAL_COMMENTS" not in codes
    body = client.get(f"{V1}/patients/{patient.id}/medical-history").json()
    assert body["comments"] == "Latex gloves only"


def test_a_legacy_comments_row_is_still_read_and_then_retired(client, patient, db_session):
    db_session.add(PatientMedicalAlert(
        tenant_id=db_session._tenant_id, patient_id=patient.id,
        alert_code="ADDITIONAL_COMMENTS", comments="Migrated note", is_active=True,
    ))
    db_session.commit()
    body = client.get(f"{V1}/patients/{patient.id}/medical-history").json()
    assert body["comments"] == "Migrated note"
    assert all(a["alert_code"] != "ADDITIONAL_COMMENTS" for a in body["alerts"])

    client.put(f"{V1}/patients/{patient.id}/medical-history", json={"comments": "Rewritten"})
    remaining = db_session.query(PatientMedicalAlert).filter_by(
        patient_id=patient.id, alert_code="ADDITIONAL_COMMENTS").count()
    assert remaining == 0


# ── MH-12: contradictions ────────────────────────────────────────────────────
def test_no_known_allergies_with_a_specific_allergy_is_422(client, patient, db_session):
    _seed_alert_catalog(db_session)
    bad = client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [
            {"alert_code": to_code("No Known Allergies"), "response": "yes"},
            {"alert_code": "penicillin", "response": "yes"},
        ],
    })
    assert bad.status_code == 422, bad.text
    assert bad.json()["error"]["code"] == "contradictory_medical_alerts"
    assert "penicillin" in bad.json()["error"]["details"]["contradictions"][0]["conflicts_with"]


def test_contradiction_is_judged_against_the_stored_rows_too(client, patient, db_session):
    _seed_alert_catalog(db_session)
    client.put(f"{V1}/patients/{patient.id}/medical-history",
               json={"alerts": [{"alert_code": "penicillin", "response": "yes"}]})
    # The second save carries only the No-Known-Allergies box.
    bad = client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [{"alert_code": to_code("No Known Allergies"), "response": "yes"}],
    })
    assert bad.status_code == 422


def test_contradiction_can_be_stored_deliberately(client, patient, db_session):
    _seed_alert_catalog(db_session)
    body = client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [
            {"alert_code": to_code("No Known Allergies"), "response": "yes"},
            {"alert_code": "penicillin", "response": "yes"},
        ],
        "allow_contradictions": True,
    })
    assert body.status_code == 200, body.text
    assert body.json()["contradictions"]


def test_the_generic_resource_enforces_the_same_rule(client, patient, db_session):
    """No client can route around the composite write one row at a time."""
    _seed_alert_catalog(db_session)
    first = client.post(f"{V1}/patient-medical-alerts", json={
        "patient_id": patient.id, "alert_code": "penicillin", "response": "yes"})
    assert first.status_code == 201, first.text
    clash = client.post(f"{V1}/patient-medical-alerts", json={
        "patient_id": patient.id, "alert_code": to_code("No Known Allergies"),
        "response": "yes"})
    assert clash.status_code == 422, clash.text


def test_published_rules_name_the_same_codes_the_api_enforces(client):
    rules = client.get(f"{V1}/metadata/medical-history-rules").json()
    assert rules["response_values"] == ["yes", "no", "unknown"]
    assert rules["not_answered_is"] == "absent_row"
    assert rules["emergency_contact_authority"] == "patient_emergency_contacts"
    codes = {r["code"] for r in rules["exclusions"]}
    assert to_code("No Known Allergies") in codes


# ── MH-14: an answer can drive a flash alert ─────────────────────────────────
def test_yes_to_a_flagged_alert_raises_a_banner_alert(client, patient, db_session):
    _seed_alert_catalog(db_session, flash_code="latex_rubber")
    client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [{"alert_code": "latex_rubber", "alert_label": "Latex Rubber",
                    "response": "yes"}],
    })
    banners = db_session.query(PatientAlert).filter_by(patient_id=patient.id).all()
    assert len(banners) == 1
    assert banners[0].is_flash_alert is True
    assert banners[0].source_medical_alert_id is not None

    # Un-answering deactivates exactly the row it created.
    client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [{"alert_code": "latex_rubber", "response": None}],
    })
    db_session.expire_all()
    banners = db_session.query(PatientAlert).filter_by(patient_id=patient.id).all()
    assert [b.is_active for b in banners] == [False]


def test_a_hand_typed_banner_alert_is_never_touched(client, patient, db_session):
    _seed_alert_catalog(db_session, flash_code="latex_rubber")
    db_session.add(PatientAlert(patient_id=patient.id, alert="Wheelchair access",
                                is_active=True))
    db_session.commit()
    client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [{"alert_code": "latex_rubber", "response": "no"}],
    })
    db_session.expire_all()
    manual = db_session.query(PatientAlert).filter_by(alert="Wheelchair access").one()
    assert manual.is_active is True


def test_the_alert_read_carries_the_catalog_flags(client, patient, db_session):
    _seed_alert_catalog(db_session, flash_code="latex_rubber")
    created = client.post(f"{V1}/patient-medical-alerts", json={
        "patient_id": patient.id, "alert_code": "latex_rubber", "response": "yes"}).json()
    assert created["is_flash_alert"] is True
    assert created["section"] == "Allergic To"


# ── MH-6 / MH-7: the signature knows what it signed ──────────────────────────
def test_signing_freezes_a_version_and_a_later_edit_makes_it_stale(client, patient):
    client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [{"alert_code": "penicillin", "response": "yes"}],
    })
    signed = client.post(f"{V1}/patients/{patient.id}/medical-history/sign",
                         json={"signature_data": "AAAA", "device_source": "pad"})
    assert signed.status_code == 201, signed.text
    body = signed.json()
    assert body["signature_status"] == "signed"
    assert body["current_signature"]["content_hash"] == body["content_hash"]
    version_id = body["version_id"]

    version = client.get(
        f"{V1}/patients/{patient.id}/medical-history/versions/{version_id}").json()
    assert version["item_count"] == 1
    assert version["answers"][0]["question_code"] == "penicillin"
    assert version["answers"][0]["answer_type"] == "alert"
    assert version["signature"]["id"] == body["signature_id"]

    # The whole point of MH-6: change an answer and the signature stops matching.
    after = client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [{"alert_code": "penicillin", "response": "no"}],
    }).json()
    assert after["signature_status"] == "stale"
    # The frozen version still reads as it was signed.
    frozen = client.get(
        f"{V1}/patients/{patient.id}/medical-history/versions/{version_id}").json()
    assert frozen["answers"][0]["answer_text"] == "yes"


def test_a_migrated_signature_with_no_hash_is_unverifiable_not_signed(
    client, patient, db_session
):
    db_session.add(PatientSignature(patient_id=patient.id, signature_data="OLD",
                                    is_active=True))
    db_session.commit()
    body = client.get(f"{V1}/patients/{patient.id}/medical-history").json()
    assert body["signature_status"] == "unverifiable"


def test_a_new_signature_supersedes_the_previous_one(client, patient):
    first = client.post(f"{V1}/patients/{patient.id}/medical-history/sign",
                        json={"signature_data": "AAAA"}).json()
    second = client.post(f"{V1}/patients/{patient.id}/medical-history/sign",
                         json={"signature_data": "BBBB"}).json()
    old = next(s for s in second["signatures"] if s["id"] == first["signature_id"])
    assert old["is_active"] is False
    assert old["superseded_by_id"] == second["signature_id"]


def test_a_signature_can_be_voided(client, patient):
    signed = client.post(f"{V1}/patients/{patient.id}/medical-history/sign",
                         json={"signature_data": "AAAA"}).json()
    voided = client.post(f"{V1}/patient-signatures/{signed['signature_id']}/void",
                         json={"reason": "captured on the wrong chart"})
    assert voided.status_code == 200, voided.text
    assert voided.json()["is_active"] is False
    assert voided.json()["voided_at"] is not None
    body = client.get(f"{V1}/patients/{patient.id}/medical-history").json()
    assert body["signature_status"] == "unsigned"
    # Voiding twice is a 422, not a silent no-op.
    again = client.post(f"{V1}/patient-signatures/{signed['signature_id']}/void", json={})
    assert again.status_code == 422


def test_a_signature_records_the_type_and_the_attesting_user(client, patient, db_session):
    signed = client.post(f"{V1}/patients/{patient.id}/medical-history/sign",
                         json={"signature_data": "AAAA"}).json()
    sig = signed["current_signature"]
    assert sig["signature_type"] == "medical_history"
    assert sig["signed_at"] is not None
    assert sig["signed_by_user_id"] == db_session._admin.id


# ── MH-4: server-side copy ───────────────────────────────────────────────────
def test_copy_medical_history_is_atomic_and_attributable(client, patient, other_patient):
    client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "comments": "Source note",
        "alerts": [{"alert_code": "penicillin", "alert_label": "Penicillin",
                    "response": "yes"}],
        "dental_responses": [{"question_code": "do_you_have_loose_teeth", "answer": "no"}],
    })
    copied = client.post(
        f"{V1}/patients/{other_patient.id}/medical-history/copy-from/{patient.id}")
    assert copied.status_code == 200, copied.text
    body = copied.json()
    assert {a["alert_code"] for a in body["alerts"]} == {"penicillin"}
    assert body["comments"] == "Source note"
    assert body["copied_from_patient_id"] == patient.id
    assert body["versions"][0]["source_patient_id"] == patient.id

    log = client.get(f"{V1}/patients/{other_patient.id}/medical-history/changes").json()
    copy_events = [e for e in log if e["action"] == "copy"]
    assert copy_events and copy_events[0]["source_patient_id"] == patient.id


def test_copy_scope_limits_what_is_copied(client, patient, other_patient):
    client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "alerts": [{"alert_code": "penicillin", "response": "yes"}],
        "dental_responses": [{"question_code": "do_you_have_loose_teeth", "answer": "no"}],
    })
    body = client.post(
        f"{V1}/patients/{other_patient.id}/medical-history/copy-from/{patient.id}",
        json={"scope": "dental"}).json()
    assert body["alerts"] == []
    assert len(body["dental_responses"]) == 1


def test_copy_onto_the_same_patient_is_rejected(client, patient):
    resp = client.post(f"{V1}/patients/{patient.id}/medical-history/copy-from/{patient.id}")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "copy_source_is_target"


# ── MH-8: the change log ─────────────────────────────────────────────────────
def test_every_answer_change_is_attributable(client, patient, db_session):
    client.put(f"{V1}/patients/{patient.id}/medical-history",
               json={"alerts": [{"alert_code": "penicillin", "response": "yes"}]})
    client.put(f"{V1}/patients/{patient.id}/medical-history",
               json={"alerts": [{"alert_code": "penicillin", "response": "no"}]})
    client.put(f"{V1}/patients/{patient.id}/medical-history",
               json={"alerts": [{"alert_code": "penicillin", "response": None}]})

    log = client.get(f"{V1}/patients/{patient.id}/medical-history/changes",
                     params={"entity_type": "alert"}).json()
    assert [e["action"] for e in log] == ["delete", "update", "create"]
    update = log[1]
    assert (update["old_value"], update["new_value"]) == ("yes", "no")
    assert update["changed_by"] == db_session._admin.id
    assert update["changed_by_name"]


def test_updated_by_is_stamped_on_the_answer_rows(client, patient, db_session):
    created = client.post(f"{V1}/patient-medical-alerts", json={
        "patient_id": patient.id, "alert_code": "penicillin", "response": "yes"}).json()
    assert created["answered_at"] is not None
    edited = client.patch(f"{V1}/patient-medical-alerts/{created['id']}",
                          json={"response": "no"}).json()
    assert edited["updated_by"] == db_session._admin.id
    assert edited["updated_by_name"]

    q = client.post(f"{V1}/patient-questionnaire-responses", json={
        "patient_id": patient.id, "questionnaire_type": "dental",
        "question_code": "do_you_have_loose_teeth", "answer": "yes"}).json()
    q = client.patch(f"{V1}/patient-questionnaire-responses/{q['id']}",
                     json={"answer": "no"}).json()
    assert q["updated_by"] == db_session._admin.id
    assert q["updated_by_name"]


# ── MH-11: one authoritative emergency contact ───────────────────────────────
def test_emergency_contacts_are_written_to_the_authoritative_table(client, patient):
    body = client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "emergency_contacts": [
            {"name": "Dana Rob", "relationship": "spouse", "phone": "5551234",
             "is_primary": True},
        ],
    }).json()
    assert len(body["emergency_contacts"]) == 1
    listed = client.get(f"{V1}/patient-emergency-contacts",
                        params={"patient_id": patient.id}).json()
    assert listed["items"][0]["name"] == "Dana Rob"


def test_the_medquest_catalog_does_not_duplicate_the_emergency_contact_block(client, patient):
    catalog = client.get(f"{V1}/patients/{patient.id}/medical-history").json()["catalogs"]["medical"]
    labels = " ".join((i["label"] or "").lower() for i in catalog)
    assert "emergency contact" not in labels


# ── MH-9 / MH-10: the patient picker ─────────────────────────────────────────
def _bulk_patients(db_session, n: int = 30) -> None:
    for i in range(n):
        db_session.add(Patient(tenant_id=db_session._tenant_id, first_name="Robert",
                               last_name=f"Aber{i:02d}", chart_no=f"B-{i}", is_active=True))
    db_session.commit()


def test_exact_name_match_outranks_hundreds_of_substring_hits(client, patient, db_session):
    """MH-9: the verified reproduction — 'Rob' returned Robert* surnames paged
    alphabetically and the exact 'Rob' was not in the first fifty rows."""
    _bulk_patients(db_session)
    body = client.get(f"{V1}/patients", params={
        "search": "Rob", "size": 5, "sort": "last_name", "order": "asc"}).json()
    assert body["items"][0]["id"] == patient.id


def test_last_comma_first_is_understood(client, patient, db_session):
    _bulk_patients(db_session)
    body = client.get(f"{V1}/patients", params={"search": "Rob, Leo", "size": 5}).json()
    assert [i["id"] for i in body["items"]] == [patient.id]


def test_chart_no_search_ranks_the_exact_chart_first(client, patient, db_session):
    _bulk_patients(db_session)
    body = client.get(f"{V1}/patients", params={"search": "C-1", "size": 5}).json()
    assert body["items"][0]["id"] == patient.id


def test_phone_filter_matches_the_cell_number(client, patient):
    """MH-10: most patients in this dataset have only a cell number."""
    body = client.get(f"{V1}/patients", params={"phone": "9092221234"}).json()
    assert [i["id"] for i in body["items"]] == [patient.id]


def test_phone_search_finds_the_cell_number(client, patient, db_session):
    _bulk_patients(db_session)
    body = client.get(f"{V1}/patients", params={"search": "9092221234"}).json()
    assert [i["id"] for i in body["items"]] == [patient.id]


# ── MH-15: the printed form ──────────────────────────────────────────────────
def test_medical_history_pdf_renders(client, patient):
    client.put(f"{V1}/patients/{patient.id}/medical-history", json={
        "comments": "Latex only",
        "alerts": [{"alert_code": "penicillin", "alert_label": "Penicillin",
                    "response": "yes"}],
    })
    resp = client.get(f"{V1}/patients/{patient.id}/medical-history/pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


# ── tenancy ──────────────────────────────────────────────────────────────────
def test_a_foreign_patient_is_a_404(client):
    assert client.get(f"{V1}/patients/999999/medical-history").status_code == 404
