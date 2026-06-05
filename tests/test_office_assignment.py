"""Office Assignment module tests (Setup -> Offices -> Office Assignment, #24-#33)."""

from __future__ import annotations

import pytest

from app.core.security import hash_password
from app.db.models import Office, ProcedureCode, Tenant, User


@pytest.fixture
def office_id(db_session) -> int:
    office = Office(tenant_id=db_session._tenant_id, office_code="MAIN", name="Main Office")
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    return office.id


@pytest.fixture
def procedure_codes(db_session) -> list[str]:
    codes = [
        ProcedureCode(code="D0120", description="Periodic exam", category="Diagnostic"),
        ProcedureCode(code="D0150", description="Comprehensive exam", category="Diagnostic"),
    ]
    db_session.add_all(codes)
    db_session.commit()
    return ["D0120", "D0150"]


def test_procedure_assignment_set_and_reconcile(client, office_id, procedure_codes):
    base = f"/api/v1/offices/{office_id}/procedure-codes"
    assert client.get(base).json() == []
    r = client.put(base, json={"ids": ["D0120", "D0150"]})
    assert r.status_code == 200
    assert {x["code"] for x in r.json()} == {"D0120", "D0150"}
    # Reconcile down to one.
    r2 = client.put(base, json={"ids": ["D0120"]})
    assert [x["code"] for x in r2.json()] == ["D0120"]
    assert len(client.get(base).json()) == 1


def test_production_types_catalog_and_assignment(client, office_id):
    # Catalog create (registry CRUD).
    created = client.post("/api/v1/production-types", json={"name": "Hygiene", "color": "#00ff00"})
    assert created.status_code == 201
    pt_id = created.json()["id"]
    # Assign to office.
    base = f"/api/v1/offices/{office_id}/production-types"
    r = client.put(base, json={"ids": [pt_id]})
    assert [x["id"] for x in r.json()] == [pt_id]
    assert len(client.get(base).json()) == 1


def test_office_users_bulk_set_and_denormalized(client, office_id, db_session):
    u1 = User(tenant_id=db_session._tenant_id, email="u1@x.com", username="u1",
              password_hash=hash_password("x"), role="staff", is_active=True, first_name="A", last_name="One")
    u2 = User(tenant_id=db_session._tenant_id, email="u2@x.com", username="u2",
              password_hash=hash_password("x"), role="staff", is_active=True, first_name="B", last_name="Two")
    db_session.add_all([u1, u2])
    db_session.commit()
    db_session.refresh(u1)
    db_session.refresh(u2)

    base = f"/api/v1/offices/{office_id}/users"
    r = client.put(base, json={"user_ids": [u1.id, u2.id]})
    assert r.status_code == 200
    body = r.json()
    assert {u["id"] for u in body} == {u1.id, u2.id}
    assert {u["username"] for u in body} == {"u1", "u2"}  # denormalized UserRead
    # Reconcile to one.
    assert len(client.put(base, json={"user_ids": [u1.id]}).json()) == 1
    # Server-side office_id filter on the generic user-offices list (#33).
    links = client.get(f"/api/v1/user-offices?office_id={office_id}").json()
    assert links["meta"]["total"] == 1


def test_copy_users_from_other_office(client, office_id, db_session):
    src = Office(tenant_id=db_session._tenant_id, office_code="SRC", name="Source")
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)
    u = User(tenant_id=db_session._tenant_id, email="c@x.com", username="cu",
             password_hash=hash_password("x"), role="staff", is_active=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    client.put(f"/api/v1/offices/{src.id}/users", json={"user_ids": [u.id]})

    copied = client.post(f"/api/v1/offices/{office_id}/users/copy-from/{src.id}")
    assert copied.status_code == 200
    assert u.id in [x["id"] for x in copied.json()]


def test_cross_tenant_office_forbidden(client, db_session):
    other = Tenant(name="Other", code="other2", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    foreign = Office(tenant_id=other.id, office_code="F", name="Foreign")
    db_session.add(foreign)
    db_session.commit()
    db_session.refresh(foreign)
    assert client.get(f"/api/v1/offices/{foreign.id}/procedure-codes").status_code == 403
