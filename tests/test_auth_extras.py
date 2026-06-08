"""Tests for the Authentication module extras (login dev-report §2.1–2.5, §4).

Covers forgot/reset password, legacy-user activation, and the standardized
disabled-account (403) login response. Redis is disabled in tests (conftest), so
the failed-attempt lockout (423) degrades to off and is not exercised here.
"""

from __future__ import annotations

from app.api.deps import get_current_user, get_tenant_id
from app.core.security import hash_password
from app.db.models import User
from app.services import auth_extras_service

PREFIX = "/api/v1"


def _clear_auth_overrides():
    from app.main import app

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_tenant_id, None)


def _make_user(db, *, username, email, password="orig1234", **kw) -> User:
    user = User(
        tenant_id=db._tenant_id,  # type: ignore[attr-defined]
        username=username,
        email=email,
        password_hash=hash_password(password),
        role="staff",
        is_active=kw.pop("is_active", True),
        **kw,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── §4 disabled account → 403 ────────────────────────────────────────────────
def test_login_disabled_account_returns_403(client, db_session):
    _clear_auth_overrides()
    _make_user(db_session, username="disabled", email="disabled@x.local", is_active=False)
    r = client.post(f"{PREFIX}/auth/login", json={"username": "disabled", "password": "orig1234"})
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "account_disabled"


# ── §2.1 forgot password (always 200, no enumeration) ────────────────────────
def test_forgot_password_always_200(client):
    _clear_auth_overrides()
    known = client.post(f"{PREFIX}/auth/forgot-password", json={"email": "admin@test.local"})
    unknown = client.post(f"{PREFIX}/auth/forgot-password", json={"email": "nobody@nowhere.local"})
    assert known.status_code == 200 and unknown.status_code == 200
    # Identical message regardless of existence.
    assert known.json()["message"] == unknown.json()["message"]


# ── §2.2 / §2.3 reset password flow ──────────────────────────────────────────
def test_reset_password_flow(client, db_session):
    _clear_auth_overrides()
    user = _make_user(db_session, username="resetme", email="reset@x.local", password="orig1234")
    raw = auth_extras_service._issue_token(
        db_session, user, auth_extras_service.PURPOSE_RESET, 60
    )

    valid = client.post(f"{PREFIX}/auth/reset-password/validate", json={"token": raw})
    assert valid.status_code == 200, valid.text
    assert valid.json() == {"valid": True, "email": "reset@x.local"}

    done = client.post(
        f"{PREFIX}/auth/reset-password", json={"token": raw, "new_password": "brandnew123"}
    )
    assert done.status_code == 200, done.text

    # New password works; old one no longer does.
    assert client.post(
        f"{PREFIX}/auth/login", json={"username": "resetme", "password": "brandnew123"}
    ).status_code == 200
    assert client.post(
        f"{PREFIX}/auth/login", json={"username": "resetme", "password": "orig1234"}
    ).status_code == 401

    # Token is single-use → now invalid.
    assert client.post(
        f"{PREFIX}/auth/reset-password/validate", json={"token": raw}
    ).json()["valid"] is False


def test_reset_password_invalid_token(client):
    _clear_auth_overrides()
    r = client.post(
        f"{PREFIX}/auth/reset-password", json={"token": "garbage", "new_password": "whatever123"}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_reset_token"


# ── §2.4 / §2.5 legacy activation flow ───────────────────────────────────────
def test_legacy_activation_flow(client, db_session):
    _clear_auth_overrides()
    _make_user(
        db_session, username="legacy", email="legacy@x.local",
        password="cannotuse", is_legacy_user=True, legacy_activation_completed=False,
    )

    verify = client.post(f"{PREFIX}/auth/legacy-user/verify", json={"username_or_email": "legacy"})
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["eligible"] is True
    assert body["legacy_activation_completed"] is False
    assert body["verification_method"] == "email"
    assert body["masked_email"] == "l•••@x.local"
    token = body["activation_token"]
    assert token

    created = client.post(
        f"{PREFIX}/auth/legacy-user/create-password",
        json={"username_or_email": "legacy", "new_password": "newsecret1", "activation_token": token},
    )
    assert created.status_code == 200, created.text

    # Can now log in with the new password.
    assert client.post(
        f"{PREFIX}/auth/login", json={"username": "legacy", "password": "newsecret1"}
    ).status_code == 200

    # Re-verify → blocked as already activated (Business Rule 2).
    again = client.post(f"{PREFIX}/auth/legacy-user/verify", json={"username_or_email": "legacy"})
    assert again.json()["eligible"] is False
    assert again.json()["legacy_activation_completed"] is True

    # Old activation token is consumed → reuse rejected (Rule 3).
    reuse = client.post(
        f"{PREFIX}/auth/legacy-user/create-password",
        json={"username_or_email": "legacy", "new_password": "another12", "activation_token": token},
    )
    assert reuse.status_code == 422


def test_legacy_verify_non_legacy_user_not_eligible(client, db_session):
    _clear_auth_overrides()
    _make_user(db_session, username="modern", email="modern@x.local", is_legacy_user=False)
    r = client.post(f"{PREFIX}/auth/legacy-user/verify", json={"username_or_email": "modern"})
    assert r.status_code == 200
    assert r.json()["eligible"] is False
    assert r.json()["activation_token"] is None
