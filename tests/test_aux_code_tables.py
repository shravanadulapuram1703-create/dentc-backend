"""Auxiliary code-tables tests — dev-report gaps AUX-1..AUX-4."""

from __future__ import annotations

from app.db.models import IcdCode
from scripts.seed_account_definitions import seed_for_tenant
from scripts.seed_aux_codes import seed_for_tenant as seed_pos
from scripts.seed_icd_codes import seed as seed_icd


def test_modifier_and_tos_definitions_seeded(client, db_session):
    # AUX-1 + AUX-2: Modifier / Type-of-Service exposed via /definitions.
    seed_for_tenant(db_session, db_session._tenant_id)

    mods = client.get("/api/v1/definitions", params={"group_code": "MODIFIER"}).json()
    by_code = {d["key1"]: d["description"] for d in mods["items"]}
    assert by_code["50"] == "Bilateral Procedure"
    assert by_code["59"] == "Distinct Procedural Service"

    tos = client.get("/api/v1/definitions", params={"group_code": "TYPEOFSERVICE"}).json()
    tos_map = {d["key1"]: d["description"] for d in tos["items"]}
    assert tos_map["01"] == "Medical Care"
    assert tos_map["02"] == "Surgery"


def test_place_of_service_crud_and_seed(client, db_session):
    # AUX-3: dedicated tenant-scoped resource with Tax ID / office_id.
    assert seed_pos(db_session, db_session._tenant_id) == 19
    listed = client.get("/api/v1/place-of-service-codes", params={"size": 200}).json()
    codes = {r["code"] for r in listed["items"]}
    assert "11" in codes and "12" in codes

    c = client.post("/api/v1/place-of-service-codes", json={
        "code": "11", "type": "Office", "name": "Main Office", "tax_id": "932060144",
    })
    assert c.status_code == 201, c.text
    assert c.json()["tax_id"] == "932060144"
    # Search hits code/type/name.
    found = client.get("/api/v1/place-of-service-codes", params={"search": "Home"}).json()
    assert any(r["code"] == "12" for r in found["items"])


def test_icd_codes_crud_search_and_filter(client, db_session):
    # AUX-4: paginated, searchable, is_active-filterable global catalog.
    db_session.add_all([
        IcdCode(code="327.2", description="Organic sleep apnea", icd10="G47.30", is_active=True),
        IcdCode(code="520.0", description="Anodontia Absence of teeth", icd10="K00.0", is_active=False),
    ])
    db_session.commit()

    by_desc = client.get("/api/v1/icd-codes", params={"search": "Anodontia"}).json()
    assert {r["code"] for r in by_desc["items"]} == {"520.0"}
    active = client.get("/api/v1/icd-codes", params={"is_active": True}).json()
    assert {r["code"] for r in active["items"]} == {"327.2"}

    c = client.post("/api/v1/icd-codes", json={
        "code": "521.0", "description": "Dental caries", "icd10": "K02.9",
    })
    assert c.status_code == 201, c.text


def test_icd_bulk_status(client, db_session):
    # AUX-4: bulk activate/deactivate (legacy "Edit ICD Codes").
    rows = [IcdCode(code=f"A{i}", description=f"d{i}", is_active=True) for i in range(3)]
    db_session.add_all(rows)
    db_session.commit()
    for r in rows:
        db_session.refresh(r)
    ids = [r.id for r in rows]

    res = client.post("/api/v1/icd-codes/bulk-status", json={"ids": ids, "is_active": False})
    assert res.status_code == 200
    assert res.json()["updated"] == 3
    # All now inactive.
    active = client.get("/api/v1/icd-codes", params={"is_active": True}).json()
    assert active["meta"]["total"] == 0


def test_icd_seed_loads_dental_set_inactive_and_idempotent(client, db_session):
    # The legacy dental ICD-9 set seeds (is_active=False) and re-running is a no-op.
    added = seed_icd(db_session)
    assert added > 200
    listed = client.get("/api/v1/icd-codes", params={"size": 1}).json()
    assert listed["meta"]["total"] == added
    # Legacy default: every seeded row is inactive until the practice activates it.
    assert client.get("/api/v1/icd-codes", params={"is_active": True, "size": 1}).json()["meta"]["total"] == 0
    one = client.get("/api/v1/icd-codes", params={"search": "Anodontia"}).json()
    assert any(r["code"] == "520.0" for r in one["items"])
    # Idempotent.
    assert seed_icd(db_session) == 0
