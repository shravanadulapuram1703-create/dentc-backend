"""RingCentral SMS (Messaging) client — the *only* place the RingCentral
secrets are used. Replaces :mod:`twilio_client` (SMS-1/2/7/8).

Isolating every outbound RingCentral call here means the rest of the app
(and the whole test suite) works with **no RingCentral configured**:
:func:`is_configured` returns False and the SMS service falls back to
durable "log only" storage (``send_status="queued"``). Flip it on by setting
``RC_APP_CLIENT_ID`` + ``RC_APP_CLIENT_SECRET`` + ``RC_USER_JWT`` — no code
change.

Auth, send, and subscription-create request/error shapes below were
confirmed against the real live API on 2026-10-01 (see the PR description /
commit messages for the exact calls run). The one piece that could **not**
be verified the same way: the shape of a *successful* send response and of
a delivered Message Event notification — this account's phone numbers have
no SMS-enabled (TCR-approved) number yet, so every real send attempt 403s
with ``FeatureNotAvailable`` before a success response is ever produced.
Both are written defensively against RingCentral's documented Message
object shape (``id``, ``to``, ``from``, ``messageStatus``, ...) and must be
re-checked against a real response the moment TCR clears — same discipline
the Stedi claims integration used for its own not-yet-enabled endpoint.

The official ``ringcentral`` SDK is deliberately not a dependency, same
reasoning as ``twilio_client``: the surface used here is small enough that
plain ``httpx`` keeps the dependency footprint down and the call shapes
explicit and auditable.
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: RingCentral's own message-status vocabulary (confirmed via the SMS quick
#: start's polling example and the high-volume SMS guide), lowercased to
#: match what actually lands in sms_messages.send_status — sms_service
#: always lowercases RingCentral's raw Title-Case ``messageStatus`` on the
#: way in (``_dispatch``/``handle_status``), so this must match or a
#: metadata-driven status filter/dropdown won't line up with real rows.
#: Unlike Twilio there is no single documented terminal/progress ordering
#: published, so SEND_STATUSES exists for display purposes; status_rank
#: below encodes the ordering actually relied on for idempotent webhook
#: handling.
SEND_STATUSES = (
    "queued", "sendingfailed", "sent", "delivered", "deliveryfailed", "received",
)

#: Mirrors twilio_client.status_rank's purpose: a stale/out-of-order
#: notification must never regress a row. Ranking is this integration's own
#: judgment call (not something RingCentral documents), based on the
#: terminal-vs-progress states the quick start's polling loop treats as such.
_STATUS_RANK = {
    "queued": 0, "sending": 1, "sent": 2,
    "delivered": 3, "deliveryfailed": 3, "sendingfailed": 3, "received": 3,
}


def status_rank(status: str | None) -> int:
    return _STATUS_RANK.get((status or "").lower(), -1)


class RingCentralError(Exception):
    """A RingCentral REST call failed. Carries RingCentral's own
    ``errorCode`` (a string, e.g. "MSG-242" or "SUB-521" — confirmed shape,
    unlike Twilio's numeric ``code``) and a short safe message; credentials
    are never included."""

    def __init__(self, message: str, *, error_code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


def is_configured() -> bool:
    """True when RingCentral can actually authenticate: app credentials plus
    a user JWT."""
    return bool(settings.RC_APP_CLIENT_ID and settings.RC_APP_CLIENT_SECRET and settings.RC_USER_JWT)


# ── Access token cache ───────────────────────────────────────────────────────
# JWT auth issues a short-lived (confirmed: 3600s) access token and no
# refresh_token — the only rotation available is re-exchanging the same JWT.
# Cached in-process (one process, no cross-worker sharing needed: the next
# worker just does its own exchange on first use) with a lock since multiple
# requests can race to refresh at once.
_token_lock = threading.Lock()
_cached_token: str | None = None
_cached_expiry: float = 0.0
#: Refresh this many seconds before actual expiry, so a request that starts
#: right before expiry doesn't race a still-valid-but-about-to-die token.
_TOKEN_REFRESH_MARGIN_S = 60


def _short_error(resp: httpx.Response) -> tuple[str, str | None]:
    """Best-effort ``(message, error_code)`` from a RingCentral error body.
    Confirmed shape (live, 2026-10-01): ``{"errorCode": "...", "message":
    "...", "errors": [{"errorCode": "...", "message": "..."}]}``."""
    try:
        data = resp.json()
        msg = str(data.get("message") or "")[:300]
        code = data.get("errorCode")
        if not msg and data.get("errors"):
            first = data["errors"][0] if data["errors"] else {}
            msg = str(first.get("message") or "")[:300]
            code = code or first.get("errorCode")
        return (msg or f"RingCentral HTTP {resp.status_code}"), code
    except Exception:  # noqa: BLE001 — fall back to raw text
        return (resp.text or resp.reason_phrase or f"RingCentral HTTP {resp.status_code}")[:300], None


def _exchange_jwt_for_token() -> tuple[str, float]:
    """POST /restapi/oauth/token with grant_type=...jwt-bearer. Confirmed
    live 2026-10-01: Basic auth (client_id:client_secret), form body,
    returns {token_type, access_token, expires_in, scope, owner_id} with no
    refresh_token."""
    base = settings.RC_SERVER_URL.rstrip("/")
    try:
        resp = httpx.post(
            f"{base}/restapi/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": settings.RC_USER_JWT,
            },
            auth=(settings.RC_APP_CLIENT_ID or "", settings.RC_APP_CLIENT_SECRET or ""),
            headers={"Accept": "application/json"},
            timeout=settings.RC_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise RingCentralError(f"RingCentral auth unreachable: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        msg, code = _short_error(resp)
        logger.warning("RingCentral auth failed (%s %s): %s", resp.status_code, code, msg)
        raise RingCentralError(msg, error_code=code, status_code=resp.status_code)
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RingCentralError("RingCentral auth response had no access_token")
    expires_in = int(data.get("expires_in") or 3600)
    return token, time.time() + expires_in


def _access_token() -> str:
    """Return a valid access token, re-exchanging the JWT when the cached
    one is missing or close to expiry."""
    global _cached_token, _cached_expiry
    with _token_lock:
        if _cached_token and time.time() < (_cached_expiry - _TOKEN_REFRESH_MARGIN_S):
            return _cached_token
        token, expiry = _exchange_jwt_for_token()
        _cached_token = token
        _cached_expiry = expiry
        return token


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.RC_SERVER_URL.rstrip("/"),
        headers={"Authorization": f"Bearer {_access_token()}", "Accept": "application/json"},
        timeout=settings.RC_TIMEOUT_SECONDS,
    )


def send_message(*, to: str, body: str, from_phone: str | None = None) -> dict[str, Any]:
    """Create an outbound SMS. Returns ``{"id", "status", "num_segments",
    "error_code", "error_message"}`` — same shape ``sms_service._dispatch``
    already expects from ``twilio_client.send_message`` (field names chosen
    to match: ``sid`` is NOT reused since RingCentral's identifier is a
    plain numeric ``id``, not a Twilio-style "SID" string; the caller maps
    it to whichever DB column holds the provider message id).

    Raises :class:`RingCentralError` on any failure. Unlike Twilio there is
    no "Messaging Service" concept — ``from_phone`` must be a specific
    SMS-enabled number on this account (confirmed live: a number without the
    SmsSender feature 403s with errorCode "FeatureNotAvailable").

    NOTE: the success-path response parsing below is written against
    RingCentral's documented Message object shape and has NOT been
    confirmed against a real 200 response (this account currently has no
    TCR-approved SMS number — every live test so far 403s before reaching
    a success body). Re-verify field names the moment a real send succeeds.
    """
    if not is_configured():
        raise RingCentralError("RingCentral is not configured")
    sender = from_phone or settings.RC_DEFAULT_FROM
    if not sender:
        raise RingCentralError("No sender: no from_phone resolved and RC_DEFAULT_FROM is unset")
    payload = {
        "from": {"phoneNumber": sender},
        "to": [{"phoneNumber": to}],
        "text": body,
    }
    try:
        with _client() as client:
            resp = client.post("/restapi/v1.0/account/~/extension/~/sms", json=payload)
    except httpx.HTTPError as exc:
        raise RingCentralError(f"RingCentral unreachable: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        msg, code = _short_error(resp)
        logger.warning("RingCentral send rejected (%s %s): %s", resp.status_code, code, msg)
        raise RingCentralError(msg, error_code=code, status_code=resp.status_code)
    data = resp.json()
    return {
        "id": data.get("id"),
        "status": data.get("messageStatus"),
        "num_segments": None,  # RingCentral's Message object doesn't appear to report segment count
        "error_code": None,
        "error_message": None,
    }


def list_sms_enabled_numbers() -> list[dict[str, Any]]:
    """Phone numbers on this account with the SmsSender feature (confirmed
    live shape, 2026-10-01). Best-effort — returns [] on failure, this is an
    admin/diagnostic helper, not part of the send path."""
    try:
        with _client() as client:
            resp = client.get("/restapi/v1.0/account/~/extension/~/phone-number")
        if resp.status_code >= 400:
            logger.warning("RingCentral phone-number list failed (%s): %s", resp.status_code, resp.text[:300])
            return []
        records = resp.json().get("records") or []
        return [r for r in records if "SmsSender" in (r.get("features") or [])]
    except Exception as exc:  # noqa: BLE001 — diagnostic helper, never raises
        logger.warning("RingCentral phone-number list error: %s", exc)
        return []


# ── Webhook subscription (SMS-2) ──────────────────────────────────────────────
def create_subscription(*, webhook_url: str, expires_in: int | None = None) -> dict[str, Any]:
    """POST /restapi/v1.0/subscription for message-store events. Confirmed
    live request shape 2026-10-01 (a fake/unreachable URL produced
    errorCode "SUB-521", not a format error — the body shape itself is
    validated). Returns the subscription resource (``id``, ``expirationTime``,
    ...) on success; raises :class:`RingCentralError` otherwise."""
    if not is_configured():
        raise RingCentralError("RingCentral is not configured")
    payload = {
        "eventFilters": ["/restapi/v1.0/account/~/extension/~/message-store"],
        "deliveryMode": {"transportType": "WebHook", "address": webhook_url},
        "expiresIn": expires_in or settings.RC_SUBSCRIPTION_EXPIRES_IN_SECONDS,
    }
    try:
        with _client() as client:
            resp = client.post("/restapi/v1.0/subscription", json=payload)
    except httpx.HTTPError as exc:
        raise RingCentralError(f"RingCentral unreachable: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        msg, code = _short_error(resp)
        logger.warning("RingCentral subscription create failed (%s %s): %s", resp.status_code, code, msg)
        raise RingCentralError(msg, error_code=code, status_code=resp.status_code)
    return resp.json()


def renew_subscription(subscription_id: str) -> dict[str, Any]:
    """PUT /restapi/v1.0/subscription/{id} — extends expiresIn without
    changing eventFilters/deliveryMode. NOT yet confirmed live (needs a real
    subscription to renew, which needs a reachable webhook URL first) —
    written against the documented renewal contract."""
    if not is_configured():
        raise RingCentralError("RingCentral is not configured")
    try:
        with _client() as client:
            resp = client.put(
                f"/restapi/v1.0/subscription/{subscription_id}",
                json={"expiresIn": settings.RC_SUBSCRIPTION_EXPIRES_IN_SECONDS},
            )
    except httpx.HTTPError as exc:
        raise RingCentralError(f"RingCentral unreachable: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        msg, code = _short_error(resp)
        raise RingCentralError(msg, error_code=code, status_code=resp.status_code)
    return resp.json()


def generate_webhook_secret() -> str:
    """A fresh opaque secret for embedding in our registered webhook URL
    (see RC_WEBHOOK_SECRET in config.py for why this — not a RingCentral
    signature — is the real trust boundary)."""
    return secrets.token_urlsafe(32)


def validate_webhook_secret(provided: str | None) -> bool:
    """True when ``provided`` matches RC_WEBHOOK_SECRET. With the secret
    unset this always returns True (local tunnel testing only — same
    posture as Twilio's TWILIO_WEBHOOK_VALIDATE off-switch)."""
    expected = settings.RC_WEBHOOK_SECRET
    if not expected:
        return True
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)
