"""Authentication routes: login, refresh, logout, current user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, status

from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, TenantId, get_token_payload
from app.db.models import Office, Permission, Tenant, UserOffice
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
from app.services import (
    auth_extras_service,
    auth_service,
    my_page_service,
    patient_context_service,
    permission_service,
)

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
    # OFF-SCOPE-10: the assignment carries what the switcher needs (short_id,
    # is_active, office_group_id, timezone) so it renders without a second fetch.
    offices = [
        OfficeAssignment(
            office_id=office.id,
            name=office.name,
            office_code=office.office_code,
            is_primary=link.is_primary,
            short_id=office.short_id,
            is_active=office.is_active,
            office_group_id=office.office_group_id,
            timezone=office.timezone,
        )
        for link, office in rows
    ]
    last_patient_id = patient_context_service.resolve_last_patient(db, current_user, tenant_id)
    provider_id = my_page_service.linked_provider_id(db, current_user.id)
    # OFF-SCOPE-3: the remembered working office, validated against the current
    # assignments; falls back to the primary (else first) assignment so a fresh
    # session always resolves *some* office to work in.
    assigned_ids = {o.office_id for o in offices}
    current_office_id = current_user.current_office_id
    if current_office_id is None or (assigned_ids and current_office_id not in assigned_ids):
        primary = next((o.office_id for o in offices if o.is_primary), None)
        current_office_id = primary or (offices[0].office_id if offices else None)
    # EDIT-PLAN-5: effective rights. A full-access role lists the whole active
    # catalog so a client can key on codes without special-casing the role.
    perms = permission_service.effective_permissions(db, current_user)
    if perms.full_access:
        codes = sorted(db.execute(
            select(Permission.code).where(Permission.is_active.is_(True))
        ).scalars().all())
    else:
        codes = sorted(perms.codes)
    # OFF-SCOPE-13 / FE-OFF-2: surface the office-scope right the caller holds
    # using the REAL catalog code (``office_scope_view_all_offices`` / the legacy
    # coverage alias), so the switcher keys on it (``officeScopeModel.ts``) like
    # any other permission. Leadership roles (owner/manager) hold the master right
    # without a group, so it is unioned in for them too.
    office_right_codes = sorted(permission_service.office_rights(db, current_user))
    codes = sorted(set(codes) | set(office_right_codes))
    return MeFull(user=current_user, tenant=tenant, offices=offices,
                  last_patient_id=last_patient_id, current_office_id=current_office_id,
                  provider_id=provider_id,
                  permissions=codes,
                  permissions_enforced=perms.enforced or perms.full_access,
                  groups=perms.groups)


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
