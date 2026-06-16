"""Procedure Code Setup tests — dev-report gaps PROC-1..PROC-6."""

from __future__ import annotations

import pytest

from app.db.models import FeeSchedule, Office, ProcedureCode, Provider


def _code(db_session, code: str, **kw) -> str:
    pc = ProcedureCode(code=code, description=kw.pop("description", code),
                       category=kw.pop("category", "Diagnostic"), **kw)
    db_session.add(pc)
    db_session.commit()
    return code


@pytest.fixture
def provider_id(db_session) -> str:
    office = Office(tenant_id=db_session._tenant_id, office_code="MAIN", name="Main")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    p = Provider(id="prov-1", tenant_id=db_session._tenant_id, office_id=office.id, name="Dr. X")
    db_session.add(p)
    db_session.commit()
    return p.id


def test_charting_and_main_fields_roundtrip(client, db_session):
    # PROC-1 + PROC-4: new charting + Main fields flow through the CRUD, valid_teeth is an array.
    _code(db_session, "D2740")
    r = client.patch("/api/v1/procedure-codes/D2740", json={
        "chart_category": "Crown", "tooth_area": "whole", "draw_as": "crown",
        "min_surfaces": 1, "max_surfaces": 5, "valid_teeth": ["1", "2", "3"],
        "taxable": True, "visit_code": "V1", "show_ada_code_in_notes": True,
    })
    assert r.status_code == 200, r.text
    g = client.get("/api/v1/procedure-codes/D2740").json()
    assert g["chart_category"] == "Crown"
    assert g["valid_teeth"] == ["1", "2", "3"]
    assert g["max_surfaces"] == 5
    assert g["taxable"] is True
    assert g["visit_code"] == "V1"


def test_procedure_stats(client, db_session):
    # PROC-5: catalog KPI roll-up.
    _code(db_session, "D0120", category="Diagnostic")
    _code(db_session, "D1110", category="Preventive")
    _code(db_session, "D8080", category="Orthodontics", is_ortho=True)
    _code(db_session, "D9999", category="Diagnostic", is_active=False)

    s = client.get("/api/v1/procedure-codes/stats").json()
    assert s["total"] == 4
    assert s["active"] == 3
    assert s["inactive"] == 1
    assert s["ortho"] == 1
    assert s["by_category"]["Diagnostic"] == 2


def test_provider_procedure_codes_set(client, db_session, provider_id):
    # PROC-2: provider↔procedure permission set.
    _code(db_session, "D8080", category="Orthodontics")
    _code(db_session, "D8090", category="Orthodontics")
    base = f"/api/v1/providers/{provider_id}/procedure-codes"
    assert client.get(base).json() == []
    r = client.put(base, json={"codes": ["D8080", "D8090"]})
    assert r.status_code == 200
    assert {c["code"] for c in r.json()} == {"D8080", "D8090"}
    # Replace-set shrinks to one.
    r2 = client.put(base, json={"codes": ["D8080"]})
    assert [c["code"] for c in r2.json()] == ["D8080"]


def test_procedure_insurance_rules_crud(client, db_session):
    # PROC-3: per-code, plan-agnostic insurance rules.
    _code(db_session, "D2740")
    base = "/api/v1/procedure-codes/D2740/insurance-rules"
    c = client.post(base, json={"coverage_pct": "50.00", "frequency_limit": "1/5yr", "age_limit": "0-99"})
    assert c.status_code == 201, c.text
    rid = c.json()["id"]
    assert len(client.get(base).json()) == 1
    u = client.patch(f"{base}/{rid}", json={"frequency_limit": "1/7yr"})
    assert u.json()["frequency_limit"] == "1/7yr"
    assert client.delete(f"{base}/{rid}").status_code == 204
    assert client.get(base).json() == []


def test_insurance_rules_unknown_code_404(client):
    assert client.get("/api/v1/procedure-codes/NOPE/insurance-rules").status_code == 404


def test_fee_schedule_options(client, db_session):
    # PROC-6: lightweight id→name/type projection (active only).
    db_session.add_all([
        FeeSchedule(tenant_id=db_session._tenant_id, name="UCR", fee_type="ucr"),
        FeeSchedule(tenant_id=db_session._tenant_id, name="Dead", fee_type="ppo", is_active=False),
    ])
    db_session.commit()
    opts = client.get("/api/v1/fee-schedules/options").json()
    assert [o["name"] for o in opts] == ["UCR"]
    assert opts[0]["fee_type"] == "ucr"
    assert set(opts[0].keys()) == {"id", "name", "fee_type"}
