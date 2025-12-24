from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.user import User
from app.models.role import Role
from app.utils.password import hash_password
from app.services.audit_service import log_audit
from app.models.user_role import UserRole

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)



def signup_user(
    db: Session,
    *,
    email: str,
    password: str,
    tenant_id: int,
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
            Role.tenant_id == tenant_id
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
        tenant_id=tenant_id,
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
        office_id=1,  # MUST be provided
    )

    user.user_roles.append(user_role)

    db.add(user)
    db.commit()
    db.refresh(user)

    log_audit(
        db,
        action="USER_SIGNUP",
        success=True,
        tenant_id=tenant_id,
        user_id=user.id,
        resource="USER",
        resource_id=str(user.id),
        request=request
    )

    return user
