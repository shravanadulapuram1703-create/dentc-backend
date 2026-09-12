"""Add New Patient — full-wizard gaps (GAP-AP-19..26).

Reports: ``docs/patients/add_patient_backend_devreport.md`` (GAP-AP-19) and
``docs/patients/add_patient_full_wizard_backend_issues.md`` (GAP-AP-20..26).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import DataError, IntegrityError

from app.core.exceptions import app_error_from_db
from app.db.models import Definition, InsuranceCarrier, InsurancePlan, Patient
from app.services.medical_history_catalog import CODE_MAX_LENGTH, to_code
from app.services.patient_extra_service import is_synthetic_identifier

PREFIX = "/api/v1"
LONG_LABEL = "Do you have difficulty in opening your mouth widely or moving your jaw"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ada", last_name="Byron",
                chart_no="CH-WZ1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def plans(db_session):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Acme", is_active=True)
    db_session.add(carrier)
    db_session.commit()
    dental = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id, is_active=True)
    medical = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id, is_active=True)
    db_session.add_all([dental, medical])
    db_session.commit()
    return dental, medical


def _register(client, body):
    return client.post(f"{PREFIX}/patients/register", json=body)


# ── GAP-AP-19: middle name ───────────────────────────────────────────────────
def test_middle_name_persists_and_derives_initial(client):
    r = client.post(f"{PREFIX}/patients",
                    json={"first_name": "Grace", "last_name": "Hopper", "middle_name": "Brewster"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["middle_name"] == "Brewster" and body["middle_initial"] == "B"

    # An explicit initial always wins over the derivation.
    r = client.patch(f"{PREFIX}/patients/{body['id']}",
                     json={"middle_name": "Bartholomew", "middle_initial": "X"})
    assert r.status_code == 200, r.text
    assert r.json()["middle_initial"] == "X"

    # Clearing the name clears a *derived* initial, keeps a hand-typed one.
    r = client.patch(f"{PREFIX}/patients/{body['id']}", json={"middle_name": None})
    assert r.json()["middle_initial"] == "X"


def test_middle_name_overflow_is_422_not_500(client):
    r = client.post(f"{PREFIX}/patients",
                    json={"first_name": "A", "last_name": "B", "middle_name": "x" * 51})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert any(e["loc"][-1] == "middle_name" for e in r.json()["error"]["details"])
    r = client.post(f"{PREFIX}/patients",
                    json={"first_name": "A", "last_name": "B", "middle_initial": "Bartholomew"})
    assert r.status_code == 422, r.text


def test_guarantor_middle_name_on_register(client):
    r = _register(client, {
        "patient": {"first_name": "Kid", "last_name": "Byron"},
        "responsible_party": {"relationship": "parent",
                              "person": {"first_name": "Anne", "middle_name": "Isabella",
                                         "last_name": "Byron"}},
    })
    assert r.status_code == 201, r.text
    rp = client.get(f"{PREFIX}/responsible-parties/{r.json()['responsible_party_id']}").json()
    assert rp["middle_name"] == "Isabella" and rp["middle_initial"] == "I"


# ── GAP-AP-20: catalog code length ───────────────────────────────────────────
def test_derivation_cap_matches_frontend():
    """The 12 long legacy questions slug past 50; the cap is part of the key."""
    assert CODE_MAX_LENGTH == 50
    code = to_code(LONG_LABEL)
    assert len(code) == 50 and code == "do_you_have_difficulty_in_opening_your_mouth_widel"


def test_long_question_code_saves_and_overflow_is_422(client, patient):
    long_code = "do_you_have_difficulty_in_opening_your_mouth_widely_or_moving"  # 61 chars
    assert len(long_code) > 50
    r = client.post(f"{PREFIX}/patient-questionnaire-responses",
                    json={"patient_id": patient.id, "questionnaire_type": "dental",
                          "question_code": long_code, "answer": "yes"})
    assert r.status_code == 201, r.text
    r = client.post(f"{PREFIX}/patient-questionnaire-responses",
                    json={"patient_id": patient.id, "questionnaire_type": "dental",
                          "question_code": "q" * 101, "answer": "yes"})
    assert r.status_code == 422, r.text
    assert any(e["loc"][-1] == "question_code" for e in r.json()["error"]["details"])
    r = client.post(f"{PREFIX}/patient-medical-alerts",
                    json={"patient_id": patient.id, "alert_code": "a" * 101, "response": "yes"})
    assert r.status_code == 422, r.text


def test_register_overflow_is_422_and_creates_nothing(client):
    before = client.get(f"{PREFIX}/patients").json()["meta"]["total"]
    r = _register(client, {
        "patient": {"first_name": "Over", "last_name": "Flow"},
        "questionnaire_responses": [
            {"questionnaire_type": "dental", "question_code": "q" * 101, "answer": "yes"}
        ],
    })
    assert r.status_code == 422, r.text
    loc = [e["loc"] for e in r.json()["error"]["details"]][0]
    assert "questionnaire_responses" in loc and "question_code" in loc
    assert client.get(f"{PREFIX}/patients").json()["meta"]["total"] == before


def test_rules_publish_both_lengths(client):
    rules = client.get(f"{PREFIX}/metadata/medical-history-rules").json()
    assert rules["code_convention"]["max_length"] == 50
    assert rules["code_convention"]["storage_max_length"] == 100


# ── GAP-AP-21: duplicate guard on POST /patients + synthetic identifiers ─────
@pytest.fixture
def existing(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Maria", last_name="Delgado",
                dob=date(1984, 3, 11), phone="555-240-8891", ssn="123-45-6789",
                chart_no="123456", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.mark.parametrize("value,synthetic", [
    ("123456789", True), ("123-45-6789", True), ("000-00-0000", True), ("111111111", True),
    ("123456", True), ("078-05-1120", True), ("666-12-3456", True), ("", True),
    ("222-33-4444", False), ("CH-DUP1", False), ("847213", False),
])
def test_synthetic_identifier_detection(value, synthetic):
    assert is_synthetic_identifier(value) is synthetic


def test_plain_create_is_guarded_like_register(client, existing):
    body = {"first_name": "Maria", "last_name": "Delgado", "dob": "1984-03-11",
            "phone": "555-240-8891"}
    r = client.post(f"{PREFIX}/patients", json=body)
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "duplicate_patient"
    assert err["details"]["override_field"] == "force_create"
    assert [c["id"] for c in err["details"]["candidates"]] == [existing.id]

    r = client.post(f"{PREFIX}/patients", json={**body, "force_create": True})
    assert r.status_code == 201, r.text
    assert r.json()["id"] != existing.id
    assert "force_create" not in r.json()


def test_shared_placeholder_ssn_and_chart_do_not_block(client, existing):
    """The dev-DB placeholder SSN 123456789 / chart 123456 blocked every registration."""
    # (chart "1234" rather than the fixture's "123456": SQLite enforces the
    # model's unique on chart_no, which the migrated Postgres table does not.)
    r = _register(client, {"patient": {"first_name": "Tomas", "last_name": "Reyes",
                                       "ssn": "123-45-6789", "chart_no": "1234"}})
    assert r.status_code == 201, r.text
    r = client.post(f"{PREFIX}/patients/check-duplicate",
                    json={"first_name": "Tomas", "last_name": "Reyes", "ssn": "123456789"})
    assert existing.id not in [c["id"] for c in r.json()["candidates"]]


def test_chart_no_plus_dob_is_strong(client, db_session):
    p = Patient(tenant_id=db_session._tenant_id, first_name="Lee", last_name="Park",
                dob=date(1990, 5, 5), chart_no="847213", is_active=True)
    db_session.add(p)
    db_session.commit()
    r = _register(client, {"patient": {"first_name": "Li", "last_name": "Parc",
                                       "dob": "1990-05-05", "chart_no": "847213"}})
    assert r.status_code == 409, r.text


# ── GAP-AP-22: bulk endpoints ────────────────────────────────────────────────
def test_bulk_alerts_upsert_counts_and_rules(client, patient):
    items = [{"alert_code": to_code("Penicillin"), "response": "yes", "comments": "rash"},
             {"alert_code": to_code("Latex Rubber"), "response": "no"}]
    r = client.post(f"{PREFIX}/patient-medical-alerts/bulk",
                    json={"patient_id": patient.id, "items": items})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["created"], body["updated"], body["unchanged"]) == (2, 0, 0)
    assert [i["alert_code"] for i in body["items"]] == [i["alert_code"] for i in items]
    # MA-3: label/section filled from the catalog on the bulk path too.
    assert body["items"][0]["alert_label"] == "Penicillin"
    assert body["items"][0]["section"] == "Allergic To"

    # Second call: one update, one unchanged, one new — no duplicate rows.
    r = client.post(f"{PREFIX}/patient-medical-alerts/bulk", json={
        "patient_id": patient.id,
        "items": [
            {"alert_code": to_code("Penicillin"), "response": "no"},
            {"alert_code": to_code("Latex Rubber"), "response": "no"},
            {"alert_code": to_code("Aspirin"), "response": "yes"},
        ],
    })
    body = r.json()
    assert (body["created"], body["updated"], body["unchanged"]) == (1, 1, 1)
    listed = client.get(f"{PREFIX}/patient-medical-alerts?patient_id={patient.id}").json()
    assert listed["meta"]["total"] == 3

    # MH-12 holds on the bulk path: No Known Allergies = yes with Aspirin = yes.
    r = client.post(f"{PREFIX}/patient-medical-alerts/bulk", json={
        "patient_id": patient.id,
        "items": [{"alert_code": to_code("No Known Allergies"), "response": "yes"}],
    })
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "contradictory_medical_alerts"

    # replace=true clears everything the payload omits.
    r = client.post(f"{PREFIX}/patient-medical-alerts/bulk", json={
        "patient_id": patient.id, "replace": True,
        "items": [{"alert_code": to_code("Aspirin"), "response": "yes"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 2
    listed = client.get(f"{PREFIX}/patient-medical-alerts?patient_id={patient.id}").json()
    assert listed["meta"]["total"] == 1


def test_bulk_alerts_is_atomic_on_contradiction(client, patient):
    r = client.post(f"{PREFIX}/patient-medical-alerts/bulk", json={
        "patient_id": patient.id,
        "items": [{"alert_code": to_code("Latex Rubber"), "response": "yes"},
                  {"alert_code": to_code("No Known Allergies"), "response": "yes"},
                  {"alert_code": to_code("Penicillin"), "response": "yes"}],
    })
    assert r.status_code == 422, r.text
    assert client.get(f"{PREFIX}/patient-medical-alerts?patient_id={patient.id}").json()["meta"]["total"] == 0


def test_bulk_questionnaire_responses(client, patient):
    r = client.post(f"{PREFIX}/patient-questionnaire-responses/bulk", json={
        "patient_id": patient.id,
        "items": [
            {"questionnaire_type": "dental", "question_code": to_code(LONG_LABEL), "answer": "yes"},
            {"questionnaire_type": "Medical", "question_code": "m1", "answer": "no"},
        ],
    })
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2
    assert r.json()["items"][1]["questionnaire_type"] == "medical"

    # Reset one to Not Answered (null answer) and touch nothing else.
    r = client.post(f"{PREFIX}/patient-questionnaire-responses/bulk", json={
        "patient_id": patient.id,
        "items": [{"questionnaire_type": "dental", "question_code": to_code(LONG_LABEL), "answer": None}],
    })
    assert r.json()["deleted"] == 1
    listed = client.get(f"{PREFIX}/patient-questionnaire-responses?patient_id={patient.id}").json()
    assert listed["meta"]["total"] == 1 and listed["items"][0]["question_code"] == "m1"

    r = client.post(f"{PREFIX}/patient-questionnaire-responses/bulk", json={
        "patient_id": patient.id,
        "items": [{"questionnaire_type": "other", "question_code": "x", "answer": "y"}],
    })
    assert r.status_code == 422, r.text


def test_bulk_on_foreign_patient_is_404(client, db_session):
    other = Patient(tenant_id=db_session._tenant_id + 999, first_name="X", last_name="Y")
    db_session.add(other)
    db_session.commit()
    r = client.post(f"{PREFIX}/patient-medical-alerts/bulk",
                    json={"patient_id": other.id, "items": [{"alert_code": "a", "response": "yes"}]})
    assert r.status_code == 404


# ── GAP-AP-23/24: recalls + insurance ride the composite ─────────────────────
def test_register_recall_carries_leg8_columns(client):
    r = _register(client, {
        "patient": {"first_name": "Rec", "last_name": "All"},
        "recalls": [{"recall_type": "prophy", "interval_months": 12, "interval_unit": "year",
                     "scheduled_date": "2027-03-01", "scheduled_time": "09:30"}],
    })
    assert r.status_code == 201, r.text
    recall = client.get(f"{PREFIX}/patient-recalls/{r.json()['recall_ids'][0]}").json()
    assert (recall["interval_unit"], recall["scheduled_date"], recall["scheduled_time"]) == \
        ("year", "2027-03-01", "09:30")


def test_register_insurance_in_one_transaction(client, plans):
    dental, medical = plans
    r = _register(client, {
        "patient": {"first_name": "Ins", "last_name": "Ured", "dob": "1980-01-01"},
        "insurance": [
            # Payload order is secondary-first on purpose: the rank rule must
            # judge the set, not the serialisation order.
            {"subscriber": {"ins_plan_id": dental.id, "sub_first_name": "Ins", "sub_last_name": "Ured"},
             "subscriber_is_patient": True,
             "link": {"legacy_plan_type": "D", "insurance_type": "secondary", "relationship": "S"}},
            {"subscriber": {"ins_plan_id": dental.id, "sub_first_name": "Ins", "sub_last_name": "Ured",
                            "sub_phone": "555-1111", "marital_status": "M"},
             "subscriber_is_patient": True,
             "link": {"legacy_plan_type": "D", "insurance_type": "primary", "relationship": "S",
                      "deductible_remaining": 50}},
            {"subscriber": {"ins_plan_id": medical.id, "sub_first_name": "Spouse", "sub_last_name": "Ured"},
             "link": {"legacy_plan_type": "M", "insurance_type": "primary", "relationship": "SP"}},
        ],
    })
    assert r.status_code == 201, r.text
    out = r.json()
    pid = out["patient_id"]
    assert [s["insurance_type"] for s in out["insurance"]] == ["secondary", "primary", "primary"]
    assert [s["legacy_plan_type"] for s in out["insurance"]] == ["D", "D", "M"]

    sub = client.get(f"{PREFIX}/insurance-subscribers/{out['insurance'][1]['subscriber_id']}").json()
    assert sub["subscriber_patient_id"] == pid and sub["sub_phone"] == "555-1111"
    sub_m = client.get(f"{PREFIX}/insurance-subscribers/{out['insurance'][2]['subscriber_id']}").json()
    assert sub_m["subscriber_patient_id"] is None
    link = client.get(f"{PREFIX}/patient-insurance/{out['insurance'][1]['patient_insurance_id']}").json()
    assert link["patient_id"] == pid and link["ins_plan_id"] == dental.id
    assert float(link["deductible_remaining"]) == 50.0

    # Reuse an existing subscriber (a dependent on the guarantor's plan).
    r = _register(client, {
        "patient": {"first_name": "Dep", "last_name": "Ured"},
        "insurance": [{"subscriber_id": out["insurance"][1]["subscriber_id"],
                       "link": {"legacy_plan_type": "D", "insurance_type": "primary",
                                "relationship": "C"}}],
    })
    assert r.status_code == 201, r.text
    assert r.json()["insurance"][0]["subscriber_id"] == out["insurance"][1]["subscriber_id"]


def test_register_insurance_failure_rolls_everything_back(client, plans):
    dental, _ = plans
    before = client.get(f"{PREFIX}/patients").json()["meta"]["total"]
    subs_before = client.get(f"{PREFIX}/insurance-subscribers").json()["meta"]["total"]
    r = _register(client, {
        "patient": {"first_name": "Orphan", "last_name": "Sub"},
        "medical_alerts": [{"alert_code": to_code("Latex Rubber"), "response": "Yes"}],
        "insurance": [{"subscriber": {"ins_plan_id": dental.id},
                       "link": {"legacy_plan_type": "D", "insurance_type": "secondary"}}],
    })
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "missing_primary_coverage" and err["details"]["index"] == 0
    assert client.get(f"{PREFIX}/patients").json()["meta"]["total"] == before
    assert client.get(f"{PREFIX}/insurance-subscribers").json()["meta"]["total"] == subs_before

    r = _register(client, {
        "patient": {"first_name": "No", "last_name": "Plan"},
        "insurance": [{"subscriber": {"ins_plan_id": 999999},
                       "link": {"legacy_plan_type": "D", "insurance_type": "primary"}}],
    })
    assert r.status_code == 422 and r.json()["error"]["code"] == "insurance_plan_not_found"

    r = _register(client, {
        "patient": {"first_name": "Two", "last_name": "Subs"},
        "insurance": [{"subscriber": {"ins_plan_id": dental.id}, "subscriber_id": 1,
                       "link": {"insurance_type": "primary"}}],
    })
    assert r.status_code == 422


def test_register_alerts_go_through_medical_history_rules(client):
    """Registration used to write bare rows; it now runs MH-12/MA-3/MH-8."""
    r = _register(client, {
        "patient": {"first_name": "Rule", "last_name": "Bound"},
        "medical_alerts": [{"alert_code": to_code("No Known Allergies"), "response": "YES"},
                           {"alert_code": to_code("Penicillin"), "response": "yes"}],
    })
    assert r.status_code == 422 and r.json()["error"]["code"] == "contradictory_medical_alerts"

    r = _register(client, {
        "patient": {"first_name": "Rule", "last_name": "Bound"},
        "medical_alerts": [{"alert_code": to_code("Penicillin"), "response": "Yes"}],
        "questionnaire_responses": [{"questionnaire_type": "Dental", "question_code": "d1", "answer": "y"}],
    })
    assert r.status_code == 201, r.text
    pid = r.json()["patient_id"]
    doc = client.get(f"{PREFIX}/patients/{pid}/medical-history").json()
    answered = {a["alert_code"]: a for a in doc["alerts"] if a.get("response")}
    assert answered[to_code("Penicillin")]["response"] == "yes"
    assert answered[to_code("Penicillin")]["section"] == "Allergic To"
    log = client.get(f"{PREFIX}/patients/{pid}/medical-history/changes").json()
    assert any(c["action"] == "create" and c["code"] == to_code("Penicillin") for c in log)

    r = _register(client, {
        "patient": {"first_name": "Bad", "last_name": "Answer"},
        "medical_alerts": [{"alert_code": "x", "response": "maybe"}],
    })
    assert r.status_code == 422


# ── GAP-AP-25: one relationship vocabulary ───────────────────────────────────
@pytest.mark.parametrize("sent,stored", [
    ("spouse", "SP"), ("Spouse", "SP"), ("SP", "SP"), ("sp", "SP"), ("Dependent", "D"),
    ("self", "S"), ("cousin", "cousin"),
])
def test_relationship_folds_to_code(client, sent, stored):
    r = client.post(f"{PREFIX}/patients", json={"first_name": "R", "last_name": "L",
                                                "responsible_party_relationship": sent})
    assert r.status_code == 201, r.text
    assert r.json()["responsible_party_relationship"] == stored


def test_register_self_relationship_is_code(client):
    r = _register(client, {"patient": {"first_name": "Me", "last_name": "Self"},
                           "responsible_party": {"is_self": True}})
    pid = r.json()["patient_id"]
    assert client.get(f"{PREFIX}/patients/{pid}").json()["responsible_party_relationship"] == "S"


def test_flag_rules_publish_relationship_vocabulary(client):
    rules = client.get(f"{PREFIX}/metadata/patient-flag-rules").json()
    rel = rules["responsible_party_relationship"]
    assert rel["canonical"] == "key1" and rel["self_code"] == "S"
    assert [c["code"] for c in rel["codes"]] == ["S", "SP", "P", "G", "C", "D", "O"]


def test_seeder_emits_one_set_and_retires_the_other(db_session):
    from scripts.seed_account_definitions import GROUPS, seed_for_tenant

    tid = db_session._tenant_id
    db_session.add(Definition(tenant_id=tid, group_code="resp_party_rel", key1="spouse",
                              description="Spouse", is_active=True))
    db_session.commit()
    assert [k for k, _ in GROUPS["resp_party_rel"]] == ["S", "SP", "P", "G", "C", "D", "O"]
    seed_for_tenant(db_session, tid)
    rows = {d.key1: d.is_active for d in db_session.query(Definition).filter_by(
        tenant_id=tid, group_code="resp_party_rel")}
    assert rows["spouse"] is False and rows["SP"] is True


# ── GAP-AP-26: database errors are diagnosable ───────────────────────────────
class _Diag:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _PgError(Exception):
    def __init__(self, pgcode, message, **diag):
        super().__init__(message)
        self.pgcode = pgcode
        self.diag = _Diag(**diag)


def _wrap(cls, orig):
    return cls("stmt", {}, orig)


def test_value_too_long_maps_to_422_with_max_length():
    err = app_error_from_db(_wrap(DataError, _PgError(
        "22001", "value too long for type character varying(50)\n", table_name="patient_questionnaire_responses")))
    assert err.status_code == 422 and err.code == "value_too_long"
    assert err.details["max_length"] == 50 and err.details["sqlstate"] == "22001"
    assert err.details["table"] == "patient_questionnaire_responses"


def test_unique_violation_maps_to_409_with_columns():
    err = app_error_from_db(_wrap(IntegrityError, _PgError(
        "23505", 'duplicate key value violates unique constraint "patients_chart_no_key"',
        constraint_name="patients_chart_no_key", table_name="patients",
        message_detail="Key (chart_no)=(123456) already exists.")), resource="patient")
    assert err.status_code == 409 and err.code == "constraint"
    assert err.details["constraint"] == "patients_chart_no_key"
    assert err.details["columns"] == ["chart_no"] and err.details["values"] == ["123456"]
    assert err.message.startswith("patient: ")


def test_foreign_key_and_not_null_map_to_422():
    fk = app_error_from_db(_wrap(IntegrityError, _PgError(
        "23503", "insert or update violates foreign key constraint",
        constraint_name="patients_preferred_provider_id_fkey",
        message_detail='Key (preferred_provider_id)=(PRV-9) is not present in table "providers".')))
    assert fk.status_code == 422 and fk.code == "foreign_key_violation"
    assert fk.details["columns"] == ["preferred_provider_id"]
    nn = app_error_from_db(_wrap(IntegrityError, _PgError(
        "23502", "null value in column \"last_name\"", column_name="last_name", table_name="patients")))
    assert nn.status_code == 422 and nn.code == "not_null_violation"
    assert nn.details["column"] == "last_name"


def test_sqlite_messages_are_classified_too():
    class _Sqlite(Exception):
        pass

    err = app_error_from_db(_wrap(IntegrityError, _Sqlite("UNIQUE constraint failed: patients.chart_no")))
    assert err.status_code == 409 and err.details["columns"] == ["chart_no"]
    assert err.details["table"] == "patients"
    err = app_error_from_db(_wrap(IntegrityError, _Sqlite("NOT NULL constraint failed: users.email")))
    assert err.status_code == 422 and err.code == "not_null_violation"


def test_unique_collision_over_http_is_409_constraint(client):
    """End to end: the CRUD commit and the register commit both land on the mapping."""
    assert client.post(f"{PREFIX}/patients",
                       json={"first_name": "A", "last_name": "B", "chart_no": "CN-77"}).status_code == 201
    r = client.post(f"{PREFIX}/patients", json={"first_name": "C", "last_name": "D", "chart_no": "CN-77"})
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "constraint" and err["details"]["kind"] == "unique"
    assert "chart_no" in err["details"]["columns"]

    r = _register(client, {"patient": {"first_name": "E", "last_name": "F", "chart_no": "CN-77"}})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "constraint"


def test_internal_error_carries_request_id(client, monkeypatch):
    from app.services import patient_intake_service

    def boom(*_a, **_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(patient_intake_service, "get_opening_balance", boom)
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"{PREFIX}/patients/1/opening-balance")
    assert r.status_code == 500
    body = r.json()["error"]
    assert body["code"] == "internal_error" and body["details"]["request_id"]
