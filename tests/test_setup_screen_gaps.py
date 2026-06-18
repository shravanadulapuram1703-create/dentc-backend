"""Setup-screen gap fixes (pick_list / notes-macros / prescriptions / medical / toolbar).

Covers the schema + registry + supplemental-router changes behind the frontend
"Setup screens — backend dev report": PICK-1/2/3, NM-1/4, RX-1, MED-1/3, TB-1/3.
"""

from __future__ import annotations

V1 = "/api/v1"


def _make_header(client, description="Allergies", is_custom=False):
    r = client.post(
        f"{V1}/questionnaire-headers",
        json={"description": description, "is_multi_select": True,
              "is_active": True, "is_custom": is_custom},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── PICK-2: atomic items replace ─────────────────────────────────────────────
def test_pick_list_atomic_replace_creates_normalizes_and_deletes(client):
    header = _make_header(client)
    hid = header["id"]

    # First save: three brand-new items.
    r = client.put(
        f"{V1}/questionnaire-headers/{hid}/options",
        json={"items": [
            {"answer_code": "01"},
            {"answer_code": "02"},
            {"answer_code": "03"},
        ]},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert [i["answer_code"] for i in items] == ["01", "02", "03"]
    assert [i["sort_order"] for i in items] == [1, 2, 3]  # normalised 1-based
    keep_id = items[0]["id"]

    # Second save: keep #1 (renamed), drop #2 & #3, add a new one. One transaction.
    r = client.put(
        f"{V1}/questionnaire-headers/{hid}/options",
        json={"items": [
            {"id": keep_id, "answer_code": "AA"},
            {"answer_code": "ZZ"},
        ]},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert [i["answer_code"] for i in items] == ["AA", "ZZ"]
    assert [i["sort_order"] for i in items] == [1, 2]
    assert items[0]["id"] == keep_id  # kept row preserved its id

    # The generic list endpoint agrees the dropped items are gone.
    r = client.get(f"{V1}/questionnaire-options", params={"questionnaire_id": hid})
    assert r.json()["meta"]["total"] == 2


def test_pick_list_replace_unknown_header_404(client):
    r = client.put(
        f"{V1}/questionnaire-headers/999999/options",
        json={"items": [{"answer_code": "01"}]},
    )
    assert r.status_code == 404


# ── PICK-1: cascade delete ───────────────────────────────────────────────────
def test_pick_list_cascade_delete_removes_items_and_soft_deletes_header(client):
    header = _make_header(client)
    hid = header["id"]
    client.put(
        f"{V1}/questionnaire-headers/{hid}/options",
        json={"items": [{"answer_code": "01"}, {"answer_code": "02"}]},
    )

    r = client.delete(f"{V1}/questionnaire-headers/{hid}/cascade")
    assert r.status_code == 200, r.text
    assert r.json() == {"header_id": hid, "options_deleted": 2}

    # Header soft-deleted (is_active False); options gone entirely.
    got = client.get(f"{V1}/questionnaire-headers/{hid}").json()
    assert got["is_active"] is False
    assert client.get(
        f"{V1}/questionnaire-options", params={"questionnaire_id": hid}
    ).json()["meta"]["total"] == 0


# ── PICK-3: is_custom filter splits Manage vs Custom ─────────────────────────
def test_questionnaire_header_is_custom_filter(client):
    _make_header(client, "Built-in list", is_custom=False)
    _make_header(client, "User list", is_custom=True)

    custom = client.get(f"{V1}/questionnaire-headers", params={"is_custom": True}).json()
    assert [h["description"] for h in custom["items"]] == ["User list"]
    builtin = client.get(f"{V1}/questionnaire-headers", params={"is_custom": False}).json()
    assert [h["description"] for h in builtin["items"]] == ["Built-in list"]


# ── NM-1 category filter + NM-4 audit columns ────────────────────────────────
def test_note_macro_category_filter_and_audit(client):
    client.post(f"{V1}/note-macros", json={"name": "A", "content": "x", "category": "DIAGNOSTIC"})
    m2 = client.post(
        f"{V1}/note-macros", json={"name": "B", "content": "y", "category": "PERIO"}
    ).json()

    filtered = client.get(f"{V1}/note-macros", params={"category": "PERIO"}).json()
    assert [m["name"] for m in filtered["items"]] == ["B"]

    # NM-4: updated_by/updated_at populate on edit.
    assert m2["updated_by"] is None
    edited = client.patch(f"{V1}/note-macros/{m2['id']}", json={"content": "z"}).json()
    assert edited["updated_by"] is not None
    assert edited["updated_at"] is not None


# ── RX-1: prescription_library Modified By ───────────────────────────────────
def test_prescription_library_modified_by(client):
    rx = client.post(f"{V1}/prescription-library", json={"drug_name": "Amoxicillin 500mg"}).json()
    assert rx["updated_by"] is None
    edited = client.patch(
        f"{V1}/prescription-library/{rx['id']}", json={"sig": "Take one"}
    ).json()
    assert edited["updated_by"] is not None


# ── MED-1 / TB-1 group_type filter + MED-3 input_type + audit ────────────────
def test_definition_group_type_filter(client):
    client.post(f"{V1}/definition-groups",
                json={"group_code": "G1", "description": "Alerts", "group_type": "MEDALERT"})
    client.post(f"{V1}/definition-groups",
                json={"group_code": "G2", "description": "Toolbars", "group_type": "TOOLBAR"})

    med = client.get(f"{V1}/definition-groups", params={"group_type": "MEDALERT"}).json()
    assert [g["description"] for g in med["items"]] == ["Alerts"]


def test_definition_input_type_and_audit(client):
    d = client.post(
        f"{V1}/definitions",
        json={"group_code": "MEDQUEST", "key1": "Q1",
              "description": "Do you smoke?", "input_type": "YESNO"},
    ).json()
    assert d["input_type"] == "YESNO"
    assert d["updated_by"] is None
    edited = client.patch(f"{V1}/definitions/{d['id']}", json={"input_type": "TEXT"}).json()
    assert edited["input_type"] == "TEXT"
    assert edited["updated_by"] is not None
