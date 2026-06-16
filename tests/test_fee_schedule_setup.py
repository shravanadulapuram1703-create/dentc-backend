"""Fee Schedule Setup tests — dev-report gaps FEE-1..FEE-4."""

from __future__ import annotations

import pytest

from app.db.models import FeeSchedule, FeeScheduleEntry, ProcedureCode


@pytest.fixture
def schedule_id(db_session) -> int:
    fs = FeeSchedule(tenant_id=db_session._tenant_id, name="CIGNA PPO", effective_date=None)
    db_session.add(fs)
    db_session.commit()
    db_session.refresh(fs)
    return fs.id


def test_fee_schedule_soft_delete_then_restore(client, schedule_id, db_session):
    # FEE-1: DELETE is a soft-delete; restore flips is_active back to true.
    assert client.delete(f"/api/v1/fee-schedules/{schedule_id}").status_code == 204
    db_session.expire_all()
    assert db_session.get(FeeSchedule, schedule_id).is_active is False
    # Soft-deleted row no longer appears under the active-only filter.
    active = client.get("/api/v1/fee-schedules", params={"is_active": True}).json()
    assert schedule_id not in {s["id"] for s in active["items"]}

    r = client.post(f"/api/v1/fee-schedules/{schedule_id}/restore")
    assert r.status_code == 200
    assert r.json()["is_active"] is True


def test_fee_entry_amb_code(client, schedule_id, db_session):
    # FEE-2: amb_code round-trips on a fee-schedule entry.
    db_session.add(ProcedureCode(code="D0120", description="Periodic Eval", category="Diagnostic"))
    db_session.commit()
    c = client.post("/api/v1/fee-schedule-entries", json={
        "fee_schedule_id": schedule_id, "procedure_code": "D0120",
        "amb_code": "AMB-1", "patient_fee": "55.00",
    })
    assert c.status_code == 201
    assert c.json()["amb_code"] == "AMB-1"


def test_assignment_office_group_filter(client, db_session):
    # FEE-3: office_group_id is stored and server-filterable.
    from app.db.models import FeeSchedule, OfficeGroup
    grp = OfficeGroup(tenant_id=db_session._tenant_id, name="North Group")
    fs = FeeSchedule(tenant_id=db_session._tenant_id, name="Grp Sched")
    db_session.add_all([grp, fs])
    db_session.commit()
    db_session.refresh(grp)
    db_session.refresh(fs)
    c = client.post("/api/v1/fee-schedule-assignments", json={
        "fee_schedule_id": fs.id, "office_group_id": grp.id,
    })
    assert c.status_code == 201
    assert c.json()["office_group_id"] == grp.id
    listed = client.get("/api/v1/fee-schedule-assignments", params={"office_group_id": grp.id}).json()
    assert len(listed["items"]) == 1
    assert listed["items"][0]["office_group_id"] == grp.id


def test_fee_schedule_new_version_clones_entries(client, schedule_id, db_session):
    # FEE-4: new-version clones the schedule + entries under a new effective date.
    db_session.add(ProcedureCode(code="D0150", description="Comp Eval", category="Diagnostic"))
    db_session.commit()
    db_session.add_all([
        FeeScheduleEntry(fee_schedule_id=schedule_id, procedure_code="D0150",
                         amb_code="A1", patient_fee="80.00", insurance_fee="60.00"),
    ])
    db_session.commit()

    r = client.post(f"/api/v1/fee-schedules/{schedule_id}/new-version",
                    json={"effective_date": "2027-01-01", "name": "CIGNA PPO 2027"})
    assert r.status_code == 200
    new = r.json()
    assert new["id"] != schedule_id
    assert new["effective_date"] == "2027-01-01"
    assert new["version"] == 2
    assert new["parent_schedule_id"] == schedule_id
    assert new["name"] == "CIGNA PPO 2027"

    # Entries copied with the new effective date.
    entries = client.get("/api/v1/fee-schedule-entries", params={"fee_schedule_id": new["id"]}).json()
    assert len(entries["items"]) == 1
    e = entries["items"][0]
    assert e["procedure_code"] == "D0150"
    assert e["amb_code"] == "A1"
    assert e["effective_date"] == "2027-01-01"


def test_fee_schedule_not_in_tenant_forbidden(client, db_session):
    from app.db.models import Tenant
    other = Tenant(name="Other", code="other-fs", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    foreign = FeeSchedule(tenant_id=other.id, name="Foreign")
    db_session.add(foreign)
    db_session.commit()
    db_session.refresh(foreign)
    assert client.post(f"/api/v1/fee-schedules/{foreign.id}/restore").status_code == 403
