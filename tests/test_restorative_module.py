"""Restorative-charting backend-gap tests (restorative dev-report REST-1..10)."""

from __future__ import annotations

import pytest

from app.db.models import Patient

PREFIX = "/api/v1"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Resto", last_name="Chart",
                chart_no="RC-1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def proc(client):
    r = client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D2740", "description": "Crown", "category": "Restorative", "default_fee": 900,
    })
    assert r.status_code == 201, r.text
    return "D2740"


# ── REST-1/7/9: first-class qualifier columns on chart_conditions ────────────
def test_condition_qualifier_columns_persist(client, patient, proc):
    r = client.post(f"{PREFIX}/chart-conditions", json={
        "patient_id": patient.id, "tooth": "3", "area": "crown", "condition_code": "CROWN",
        "procedure_code": proc, "chart_as": "pre-existing", "grade": "m2", "segment": "root",
        "root_segment": "mesiobuccal", "tooth_status": "permanent", "rct_fill": "gutta",
        "watch_dir": "ne", "watch_x": 40, "watch_y": 60, "status": "existing",
        "group_id": "grp-1",
    })
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["grade"] == "m2"
    assert b["root_segment"] == "mesiobuccal"
    assert b["watch_x"] == 40 and b["watch_y"] == 60
    assert b["status"] == "existing"
    assert b["group_id"] == "grp-1"
    assert "updated_at" in b  # audit (TimestampMixin)


# ── server-side chart filters (capability §6) ────────────────────────────────
def test_condition_server_filters(client, patient, proc):
    client.post(f"{PREFIX}/chart-conditions", json={
        "patient_id": patient.id, "tooth": "3", "condition_code": "CROWN",
        "procedure_code": proc, "chart_as": "pre-existing", "group_id": "g1"})
    client.post(f"{PREFIX}/chart-conditions", json={
        "patient_id": patient.id, "tooth": "4", "condition_code": "DECAY",
        "chart_as": "completed", "group_id": "g2"})

    by_proc = client.get(f"{PREFIX}/chart-conditions?patient_id={patient.id}&procedure_code={proc}").json()
    assert by_proc["meta"]["total"] == 1
    by_chartas = client.get(f"{PREFIX}/chart-conditions?patient_id={patient.id}&chart_as=completed").json()
    assert by_chartas["meta"]["total"] == 1
    by_group = client.get(f"{PREFIX}/chart-conditions?group_id=g1").json()
    assert by_group["meta"]["total"] == 1


# ── REST-8: procedure_codes alternate-benefit metadata ───────────────────────
def test_procedure_code_amb_fields(client):
    r = client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D2542", "description": "Onlay metallic", "category": "Restorative",
        "amb_code": "D2740", "is_downgrade": True, "alternate_of": "D2740",
    })
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["amb_code"] == "D2740" and b["is_downgrade"] is True and b["alternate_of"] == "D2740"


# ── REST-10: progress_notes first-class drawing ──────────────────────────────
def test_progress_note_drawing_fields(client, patient):
    r = client.post(f"{PREFIX}/progress-notes", json={
        "patient_id": patient.id, "notes": "draw",
        "drawing_strokes": [{"color": "#000", "width": 2, "pts": [[1, 2], [3, 4]]}],
    })
    assert r.status_code == 201, r.text
    assert r.json()["drawing_strokes"][0]["width"] == 2


# ── REST: patient_procedures.treatment_plan_id lineage filter ────────────────
def test_patient_procedure_treatment_plan_link(client, patient, proc):
    for pid, tp in [("PP-1", "TP-A"), ("PP-2", None)]:
        body = {"id": pid, "patient_id": patient.id, "procedure_code": proc,
                "date_of_service": "2026-06-01", "provider_id": "P1", "office_id": 1, "fee": 900}
        if tp:
            body["treatment_plan_id"] = tp
        assert client.post(f"{PREFIX}/patient-procedures", json=body).status_code == 201
    linked = client.get(f"{PREFIX}/patient-procedures?patient_id={patient.id}&treatment_plan_id=TP-A").json()
    assert linked["meta"]["total"] == 1
    assert linked["items"][0]["id"] == "PP-1"


# ── REST-2: chart_status_templates catalog ───────────────────────────────────
def test_chart_status_template_crud(client):
    r = client.post(f"{PREFIX}/chart-status-templates", json={
        "name": "Upper Anterior 4-Unit (Zircon)", "template_type": "span", "arch": "upper",
        "material": "zircon", "teeth": {"pillars": [6, 11], "pontics": [7, 8, 9, 10]},
    })
    assert r.status_code == 201, r.text
    assert r.json()["teeth"]["pontics"] == [7, 8, 9, 10]
    listed = client.get(f"{PREFIX}/chart-status-templates?template_type=span").json()
    assert listed["meta"]["total"] == 1


# ── REST-3: chart_settings get-or-default + upsert ───────────────────────────
def test_chart_settings_defaults_and_upsert(client, patient):
    default = client.get(f"{PREFIX}/chart-settings?patient_id={patient.id}")
    assert default.status_code == 200, default.text
    assert default.json()["numbering_system"] == "UNIVERSAL"
    assert default.json()["wisdom_visible"] is True

    upd = client.put(f"{PREFIX}/chart-settings", json={
        "patient_id": patient.id, "numbering_system": "FDI", "edentulous": True})
    assert upd.status_code == 200
    assert upd.json()["numbering_system"] == "FDI" and upd.json()["edentulous"] is True

    again = client.get(f"{PREFIX}/chart-settings?patient_id={patient.id}").json()
    assert again["numbering_system"] == "FDI"  # persisted


# ── REST-4: per-tooth note upsert (one per patient+tooth) ────────────────────
def test_tooth_note_upsert(client, patient):
    u1 = client.put(f"{PREFIX}/chart-tooth-notes/upsert",
                    json={"patient_id": patient.id, "tooth": "8", "note": "first"})
    assert u1.status_code == 200, u1.text
    u2 = client.put(f"{PREFIX}/chart-tooth-notes/upsert",
                    json={"patient_id": patient.id, "tooth": "8", "note": "second"})
    assert u2.status_code == 200
    assert u2.json()["note"] == "second"
    listed = client.get(f"{PREFIX}/chart-tooth-notes?patient_id={patient.id}").json()
    assert listed["meta"]["total"] == 1  # upsert, not duplicate


# ── bulk condition write (server group_id) ───────────────────────────────────
def test_bulk_conditions(client, patient):
    r = client.post(f"{PREFIX}/chart-conditions/bulk", json={
        "patient_id": patient.id,
        "conditions": [
            {"tooth": "6", "condition_code": "BRIDGE_PILLAR", "area": "whole"},
            {"tooth": "7", "condition_code": "BRIDGE_PONTIC", "area": "whole"},
            {"tooth": "8", "condition_code": "BRIDGE_PILLAR", "area": "whole"},
        ],
    })
    assert r.status_code == 201, r.text
    gid = r.json()["group_id"]
    assert gid and len(r.json()["conditions"]) == 3
    same_group = client.get(f"{PREFIX}/chart-conditions?group_id={gid}").json()
    assert same_group["meta"]["total"] == 3


# ── aggregate GET /patients/{id}/chart ───────────────────────────────────────
def test_patient_chart_aggregate(client, patient, proc):
    client.post(f"{PREFIX}/chart-conditions", json={
        "patient_id": patient.id, "tooth": "3", "condition_code": "CROWN", "procedure_code": proc})
    client.post(f"{PREFIX}/patient-procedures", json={
        "id": "PP-A", "patient_id": patient.id, "procedure_code": proc,
        "date_of_service": "2026-06-01", "provider_id": "P1", "office_id": 1, "fee": 900})
    client.put(f"{PREFIX}/chart-tooth-notes/upsert",
               json={"patient_id": patient.id, "tooth": "8", "note": "n"})

    agg = client.get(f"{PREFIX}/patients/{patient.id}/chart")
    assert agg.status_code == 200, agg.text
    b = agg.json()
    assert b["patient_id"] == patient.id
    assert len(b["conditions"]) == 1
    assert len(b["procedures"]) == 1
    assert len(b["tooth_notes"]) == 1
    assert b["settings"]["numbering_system"] == "UNIVERSAL"
