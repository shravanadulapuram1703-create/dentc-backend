"""SendGrid v3 mail client — the *only* place the SendGrid API key is used (EMAIL-1).

Same isolation contract as :mod:`twilio_client`: with ``SENDGRID_API_KEY`` unset
:func:`is_configured` is False and the e-mail service persists the row as
``queued`` (log-only mode). Flip it on with the key + a verified sender.

Event-webhook verification uses SendGrid's ECDSA "Signed Event Webhook"
(``X-Twilio-Email-Event-Webhook-Signature`` / ``-Timestamp``) via the
``cryptography`` package that is already a dependency (Fernet in ``core.crypto``).
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: SendGrid event vocabulary mapped onto the row's ``send_status``.
EVENT_STATUSES = (
    "processed", "dropped", "delivered", "deferred", "bounce",
    "open", "click", "spamreport", "unsubscribe", "group_unsubscribe", "group_resubscribe",
)


class SendGridError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def is_configured() -> bool:
    return bool(settings.SENDGRID_API_KEY and settings.SENDGRID_FROM_EMAIL)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.SENDGRID_API_BASE_URL.rstrip("/"),
        headers={
            "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=settings.SENDGRID_TIMEOUT_SECONDS,
    )


def _short_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        errs = data.get("errors") or []
        parts = [str(e.get("message") or e) for e in errs if e]
        if parts:
            return "; ".join(parts)[:300]
    except Exception:  # noqa: BLE001
        pass
    return (resp.text or resp.reason_phrase or f"SendGrid HTTP {resp.status_code}")[:300]


def send_mail(
    *,
    to_email: str,
    subject: str,
    body_html: str | None,
    body_text: str | None,
    from_email: str | None = None,
    from_name: str | None = None,
    custom_args: dict[str, str] | None = None,
) -> dict[str, Any]:
    """POST /v3/mail/send. Returns ``{"message_id"}`` (the ``X-Message-Id``
    header SendGrid echoes, which its event webhook later reports as
    ``sg_message_id``'s prefix). Raises :class:`SendGridError` on failure."""
    if not is_configured():
        raise SendGridError("SendGrid is not configured")
    content = []
    if body_text:
        content.append({"type": "text/plain", "value": body_text})
    if body_html:
        content.append({"type": "text/html", "value": body_html})
    if not content:
        content.append({"type": "text/plain", "value": ""})
    sender: dict[str, str] = {"email": from_email or settings.SENDGRID_FROM_EMAIL or ""}
    name = from_name or settings.SENDGRID_FROM_NAME
    if name:
        sender["name"] = name
    payload: dict[str, Any] = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": sender,
        "subject": subject[:500],
        "content": content,
    }
    if custom_args:
        payload["custom_args"] = {k: str(v) for k, v in custom_args.items()}
    try:
        with _client() as client:
            resp = client.post("/v3/mail/send", json=payload)
    except httpx.HTTPError as exc:
        raise SendGridError(f"SendGrid unreachable: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        msg = _short_error(resp)
        logger.warning("SendGrid send rejected (%s): %s", resp.status_code, msg)
        raise SendGridError(msg, status_code=resp.status_code)
    return {"message_id": resp.headers.get("X-Message-Id")}


def verify_event_signature(*, public_key: str | None, signature: str | None,
                           timestamp: str | None, body: bytes) -> bool:
    """SendGrid Signed Event Webhook: ECDSA-P256/SHA-256 over ``timestamp + body``.

    ``SENDGRID_WEBHOOK_VALIDATE`` off -> always True (local testing only). On
    with no public key -> always False.
    """
    if not settings.SENDGRID_WEBHOOK_VALIDATE:
        return True
    if not public_key or not signature or not timestamp:
        return False
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        pem = public_key.strip()
        if "BEGIN" not in pem:
            pem = "-----BEGIN PUBLIC KEY-----\n" + pem + "\n-----END PUBLIC KEY-----\n"
        key = serialization.load_pem_public_key(pem.encode("utf-8"))
        key.verify(  # type: ignore[union-attr]
            base64.b64decode(signature),
            timestamp.encode("utf-8") + body,
            ec.ECDSA(hashes.SHA256()),
        )
        return True
    except Exception as exc:  # noqa: BLE001 — any failure is "not verified"
        logger.warning("SendGrid webhook signature rejected: %s", type(exc).__name__)
        return False
