"""CORS regression tests.

Guards the two failure modes that broke the deployed login:
1. The Cloud Run frontend origin must be allowed (via CORS_ORIGIN_REGEX).
2. CORS headers must be present even on error responses (CORS middleware is
   outermost), so a 4xx/5xx from login never surfaces in the browser as a
   misleading "No 'Access-Control-Allow-Origin' header" error.
"""

from __future__ import annotations

from app.api.deps import get_current_user, get_tenant_id

PREFIX = "/api/v1"
CLOUD_RUN_FE = "https://dentc-frontend-477406612596.us-central1.run.app"


def _clear_auth_overrides():
    from app.main import app

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_tenant_id, None)


def test_preflight_allows_cloud_run_frontend(client):
    r = client.options(
        f"{PREFIX}/auth/login",
        headers={
            "Origin": CLOUD_RUN_FE,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("access-control-allow-origin") == CLOUD_RUN_FE
    assert r.headers.get("access-control-allow-credentials") == "true"


def test_preflight_allows_production_domain(client):
    origin = "https://reckondental.com"
    r = client.options(
        f"{PREFIX}/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("access-control-allow-origin") == origin
    assert r.headers.get("access-control-allow-credentials") == "true"


def test_preflight_allows_localhost_exact_origin(client):
    r = client.options(
        f"{PREFIX}/auth/login",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_disallowed_origin_gets_no_cors_header(client):
    r = client.options(
        f"{PREFIX}/auth/login",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    # Starlette returns 400 for a disallowed preflight; crucially no ACAO is echoed.
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"


def test_error_response_still_carries_cors_header(client):
    """A 401 from login must still include the CORS header (middleware outermost)."""
    _clear_auth_overrides()
    r = client.post(
        f"{PREFIX}/auth/login",
        headers={"Origin": CLOUD_RUN_FE},
        json={"username": "__nouser__", "password": "wrong"},
    )
    assert r.status_code == 401
    assert r.headers.get("access-control-allow-origin") == CLOUD_RUN_FE
