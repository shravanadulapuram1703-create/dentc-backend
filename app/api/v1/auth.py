"""Authentication routes: login, refresh, logout, current user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, status

from app.api.deps import CurrentUser, DbSession, get_token_payload
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserRead
from app.schemas.common import ErrorResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"], responses={401: {"model": ErrorResponse}})


@router.post(
    "/login",
    response_model=TokenResponse,
    operation_id="login",
    summary="Authenticate and obtain an access/refresh token pair",
)
def login(db: DbSession, credentials: LoginRequest) -> TokenResponse:
    return auth_service.login(db, credentials.username, credentials.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    operation_id="refresh_token",
    summary="Exchange a refresh token for a new token pair",
)
def refresh(db: DbSession, body: RefreshRequest) -> TokenResponse:
    return auth_service.refresh(db, body.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="logout",
    summary="Revoke the current access token (and optionally a refresh token)",
)
def logout(
    payload: Annotated[dict, Depends(get_token_payload)],
    refresh_token: Annotated[str | None, Body(embed=True)] = None,
) -> None:
    auth_service.logout(payload, refresh_token)


@router.get(
    "/me",
    response_model=UserRead,
    operation_id="get_me",
    summary="Return the authenticated user",
)
def me(current_user: CurrentUser) -> UserRead:
    return current_user
