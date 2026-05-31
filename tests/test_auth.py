"""Auth happy-path and failure tests (real login, no dependency override)."""

from __future__ import annotations

from app.api.deps import get_current_user, get_tenant_id

PREFIX = "/api/v1"


def _clear_auth_overrides():
    # login/refresh must hit the real code path, not the seeded-user override.
    from app.main import app

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_tenant_id, None)


def test_login_success_and_me(client):
    _clear_auth_overrides()
    resp = client.post(f"{PREFIX}/auth/login", json={"username": "admin", "password": "test1234"})
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]

    me = client.get(f"{PREFIX}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert "password_hash" not in me.json()


def test_login_bad_password(client):
    _clear_auth_overrides()
    resp = client.post(f"{PREFIX}/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_unauthenticated_request_rejected(client):
    _clear_auth_overrides()
    resp = client.get(f"{PREFIX}/patients")
    assert resp.status_code == 401
