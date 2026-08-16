"""Transactional email sender (password-reset links, etc.).

Transports, in priority order:

1. **Microsoft Graph** (``sendMail``, app-only/client-credentials) when the
   ``GRAPH_*`` settings are present. Preferred: it works with Entra Security
   Defaults enabled, stores no mailbox password, and is unaffected by the
   Dec-2026 retirement of SMTP basic auth.
2. **SMTP** (stdlib ``smtplib``) when ``SMTP_HOST`` is configured.
3. **Log-only**, so local dev works without creds (the reset link is written to
   the logs and can be copied from there).

Never raises to the caller — a delivery failure must not change the "always 200"
contract of the forgot-password endpoint (which must not leak account existence).
That fail-soft behaviour also means a broken transport is *only* visible in the
logs, so both failure paths below log loudly.
"""

from __future__ import annotations

import smtplib
import ssl
import threading
import time
from email.message import EmailMessage

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_LOGIN_HOST = "https://login.microsoftonline.com"
_GRAPH_HOST = "https://graph.microsoft.com/v1.0"
# Refresh a little before true expiry so a token can't lapse mid-request.
_TOKEN_EXPIRY_SKEW_SECONDS = 60


def _from_address() -> str:
    addr = settings.EMAIL_FROM or settings.SMTP_USER or "no-reply@localhost"
    name = settings.EMAIL_FROM_NAME
    return f"{name} <{addr}>" if name else addr


# ── Microsoft Graph transport ────────────────────────────────────────────────
def graph_is_configured() -> bool:
    return bool(
        settings.GRAPH_TENANT_ID
        and settings.GRAPH_CLIENT_ID
        and settings.GRAPH_CLIENT_SECRET
        and _graph_sender()
    )


def _graph_sender() -> str | None:
    return settings.GRAPH_SENDER or settings.EMAIL_FROM


# Access tokens live ~1h; caching one avoids a token round-trip per email. Guarded
# by a lock because gunicorn workers serve requests on threads.
_token_lock = threading.Lock()
_token_cache: dict[str, float | str | None] = {"value": None, "expires_at": 0.0}


def reset_token_cache() -> None:
    """Drop the cached access token (tests, and after a credential rotation)."""
    with _token_lock:
        _token_cache["value"] = None
        _token_cache["expires_at"] = 0.0


def _graph_token() -> str:
    """Fetch (and cache) an app-only access token via the client-credentials flow."""
    with _token_lock:
        cached, expires_at = _token_cache["value"], _token_cache["expires_at"]
        if cached and time.time() < float(expires_at):
            return str(cached)

        resp = httpx.post(
            f"{_LOGIN_HOST}/{settings.GRAPH_TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id": settings.GRAPH_CLIENT_ID,
                "client_secret": settings.GRAPH_CLIENT_SECRET,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=settings.GRAPH_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            # Surface Entra's own description — it names the cause precisely
            # (bad secret, wrong tenant, consent not granted, …).
            raise RuntimeError(
                f"Graph token request failed ({resp.status_code}): {_describe(resp)}"
            )
        payload = resp.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Graph token response contained no access_token")
        ttl = int(payload.get("expires_in", 3600)) - _TOKEN_EXPIRY_SKEW_SECONDS
        _token_cache["value"] = token
        _token_cache["expires_at"] = time.time() + max(ttl, 0)
        return token


def _describe(resp: httpx.Response) -> str:
    """Best-effort human-readable reason from a Graph/Entra error response."""
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001 — non-JSON error body
        return resp.text[:500]
    if isinstance(data, dict):
        if "error_description" in data:  # Entra token endpoint
            return str(data["error_description"]).splitlines()[0]
        err = data.get("error")
        if isinstance(err, dict):  # Graph API
            return f"{err.get('code')}: {err.get('message')}"
    return str(data)[:500]


def _send_via_graph(to: str, subject: str, body: str) -> bool:
    sender = _graph_sender()
    resp = httpx.post(
        f"{_GRAPH_HOST}/users/{sender}/sendMail",
        headers={"Authorization": f"Bearer {_graph_token()}"},
        json={
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            # The sending identity comes from the mailbox in the URL; setting an
            # explicit "from" here only invites ErrorInvalidUser mismatches.
            "saveToSentItems": settings.GRAPH_SAVE_TO_SENT_ITEMS,
        },
        timeout=settings.GRAPH_TIMEOUT_SECONDS,
    )
    if resp.status_code == 401:
        # A rotated secret or revoked consent can invalidate a cached token early.
        reset_token_cache()
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"Graph sendMail failed ({resp.status_code}): {_describe(resp)}")
    return True


def _send_via_smtp(to: str, subject: str, body: str) -> bool:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _from_address()
    msg["To"] = to
    msg.set_content(body)

    timeout = settings.SMTP_TIMEOUT_SECONDS
    if settings.SMTP_USE_SSL:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout, context=context
        ) as server:
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
            server.send_message(msg)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout) as server:
            if settings.SMTP_USE_TLS:
                server.starttls(context=ssl.create_default_context())
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
            server.send_message(msg)
    return True


def active_transport() -> str:
    """Which transport ``send_email`` will use: ``graph`` | ``smtp`` | ``log``."""
    if graph_is_configured():
        return "graph"
    if settings.SMTP_HOST:
        return "smtp"
    return "log"


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email. Returns True if handed off to a transport.

    Prefers Microsoft Graph, then SMTP, then log-only (dev default). Never raises
    — a delivery failure is logged and returns False.
    """
    transport = active_transport()
    if transport == "log":
        logger.info("EMAIL (log-only, no transport configured) → %s | %s\n%s", to, subject, body)
        return True
    try:
        if transport == "graph":
            _send_via_graph(to, subject, body)
        else:
            _send_via_smtp(to, subject, body)
        logger.info("EMAIL sent via %s → %s | %s", transport, to, subject)
        return True
    except Exception as exc:  # noqa: BLE001 — delivery must never raise to callers
        logger.warning("Email send failed via %s (degraded), %s: %s", transport, to, exc)
        return False


def send_password_reset(to: str, raw_token: str) -> bool:
    link = f"{settings.PASSWORD_RESET_URL_BASE}?token={raw_token}"
    body = (
        "We received a request to reset your password.\n\n"
        f"Reset link (valid for {settings.PASSWORD_RESET_TOKEN_TTL_MINUTES} minutes):\n{link}\n\n"
        "If you didn't request this, you can ignore this email."
    )
    return send_email(to, "Reset your password", body)
