"""Prescriptions Setup — RX-1/2/4 of ``docs/pick-list/pick_list_setup_backend_devreport.md``.

RX-4: the library had no uniqueness at all (every migration re-run appended the
whole Denticon library again). The migration adds ``(tenant_id, legacy_id)``
uniqueness for the importer; ``PrescriptionLibraryCRUD`` is the API-side guard —
409 ``duplicate_prescription`` on an identical active drug name + dispense + sig,
overridable with ``allow_duplicate``, never blocking on a same-name row with a
different configuration. RX-2: the 240-char sig cap is enforced + published.
RX-1: ``created_by_name`` / ``updated_by_name`` on the read model.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import PrescriptionLibrary

V1 = "/api/v1"
RX = f"{V1}/prescription-library"


def _add(client, **body):
    body.setdefault("drug_name", "Amoxicillin 500mg")
    return client.post(RX, json=body)


# ── RX-4: duplicate guard ────────────────────────────────────────────────────
def test_identical_active_prescription_is_409_with_override(client):
    first = _add(client, dispense="30 caps", sig="1 cap tid x 10 days")
    assert first.status_code == 201, first.text

    dup = _add(client, dispense="30 caps", sig="1 cap tid x 10 days")
    assert dup.status_code == 409, dup.text
    err = dup.json()["error"]
    assert err["code"] == "duplicate_prescription"
    assert err["details"]["matches"][0]["id"] == first.json()["id"]
    assert err["details"]["override_field"] == "allow_duplicate"
    assert err["details"]["same_name_matches"] == []

    # The dialog's third option: legacy allows the duplicate, so the API must too.
    forced = _add(client, dispense="30 caps", sig="1 cap tid x 10 days", allow_duplicate=True)
    assert forced.status_code == 201, forced.text
    assert "allow_duplicate" not in forced.json()  # not persisted, not echoed


def test_duplicate_match_is_case_space_and_blank_insensitive(client):
    assert _add(client, drug_name="Ibuprofen 800mg", dispense="20 tabs", sig=None).status_code == 201
    r = _add(client, drug_name="  ibuprofen   800MG ", dispense=" 20 TABS", sig="")
    assert r.status_code == 409, r.text


def test_same_name_different_config_is_allowed_but_reported(client):
    # The seed's Chlorhexidine case: one drug, two legitimate configurations.
    a = _add(client, drug_name="Chlorhexidine Gluconate 0.12% Oral Rinse",
             dispense="16 oz", sig="Rinse 15 ml bid")
    assert a.status_code == 201, a.text
    b = _add(client, drug_name="Chlorhexidine Gluconate 0.12% Oral Rinse",
             dispense="8 oz", sig="Rinse 15 ml qd")
    assert b.status_code == 201, b.text

    probe = client.get(f"{RX}/availability", params={
        "drug_name": "chlorhexidine gluconate 0.12% oral rinse", "dispense": "4 oz", "sig": "x",
    }).json()
    assert probe["taken"] is False
    assert {m["id"] for m in probe["same_name_matches"]} == {a.json()["id"], b.json()["id"]}


def test_inactive_twin_is_reported_never_blocking_and_reactivation_is_guarded(client):
    live = _add(client, dispense="10", sig="qd").json()
    dead = _add(client, dispense="10", sig="qd", is_active=False)
    # Creating inactive never collides — the picker does not offer it.
    assert dead.status_code == 201, dead.text
    dead_id = dead.json()["id"]

    probe = client.get(f"{RX}/availability", params={
        "drug_name": "Amoxicillin 500mg", "dispense": "10", "sig": "qd", "exclude_id": live["id"],
    }).json()
    assert probe["taken"] is False
    assert [m["id"] for m in probe["inactive_matches"]] == [dead_id]

    # Flipping the inactive twin back on is what would recreate the duplicate.
    r = client.patch(f"{RX}/{dead_id}", json={"is_active": True})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["details"]["matches"][0]["id"] == live["id"]
    r = client.patch(f"{RX}/{dead_id}", json={"is_active": True, "allow_duplicate": True})
    assert r.status_code == 200, r.text


def test_patch_guard_fires_on_a_move_not_on_stored_state(client):
    a = _add(client, dispense="30", sig="tid").json()
    b = _add(client, dispense="30", sig="tid", allow_duplicate=True).json()  # pre-existing dupe

    # Editing an unrelated field on an existing duplicate stays possible.
    r = client.patch(f"{RX}/{b['id']}", json={"refills": 2})
    assert r.status_code == 200, r.text
    # Re-sending the identical identity is not a move either.
    r = client.patch(f"{RX}/{b['id']}", json={"sig": "TID "})
    assert r.status_code == 200, r.text

    # Moving a third row *onto* the taken identity is — judged against the merge
    # of payload + stored row (only ``sig`` is sent here).
    c = _add(client, dispense="30", sig="bid").json()
    r = client.patch(f"{RX}/{c['id']}", json={"sig": "tid"})
    assert r.status_code == 409, r.text
    ids = {m["id"] for m in r.json()["error"]["details"]["matches"]}
    assert ids == {a["id"], b["id"]}

    # Moving away is always fine.
    r = client.patch(f"{RX}/{c['id']}", json={"drug_name": "Amoxicillin 875mg"})
    assert r.status_code == 200, r.text


def test_availability_probe_agrees_with_the_save_path(client):
    row = _add(client, dispense="30", sig="tid").json()
    taken = client.get(f"{RX}/availability", params={
        "drug_name": "amoxicillin 500MG", "dispense": "30", "sig": "tid",
    }).json()
    assert taken["taken"] is True
    assert taken["matches"][0]["id"] == row["id"]
    assert taken["override_field"] == "allow_duplicate"
    # The row being edited never collides with itself.
    mine = client.get(f"{RX}/availability", params={
        "drug_name": "Amoxicillin 500mg", "dispense": "30", "sig": "tid", "exclude_id": row["id"],
    }).json()
    assert mine["taken"] is False
    # A blank name is simply "free" — nothing to compare against.
    free = client.get(f"{RX}/availability", params={"drug_name": "   "}).json()
    assert free["taken"] is False


def test_duplicate_guard_is_tenant_scoped(client, db_session):
    other_tenant_id = db_session._tenant_id + 1
    from app.db.models import Tenant
    db_session.add(Tenant(id=other_tenant_id, name="Other", code="other", is_active=True))
    db_session.add(PrescriptionLibrary(
        tenant_id=other_tenant_id, drug_name="Amoxicillin 500mg", dispense="30", sig="tid",
        refills=0, is_as_written=False, is_active=True,
    ))
    db_session.commit()
    assert _add(client, dispense="30", sig="tid").status_code == 201


def test_migration_uniqueness_on_tenant_legacy_id(db_session):
    """The importer's ``ON CONFLICT DO NOTHING`` needs a constraint to conflict on.
    NULL legacy_id (API-created rows) stays exempt."""
    tid = db_session._tenant_id
    db_session.add(PrescriptionLibrary(tenant_id=tid, legacy_id="101", drug_name="A",
                                       refills=0, is_as_written=False, is_active=True))
    db_session.add(PrescriptionLibrary(tenant_id=tid, legacy_id=None, drug_name="B",
                                       refills=0, is_as_written=False, is_active=True))
    db_session.add(PrescriptionLibrary(tenant_id=tid, legacy_id=None, drug_name="C",
                                       refills=0, is_as_written=False, is_active=True))
    db_session.commit()
    db_session.add(PrescriptionLibrary(tenant_id=tid, legacy_id="101", drug_name="A again",
                                       refills=0, is_as_written=False, is_active=True))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ── RX-2: sig cap ────────────────────────────────────────────────────────────
def test_sig_cap_is_enforced_and_published(client):
    limits = client.get(f"{RX}/limits").json()
    assert limits["sig_max_length"] == 240
    assert limits["duplicate_key_fields"] == ["drug_name", "dispense", "sig"]
    assert limits["override_field"] == "allow_duplicate"

    ok = _add(client, sig="x" * 240)
    assert ok.status_code == 201, ok.text
    too_long = _add(client, drug_name="Other", sig="x" * 241)
    assert too_long.status_code == 422, too_long.text
    err = too_long.json()["error"]
    assert err["code"] == "sig_too_long"
    assert err["details"] == {"field": "sig", "max_length": 240, "length": 241}

    r = client.patch(f"{RX}/{ok.json()['id']}", json={"sig": "y" * 300})
    assert r.status_code == 422
    # A PATCH that does not touch sig is never judged on it.
    r = client.patch(f"{RX}/{ok.json()['id']}", json={"refills": 1})
    assert r.status_code == 200, r.text


def test_blank_drug_name_is_422_not_a_db_error(client):
    r = _add(client, drug_name="   ")
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "drug_name_required"


def test_strings_are_stored_trimmed(client):
    r = _add(client, drug_name="  Penicillin VK 500mg  ", dispense=" 28 ", sig=" qid ")
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["drug_name"], body["dispense"], body["sig"]) == ("Penicillin VK 500mg", "28", "qid")


# ── RX-1: Created By / Modified By names ─────────────────────────────────────
def test_actor_names_on_read(client, db_session):
    created = _add(client).json()
    assert created["created_by"] == db_session._admin.id
    assert created["created_by_name"] == "admin"  # username fallback (no first/last)
    assert created["updated_by"] is None and created["updated_by_name"] is None

    edited = client.patch(f"{RX}/{created['id']}", json={"refills": 3}).json()
    assert edited["updated_by"] == db_session._admin.id
    assert edited["updated_by_name"] == "admin"

    listed = client.get(RX).json()["items"]
    assert listed[0]["updated_by_name"] == "admin"


def test_list_can_sort_by_drug_name(client):
    for name in ("Zithromax", "Amoxicillin", "Motrin"):
        assert _add(client, drug_name=name).status_code == 201
    names = [i["drug_name"] for i in client.get(RX, params={"sort": "drug_name", "order": "asc"}).json()["items"]]
    assert names == ["Amoxicillin", "Motrin", "Zithromax"]
