"""Stripe REST client — the *only* place the Stripe secret key is used (AN-27).

Same isolation contract as :mod:`sendgrid_client` / :mod:`ringcentral_client`:
raw ``httpx``, no SDK. With ``STRIPE_SECRET_KEY`` unset :func:`is_configured`
is False and AppointNow falls back to the ``manual`` provider (staff record
the payment they collected themselves), so dev/tests need no credentials.

Three calls are all AppointNow needs: create a hosted Checkout Session (the
"secure payment link"), expire one (a re-sent link must kill the old one so
the patient cannot pay twice), and refund a PaymentIntent. Webhook signatures
use Stripe's documented scheme — ``Stripe-Signature: t=<ts>,v1=<hex>`` where
``v1 = HMAC-SHA256(secret, "<ts>.<raw body>")``.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class StripeError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def is_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.STRIPE_API_BASE_URL.rstrip("/"),
        auth=(settings.STRIPE_SECRET_KEY or "", ""),
        timeout=settings.STRIPE_TIMEOUT_SECONDS,
    )


def _raise_for(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    message, code = f"Stripe HTTP {resp.status_code}", None
    try:
        err = resp.json().get("error") or {}
        message = str(err.get("message") or message)[:300]
        code = err.get("code") or err.get("type")
    except Exception:  # noqa: BLE001
        pass
    raise StripeError(message, status_code=resp.status_code, code=code)


def to_minor_units(amount: Decimal) -> int:
    """Dollars → cents (Stripe amounts are integers in the smallest unit)."""
    return int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def create_checkout_session(
    *,
    amount: Decimal,
    currency: str,
    description: str,
    success_url: str,
    cancel_url: str,
    expires_at: int,
    metadata: dict[str, str],
    customer_email: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """One-line-item hosted Checkout Session. Returns the session object
    (``id``, ``url``, ``expires_at``)."""
    form: dict[str, Any] = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "expires_at": str(expires_at),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": currency.lower(),
        "line_items[0][price_data][unit_amount]": str(to_minor_units(amount)),
        "line_items[0][price_data][product_data][name]": description[:250],
    }
    for key, value in metadata.items():
        form[f"metadata[{key}]"] = value
        # Mirror onto the PaymentIntent so a refund / dispute in the Stripe
        # dashboard can be traced back to the request as well.
        form[f"payment_intent_data[metadata][{key}]"] = value
    if customer_email:
        form["customer_email"] = customer_email
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    with _client() as client:
        resp = client.post("/v1/checkout/sessions", data=form, headers=headers)
    _raise_for(resp)
    return resp.json()


def expire_checkout_session(session_id: str) -> None:
    """Best-effort: an already-completed/expired session is not an error here."""
    with _client() as client:
        resp = client.post(f"/v1/checkout/sessions/{session_id}/expire")
    if resp.status_code >= 400:
        logger.info("Stripe expire session %s skipped: HTTP %s", session_id, resp.status_code)


def create_refund(
    *, payment_intent: str, amount: Decimal | None = None, reason_note: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    form: dict[str, Any] = {"payment_intent": payment_intent}
    if amount is not None:
        form["amount"] = str(to_minor_units(amount))
    if reason_note:
        form["metadata[note]"] = reason_note[:450]
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    with _client() as client:
        resp = client.post("/v1/refunds", data=form, headers=headers)
    _raise_for(resp)
    return resp.json()


def verify_webhook_signature(payload: bytes, header: str | None, *, now: float | None = None) -> bool:
    """Stripe's ``v1`` scheme. False on a missing secret (refuse, never accept
    unsigned), a malformed header, a stale timestamp or no matching signature."""
    secret = settings.STRIPE_WEBHOOK_SECRET
    if not secret or not header:
        return False
    timestamp: str | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    if not timestamp or not signatures:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    current = time.time() if now is None else now
    if abs(current - ts) > settings.STRIPE_WEBHOOK_TOLERANCE_SECONDS:
        return False
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


def sign_payload(payload: bytes, *, timestamp: int | None = None, secret: str | None = None) -> str:
    """Build a ``Stripe-Signature`` header (tests / local replay tooling)."""
    ts = int(time.time()) if timestamp is None else timestamp
    key = (secret or settings.STRIPE_WEBHOOK_SECRET or "").encode()
    sig = hmac.new(key, f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"
