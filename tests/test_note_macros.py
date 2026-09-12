"""Notes Macros Setup — NM-3/5/6/7 of ``docs/pick-list/pick_list_setup_backend_devreport.md``.

NM-7: the catalog had no uniqueness (every migration re-run appended it again);
the migration adds ``(tenant_id, legacy_id)`` uniqueness for the importer and
``NoteMacroCRUD`` is the API-side guard — 409 ``duplicate_note_macro`` on the
same name in the same category, overridable with ``allow_duplicate``, never
blocking across categories. NM-6: ``?sort=name`` is honoured. NM-3: actor names.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import NoteMacro

V1 = "/api/v1"
NM = f"{V1}/note-macros"


def _add(client, **body):
    body.setdefault("name", "Cold Sensitivity")
    body.setdefault("content", "Patient reports cold sensitivity.")
    return client.post(NM, json=body)


# ── NM-5: duplicate guard ────────────────────────────────────────────────────
def test_same_name_same_category_is_409_with_override(client):
    first = _add(client, category="DIAGNOSTIC")
    assert first.status_code == 201, first.text
    dup = _add(client, category="diagnostic ")
    assert dup.status_code == 409, dup.text
    err = dup.json()["error"]
    assert err["code"] == "duplicate_note_macro"
    assert err["details"]["matches"][0]["id"] == first.json()["id"]
    assert err["details"]["override_field"] == "allow_duplicate"
    forced = _add(client, category="DIAGNOSTIC", allow_duplicate=True)
    assert forced.status_code == 201, forced.text
    assert "allow_duplicate" not in forced.json()


def test_same_name_other_category_is_allowed_but_reported(client):
    a = _add(client, category="DIAGNOSTIC").json()
    b = _add(client, category="PERIO")
    assert b.status_code == 201, b.text
    probe = client.get(f"{NM}/availability", params={"name": "cold  sensitivity", "category": "ORTHO"}).json()
    assert probe["taken"] is False
    assert {m["id"] for m in probe["other_category_matches"]} == {a["id"], b.json()["id"]}


def test_blank_and_null_category_are_the_same_bucket(client):
    assert _add(client, category=None).status_code == 201
    r = _add(client, category="")
    assert r.status_code == 409, r.text
    # A blank category is stored as NULL so the dropdown never grows an "" bucket.
    ok = _add(client, name="Other", category="  ")
    assert ok.status_code == 201 and ok.json()["category"] is None


def test_patch_guard_fires_on_a_move_not_on_stored_state(client):
    a = _add(client, category="DIAGNOSTIC").json()
    b = _add(client, category="DIAGNOSTIC", allow_duplicate=True).json()
    # The pre-existing duplicate (the migrated "fixed/detach try-in" pair) stays editable.
    assert client.patch(f"{NM}/{b['id']}", json={"content": "new body"}).status_code == 200
    assert client.patch(f"{NM}/{b['id']}", json={"name": "COLD SENSITIVITY "}).status_code == 200
    # Moving a third macro onto the taken identity is refused (only category sent —
    # judged against the merge with the stored name).
    c = _add(client, category="PERIO").json()
    r = client.patch(f"{NM}/{c['id']}", json={"category": "DIAGNOSTIC"})
    assert r.status_code == 409, r.text
    assert {m["id"] for m in r.json()["error"]["details"]["matches"]} == {a["id"], b["id"]}
    assert client.patch(f"{NM}/{c['id']}", json={"category": "DIAGNOSTIC", "allow_duplicate": True}).status_code == 200


def test_availability_probe_agrees_with_save_path(client):
    row = _add(client, category="DIAGNOSTIC").json()
    taken = client.get(f"{NM}/availability", params={"name": "Cold Sensitivity", "category": "DIAGNOSTIC"}).json()
    assert taken["taken"] is True and taken["matches"][0]["id"] == row["id"]
    mine = client.get(f"{NM}/availability", params={
        "name": "Cold Sensitivity", "category": "DIAGNOSTIC", "exclude_id": row["id"]}).json()
    assert mine["taken"] is False
    assert client.get(f"{NM}/availability", params={"name": "  "}).json()["taken"] is False


def test_limits_and_length_caps(client):
    limits = client.get(f"{NM}/limits").json()
    assert limits == {"name_max_length": 100, "category_max_length": 100,
                      "duplicate_key_fields": ["name", "category"], "override_field": "allow_duplicate"}
    r = _add(client, name="x" * 101)
    # LAB-6: the schema factory now carries the column's String(100) onto the
    # generated Create, so the length cap fires as the standard validation
    # error (naming the field) before the service's ``name_too_long`` can.
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error" and any("name" in e["loc"] for e in err["details"])
    r = _add(client, name="   ")
    assert r.status_code == 422 and r.json()["error"]["code"] == "name_required"


def test_migration_uniqueness_on_tenant_legacy_id(db_session):
    tid = db_session._tenant_id
    db_session.add(NoteMacro(tenant_id=tid, legacy_id="7", name="A", content="a"))
    db_session.add(NoteMacro(tenant_id=tid, legacy_id=None, name="B", content="b"))
    db_session.add(NoteMacro(tenant_id=tid, legacy_id=None, name="C", content="c"))
    db_session.commit()
    db_session.add(NoteMacro(tenant_id=tid, legacy_id="7", name="A again", content="a"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ── NM-6: sort is honoured ───────────────────────────────────────────────────
def test_list_sorts_by_name_and_category(client):
    for name, cat in (("Zebra", "B"), ("Apple", "C"), ("Mango", "A")):
        assert _add(client, name=name, category=cat).status_code == 201
    by_name = [i["name"] for i in client.get(NM, params={"sort": "name", "order": "asc"}).json()["items"]]
    assert by_name == ["Apple", "Mango", "Zebra"]
    by_cat = [i["category"] for i in client.get(NM, params={"sort": "category", "order": "desc"}).json()["items"]]
    assert by_cat == ["C", "B", "A"]


# ── NM-3: actor names ────────────────────────────────────────────────────────
def test_actor_names_on_read(client, db_session):
    created = _add(client).json()
    assert created["created_by"] == db_session._admin.id
    assert created["created_by_name"] == "admin"
    assert created["updated_by_name"] is None
    edited = client.patch(f"{NM}/{created['id']}", json={"content": "v2"}).json()
    assert edited["updated_by_name"] == "admin"
    assert client.get(NM).json()["items"][0]["updated_by_name"] == "admin"
