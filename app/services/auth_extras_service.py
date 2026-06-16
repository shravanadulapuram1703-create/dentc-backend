"""Auth extras: forgot/reset password + legacy-user activation.

Resolves the Authentication backend dev-report gaps §2.1–2.5. Tokens are
single-use, TTL-bounded rows in ``auth_action_tokens`` (DB-backed so the flows
work without Redis). Only the SHA-256 of the raw token is stored; the raw value
is emailed (reset) or returned by the legacy-verify endpoint (activation).

Account-enumeration safety: ``forgot_password`` and ``legacy_verify`` never
confirm whether a given email/username exists beyond what the documented contract
requires (forgot always returns the same message; legacy returns ``eligible``).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.security import hash_password
from app.db.models import AuthActionToken, User
from app.integrations import email as email_integration

PURPOSE_RESET = "password_reset"
PURPOSE_ACTIVATION = "legacy_activation"

_GENERIC_FORGOT_MESSAGE = "If an account exists for that email, a reset link has been sent."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def mask_email(email: str | None) -> str | None:
    """``shravan@dental.local`` → ``s•••@dental.local``.

    Keeps the first character of the local part + the full domain, with a fixed
    3-dot mask (matches the FE display and does not leak the local-part length).
    """
    if not email or "@" not in email:
        return None
    local, _, domain = email.partition("@")
    if not local:
        return None
    return f"{local[0]}•••@{domain}"


def _find_user(db: Session, username_or_email: str) -> User | None:
    ident = (username_or_email or "").strip()
    if not ident:
        return None
    return db.execute(
        select(User).where(or_(User.username == ident, User.email == ident))
    ).scalar_one_or_none()


def _issue_token(db: Session, user: User, purpose: str, ttl_minutes: int) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(
        AuthActionToken(
            user_id=user.id,
            token_hash=_hash_token(raw),
            purpose=purpose,
            expires_at=_now() + timedelta(minutes=ttl_minutes),
        )
    )
    db.commit()
    return raw


def _consume_token(db: Session, raw: str, purpose: str) -> tuple[AuthActionToken, User] | None:
    """Return (token, user) for a valid, unused, unexpired token — else None.

    Does NOT mark used; caller marks ``used_at`` only after the password is set so
    a failed write doesn't burn the token.
    """
    token = db.execute(
        select(AuthActionToken).where(
            AuthActionToken.token_hash == _hash_token(raw),
            AuthActionToken.purpose == purpose,
        )
    ).scalar_one_or_none()
    if token is None or token.used_at is not None:
        return None
    expires_at = token.expires_at
    if expires_at.tzinfo is None:  # SQLite returns naive datetimes
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _now():
        return None
    user = db.get(User, token.user_id)
    if user is None:
        return None
    return token, user


# ── Forgot / reset password ──────────────────────────────────────────────────
def forgot_password(db: Session, email: str, background_tasks=None) -> dict:
    """Always returns the same message (no account enumeration).

    The token is committed synchronously; the (potentially slow) email send is
    offloaded to ``background_tasks`` so the response doesn't block on SMTP. When
    no ``background_tasks`` is provided (direct callers/tests), it sends inline.
    """
    ident = (email or "").strip()
    user = db.execute(select(User).where(User.email == ident)).scalar_one_or_none()
    if user is not None and user.is_active:
        raw = _issue_token(db, user, PURPOSE_RESET, settings.PASSWORD_RESET_TOKEN_TTL_MINUTES)
        if background_tasks is not None:
            background_tasks.add_task(email_integration.send_password_reset, user.email, raw)
        else:
            email_integration.send_password_reset(user.email, raw)
    return {"message": _GENERIC_FORGOT_MESSAGE}


def validate_reset_token(db: Session, token: str) -> dict:
    result = _consume_token(db, token, PURPOSE_RESET)
    if result is None:
        return {"valid": False, "email": None}
    _, user = result
    return {"valid": True, "email": user.email}


def reset_password(db: Session, token: str, new_password: str) -> dict:
    result = _consume_token(db, token, PURPOSE_RESET)
    if result is None:
        raise ValidationError(
            "This reset link is invalid or has expired", code="invalid_reset_token"
        )
    action_token, user = result
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.password_created_at = _now()
    action_token.used_at = _now()
    db.commit()
    return {"message": "Your password has been reset. You can now sign in."}


# ── Legacy activation ────────────────────────────────────────────────────────
def legacy_verify(db: Session, username_or_email: str) -> dict:
    user = _find_user(db, username_or_email)
    # Not a (eligible) legacy user → generic not-eligible response.
    if user is None or not user.is_legacy_user or not user.is_active:
        return {
            "eligible": False,
            "legacy_activation_completed": False,
            "verification_method": None,
            "masked_email": None,
            "activation_token": None,
        }
    # Already activated → block (Business Rule 2); UI routes to Forgot Password.
    if user.legacy_activation_completed:
        return {
            "eligible": False,
            "legacy_activation_completed": True,
            "verification_method": None,
            "masked_email": mask_email(user.email),
            "activation_token": None,
        }
    raw = _issue_token(db, user, PURPOSE_ACTIVATION, settings.LEGACY_ACTIVATION_TOKEN_TTL_MINUTES)
    return {
        "eligible": True,
        "legacy_activation_completed": False,
        "verification_method": "email",
        "masked_email": mask_email(user.email),
        "activation_token": raw,
    }


def legacy_create_password(
    db: Session, username_or_email: str, new_password: str, activation_token: str
) -> dict:
    result = _consume_token(db, activation_token, PURPOSE_ACTIVATION)
    if result is None:
        raise ValidationError(
            "This activation link is invalid or has expired", code="invalid_activation_token"
        )
    action_token, user = result
    # Token must belong to the same user the caller named (defense in depth).
    named = _find_user(db, username_or_email)
    if named is None or named.id != user.id:
        raise ValidationError(
            "This activation link is invalid or has expired", code="invalid_activation_token"
        )
    # One-time only (Business Rule 3).
    if user.legacy_activation_completed:
        raise ValidationError(
            "This account has already been activated. Use Forgot Password instead.",
            code="already_activated",
        )
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.password_created_at = _now()
    user.legacy_activation_completed = True  # Rule 4: is_legacy_user stays True
    action_token.used_at = _now()
    db.commit()
    return {"message": "Your account is activated. You can now sign in."}
