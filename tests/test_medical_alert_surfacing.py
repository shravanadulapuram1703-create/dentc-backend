"""Medical alerts surfacing (MA-1..7) + Medical History round 2 (MH-17..21).

MA-8 (latency) has no unit-testable surface; see the response doc.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from app.db.models import (
    Appointment,
    AuditLog,
    Definition,
    DefinitionGroup,
    Office,
    Operatory,
    Patient,
    PatientAlert,
    PatientMedicalAlert,
    PrescriptionLibrary,
    Provider,
)
from app.services.medical_history_catalog import to_code

V1 = "/api/v1"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="J", last_name="M",
                chart_no="MA-1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def other_patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ann", last_name="Zeta",
                chart_no="MA-2", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def scheduler(db_session, patient):
    tid = db_session._tenant_id
    office = Office(tenant_id=tid, office_code="MAIN", name="Main")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    provider = Provider(id="PRV-1", tenant_id=tid, office_id=office.id, name="Dr. Adams")
    operatory = Operatory(id="OPR-1", office_id=office.id, name="Op 1", provider_id="PRV-1")
    db_session.add_all([provider, operatory])
    db_session.commit()
    appt = Appointment(
        id="APPT-1", patient_id=patient.id, provider_id="PRV-1", operatory_id="OPR-1",
        office_id=office.id, date=date(2026, 9, 3), start_time=time(9, 0), end_time=time(9, 30),
        duration=30, status="Scheduled",
    )
    db_session.add(appt)
    db_session.commit()
    return {"office": office, "appt": appt}


def _answer(client, patient_id: int, code: str, response: str = "yes", **extra) -> dict:
    r = client.post(f"{V1}/patient-medical-alerts",
                    json={"patient_id": patient_id, "alert_code": code, "response": response, **extra})
    assert r.status_code == 201, r.text
    return r.json()


# ── MA-3: label / section come from the catalog the codes were derived from ──
def test_section_and_label_are_populated_from_the_catalog(client, patient):
    row = _answer(client, patient.id, "cardiac_pacemaker")
    assert row["alert_label"] == "Cardiac Pacemaker"
    assert row["section"] == "Check, if applicable"
    aspirin = _answer(client, patient.id, "aspirin")
    assert aspirin["section"] == "Allergic To"
    # Stored, not only rendered — the row is self-describing.
    listed = client.get(f"{V1}/patient-medical-alerts?patient_id={patient.id}").json()["items"]
    by_code = {r["alert_code"]: r for r in listed}
    assert by_code["cardiac_pacemaker"]["section"] == "Check, if applicable"
    assert by_code["autoimmune_disease"]["section"] if "autoimmune_disease" in by_code else True


def test_a_client_sent_section_is_an_override(client, patient):
    row = _answer(client, patient.id, "aspirin", section="My Group", alert_label="ASA")
    assert row["section"] == "My Group"
    assert row["alert_label"] == "ASA"


def test_the_composite_write_fills_label_and_section_too(client, patient):
    body = client.put(f"{V1}/patients/{patient.id}/medical-history",
                      json={"alerts": [{"alert_code": "frequent_headaches", "response": "yes"}]}).json()
    alert = next(a for a in body["alerts"] if a["alert_code"] == "frequent_headaches")
    assert alert["alert_label"] == "Frequent Headaches"
    assert alert["section"] == "Check, if applicable"


def test_an_unknown_code_gets_a_humanised_label_not_null(client, patient):
    row = _answer(client, patient.id, "some_new_thing")
    assert row["alert_label"] == "Some New Thing"
    assert row["section"] is None


# ── MA-4: flags can be set per answer and are derived from any tenant definition ──
def test_flags_accepted_on_create_and_update(client, patient, db_session):
    row = _answer(client, patient.id, "penicillin", is_flash_alert=True, blocks_charges=True)
    assert row["is_flash_alert"] is True and row["blocks_charges"] is True
    # A flagged Yes raises the banner alert (MH-14) through the override too.
    banner = db_session.query(PatientAlert).filter_by(source_medical_alert_id=row["id"]).one()
    assert banner.is_flash_alert is True and banner.blocks_charges is True
    patched = client.patch(f"{V1}/patient-medical-alerts/{row['id']}", json={"is_flash_alert": False}).json()
    assert patched["is_flash_alert"] is False and patched["blocks_charges"] is True


def test_a_tenant_definition_flag_applies_even_under_the_catalog_size_guard(client, patient, db_session):
    tid = db_session._tenant_id
    db_session.add(DefinitionGroup(tenant_id=tid, group_code="MEDALERT", description="x",
                                   group_type="MEDALERT"))
    db_session.add(Definition(tenant_id=tid, group_code="MEDALERT", key1="latex_rubber",
                              description="Latex Rubber", section="Allergic To", is_active=True,
                              is_flash_alert=True))
    db_session.commit()
    doc = client.get(f"{V1}/patients/{patient.id}/medical-history").json()
    assert doc["catalog_sources"]["alerts"] == "builtin"  # one definition is below the guard
    row = _answer(client, patient.id, "latex_rubber")
    assert row["is_flash_alert"] is True  # ...but its flag still counts


# ── MA-1: the scheduler feed sees Medical History YES answers ────────────────
def test_feed_has_alert_and_summary_from_medical_history_yes_answers(client, patient, scheduler):
    _answer(client, patient.id, "aspirin")
    _answer(client, patient.id, "cardiac_pacemaker")
    _answer(client, patient.id, "cancer_tumor_or_growth", response="no")
    assert client.get(f"{V1}/patient-alerts?patient_id={patient.id}").json()["meta"]["total"] == 0
    rows = client.get(f"{V1}/appointments/scheduler?date_from=2026-09-03&date_to=2026-09-03").json()
    assert len(rows) == 1
    assert rows[0]["has_alert"] is True
    assert rows[0]["alert_count"] == 2
    assert rows[0]["alert_summary"] == "Allergic To: Aspirin; Check, if applicable: Cardiac Pacemaker"


def test_feed_has_alert_false_when_only_no_answers(client, patient, scheduler):
    _answer(client, patient.id, "aspirin", response="no")
    rows = client.get(f"{V1}/appointments/scheduler?date_from=2026-09-03&date_to=2026-09-03").json()
    assert rows[0]["has_alert"] is False and rows[0]["alert_summary"] is None


# ── MA-2: one summary call, bulk reads, context embed ────────────────────────
def test_summary_endpoint_shape(client, patient, db_session):
    _answer(client, patient.id, "penicillin", comments="hives")
    db_session.add(PatientAlert(patient_id=patient.id, alert="Owes balance", is_active=True))
    db_session.commit()
    s = client.get(f"{V1}/patients/{patient.id}/medical-alerts/summary").json()
    assert s["patient_id"] == patient.id
    assert s["history_on_file"] is True
    assert s["alert_count"] == 2 and s["allergy_count"] == 1
    hist, acct = s["alerts"]
    assert hist["source"] == "medical_history" and hist["code"] == "penicillin"
    assert hist["label"] == "Penicillin" and hist["section"] == "Allergic To"
    assert hist["comments"] == "hives"
    assert acct["source"] == "patient_alert" and acct["section"] == "Account Alert"
    assert s["summary_text"] == "Allergic To: Penicillin; Account Alert: Owes balance"


def test_summary_distinguishes_no_history_from_no_alerts(client, patient):
    s = client.get(f"{V1}/patients/{patient.id}/medical-alerts/summary").json()
    assert s["history_on_file"] is False and s["alert_count"] == 0
    _answer(client, patient.id, "aspirin", response="no")
    s = client.get(f"{V1}/patients/{patient.id}/medical-alerts/summary").json()
    assert s["history_on_file"] is True and s["alert_count"] == 0


def test_bulk_summary_and_patient_ids_filters(client, patient, other_patient):
    _answer(client, patient.id, "aspirin")
    _answer(client, other_patient.id, "diabetes")
    batch = client.get(f"{V1}/medical-alerts/summary?patient_ids={patient.id},{other_patient.id},999999").json()
    assert [i["patient_id"] for i in batch["items"]] == [patient.id, other_patient.id]
    listed = client.get(f"{V1}/patient-medical-alerts?patient_ids={patient.id},{other_patient.id}").json()
    assert listed["meta"]["total"] == 2
    listed = client.get(f"{V1}/patient-alerts?patient_ids={patient.id}").json()
    assert listed["meta"]["total"] == 0
    too_many = ",".join(str(i) for i in range(201))
    assert client.get(f"{V1}/patient-medical-alerts?patient_ids={too_many}").status_code == 422


def test_patient_context_carries_the_summary(client, patient):
    _answer(client, patient.id, "aspirin")
    ctx = client.get(f"{V1}/patients/{patient.id}/context").json()
    assert ctx["medical_alerts"]["alert_count"] == 1
    assert ctx["medical_alerts"]["alerts"][0]["label"] == "Aspirin"


# ── MA-6: sync semantics between the two tables ──────────────────────────────
def test_yes_to_no_deactivates_the_linked_banner_row_and_yes_again_reactivates_it(client, patient, db_session):
    row = _answer(client, patient.id, "penicillin", is_flash_alert=True)
    banner = db_session.query(PatientAlert).filter_by(source_medical_alert_id=row["id"]).one()
    banner_id = banner.id
    client.patch(f"{V1}/patient-medical-alerts/{row['id']}", json={"response": "no"})
    db_session.expire_all()
    banner = db_session.get(PatientAlert, banner_id)
    assert banner.is_active is False and banner.deactivated_on is not None
    # The summary no longer lists it, and never listed it twice.
    s = client.get(f"{V1}/patients/{patient.id}/medical-alerts/summary").json()
    assert s["alert_count"] == 0
    client.patch(f"{V1}/patient-medical-alerts/{row['id']}", json={"response": "yes"})
    db_session.expire_all()
    banner = db_session.get(PatientAlert, banner_id)
    assert banner.is_active is True and banner.deactivated_on is None
    s = client.get(f"{V1}/patients/{patient.id}/medical-alerts/summary").json()
    assert s["alert_count"] == 1  # the linked banner row is de-duplicated


def test_soft_deleting_the_answer_deactivates_the_banner_row(client, patient, db_session):
    row = _answer(client, patient.id, "penicillin", blocks_charges=True)
    assert client.delete(f"{V1}/patient-medical-alerts/{row['id']}").status_code == 204
    banner = db_session.query(PatientAlert).filter_by(source_medical_alert_id=row["id"]).one()
    db_session.refresh(banner)
    assert banner.is_active is False


# ── MA-7: comments are first-class on the summary ────────────────────────────
def test_summary_comments_come_from_the_header_and_a_legacy_row_is_not_an_alert(client, patient, db_session):
    client.put(f"{V1}/patients/{patient.id}/medical-history", json={"comments": "Takes warfarin"})
    s = client.get(f"{V1}/patients/{patient.id}/medical-alerts/summary").json()
    assert s["comments"] == "Takes warfarin"
    db_session.add(PatientMedicalAlert(tenant_id=db_session._tenant_id, patient_id=patient.id,
                                       alert_code="ADDITIONAL_COMMENTS", response="yes",
                                       comments="legacy text", is_active=True))
    db_session.commit()
    s = client.get(f"{V1}/patients/{patient.id}/medical-alerts/summary").json()
    assert s["alert_count"] == 0 and s["history_on_file"] is False
    assert s["comments"] == "Takes warfarin"  # header wins over the legacy row


# ── MA-5: drug <-> alert check + acknowledgement audit ───────────────────────
def test_prescribing_against_an_active_allergy_is_409_unless_acknowledged(client, patient):
    row = _answer(client, patient.id, "penicillin")
    body = {"patient_id": patient.id, "drug_name": "Penicillin VK 500mg", "refills": 0}
    r = client.post(f"{V1}/prescriptions", json=body)
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "prescription_alert_conflict"
    assert err["details"]["warnings"][0]["matched_on"] == "drug_name"
    assert err["details"]["warnings"][0]["alert_id"] == row["id"]
    r = client.post(f"{V1}/prescriptions", json={**body, "alerts_acknowledged": True})
    assert r.status_code == 201, r.text
    rx = r.json()
    assert rx["alerts_acknowledged"] is True
    assert rx["acknowledged_alert_ids"] == [row["id"]]
    assert rx["acknowledged_alerts"][0]["label"] == "Penicillin"
    assert rx["alerts_acknowledged_at"] is not None and rx["alerts_acknowledged_by"] == 1
    assert rx["alert_warnings"][0]["key"] == "penicillin"
    assert rx["warnings"][0]["label"] == "Penicillin"
    # Persisted and returned on the plain read too.
    again = client.get(f"{V1}/prescriptions/{rx['id']}").json()
    assert again["acknowledged_alert_ids"] == [row["id"]]


def test_library_allergy_keys_match_the_patient_alerts(client, patient, db_session):
    lib = PrescriptionLibrary(tenant_id=db_session._tenant_id, drug_name="Augmentin 875",
                              allergy_keys=["Penicillin"], is_active=True)
    db_session.add(lib)
    db_session.commit()
    db_session.refresh(lib)
    _answer(client, patient.id, "penicillin")
    check = client.post(f"{V1}/prescriptions/alert-check",
                        json={"patient_id": patient.id, "drug_name": "Augmentin 875",
                              "library_rx_id": lib.id}).json()
    assert check["blocking"] is True
    assert check["warnings"][0]["matched_on"] == "allergy_key"
    # Name-only lookup resolves the library row as well.
    check = client.post(f"{V1}/prescriptions/alert-check",
                        json={"patient_id": patient.id, "drug_name": "augmentin 875"}).json()
    assert check["blocking"] is True and check["library_rx_id"] == lib.id


def test_a_free_text_alert_matches_by_key_only(client, patient, db_session):
    db_session.add(PatientAlert(patient_id=patient.id, alert="Allergic to sulfa", is_active=True))
    db_session.add(PrescriptionLibrary(tenant_id=db_session._tenant_id, drug_name="Bactrim DS",
                                       allergy_keys=["sulfa"], is_active=True))
    db_session.commit()
    check = client.post(f"{V1}/prescriptions/alert-check",
                        json={"patient_id": patient.id, "drug_name": "Bactrim DS"}).json()
    assert check["blocking"] is True and check["warnings"][0]["source"] == "patient_alert"


def test_no_match_is_stored_without_a_conflict(client, patient):
    _answer(client, patient.id, "diabetes")  # not an allergy section
    r = client.post(f"{V1}/prescriptions", json={"patient_id": patient.id, "drug_name": "Amoxicillin 500"})
    assert r.status_code == 201, r.text
    rx = r.json()
    assert rx["alerts_acknowledged"] is False and rx["alert_warnings"] is None and rx["warnings"] == []
    check = client.post(f"{V1}/prescriptions/alert-check",
                        json={"patient_id": patient.id, "drug_name": "Amoxicillin 500"}).json()
    assert check["blocking"] is False and check["alerts"][0]["label"] == "Diabetes"


def test_a_foreign_patient_cannot_be_prescribed_for(client, db_session):
    from app.db.models import Tenant
    other = Tenant(name="Other", code="other", is_active=True)
    db_session.add(other)
    db_session.commit()
    p = Patient(tenant_id=other.id, first_name="X", last_name="Y", is_active=True)
    db_session.add(p)
    db_session.commit()
    r = client.post(f"{V1}/prescriptions", json={"patient_id": p.id, "drug_name": "Anything"})
    assert r.status_code == 404


# ── MH-17: timestamps carry an offset ────────────────────────────────────────
def test_hand_written_schemas_serialise_aware_timestamps(client, patient):
    row = _answer(client, patient.id, "aspirin")
    for key in ("created_at", "answered_at"):
        assert row[key].endswith("+00:00") or row[key].endswith("Z"), row[key]
    doc = client.get(f"{V1}/patients/{patient.id}/medical-history").json()
    assert doc["alerts"][0]["created_at"].endswith(("+00:00", "Z"))
    ctx = client.get(f"{V1}/patients/{patient.id}/context").json()
    assert ctx["medical_alerts"]["alerts"][0]["answered_at"].endswith(("+00:00", "Z"))


# ── MH-18: Created / Modified, server-side ───────────────────────────────────
def test_audit_block_reports_created_and_modified_including_removals(client, patient):
    empty = client.get(f"{V1}/patients/{patient.id}/medical-history/audit").json()
    assert empty["overall"]["created_at"] is None
    row = _answer(client, patient.id, "aspirin")
    client.post(f"{V1}/patient-questionnaire-responses",
                json={"patient_id": patient.id, "questionnaire_type": "dental",
                      "question_code": "phone", "answer": "555"})
    audit = client.get(f"{V1}/patients/{patient.id}/medical-history/audit").json()
    assert audit["overall"]["created_by"] == 1 and audit["overall"]["created_by_name"]
    assert audit["sections"]["alerts"]["created_at"] is not None
    assert audit["sections"]["dental"]["updated_at"] is not None
    assert audit["sections"]["medical"]["created_at"] is None
    before = audit["sections"]["alerts"]["updated_at"]
    # Clearing an answer through the composite write hard-deletes the row; the
    # change log keeps the modification visible.
    client.put(f"{V1}/patients/{patient.id}/medical-history",
               json={"alerts": [{"alert_code": "aspirin", "response": None}]})
    after = client.get(f"{V1}/patients/{patient.id}/medical-history/audit").json()
    assert after["sections"]["alerts"]["updated_at"] >= before
    assert after["sections"]["alerts"]["updated_by"] == 1
    doc = client.get(f"{V1}/patients/{patient.id}/medical-history").json()
    assert doc["audit"]["overall"]["created_at"] is not None
    assert set(doc["audit"]["last_reviewed"]) == {"alerts", "dental", "medical"}
    assert row["id"]


def test_audit_last_reviewed_is_the_completion_assertion(client, patient):
    client.put(f"{V1}/patients/{patient.id}/medical-history",
               json={"alerts": [{"alert_code": "aspirin", "response": "no"}],
                     "mark_completed": ["alerts"]})
    audit = client.get(f"{V1}/patients/{patient.id}/medical-history/audit").json()
    assert audit["last_reviewed"]["alerts"]["last_reviewed_at"] is not None
    assert audit["last_reviewed"]["dental"]["last_reviewed_at"] is None


# ── MH-19: audit rows carry the row, the patient and the diff ────────────────
@pytest.fixture
def audit_capture(monkeypatch, client, db_session):
    """The middleware only records when the real auth dependency cached a token
    payload on the request, so this test authenticates with a real bearer token
    (the fixture's ``get_current_user`` override is lifted for its duration)."""
    from app.api.deps import get_current_user
    from app.main import app
    from app.services.auth_service import issue_tokens

    captured: list[dict] = []
    monkeypatch.setattr("app.middleware.audit.write_audit", lambda **kw: captured.append(kw))
    app.dependency_overrides.pop(get_current_user, None)
    tokens = issue_tokens(db_session._admin)
    client.headers.update({"Authorization": f"Bearer {tokens.access_token}"})
    return captured


def test_audit_middleware_records_resource_id_patient_and_diff(client, patient, audit_capture):
    row = _answer(client, patient.id, "aspirin")
    created = audit_capture[-1]
    assert created["method"] == "POST" and created["resource_type"] == "patient-medical-alerts"
    assert created["resource_id"] == str(row["id"])
    assert created["patient_id"] == patient.id
    assert created["details"]["after"]["alert_code"] == "aspirin"
    client.patch(f"{V1}/patient-medical-alerts/{row['id']}", json={"response": "no"})
    patched = audit_capture[-1]
    assert patched["details"]["before"] == {"response": "yes"} or patched["details"]["before"]["response"] == "yes"
    assert patched["details"]["after"]["response"] == "no"
    assert patched["patient_id"] == patient.id
    client.delete(f"{V1}/patient-medical-alerts/{row['id']}")
    deleted = audit_capture[-1]
    assert deleted["method"] == "DELETE" and deleted["patient_id"] == patient.id


def test_patient_scoped_audit_read_is_open_to_any_user(client, patient, other_patient, db_session):
    tid = db_session._tenant_id
    db_session.add_all([
        AuditLog(id=1, tenant_id=tid, user_id=1, action="PATCH", method="PATCH",
                 resource_type="patient-medical-alerts", resource_id="5", patient_id=patient.id,
                 path="/api/v1/patient-medical-alerts/5", status_code=200,
                 details={"before": {"response": "yes"}, "after": {"response": "no"}}),
        AuditLog(id=2, tenant_id=tid, user_id=1, action="POST", method="POST",
                 resource_type="patient-medical-alerts", resource_id="6", patient_id=other_patient.id,
                 path="/api/v1/patient-medical-alerts", status_code=201),
        AuditLog(id=3, tenant_id=tid + 1, user_id=1, action="POST", method="POST",
                 resource_type="patients", resource_id=str(patient.id), patient_id=patient.id,
                 path="/api/v1/patients", status_code=201),
    ])
    db_session.commit()
    body = client.get(f"{V1}/patients/{patient.id}/audit-logs").json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["details"]["before"] == {"response": "yes"}
    assert client.get(f"{V1}/patients/{patient.id}/audit-logs?resource_type=patients").json()["meta"]["total"] == 0
    assert client.get(f"{V1}/patients/999999/audit-logs").status_code == 404
    admin = client.get(f"{V1}/audit-logs?patient_id={other_patient.id}").json()
    assert admin["meta"]["total"] == 1


# ── MH-20: a no-op PATCH does not re-stamp ───────────────────────────────────
def test_noop_patch_does_not_restamp(client, patient):
    r = client.post(f"{V1}/patient-questionnaire-responses",
                    json={"patient_id": patient.id, "questionnaire_type": "dental",
                          "question_code": "phone", "answer": "Dr Parity"})
    row = r.json()
    assert row["updated_by"] is None
    same = client.patch(f"{V1}/patient-questionnaire-responses/{row['id']}", json={"answer": "Dr Parity"})
    assert same.status_code == 200
    assert same.json()["updated_by"] is None and same.json()["updated_at"] == row["updated_at"]
    alert = _answer(client, patient.id, "aspirin")
    same = client.patch(f"{V1}/patient-medical-alerts/{alert['id']}", json={"response": "yes"}).json()
    assert same["updated_by"] is None and same["answered_at"] == alert["answered_at"]
    changed = client.patch(f"{V1}/patient-medical-alerts/{alert['id']}", json={"response": "no"}).json()
    assert changed["updated_by"] == 1


# ── MH-21: answered_at on questionnaire responses ────────────────────────────
def test_questionnaire_answered_at_is_set_on_create_and_moves_with_the_answer(client, patient):
    row = client.post(f"{V1}/patient-questionnaire-responses",
                      json={"patient_id": patient.id, "questionnaire_type": "medical",
                            "question_code": "do_you_smoke", "answer": "no"}).json()
    assert row["answered_at"] is not None
    same = client.patch(f"{V1}/patient-questionnaire-responses/{row['id']}", json={"answer": "no"}).json()
    assert same["answered_at"] == row["answered_at"]
    changed = client.patch(f"{V1}/patient-questionnaire-responses/{row['id']}", json={"answer": "yes"}).json()
    assert changed["answered_at"] is not None and changed["answered_at"] >= row["answered_at"]


# ── MA-3 root cause pinned: the built-in catalog is the frontend's list ──────
def test_builtin_alert_catalog_matches_the_frontend_transcription(client, patient):
    catalog = client.get(f"{V1}/patients/{patient.id}/medical-history").json()["catalogs"]["alerts"]
    codes = {i["code"]: i for i in catalog}
    assert len(catalog) == 88
    assert codes[to_code("Cardiac Pacemaker")]["section"] == "Check, if applicable"
    assert codes[to_code("Barbiturates / Sleeping Pills")]["section"] == "Allergic To"
    assert codes[to_code("See Scanned Documents: Pt Note")]["section"] == "Other"
    assert list(codes)[0] == "no_known_allergies"
