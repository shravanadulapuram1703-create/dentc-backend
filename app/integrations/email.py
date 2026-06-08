"""Transactional email sender (password-reset links, etc.).

Intentionally a thin abstraction with a **log-only** default implementation: the
production SMTP/provider wiring (SES/SendGrid/etc.) is a separate infra task. The
auth flows depend only on ``send_email`` / ``send_password_reset`` returning
without raising, so the endpoints behave correctly today and delivery can be
swapped in later without touching callers.

Never raises to the caller — a delivery failure must not change the "always 200"
contract of the forgot-password endpoint (which must not leak account existence).
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email. Returns True if handed off to a transport.

    Default (no SMTP configured): log the message and return True. Replace the
    body of this function with a real transport in production.
    """
    try:
        logger.info("EMAIL → %s | %s\n%s", to, subject, body)
        return True
    except Exception as exc:  # noqa: BLE001 — delivery must never raise to callers
        logger.warning("Email send failed (degraded): %s", exc)
        return False


def send_password_reset(to: str, raw_token: str) -> bool:
    link = f"{settings.PASSWORD_RESET_URL_BASE}?token={raw_token}"
    body = (
        "We received a request to reset your password.\n\n"
        f"Reset link (valid for {settings.PASSWORD_RESET_TOKEN_TTL_MINUTES} minutes):\n{link}\n\n"
        "If you didn't request this, you can ignore this email."
    )
    return send_email(to, "Reset your password", body)
