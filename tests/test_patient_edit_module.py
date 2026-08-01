"""Edit Patient backend gaps (docs/patients/patient_edit_backend_devreport.md, PE-1..4)."""

from __future__ import annotations

from app.db.models import Patient


# ── PE-4: updated_by + resolved created/updated_by_name on PatientRead ─────────
def test_patient_read_audit_names(client, db_session):
    created = client.post("/api/v1/patients", json={"first_name": "Edit", "last_name": "Me"})
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    # create stamps created_by; read resolves the name (admin fixture).
    assert created.json()["created_by_name"] is not None

    patched = client.patch(f"/api/v1/patients/{pid}", json={"preferred_name": "Eddie"})
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["updated_by"] is not None
    assert body["updated_by_name"] is not None
    assert body["preferred_name"] == "Eddie"


# ── PE-3: opening_balance folded into /patients/{id}/context ──────────────────
def test_context_includes_opening_balance(client, db_session):
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ctx", last_name="Pat")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    client.put(f"/api/v1/patients/{p.id}/opening-balance", json={"over_30": 1.0, "over_120": 1.0})

    ctx = client.get(f"/api/v1/patients/{p.id}/context")
    assert ctx.status_code == 200, ctx.text
    body = ctx.json()
    assert "opening_balance" in body
    assert body["opening_balance"]["total"] == 2.0


# ── PE-2: patient_type catalog is seedable as a definitions group ─────────────
def test_patient_type_catalog_seeded_group(client, db_session):
    from scripts.seed_account_definitions import GROUPS, seed_for_tenant

    assert "patient_type" in GROUPS
    codes = {c for c, _ in GROUPS["patient_type"]}
    assert codes == {"CH", "CP", "EF", "OR", "SN", "SR", "SS", "UP"}

    seed_for_tenant(db_session, db_session._tenant_id)
    got = client.get("/api/v1/definitions?group_code=patient_type").json()
    assert got["meta"]["total"] == 8
    labels = {i["key1"]: i["description"] for i in got["items"]}
    assert labels["OR"] == "Ortho"
