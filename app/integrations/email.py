"""Transactional email sender (password-reset links, etc.).

Transport is **SMTP** (stdlib ``smtplib``) when ``SMTP_HOST`` is configured;
otherwise the sender stays in **log-only** mode so local dev works without creds
(the reset link is written to the logs and can be copied from there).

Never raises to the caller — a delivery failure must not change the "always 200"
contract of the forgot-password endpoint (which must not leak account existence).
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _from_address() -> str:
    addr = settings.EMAIL_FROM or settings.SMTP_USER or "no-reply@localhost"
    name = settings.EMAIL_FROM_NAME
    return f"{name} <{addr}>" if name else addr


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


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email. Returns True if handed off to a transport.

    Uses SMTP when ``SMTP_HOST`` is configured; falls back to logging the message
    (dev default). Never raises — a delivery failure is logged and returns False.
    """
    if not settings.SMTP_HOST:
        logger.info("EMAIL (log-only, no SMTP_HOST) → %s | %s\n%s", to, subject, body)
        return True
    try:
        _send_via_smtp(to, subject, body)
        logger.info("EMAIL sent → %s | %s", to, subject)
        return True
    except Exception as exc:  # noqa: BLE001 — delivery must never raise to callers
        logger.warning("Email send failed (degraded), %s: %s", to, exc)
        return False


def send_password_reset(to: str, raw_token: str) -> bool:
    link = f"{settings.PASSWORD_RESET_URL_BASE}?token={raw_token}"
    body = (
        "We received a request to reset your password.\n\n"
        f"Reset link (valid for {settings.PASSWORD_RESET_TOKEN_TTL_MINUTES} minutes):\n{link}\n\n"
        "If you didn't request this, you can ignore this email."
    )
    return send_email(to, "Reset your password", body)
