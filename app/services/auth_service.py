"""Authentication service: credential verification + token lifecycle.

Multi-step logic that doesn't belong in a route handler, so it lives here. Tokens
are JWTs; the refresh-token whitelist and access-token blacklist live in Redis
(degrading gracefully when Redis is off — see ``integrations.redis_store``).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import Tenant, User
from app.integrations import redis_store
from app.schemas.auth import SignupRequest, TokenResponse


def _access_ttl_seconds() -> int:
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def _refresh_ttl_seconds() -> int:
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 86_400


def authenticate(db: Session, username: str, password: str) -> User:
    user = db.execute(
        select(User).where(or_(User.username == username, User.email == username))
    ).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("Invalid credentials", code="invalid_credentials")
    if not user.is_active:
        raise UnauthorizedError("User is inactive", code="inactive_user")
    return user


def issue_tokens(user: User) -> TokenResponse:
    claims = {"tenant_id": user.tenant_id, "role": user.role}
    access, _ = create_access_token(user.id, claims)
    refresh, refresh_jti = create_refresh_token(user.id, {"tenant_id": user.tenant_id})
    redis_store.store_refresh_token(user.id, refresh_jti, _refresh_ttl_seconds())
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=_access_ttl_seconds(),
    )


def login(db: Session, username: str, password: str) -> TokenResponse:
    user = authenticate(db, username, password)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return issue_tokens(user)


def signup(db: Session, data: SignupRequest) -> TokenResponse:
    """Self-service registration: provision a NEW tenant + its admin user.

    Joining an existing practice is intentionally NOT supported here (that path
    is invite-only via ``POST /users``), which avoids the tenant-assignment
    security gate of injecting unauthenticated callers into an existing tenant.
    """
    if db.execute(select(Tenant.id).where(Tenant.code == data.practice_code)).scalar_one_or_none():
        raise ConflictError("A practice with this code already exists", code="tenant_exists")
    if db.execute(
        select(User.id).where(or_(User.email == data.email, User.username == data.username))
    ).scalar_one_or_none():
        raise ConflictError("Email or username already in use", code="user_exists")

    tenant = Tenant(name=data.practice_name, code=data.practice_code, is_active=True)
    db.add(tenant)
    db.flush()  # assign tenant.id without a second round-trip

    user = User(
        tenant_id=tenant.id,
        email=data.email,
        username=data.username,
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return issue_tokens(user)


def refresh(db: Session, refresh_token: str) -> TokenResponse:
    payload = decode_token(refresh_token, expected_type=REFRESH_TOKEN_TYPE)
    user_id = payload.get("sub")
    jti = payload.get("jti", "")
    if not redis_store.is_refresh_token_valid(user_id, jti):
        raise UnauthorizedError("Refresh token revoked or expired", code="invalid_refresh")
    user = db.get(User, int(user_id)) if user_id else None
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive", code="invalid_user")
    # Rotate: revoke the presented refresh token, then mint a fresh pair.
    redis_store.revoke_refresh_token(user_id, jti)
    return issue_tokens(user)


def logout(access_payload: dict, refresh_token: str | None = None) -> None:
    jti = access_payload.get("jti")
    exp = access_payload.get("exp")
    if jti and exp:
        remaining = int(exp - datetime.now(timezone.utc).timestamp())
        redis_store.blacklist_access_token(jti, max(remaining, 0))
    if refresh_token:
        try:
            r = decode_token(refresh_token, expected_type=REFRESH_TOKEN_TYPE)
            redis_store.revoke_refresh_token(r.get("sub"), r.get("jti", ""))
        except UnauthorizedError:
            pass
