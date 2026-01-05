from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Request

from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.utils.password import verify_password, hash_token, verify_token
from app.utils.token import create_access_token, create_refresh_token
from app.services.audit_service import log_audit

from app.models.role import Role
from app.utils.password import hash_password
from app.models.user_role import UserRole

from sqlalchemy import or_

from app.api.v1.auth.dependencies import get_current_user


import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)








REFRESH_TOKEN_EXPIRE_DAYS = 7


# def login_user(db: Session, email: str, password: str, request: Request):

#     logger.info(f"email {email} --------password -----------  {password} ")

#     user = (
#         db.query(User)
#         .filter(
#             User.email == email,
#             # User.tenant_id == tenant_id,
#         )
#         .first()
#     )

#     # User not found
#     if not user:
#         log_audit(
#             db,
#             action="LOGIN_FAILED",
#             success=False,
#             tenant_id=tenant_id,
#             actor_user_id=None,
#             resource="auth",
#             resource_type="login",
#             reason="Invalid credentials - username",
#             request=request,
#         )
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid credentials - User Name"
#         )

#     # Wrong password
#     if not verify_password(password, user.password_hash):
#         log_audit(
#             db,
#             action="LOGIN_FAILED",
#             success=False,
#             tenant_id=tenant_id,
#             actor_user_id=user.id,
#             resource="auth",
#             resource_type="login",
#             reason="Invalid credentials - password",
#             request=request,
#         )
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid credentials - Password"
#         )

#     is_superuser = user.role == "super_admin"

#     access_token = create_access_token({
#         "sub": str(user.id),
#         "tenant_id": user.tenant_id,
#         "is_superuser": is_superuser
#     })

#     raw_refresh = create_refresh_token()
#     refresh_token = RefreshToken(
#         user_id=user.id,
#         tenant_id=user.tenant_id,
#         token_hash=hash_token(raw_refresh),
#         expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
#     )

#     db.add(refresh_token)
#     db.commit()

#     # Login success 
#     log_audit(
#         db,
#         action="LOGIN_SUCCESS",
#         success=True,
#         tenant_id=user.tenant_id,
#         actor_user_id=user.id,
#         resource="auth",
#         resource_type="login",
#         resource_id=str(user.id),
#         resource_pk=str(user.id),
#         reason="User logged in successfully",
#         request=request,
#     )

#     return access_token, raw_refresh




def login_user(db: Session, identifier: str, password: str, request: Request):
    """
    identifier → can be email OR username
    """

    logger.info(f"identifier={identifier} -------- password=********")

    user = (
        db.query(User)
        .filter(
            or_(
                User.email == identifier,
                User.username == identifier
            )
        )
        .first()
    )

    # User not found
    if not user:
        log_audit(
            db,
            action="LOGIN_FAILED",
            success=False,
            tenant_id=None,
            actor_user_id=None,
            resource="auth",
            resource_type="login",
            reason="Invalid credentials - email/username",
            request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    #  Wrong password
    if not verify_password(password, user.password_hash):
        log_audit(
            db,
            action="LOGIN_FAILED",
            success=False,
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            resource="auth",
            resource_type="login",
            reason="Invalid credentials - password",
            request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Successful login
    is_superuser = user.role == "super_admin"

    access_token = create_access_token({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "is_superuser": is_superuser
    })

    raw_refresh = create_refresh_token()

    refresh_token = RefreshToken(
        user_id=user.id,
        tenant_id=user.tenant_id,
        token_hash=hash_token(raw_refresh),
        expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    db.add(refresh_token)
    db.commit()

    log_audit(
        db,
        action="LOGIN_SUCCESS",
        success=True,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        resource="auth",
        resource_type="login",
        resource_id=str(user.id),
        resource_pk=str(user.id),
        reason="User logged in successfully",
        request=request,
    )

    return access_token, raw_refresh



def refresh_access_token(db: Session, refresh_token: str):
    tokens = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.utcnow()
        )
        .all()
    )

    for token in tokens:
        if verify_token(refresh_token, token.token_hash):
            user = db.query(User).get(token.user_id)

            if not user or not user.is_active:
                break

            is_superuser = user.role == "super_admin"

            new_access = create_access_token({
                "sub": str(user.id),
                "tenant_id": user.tenant_id,
                "is_superuser": is_superuser,
            })

            # Token refresh success
            log_audit(
                db,
                action="TOKEN_REFRESH",
                success=True,
                tenant_id=user.tenant_id,
                actor_user_id=user.id,
                resource="auth",
                resource_type="refresh_token",
                resource_id=str(token.id),
                resource_pk=str(token.id),
                reason="Access token refreshed",
            )

            return new_access

    # Invalid / expired refresh token
    log_audit(
        db,
        action="TOKEN_REFRESH",
        success=False,
        tenant_id=None,
        actor_user_id=None,
        resource="auth",
        resource_type="refresh_token",
        reason="Invalid or expired refresh token",
    )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token"
    )



# def logout(db: Session, refresh_token: str):
#     tokens = db.query(RefreshToken).filter(
#         RefreshToken.revoked.is_(False)
#     ).all()

#     for token in tokens:
#         if verify_token(refresh_token, token.token_hash):
#             token.revoked = True
#             db.commit()

#             # Logout success
#             log_audit(
#                 db,
#                 action="LOGOUT",
#                 success=True,
#                 tenant_id=token.tenant_id,
#                 actor_user_id=token.user_id,
#                 resource="auth",
#                 resource_type="logout",
#                 resource_id=str(token.id),
#                 resource_pk=str(token.id),
#                 reason="User logged out",
#             )

#             # blacklist_access_token(
#             #     jti=access_jti,
#             #     expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
#             # )
#             # revoke_refresh_token(user.id, refresh_jti)

#             return

#     raise HTTPException(
#         status_code=status.HTTP_400_BAD_REQUEST,
#         detail="Invalid refresh token"
#     )
def logout(db: Session, refresh_token: str):
    tokens = db.query(RefreshToken).filter(RefreshToken.revoked.is_(False)).all()

    for token in tokens:
        if verify_token(refresh_token, token.token_hash):

            if not token.revoked:
                token.revoked = True
                db.commit()

                log_audit(
                    db,
                    action="LOGOUT",
                    success=True,
                    tenant_id=token.tenant_id,
                    actor_user_id=token.user_id,
                    resource="auth",
                    resource_type="logout",
                    resource_id=str(token.id),
                    resource_pk=str(token.id),
                    reason="User logged out",
                )

            #  idempotent logout
            return

    #  logout should never error
    return


def revoke_user_tokens(db: Session, user_id: int, tenant_id: int):
    tokens = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.tenant_id == tenant_id,
        RefreshToken.revoked.is_(False)
    ).all()

    for token in tokens:
        token.revoked = True

    db.commit()

    # Revoke tokens success
    log_audit(
        db,
        action="REVOKE_TOKENS",
        success=True,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        resource="auth",
        resource_type="revoke_tokens",
        reason="All refresh tokens revoked for user",
    )

    return True


def signup_user(
    db: Session,
    *,
    email: str,
    password: str,
    # tenant_id: int,
    request
):
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    print(f"Inside the sign up")

    basic_role = (
        db.query(Role)
        .filter(
            Role.name == "Read Only",
            # Role.tenant_id == tenant_id
        )
        .first()
    )

    if not basic_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default role not configured for tenant"
        )

    user = User(
        email=email,
        password_hash=hash_password(password),
        # tenant_id=tenant_id,
        is_active=True,
        role="Read Only"
    )

    logger.info(f" basic_role  : {basic_role}")

    # user.role.append(basic_role)

    db.add(user)
    db.flush()  # ensures user.id exists

    user_role = UserRole(
        user_id=user.id,      # OR user=user (after flush)
        role_id=basic_role.id,
        # office_id=1,  # MUST be provided
    )

    user.user_roles.append(user_role)

    db.add(user)
    db.commit()
    db.refresh(user)

    log_audit(
        db,
        action="USER_SIGNUP",
        success=True,
        # tenant_id=tenant_id,
        actor_user_id=user.id,
        resource="auth",
        resource_id=str(user.id),
        resource_pk=str(user.id),
        reason="User Signed up successfully",
    )

    return user
