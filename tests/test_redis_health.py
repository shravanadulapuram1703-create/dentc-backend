"""Redis health endpoint + helper (local ⇄ cloud connectivity check).

The suite runs with Redis off, so the "down" path is the default. For the "up"
path we swap in a tiny in-memory stub for ``redis.Redis`` — Docker/Memorystore
aren't reachable from CI — which is enough to prove the set/get round-trip and the
endpoint's status mapping.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.integrations import redis_store


class _FakeRedis:
    """Just enough of redis.Redis for the health round-trip."""

    _store: dict[str, str] = {}

    def __init__(self, **kwargs):
        pass

    def set(self, key, value, ex=None):
        type(self)._store[key] = value

    def get(self, key):
        return type(self)._store.get(key)

    def ping(self):
        return True


@pytest.fixture
def redis_up(monkeypatch):
    """Make redis_store see a reachable (fake) Redis."""
    monkeypatch.setattr(settings, "REDIS_ENABLED", True)

    class _Module:
        Redis = _FakeRedis

    monkeypatch.setattr(redis_store, "_redis", _Module)
    _FakeRedis._store.clear()


def test_health_reports_disabled_when_off(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_ENABLED", False)
    result = redis_store.health()
    assert result["connected"] is False
    assert result["enabled"] is False


def test_health_reports_connected_when_up(redis_up):
    result = redis_store.health()
    assert result["connected"] is True
    assert result["enabled"] is True


def test_health_endpoint_ok_when_up(client, redis_up):
    body = client.get("/health/redis").json()
    assert body["status"] == "ok"
    assert body["connected"] is True


def test_health_endpoint_degraded_when_down(client, monkeypatch):
    """Down Redis must degrade, not 500 — the check has to stay reachable."""
    monkeypatch.setattr(settings, "REDIS_ENABLED", True)

    class _Boom:
        class Redis:
            def __init__(self, **kwargs):
                raise ConnectionError("no route to host")

    monkeypatch.setattr(redis_store, "_redis", _Boom)

    resp = client.get("/health/redis")
    assert resp.status_code == 200  # never 500
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["connected"] is False
    assert "no route to host" in body["detail"]
