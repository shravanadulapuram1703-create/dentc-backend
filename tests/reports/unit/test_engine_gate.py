"""ENG-01 / ENG-02 / ENG-56 thin parts: engine gate, fail-closed settings, headers, Redis ns."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings, settings
from app.main import app
from app.reports.gate import configuration_problems
from app.services import messaging_events as me


@pytest.fixture
def engine_flag():
    old = settings.REPORTS_ENGINE_ENABLED
    yield
    settings.REPORTS_ENGINE_ENABLED = old


# NB: the ``client`` fixture overrides get_current_user, so these tests exercise the
# gate, not authentication (the router also depends on get_current_user).


def test_catalog_is_404_when_engine_disabled(client, engine_flag):
    settings.REPORTS_ENGINE_ENABLED = False
    r = client.get("/api/v1/reports/catalog")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "reports_engine_disabled"


def test_catalog_is_404_unauthenticated_when_disabled(client, engine_flag):
    settings.REPORTS_ENGINE_ENABLED = False
    r = client.get("/api/v1/reports/catalog")
    assert r.status_code == 404


def test_catalog_is_200_when_engine_enabled(client, engine_flag):
    settings.REPORTS_ENGINE_ENABLED = True
    r = client.get("/api/v1/reports/catalog")
    assert r.status_code == 200, r.text
    assert r.json() == {"reports": []}


def test_openapi_has_engine_paths_and_no_internal_paths():
    paths = app.openapi()["paths"]
    assert "/api/v1/reports/catalog" in paths
    assert paths["/api/v1/reports/catalog"]["get"]["operationId"] == "list_report_catalog"
    assert not [p for p in paths if "/internal/" in p]


def test_service_role_all_refused_outside_dev():
    with pytest.raises(PydanticValidationError):
        Settings(ENV="prod", SERVICE_ROLE="all", _env_file=None)
    assert Settings(ENV="dev", SERVICE_ROLE="all", _env_file=None).SERVICE_ROLE == "all"


def test_prod_with_local_storage_is_misconfigured():
    cfg = Settings(ENV="prod", REPORT_STORAGE_BACKEND="local", _env_file=None)
    assert configuration_problems(cfg)
    cfg = Settings(ENV="prod", GCS_BUCKET_DOCUMENTS=None, GCS_BUCKET_REPORTS=None, _env_file=None)
    assert configuration_problems(cfg) == ["GCS_BUCKET_REPORTS or GCS_BUCKET_DOCUMENTS"]
    cfg = Settings(ENV="prod", GCS_BUCKET_REPORTS="rd-x-reports", _env_file=None)
    assert configuration_problems(cfg) == []
    assert configuration_problems(Settings(ENV="dev", _env_file=None)) == []


def test_prod_misconfiguration_answers_503(client, engine_flag, monkeypatch):
    settings.REPORTS_ENGINE_ENABLED = True
    monkeypatch.setattr(settings, "ENV", "prod")
    monkeypatch.setattr(settings, "REPORT_STORAGE_BACKEND", "local")
    r = client.get("/api/v1/reports/catalog")
    assert r.status_code == 503
    body = r.json()["error"]
    assert body["code"] == "reports_engine_misconfigured"
    assert body["details"]["missing"]


def test_content_disposition_is_exposed(client):
    r = client.options(
        "/api/v1/reports/catalog",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    exposed = r.headers.get("access-control-expose-headers", "")
    assert "Content-Disposition" in exposed


def test_redis_namespace_separates_channels(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_NAMESPACE", "")
    plain_user, plain_tenant = me.channel_for(7, 42), me.tenant_channel_for(7)
    assert plain_user == "msg:7:42"
    assert me._parse_channel(plain_user) == (7, 42)

    monkeypatch.setattr(settings, "REDIS_NAMESPACE", "clienta")
    a_user = me.channel_for(7, 42)
    assert a_user == "clienta:msg:7:42"
    assert me._parse_channel(a_user) == (7, 42)
    assert me._parse_channel(me.tenant_channel_for(7)) == (7, None)
    # Envelopes of a namespace-less service or of another client are not ours.
    assert me._parse_channel(plain_user) is None
    assert me._parse_channel(plain_tenant) is None
    assert me._parse_channel("clientb:msg:7:42") is None

    monkeypatch.setattr(settings, "REDIS_NAMESPACE", "clientb")
    assert me._parse_channel(a_user) is None
