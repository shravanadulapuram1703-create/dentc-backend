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


def test_invalid_production_origin_variants_are_not_reflected(client):
    """Regression for the incident report §4: with `allow_credentials=True` we must
    NOT reflect arbitrary/near-miss origins (insecure http, trailing slash, look-alike
    hostname). Only the exact allow-list + tight regex may match."""
    for origin in (
        "http://reckondental.com",  # insecure scheme
        "https://reckondental.com/",  # trailing slash
        "https://notreckondental.com",  # look-alike hostname
        "https://reckondental.com.evil.com",  # suffix-attack hostname
    ):
        r = client.options(
            f"{PREFIX}/auth/login",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
        assert r.headers.get("access-control-allow-origin") != origin, origin


def test_wildcard_origin_is_stripped_when_credentials_enabled():
    """A `CORS_ORIGINS=*` (env or default) must be dropped, since Starlette would
    otherwise reflect any origin back alongside allow-credentials."""
    from app.core.config import Settings

    s = Settings(CORS_ORIGINS="*")
    assert "*" not in s.CORS_ORIGINS

    s2 = Settings(CORS_ORIGINS="*,https://reckondental.com")
    assert s2.CORS_ORIGINS == ["https://reckondental.com"]


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


def test_unhandled_500_still_carries_cors_header(db_session):
    """Regression for the appointments incident: an *unhandled* 500 (e.g. a bad DB
    query) must still carry CORS headers, so the browser sees a real 500 instead of a
    phantom 'No Access-Control-Allow-Origin' error. CatchAllMiddleware (inside CORS)
    guarantees this — FastAPI's built-in 500 handler runs above CORS and would not."""
    from fastapi.testclient import TestClient

    from app.main import app

    path = "/api/v1/__boom_test__"

    async def _boom():
        raise RuntimeError("boom")

    app.add_api_route(path, _boom, methods=["GET"], include_in_schema=False)
    try:
        # raise_server_exceptions=False so the client returns the 500 response
        # instead of re-raising, letting us inspect the headers the browser would see.
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get(path, headers={"Origin": CLOUD_RUN_FE})
        assert r.status_code == 500
        assert r.headers.get("access-control-allow-origin") == CLOUD_RUN_FE
        assert r.json()["error"]["code"] == "internal_error"
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", None) != path]
