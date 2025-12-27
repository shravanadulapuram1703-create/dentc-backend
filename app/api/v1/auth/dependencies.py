from fastapi import Request, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.utils.token import decode_access_token
from app.models.user import User
from app.services.rbac_service import user_has_permission
from app.services.audit_service import log_audit

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login-swager")


import re

def name_from_email(email: str) -> str:
    # Take part before @
    local_part = email.split("@")[0]

    # Replace separators with space
    local_part = re.sub(r"[._\-]+", " ", local_part)

    # Remove digits and extra spaces
    local_part = re.sub(r"\d+", "", local_part).strip()

    logger.info(f"local_part ===>  {local_part.title()}")

    # Convert to proper case
    return local_part.title()

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    payload = decode_access_token(token)

    user_id: str | None = payload.get("sub")
    tenant_id: int | None = payload.get("tenant_id")

    logger.info(f"user_id {user_id}, tenant_id : {tenant_id}")

    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )

    user = (
        db.query(User)
        .filter(
            User.id == int(user_id),
            User.tenant_id == tenant_id,
            # User.is_active == True
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    logger.info(f"user ----> {type(user)}")
    user.name = name_from_email(user.email)

    return user


def require_superuser(
    current_user: User = Depends(get_current_user)
) -> User:
    logger.info(f"current_user {current_user}")
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return current_user


def enforce_tenant(
    tenant_id: int,
    current_user: User = Depends(get_current_user)
):
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access violation"
        )


def require_permission(permission_code: str):
    def dependency(
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
    ):
        if not user_has_permission(current_user, permission_code):
            log_audit(
                db,
                action="RBAC_DENIED",
                success=False,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                resource="PERMISSION",
                resource_id=permission_code,
                reason="Permission denied",
                request=request
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )

        return current_user

    return dependency