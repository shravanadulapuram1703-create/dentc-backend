"""Shared FastAPI dependencies: DB session, current user, tenant scope, paging.

Tenancy is resolved here (column-based): every request carries a ``tenant_id``
derived from the JWT. A ``super_admin`` may target another tenant via the
``X-Tenant-ID`` header. CRUD operations receive this id and filter on it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.logging import tenant_id_ctx, user_id_ctx
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.db.models import User
from app.db.session import get_db
from app.integrations.redis_store import is_access_token_blacklisted
from app.schemas.common import SortOrder

DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False, description="JWT access token")

SUPER_ADMIN_ROLE = "super_admin"


def get_token_payload(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    # TenantMiddleware-free design: decode here, once, and cache on request.state.
    cached = getattr(request.state, "token_payload", None)
    if cached is not None:
        return cached
    if credentials is None:
        raise UnauthorizedError("Missing bearer token", code="missing_token")
    payload = decode_token(credentials.credentials, expected_type=ACCESS_TOKEN_TYPE)
    if is_access_token_blacklisted(payload.get("jti", "")):
        raise UnauthorizedError("Token has been revoked", code="token_revoked")
    request.state.token_payload = payload
    return payload


def get_current_user(
    db: DbSession,
    payload: Annotated[dict, Depends(get_token_payload)],
) -> User:
    user_id = payload.get("sub")
    user = db.get(User, int(user_id)) if user_id else None
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive", code="invalid_user")
    user_id_ctx.set(str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_tenant_id(
    current_user: CurrentUser,
    x_tenant_id: Annotated[int | None, Header(alias="X-Tenant-ID")] = None,
) -> int:
    if x_tenant_id is not None and x_tenant_id != current_user.tenant_id:
        if current_user.role != SUPER_ADMIN_ROLE:
            raise ForbiddenError("Not permitted to access another tenant")
        tenant_id_ctx.set(str(x_tenant_id))
        return x_tenant_id
    tenant_id_ctx.set(str(current_user.tenant_id))
    return current_user.tenant_id


TenantId = Annotated[int, Depends(get_tenant_id)]


def require_roles(*roles: str):
    """Dependency factory guarding an endpoint to the given roles."""

    def _guard(current_user: CurrentUser) -> User:
        if current_user.role not in roles and current_user.role != SUPER_ADMIN_ROLE:
            raise ForbiddenError("Insufficient role for this operation")
        return current_user

    return _guard


class Pagination(BaseModel):
    page: int
    size: int
    sort: str | None
    order: SortOrder
    search: str | None


def get_pagination(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 20,
    sort: Annotated[str | None, Query(description="Column to sort by")] = None,
    order: Annotated[SortOrder, Query()] = "desc",
    search: Annotated[str | None, Query(description="Free-text search")] = None,
) -> Pagination:
    return Pagination(page=page, size=size, sort=sort, order=order, search=search)


PageParams = Annotated[Pagination, Depends(get_pagination)]
