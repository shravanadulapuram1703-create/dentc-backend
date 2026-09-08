"""Twilio Programmable Messaging client — the *only* place the Twilio secrets are used.

Isolating every outbound Twilio call here means the rest of the app (and the
whole test suite) works with **no Twilio configured**: :func:`is_configured`
returns False and the SMS service falls back to durable "log only" storage
(``send_status="queued"``). Flip it on by setting ``TWILIO_ACCOUNT_SID`` plus
either an API key pair or the Auth Token (SMS-1) — no code change.

The official ``twilio`` SDK is deliberately not a dependency: the surface we
use is one REST call (``POST /2010-04-01/Accounts/{sid}/Messages.json``) and
one HMAC check (``X-Twilio-Signature``), both a dozen lines over ``httpx``,
and the SDK pins its own ``requests``/``aiohttp`` stack.

Auth is HTTP Basic ``api_key_sid:api_key_secret`` (preferred — rotatable) or
``account_sid:auth_token``. Neither is ever returned to the browser.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Mapping

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Twilio's own status vocabulary (SMS-1 / SMS-2). ``received`` is the inbound
#: terminal state; the rest describe an outbound message's life.
SEND_STATUSES = (
    "queued", "accepted", "scheduled", "sending", "sent",
    "delivered", "undelivered", "failed", "canceled", "received",
)

#: Ordering used to make the status webhook idempotent: Twilio retries and can
#: deliver callbacks out of order, so a ``sent`` arriving after ``delivered``
#: must not regress the row. Terminal failures always win over progress states.
_STATUS_RANK = {
    "queued": 0, "accepted": 1, "scheduled": 1, "sending": 2, "sent": 3,
    "delivered": 4, "undelivered": 5, "failed": 5, "canceled": 5, "received": 4,
}


def status_rank(status: str | None) -> int:
    return _STATUS_RANK.get((status or "").lower(), -1)


class TwilioError(Exception):
    """A Twilio REST call failed. Carries Twilio's numeric ``code`` (e.g. 21211
    "invalid To number") and a short safe message; credentials are never included."""

    def __init__(self, message: str, *, code: int | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def is_configured() -> bool:
    """True when Twilio can actually send: an Account SID plus a credential."""
    return bool(
        settings.TWILIO_ACCOUNT_SID
        and (
            (settings.TWILIO_API_KEY_SID and settings.TWILIO_API_KEY_SECRET)
            or settings.TWILIO_AUTH_TOKEN
        )
    )


def can_validate_webhooks() -> bool:
    """Signature validation needs the Auth Token specifically (API keys cannot
    verify ``X-Twilio-Signature``)."""
    return bool(settings.TWILIO_AUTH_TOKEN)


def _auth() -> tuple[str, str]:
    if settings.TWILIO_API_KEY_SID and settings.TWILIO_API_KEY_SECRET:
        return settings.TWILIO_API_KEY_SID, settings.TWILIO_API_KEY_SECRET
    return settings.TWILIO_ACCOUNT_SID or "", settings.TWILIO_AUTH_TOKEN or ""


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.TWILIO_API_BASE_URL.rstrip("/"),
        auth=_auth(),
        timeout=settings.TWILIO_TIMEOUT_SECONDS,
        headers={"Accept": "application/json"},
    )


def _short_error(resp: httpx.Response) -> tuple[str, int | None]:
    """Best-effort ``(message, twilio_code)`` from a Twilio error body."""
    try:
        data = resp.json()
        msg = str(data.get("message") or data.get("error_message") or "")[:300]
        code = data.get("code")
        return (msg or f"Twilio HTTP {resp.status_code}"), (int(code) if code is not None else None)
    except Exception:  # noqa: BLE001 — fall back to raw text
        return (resp.text or resp.reason_phrase or f"Twilio HTTP {resp.status_code}")[:300], None


def send_message(
    *,
    to: str,
    body: str,
    from_phone: str | None = None,
    messaging_service_sid: str | None = None,
    status_callback: str | None = None,
) -> dict[str, Any]:
    """Create an outbound message. Returns ``{"sid", "status", "num_segments",
    "error_code", "error_message"}`` from Twilio's response.

    Exactly one of ``messaging_service_sid`` / ``from_phone`` is required — a
    Messaging Service is preferred (Twilio picks the sender, handles STOP/HELP
    and sticky sender). Raises :class:`TwilioError` on any failure.
    """
    if not is_configured():
        raise TwilioError("Twilio is not configured", code=None)
    form: dict[str, str] = {"To": to, "Body": body}
    if messaging_service_sid:
        form["MessagingServiceSid"] = messaging_service_sid
    elif from_phone:
        form["From"] = from_phone
    else:
        raise TwilioError("No sender: neither a Messaging Service SID nor a From number resolved",
                          code=21603)
    if status_callback:
        form["StatusCallback"] = status_callback
    path = f"/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    try:
        with _client() as client:
            resp = client.post(path, data=form)
    except httpx.HTTPError as exc:
        raise TwilioError(f"Twilio unreachable: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        msg, code = _short_error(resp)
        logger.warning("Twilio send rejected (%s %s): %s", resp.status_code, code, msg)
        raise TwilioError(msg, code=code, status_code=resp.status_code)
    data = resp.json()
    segments = data.get("num_segments")
    try:
        segments = int(segments) if segments is not None else None
    except (TypeError, ValueError):
        segments = None
    return {
        "sid": data.get("sid"),
        "status": data.get("status"),
        "num_segments": segments,
        "error_code": data.get("error_code"),
        "error_message": data.get("error_message"),
    }


# ── Webhook signature (SMS-2) ─────────────────────────────────────────────────
def compute_signature(url: str, params: Mapping[str, str], auth_token: str) -> str:
    """Twilio's request-signing scheme: the full URL, then every POST parameter
    ``key+value`` appended in key order, HMAC-SHA1 with the Auth Token, base64."""
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def _url_candidates(request_url: str, path_qs: str) -> list[str]:
    """Twilio signs the URL *it* requested. Behind a proxy the app sees a
    different scheme/host, so try the public base as well and both schemes."""
    out: list[str] = [request_url]
    base = (settings.PUBLIC_API_BASE_URL or "").rstrip("/")
    if base:
        out.append(base + path_qs)
    for u in list(out):
        if u.startswith("https://"):
            out.append("http://" + u[len("https://"):])
        elif u.startswith("http://"):
            out.append("https://" + u[len("http://"):])
    # Twilio also varies on a trailing slash and an explicit default port.
    for u in list(out):
        if u.endswith("/"):
            out.append(u[:-1])
        else:
            out.append(u + "/")
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


def validate_signature(
    *, signature: str | None, request_url: str, path_qs: str, params: Mapping[str, str]
) -> bool:
    """True when ``signature`` matches one of the plausible URLs for this request.

    With ``TWILIO_WEBHOOK_VALIDATE`` off this always returns True (local tunnel
    testing only). With it on and no Auth Token configured it always returns
    False — accepting unsigned "patient replies" is worse than a dead webhook.
    """
    if not settings.TWILIO_WEBHOOK_VALIDATE:
        return True
    token = settings.TWILIO_AUTH_TOKEN
    if not token or not signature:
        return False
    for url in _url_candidates(request_url, path_qs):
        expected = compute_signature(url, params, token)
        if hmac.compare_digest(expected, signature):
            return True
    return False
