"""PT-SEARCH-1/2: Patient ID / Legacy ID search on ``GET /patients``.

A Legacy-ID search used to be silently ignored (``?legacy_id=`` was not a
declared filter, and free-text ``search`` never reached the column), so the
frontend got an unfiltered page 1 back. ``?id=`` / ``?ids=`` give the by-id
search the same paged, office/active-filtered code path as every other mode.
"""

from __future__ import annotations

import pytest

from app.db.models import Office, Patient


@pytest.fixture
def roster(db_session):
    t = db_session._tenant_id
    o1 = Office(tenant_id=t, name="Main", office_code="MAIN", is_active=True)
    o2 = Office(tenant_id=t, name="Annex", office_code="ANX", is_active=True)
    db_session.add_all([o1, o2])
    db_session.commit()
    rows = [
        Patient(tenant_id=t, first_name="Ann", last_name="Legacy", legacy_id="100001",
                home_office_id=o1.id, is_active=True),
        Patient(tenant_id=t, first_name="Bob", last_name="Legacy", legacy_id="10021076",
                home_office_id=o2.id, is_active=True),
        Patient(tenant_id=t, first_name="Cid", last_name="Inactive", legacy_id="100002",
                home_office_id=o1.id, is_active=False),
        Patient(tenant_id=t, first_name="Dee", last_name="Native", legacy_id=None,
                home_office_id=o1.id, is_active=True),
    ]
    db_session.add_all(rows)
    db_session.commit()
    for r in rows:
        db_session.refresh(r)
    return {"offices": (o1, o2), "patients": rows}


def _ids(payload) -> list[int]:
    return [row["id"] for row in payload["items"]]


def test_legacy_id_filter_is_exact(client, roster):
    ann, bob, *_ = roster["patients"]
    r = client.get("/api/v1/patients", params={"legacy_id": "10021076"}).json()
    assert r["meta"]["total"] == 1
    assert _ids(r) == [bob.id]
    assert r["items"][0]["legacy_id"] == "10021076"
    # A prefix of a real id is not a hit — exact, never substring.
    assert client.get("/api/v1/patients", params={"legacy_id": "1000"}).json()["meta"]["total"] == 0
    r = client.get("/api/v1/patients", params={"legacy_id": "100001"}).json()
    assert _ids(r) == [ann.id]


def test_legacy_id_unknown_is_empty_not_unfiltered(client, roster):
    # The bug being fixed: an unknown value used to return page 1 of everyone.
    r = client.get("/api/v1/patients", params={"legacy_id": "ZZZNOPE", "size": 1}).json()
    assert r["meta"]["total"] == 0
    assert r["items"] == []
    # An explicit blank is "match nothing" too, not "ignore the filter".
    assert client.get("/api/v1/patients?legacy_id=").json()["meta"]["total"] == 0


def test_legacy_id_filter_tolerates_pasted_whitespace(client, roster):
    bob = roster["patients"][1]
    r = client.get("/api/v1/patients", params={"legacy_id": "  10021076 "}).json()
    assert _ids(r) == [bob.id]


def test_legacy_id_combines_with_office_and_active_filters(client, roster):
    o1, o2 = roster["offices"]
    ann, bob, cid, _ = roster["patients"]
    # "Search In: Current Office" — Bob belongs to the Annex, so the Main office
    # search must not find him.
    assert client.get("/api/v1/patients", params={
        "legacy_id": "10021076", "home_office_id": o1.id}).json()["meta"]["total"] == 0
    assert _ids(client.get("/api/v1/patients", params={
        "legacy_id": "10021076", "home_office_id": o2.id}).json()) == [bob.id]
    # "Include Inactive" off -> an inactive legacy id is hidden; on -> found.
    assert client.get("/api/v1/patients", params={
        "legacy_id": "100002", "is_active": "true"}).json()["meta"]["total"] == 0
    assert _ids(client.get("/api/v1/patients", params={
        "legacy_id": "100002", "is_active": "false"}).json()) == [cid.id]


def test_free_text_search_resolves_a_legacy_id(client, roster):
    # Dashboard Quick Search has no mode selector: a typed legacy id must hit.
    ann, bob, *_ = roster["patients"]
    r = client.get("/api/v1/patients", params={"search": "10021076"}).json()
    assert _ids(r) == [bob.id]
    r = client.get("/api/v1/patients", params={"search": "100001"}).json()
    assert _ids(r) == [ann.id]
    # Exact only — a name search is not polluted by partial id matches.
    r = client.get("/api/v1/patients", params={"search": "Legacy"}).json()
    assert sorted(_ids(r)) == sorted([ann.id, bob.id])


def test_legacy_id_ranks_first_when_it_also_matches_a_name(client, roster, db_session):
    # A patient whose *chart number* happens to equal someone else's legacy id
    # ties for the exact tier; a mere name-prefix hit must sort behind both.
    t = db_session._tenant_id
    twin = Patient(tenant_id=t, first_name="100001x", last_name="Prefixy", is_active=True)
    db_session.add(twin)
    db_session.commit()
    r = client.get("/api/v1/patients", params={"search": "100001"}).json()
    assert _ids(r)[0] == roster["patients"][0].id


def test_id_filter_shares_the_list_code_path(client, roster):
    o1, o2 = roster["offices"]
    ann, bob, cid, dee = roster["patients"]
    r = client.get("/api/v1/patients", params={"id": bob.id}).json()
    assert r["meta"]["total"] == 1 and _ids(r) == [bob.id]
    # ...so the advanced filters apply server-side instead of being re-applied
    # client-side on the single /patients/{id} row.
    assert client.get("/api/v1/patients", params={
        "id": bob.id, "home_office_id": o1.id}).json()["meta"]["total"] == 0
    assert client.get("/api/v1/patients", params={
        "id": cid.id, "is_active": "true"}).json()["meta"]["total"] == 0
    assert _ids(client.get("/api/v1/patients", params={
        "id": cid.id, "is_active": "false"}).json()) == [cid.id]
    # Unknown id -> empty page, not an unfiltered one.
    assert client.get("/api/v1/patients", params={"id": 999999}).json()["meta"]["total"] == 0
    # A non-numeric id is a typed-param 422, not a silent ignore.
    assert client.get("/api/v1/patients", params={"id": "abc"}).status_code == 422


def test_ids_batch_filter(client, roster):
    ann, bob, cid, dee = roster["patients"]
    r = client.get("/api/v1/patients", params={"ids": f"{ann.id},{dee.id}, 999999"}).json()
    assert sorted(_ids(r)) == sorted([ann.id, dee.id])
    # ids composes with the other filters like any list call.
    assert client.get("/api/v1/patients", params={
        "ids": f"{ann.id},{bob.id}", "home_office_id": roster["offices"][1].id,
    }).json()["meta"]["total"] == 1


def test_openapi_declares_the_new_params(client):
    spec = client.get("/api/v1/openapi.json").json()
    names = {p["name"] for p in spec["paths"]["/api/v1/patients"]["get"]["parameters"]}
    assert {"legacy_id", "id", "ids"} <= names
