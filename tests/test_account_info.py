"""Account Information module tests (Setup -> Account Info)."""

from __future__ import annotations


def _base(db_session) -> str:
    return f"/api/v1/tenants/{db_session._tenant_id}"


def test_account_settings_upsert_and_secret_hidden(client, db_session):
    base = _base(db_session)
    # First GET creates the row (upsert).
    assert client.get(f"{base}/account-settings").status_code == 200

    r = client.patch(
        f"{base}/account-settings",
        json={"contact_first_name": "Jane", "theme": "blue",
              "ai_assist_client_secret": "topsecret", "max_treatment_plan_discount": 25.5},
    )
    assert r.status_code == 200
    g = client.get(f"{base}/account-settings").json()
    assert g["contact_first_name"] == "Jane"
    assert g["theme"] == "blue"
    assert g["ai_assist_has_secret"] is True
    assert "ai_assist_client_secret" not in g  # write-only, never returned


def test_holidays_federal_range_and_bulk_delete(client, db_session):
    base = _base(db_session)
    fed = client.post(f"{base}/holidays/federal", json={"year": 2026})
    assert fed.status_code == 200
    assert len(fed.json()) == 11

    # Range overlaps Christmas (already imported) -> only the 2 new days are created.
    rng = client.post(f"{base}/holidays/range",
                      json={"from_date": "2026-12-24", "to_date": "2026-12-26", "name": "Winter Break"})
    assert len(rng.json()) == 2

    listed = client.get(f"{base}/holidays").json()
    assert len(listed) == 13
    ids = [listed[0]["id"], listed[1]["id"]]
    deleted = client.post(f"{base}/holidays/bulk-delete", json={"ids": ids}).json()
    assert deleted["deleted"] == 2
    assert len(client.get(f"{base}/holidays").json()) == 11


def test_communications_ein_masked(client, db_session):
    base = _base(db_session)
    r = client.patch(f"{base}/communications", json={"business_name": "Excel Dental", "ein": "123456789"})
    assert r.status_code == 200
    g = client.get(f"{base}/communications").json()
    assert g["business_name"] == "Excel Dental"
    assert g["ein_masked"].endswith("6789")
    assert "ein" not in g  # only masked form is exposed


def test_consent_versioning_and_sanitize(client, db_session):
    base = _base(db_session)
    client.post(f"{base}/consents", json={"header": "C1", "body_html": "<p>Hi</p><script>alert(1)</script>"})
    client.post(f"{base}/consents", json={"header": "C2", "body_html": "<b>Welcome</b>"})

    active = client.get(f"{base}/consents/active").json()
    assert active["version_number"] == 2
    assert active["header"] == "C2"

    all_consents = client.get(f"{base}/consents").json()
    assert len(all_consents) == 2
    v1 = next(c for c in all_consents if c["version_number"] == 1)
    assert "<script" not in v1["body_html"]  # sanitized at write
    assert v1["is_active"] is False           # auto-archived


def test_phone_assignments_max_five_rule(client, db_session):
    base = _base(db_session)
    too_many = {"assignments": [
        {"office_id": i, "assignment_type": "office_specific"} for i in range(1, 7)
    ]}
    assert client.put(f"{base}/phone-assignments", json=too_many).status_code == 422


def test_cross_tenant_path_forbidden(client, db_session):
    # Path tenant must equal the authenticated/effective tenant.
    other = db_session._tenant_id + 9999
    assert client.get(f"/api/v1/tenants/{other}/account-settings").status_code == 403
