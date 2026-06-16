"""Authentication routes: login, refresh, logout, current user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, status

from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, TenantId, get_token_payload
from app.db.models import Office, Tenant, UserOffice
from app.schemas.auth import (
    ForgotPasswordRequest,
    LegacyCreatePasswordRequest,
    LegacyVerifyRequest,
    LegacyVerifyResponse,
    LoginRequest,
    MeFull,
    MessageResponse,
    OfficeAssignment,
    RefreshRequest,
    ResetPasswordRequest,
    ResetTokenValidateRequest,
    ResetTokenValidateResponse,
    SignupRequest,
    TokenResponse,
    UserRead,
)
from app.schemas.common import ErrorResponse
from app.services import auth_extras_service, auth_service

router = APIRouter(prefix="/auth", tags=["Auth"], responses={401: {"model": ErrorResponse}})


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="signup",
    summary="Self-register a new practice (tenant) and its admin user",
    responses={409: {"model": ErrorResponse}},
)
def signup(db: DbSession, body: SignupRequest) -> TokenResponse:
    return auth_service.signup(db, body)


@router.post(
    "/login",
    response_model=TokenResponse,
    operation_id="login",
    summary="Authenticate and obtain an access/refresh token pair",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        403: {"model": ErrorResponse, "description": "Account disabled"},
        423: {"model": ErrorResponse, "description": "Account temporarily locked"},
    },
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


@router.get(
    "/me-full",
    response_model=MeFull,
    operation_id="get_me_full",
    summary="Return the authenticated user with tenant and assigned offices",
)
def me_full(db: DbSession, current_user: CurrentUser, tenant_id: TenantId) -> MeFull:
    tenant = db.get(Tenant, current_user.tenant_id)
    rows = db.execute(
        select(UserOffice, Office)
        .join(Office, Office.id == UserOffice.office_id)
        .where(UserOffice.user_id == current_user.id)
    ).all()
    offices = [
        OfficeAssignment(
            office_id=office.id,
            name=office.name,
            office_code=office.office_code,
            is_primary=link.is_primary,
        )
        for link, office in rows
    ]
    return MeFull(user=current_user, tenant=tenant, offices=offices)


# ── Forgot / reset password (login dev-report §2.1–2.3) ──────────────────────
@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    operation_id="forgot_password",
    summary="Request a password-reset email (always 200, never reveals existence)",
)
def forgot_password(
    db: DbSession, body: ForgotPasswordRequest, background_tasks: BackgroundTasks
) -> MessageResponse:
    return MessageResponse(
        **auth_extras_service.forgot_password(db, body.email, background_tasks=background_tasks)
    )


@router.post(
    "/reset-password/validate",
    response_model=ResetTokenValidateResponse,
    operation_id="validate_reset_token",
    summary="Check whether a password-reset token is still valid",
)
def validate_reset_token(
    db: DbSession, body: ResetTokenValidateRequest
) -> ResetTokenValidateResponse:
    return ResetTokenValidateResponse(**auth_extras_service.validate_reset_token(db, body.token))


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    operation_id="reset_password",
    summary="Set a new password using a valid reset token",
    responses={422: {"model": ErrorResponse, "description": "Invalid or expired token"}},
)
def reset_password(db: DbSession, body: ResetPasswordRequest) -> MessageResponse:
    return MessageResponse(**auth_extras_service.reset_password(db, body.token, body.new_password))


# ── Legacy activation (login dev-report §2.4–2.5) ────────────────────────────
@router.post(
    "/legacy-user/verify",
    response_model=LegacyVerifyResponse,
    operation_id="legacy_user_verify",
    summary="Verify a legacy user is eligible to activate and start the challenge",
)
def legacy_user_verify(db: DbSession, body: LegacyVerifyRequest) -> LegacyVerifyResponse:
    return LegacyVerifyResponse(**auth_extras_service.legacy_verify(db, body.username_or_email))


@router.post(
    "/legacy-user/create-password",
    response_model=MessageResponse,
    operation_id="legacy_user_create_password",
    summary="Set the new-platform password for a verified legacy user (one-time)",
    responses={422: {"model": ErrorResponse, "description": "Invalid token or already activated"}},
)
def legacy_user_create_password(
    db: DbSession, body: LegacyCreatePasswordRequest
) -> MessageResponse:
    return MessageResponse(
        **auth_extras_service.legacy_create_password(
            db, body.username_or_email, body.new_password, body.activation_token
        )
    )
