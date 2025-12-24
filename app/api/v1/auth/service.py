from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from fastapi import Request

from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.utils.password import verify_password, hash_token, verify_token
from app.utils.token import create_access_token, create_refresh_token
from app.services.audit_service import log_audit

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)



REFRESH_TOKEN_EXPIRE_DAYS = 7


def login_user(db: Session, email: str, password: str, tenant_id: int, request: Request):

    logger.info(f"email {email} -------- {password} ----------- {tenant_id}")
    user = (
        db.query(User)
        .filter(
            User.email == email,
            User.tenant_id == tenant_id,
            User.is_active == True
        ).first()
    )

    if not user:
        log_audit(
                db,
                action="LOGIN_FAILED",
                success=False,
                tenant_id=tenant_id,
                reason="Invalid credentials - User Name",
                request=request
                        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials - User Name"
        )

    if not verify_password(password, user.password_hash):
        log_audit(
                db,
                action="LOGIN_FAILED",
                success=False,
                tenant_id=tenant_id,
                reason="Invalid credentials - Password",
                request=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials - Password"
        )

    if user.role == "super_admin":
        is_superuser = True
    else:
        is_superuser = False

    access_token = create_access_token({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "is_superuser":is_superuser
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
            user_id=user.id,
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
            if user.role == "super_admin":
                is_superuser = True
            else:
                is_superuser = False


            new_access = create_access_token({
                "sub": str(user.id),
                "tenant_id": user.tenant_id,
                "is_superuser": is_superuser,
            })

            #  log ONLY after user is known
            log_audit(
                db,
                action="TOKEN_REFRESH",
                success=True,
                tenant_id=user.tenant_id,
                user_id=user.id
            )

            return new_access

    #  invalid or expired token
    log_audit(
        db,
        action="TOKEN_REFRESH",
        success=False,
        tenant_id=None,
        user_id=None
    )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token"
    )




def logout(db: Session, refresh_token: str):
    tokens = db.query(RefreshToken).filter(
        RefreshToken.revoked == False
    ).all()
    for token in tokens:
        if verify_token(refresh_token, token.token_hash):
            token.revoked = True
            db.commit()
            
            log_audit(
                db,
                action="LOGOUT",
                success=True,
                tenant_id=token.tenant_id,
                user_id=token.user_id
            )
            return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid refresh token"
    )



