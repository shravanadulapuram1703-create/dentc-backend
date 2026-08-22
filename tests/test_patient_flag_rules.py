"""Add/Edit Patient checkbox-integrity rules.

The three checkbox panels (Patient Status / Coverage Type / Patient Type) let
every box be ticked independently, so a patient could be saved as both a Child
and a Senior Citizen, or flagged No Correspondence while automated e-mail and
SMS stayed on. These pin the rules on every write path — generic create/PATCH,
the atomic register endpoint, and the coverage slots.
"""

from __future__ import annotations

import pytest

from app.db.models import InsuranceCarrier, InsurancePlan, Patient

PREFIX = "/api/v1"


@pytest.fixture
def patient(db_session):
    row = Patient(tenant_id=db_session._tenant_id, first_name="Rin", last_name="Okabe")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture
def plan(db_session):
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Delta", is_active=True)
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    row = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id, is_active=True)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


# ── Patient Type: mutually exclusive tags ────────────────────────────────────
def test_child_and_senior_cannot_both_be_selected_on_create(client):
    r = client.post(f"{PREFIX}/patients", json={
        "first_name": "Contra", "last_name": "Diction",
        "patient_types": ["CH", "OR", "SR"],
    })
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "conflicting_patient_types"
    assert err["details"]["conflict"] == ["CH", "SR"]
    # The message names both, so the form can point at the right two boxes.
    assert "Child" in err["message"] and "Senior Citizen" in err["message"]


def test_child_and_senior_cannot_both_be_selected_on_patch(client, patient):
    assert client.patch(f"{PREFIX}/patients/{patient.id}",
                        json={"patient_types": ["CH"]}).status_code == 200
    r = client.patch(f"{PREFIX}/patients/{patient.id}", json={"patient_types": ["CH", "SR"]})
    assert r.status_code == 422
    # The rejected write left the stored value alone.
    assert client.get(f"{PREFIX}/patients/{patient.id}").json()["patient_types"] == ["CH"]


def test_child_and_senior_rejected_on_register(client):
    r = client.post(f"{PREFIX}/patients/register", json={
        "patient": {"first_name": "Reg", "last_name": "Conflict",
                    "patient_types": ["SR", "CH"]},
    })
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "conflicting_patient_types"


def test_the_other_tags_stay_multi_select(client):
    """Only genuinely contradictory pairs are blocked — the rest are orthogonal."""
    r = client.post(f"{PREFIX}/patients", json={
        "first_name": "Multi", "last_name": "Tag",
        "patient_types": ["CP", "EF", "OR", "SN", "SS", "UP"],
    })
    assert r.status_code == 201, r.text
    assert r.json()["patient_types"] == ["CP", "EF", "OR", "SN", "SS", "UP"]


def test_patient_types_are_normalized_and_deduped(client):
    r = client.post(f"{PREFIX}/patients", json={
        "first_name": "Dupe", "last_name": "Tag",
        "patient_types": [" or ", "OR", "ss", "", "SS"],
    })
    assert r.status_code == 201, r.text
    assert r.json()["patient_types"] == ["OR", "SS"]


# ── Patient Status: implications are auto-applied ────────────────────────────
def test_no_correspondence_forces_the_automated_channels_off(client):
    r = client.post(f"{PREFIX}/patients", json={
        "first_name": "Opt", "last_name": "Out",
        "no_correspondence": True, "no_auto_email": False, "no_auto_sms": False,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    # The contradiction is resolved rather than rejected, and the corrected
    # values come back so the form can re-tick the boxes.
    assert body["no_correspondence"] is True
    assert body["no_auto_email"] is True
    assert body["no_auto_sms"] is True


def test_no_correspondence_on_patch_reaches_stored_flags(client, patient):
    """The PATCH sends only the box the user ticked; the rule still has to see
    the e-mail/SMS flags already sitting true in the database."""
    client.patch(f"{PREFIX}/patients/{patient.id}",
                 json={"no_auto_email": False, "no_auto_sms": False})
    body = client.patch(f"{PREFIX}/patients/{patient.id}",
                        json={"no_correspondence": True}).json()
    assert (body["no_auto_email"], body["no_auto_sms"]) == (True, True)


def test_inactive_patient_leaves_the_quickfill_list(client, patient):
    client.patch(f"{PREFIX}/patients/{patient.id}", json={"add_to_quickfill": True})
    body = client.patch(f"{PREFIX}/patients/{patient.id}", json={"is_active": False}).json()
    assert body["is_active"] is False
    assert body["add_to_quickfill"] is False


def test_active_patient_keeps_quickfill(client):
    """The implication fires on is_active=False only — it must not clear the
    flag for an ordinary active patient."""
    body = client.post(f"{PREFIX}/patients", json={
        "first_name": "Still", "last_name": "Active",
        "is_active": True, "add_to_quickfill": True,
    }).json()
    assert body["add_to_quickfill"] is True


def test_register_applies_the_status_implications(client):
    r = client.post(f"{PREFIX}/patients/register", json={
        "patient": {"first_name": "Reg", "last_name": "Flags",
                    "no_correspondence": True, "no_auto_sms": False},
    })
    assert r.status_code == 201, r.text
    pid = r.json()["patient_id"]
    saved = client.get(f"{PREFIX}/patients/{pid}").json()
    assert (saved["no_auto_email"], saved["no_auto_sms"]) == (True, True)


# ── Coverage Type: a secondary slot needs its primary ────────────────────────
def test_secondary_coverage_requires_a_primary(client, patient, plan):
    r = client.post(f"{PREFIX}/patient-insurance", json={
        "patient_id": patient.id, "ins_plan_id": plan.id,
        "legacy_plan_type": "D", "insurance_type": "secondary",
    })
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "missing_primary_coverage"
    assert err["details"]["requires"] == "primary"
    assert "Dental" in err["message"]


def test_secondary_coverage_is_accepted_once_the_primary_exists(client, patient, plan):
    assert client.post(f"{PREFIX}/patient-insurance", json={
        "patient_id": patient.id, "ins_plan_id": plan.id,
        "legacy_plan_type": "D", "insurance_type": "primary",
    }).status_code == 201
    assert client.post(f"{PREFIX}/patient-insurance", json={
        "patient_id": patient.id, "ins_plan_id": plan.id,
        "legacy_plan_type": "D", "insurance_type": "secondary",
    }).status_code == 201


def test_dental_primary_does_not_satisfy_a_medical_secondary(client, patient, plan):
    """The slot key is (plan type × ordinal) — the ranks are per plan type."""
    client.post(f"{PREFIX}/patient-insurance", json={
        "patient_id": patient.id, "ins_plan_id": plan.id,
        "legacy_plan_type": "D", "insurance_type": "primary",
    })
    r = client.post(f"{PREFIX}/patient-insurance", json={
        "patient_id": patient.id, "ins_plan_id": plan.id,
        "legacy_plan_type": "M", "insurance_type": "secondary",
    })
    assert r.status_code == 422
    assert "Medical" in r.json()["error"]["message"]


def test_an_inactive_secondary_slot_is_not_a_contradiction(client, patient, plan):
    """An archived secondary left behind by a plan change is history, not a
    coverage arrangement — it must not block the write."""
    assert client.post(f"{PREFIX}/patient-insurance", json={
        "patient_id": patient.id, "ins_plan_id": plan.id,
        "legacy_plan_type": "D", "insurance_type": "secondary", "is_active": False,
    }).status_code == 201


def test_activating_an_orphan_secondary_is_rejected(client, patient, plan):
    slot = client.post(f"{PREFIX}/patient-insurance", json={
        "patient_id": patient.id, "ins_plan_id": plan.id,
        "legacy_plan_type": "D", "insurance_type": "secondary", "is_active": False,
    }).json()
    r = client.patch(f"{PREFIX}/patient-insurance/{slot['id']}", json={"is_active": True})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "missing_primary_coverage"


def test_primary_coverage_never_needs_a_prerequisite(client, patient, plan):
    assert client.post(f"{PREFIX}/patient-insurance", json={
        "patient_id": patient.id, "ins_plan_id": plan.id,
        "legacy_plan_type": "M", "insurance_type": "primary",
    }).status_code == 201


# ── The published rule table ─────────────────────────────────────────────────
def test_rules_are_published_for_the_form(client):
    rules = client.get(f"{PREFIX}/metadata/patient-flag-rules").json()

    assert rules["patient_type"]["field"] == "patient_types"
    assert rules["patient_type"]["exclusions"][0]["codes"] == ["CH", "SR"]
    assert rules["patient_type"]["exclusions"][0]["labels"] == ["Child", "Senior Citizen"]

    whens = [i["when"] for i in rules["patient_status"]["implications"]]
    assert {"no_correspondence": True} in whens
    assert {"is_active": False} in whens

    coverage = rules["coverage_type"]
    assert coverage["no_coverage_is_derived"] is True
    assert coverage["ranks"][:2] == ["primary", "secondary"]
    assert {"legacy_plan_type": "D", "insurance_type": "primary"} in coverage["no_coverage_excludes"]


def test_published_rules_match_what_the_api_enforces(client):
    """The form and the API read the same table — if this drifts, the UI starts
    allowing something the server rejects."""
    rules = client.get(f"{PREFIX}/metadata/patient-flag-rules").json()
    for exclusion in rules["patient_type"]["exclusions"]:
        r = client.post(f"{PREFIX}/patients", json={
            "first_name": "Rule", "last_name": "Check",
            "patient_types": exclusion["codes"],
        })
        assert r.status_code == 422, f"{exclusion['codes']} is published but accepted"


def test_an_unrelated_edit_of_a_legacy_contradiction_is_not_blocked(client, db_session, patient):
    """A migrated row can already hold both tags. Correcting that patient's phone
    number must not 422 with a patient-type error the user cannot act on from
    that screen — only a write that touches patient_types is validated."""
    patient.patient_types = ["CH", "SR"]  # as migrated, bypassing the API
    db_session.commit()

    r = client.patch(f"{PREFIX}/patients/{patient.id}", json={"phone": "555-0101"})
    assert r.status_code == 200, r.text
    assert r.json()["phone"] == "555-0101"
    assert r.json()["patient_types"] == ["CH", "SR"]  # untouched, still stale

    # ...but the moment the field itself is written, the rule applies.
    assert client.patch(f"{PREFIX}/patients/{patient.id}",
                        json={"patient_types": ["CH", "SR"]}).status_code == 422
