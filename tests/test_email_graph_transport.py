"""KAN-12 — Microsoft Graph (app-only) email transport.

No network: the httpx calls are stubbed. What matters is that the transport is
selected correctly, the token is cached and re-fetched appropriately, the
sendMail payload is well-formed, and every failure stays fail-soft so the
forgot-password endpoint keeps its "always 200" contract.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import settings
from app.integrations import email as E


@pytest.fixture(autouse=True)
def _clean_token_cache():
    E.reset_token_cache()
    yield
    E.reset_token_cache()


@pytest.fixture
def graph_configured(monkeypatch):
    monkeypatch.setattr(settings, "GRAPH_TENANT_ID", "tenant-uuid", raising=False)
    monkeypatch.setattr(settings, "GRAPH_CLIENT_ID", "client-uuid", raising=False)
    monkeypatch.setattr(settings, "GRAPH_CLIENT_SECRET", "shhh", raising=False)
    monkeypatch.setattr(settings, "GRAPH_SENDER", "admin@reckondental.com", raising=False)


def _resp(status: int, json_body=None, text="") -> httpx.Response:
    return httpx.Response(
        status_code=status, json=json_body, text=None if json_body else text,
        request=httpx.Request("POST", "https://example.invalid"),
    )


# ── transport selection ──────────────────────────────────────────────────────
def test_graph_preferred_over_smtp(monkeypatch, graph_configured):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.office365.com", raising=False)
    assert E.active_transport() == "graph"


def test_falls_back_to_smtp_without_graph(monkeypatch):
    monkeypatch.setattr(settings, "GRAPH_TENANT_ID", None, raising=False)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.office365.com", raising=False)
    assert E.active_transport() == "smtp"


def test_log_only_when_nothing_configured(monkeypatch):
    monkeypatch.setattr(settings, "GRAPH_TENANT_ID", None, raising=False)
    monkeypatch.setattr(settings, "SMTP_HOST", None, raising=False)
    assert E.active_transport() == "log"
    assert E.send_email("a@b.com", "s", "b") is True


def test_partial_graph_config_does_not_activate(monkeypatch):
    """A half-filled GRAPH_* block must not silently shadow a working SMTP setup."""
    monkeypatch.setattr(settings, "GRAPH_TENANT_ID", "tenant-uuid", raising=False)
    monkeypatch.setattr(settings, "GRAPH_CLIENT_ID", "client-uuid", raising=False)
    monkeypatch.setattr(settings, "GRAPH_CLIENT_SECRET", None, raising=False)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.office365.com", raising=False)
    assert E.active_transport() == "smtp"


# ── send path ────────────────────────────────────────────────────────────────
def test_sendmail_payload_and_success(monkeypatch, graph_configured):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        if "oauth2" in url:
            return _resp(200, {"access_token": "tok-abc", "expires_in": 3600})
        return _resp(202)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert E.send_email("user@example.com", "Reset your password", "link here") is True

    token_url, token_kw = calls[0]
    assert token_url == "https://login.microsoftonline.com/tenant-uuid/oauth2/v2.0/token"
    assert token_kw["data"]["grant_type"] == "client_credentials"
    assert token_kw["data"]["scope"] == "https://graph.microsoft.com/.default"

    mail_url, mail_kw = calls[1]
    assert mail_url == "https://graph.microsoft.com/v1.0/users/admin@reckondental.com/sendMail"
    assert mail_kw["headers"]["Authorization"] == "Bearer tok-abc"
    msg = mail_kw["json"]["message"]
    assert msg["subject"] == "Reset your password"
    assert msg["toRecipients"] == [{"emailAddress": {"address": "user@example.com"}}]
    # Sender identity comes from the URL mailbox, not an explicit "from".
    assert "from" not in msg


def test_token_is_cached_across_sends(monkeypatch, graph_configured):
    token_calls = []

    def fake_post(url, **kw):
        if "oauth2" in url:
            token_calls.append(url)
            return _resp(200, {"access_token": "tok", "expires_in": 3600})
        return _resp(202)

    monkeypatch.setattr(httpx, "post", fake_post)
    E.send_email("a@example.com", "s", "b")
    E.send_email("b@example.com", "s", "b")
    assert len(token_calls) == 1


def test_expired_token_is_refetched(monkeypatch, graph_configured):
    token_calls = []

    def fake_post(url, **kw):
        if "oauth2" in url:
            token_calls.append(url)
            # expires_in below the skew ⇒ cached token is already stale.
            return _resp(200, {"access_token": "tok", "expires_in": 1})
        return _resp(202)

    monkeypatch.setattr(httpx, "post", fake_post)
    E.send_email("a@example.com", "s", "b")
    E.send_email("b@example.com", "s", "b")
    assert len(token_calls) == 2


# ── failure handling ─────────────────────────────────────────────────────────
def test_bad_secret_is_fail_soft(monkeypatch, graph_configured, caplog):
    def fake_post(url, **kw):
        return _resp(401, {"error": "invalid_client",
                           "error_description": "AADSTS7000215: Invalid client secret provided."})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert E.send_email("a@example.com", "s", "b") is False
    assert "AADSTS7000215" in caplog.text  # the operator needs the real cause


def test_missing_consent_is_fail_soft(monkeypatch, graph_configured, caplog):
    def fake_post(url, **kw):
        if "oauth2" in url:
            return _resp(200, {"access_token": "tok", "expires_in": 3600})
        return _resp(403, {"error": {"code": "ErrorAccessDenied",
                                     "message": "Access to OData is disabled."}})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert E.send_email("a@example.com", "s", "b") is False
    assert "ErrorAccessDenied" in caplog.text


def test_401_on_send_clears_cached_token(monkeypatch, graph_configured):
    """A rotated secret must not wedge the process behind a stale cached token."""
    def fake_post(url, **kw):
        if "oauth2" in url:
            return _resp(200, {"access_token": "tok", "expires_in": 3600})
        return _resp(401, {"error": {"code": "InvalidAuthenticationToken", "message": "expired"}})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert E.send_email("a@example.com", "s", "b") is False
    assert E._token_cache["value"] is None


def test_network_error_is_fail_soft(monkeypatch, graph_configured):
    def fake_post(url, **kw):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "post", fake_post)
    assert E.send_email("a@example.com", "s", "b") is False


def test_password_reset_goes_through_graph(monkeypatch, graph_configured):
    sent = {}

    def fake_post(url, **kw):
        if "oauth2" in url:
            return _resp(200, {"access_token": "tok", "expires_in": 3600})
        sent.update(kw["json"]["message"])
        return _resp(202)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert E.send_password_reset("user@example.com", "RAW-TOKEN") is True
    assert "RAW-TOKEN" in sent["body"]["content"]
    assert settings.PASSWORD_RESET_URL_BASE in sent["body"]["content"]
