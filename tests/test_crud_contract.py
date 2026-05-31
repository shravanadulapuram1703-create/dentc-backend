"""Contract tests that run against EVERY registered CRUD entity.

A single parametrized test asserts the list endpoint of all ~33 entities returns
the standard paginated envelope. A focused round-trip exercises create/read/list/
delete on a simple entity through the generic engine.
"""

from __future__ import annotations

import pytest

from app.api.v1.registry import ALL_CONFIGS

PREFIX = "/api/v1"


@pytest.mark.parametrize("cfg", ALL_CONFIGS, ids=[c.prefix for c in ALL_CONFIGS])
def test_list_endpoint_contract(client, cfg):
    resp = client.get(f"{PREFIX}/{cfg.prefix}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"items", "meta"}
    assert set(body["meta"]) == {"page", "size", "total", "pages"}
    assert isinstance(body["items"], list)


def test_chart_material_round_trip(client):
    base = f"{PREFIX}/chart-materials"

    created = client.post(base, json={"name": "Amalgam", "color": "#888"})
    assert created.status_code == 201, created.text
    obj = created.json()
    assert obj["name"] == "Amalgam"
    assert obj["tenant_id"] == 1  # injected from tenant scope
    mat_id = obj["id"]

    fetched = client.get(f"{base}/{mat_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == mat_id

    listing = client.get(base)
    assert listing.json()["meta"]["total"] == 1

    deleted = client.delete(f"{base}/{mat_id}")
    assert deleted.status_code == 204

    missing = client.get(f"{base}/{mat_id}")
    # chart_materials has no soft-delete column -> hard delete -> 404
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_patient_create_and_search(client):
    base = f"{PREFIX}/patients"
    client.post(base, json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@x.io"})
    client.post(base, json={"first_name": "Alan", "last_name": "Turing", "email": "alan@x.io"})

    all_patients = client.get(base)
    assert all_patients.json()["meta"]["total"] == 2

    searched = client.get(base, params={"search": "Lovelace"})
    assert searched.json()["meta"]["total"] == 1
    assert searched.json()["items"][0]["last_name"] == "Lovelace"
