from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.tenant import Tenant
from app.services.audit_service import log_audit

from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.utils.password import hash_password
from app.utils.token import create_access_token
from app.models.impersonation_session import ImpersonationSession

from app.api.v1.users.schemas import UserCreate, UserUpdate, UserResponse

from app.api.v1.users.service import create_user

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)


def create_tenant(
    db: Session,
    *,
    name: str,
    code: str,
    created_by: int,
    request
) -> Tenant:

    #  Uniqueness checks
    if db.query(Tenant).filter(Tenant.name == name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant name already exists"
        )

    if db.query(Tenant).filter(Tenant.code == code).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant code already exists"
        )

    # Create tenant
    tenant = Tenant(
        name=name,
        code=code,
        created_by=created_by
    )

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    # Audit log
    log_audit(
        db=db,
        actor_user_id=created_by,
        tenant_id=tenant.id,
        action="TENANT_CREATED",
        resource_type="tenant",
        resource_id=tenant.id,
        metadata={"name": name, "code": code},
        request=request
    )

    return tenant


def create_tenant_owner(
    db: Session,
    *,
    tenant_id: int,
    # email: str,
    # name: str,
    # password: str,
    payload: UserCreate,
    created_by: int,
    request
):
    # Email uniqueness
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )

    # Get tenant_owner role
    role = db.query(Role).filter(
        Role.name == "Practice Owner",
        Role.scope == "tenant"
    ).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant owner role not configured"
        )

    # Create user
    # user = User(
    #     email=email,
    #     name=name,
    #     password_hash=hash_password(password),
    #     tenant_id=tenant_id,
    #     created_by=created_by,
    #     is_platform_user=False,
    #     is_active=True
    # )


    # {
    # "tenant_id": tenant_id,
    # "email": email,
    # "name": name,
    # "password": password,
    # "created_by": created_by
    # }
    # payload = 
    logger.info(f"payload before creating tenant owner >>>>> {payload}")

    # payload['role_ids'] = [role.id]
    payload.role_ids = [role.id]

    payload.tenant_id = tenant_id

    logger.info(f"payload before creating tenant owner >>>>> {[role.id]}")

    user = create_user(
        db=db,
        # tenant_id=request.state.tenant_id,
        payload=payload,
        request=request
    )


    # user = User(
    #     email=email,
    #     password_hash=hash_password(password),
    #     tenant_id=tenant_id,
    #     created_by=created_by,
    #     role = role.name,# if roles else "Read Only",
    #     is_active=True
    # )

    # db.add(user)
    # db.commit()
    # db.refresh(user)

    # # Assign tenant_owner role (tenant scoped)
    # user_role = UserRole(
    #     user_id=user.id,
    #     role_id=role.id,
    #     tenant_id=tenant_id,
    #     # office_id=None,  # tenant-level role
    #     assigned_by=created_by
    # )

    # db.add(user_role)
    # db.commit()

    # Audit log
    log_audit(
        db=db,
        actor_user_id=created_by,
        tenant_id=tenant_id,
        action="TENANT_OWNER_CREATED",
        resource_type="user",
        resource_id=user.id,
        metadata={
            "email": payload.email,
            "role": "tenant_owner"
        },
        request=request
    )

    return user


def update_tenant_status(
    db: Session,
    *,
    tenant_id: int,
    is_active: bool | None,
    is_locked: bool | None,
    reason: str | None,
    actor_user_id: int,
    request
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    old_state = {
        "is_active": tenant.is_active,
        "is_locked": tenant.is_locked
    }

    # Apply changes
    if is_active is not None:
        tenant.is_active = is_active

    if is_locked is not None:
        tenant.is_locked = is_locked

        # Lock / unlock all users
        db.query(User).filter(
            User.tenant_id == tenant_id
        ).update(
            {"is_locked": is_locked},
            synchronize_session=False
        )

    db.commit()

    # Audit log
    log_audit(
        db=db,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        action="TENANT_STATUS_UPDATED",
        resource_type="tenant",
        resource_id=tenant_id,
        metadata={
            "old": old_state,
            "new": {
                "is_active": tenant.is_active,
                "is_locked": tenant.is_locked
            },
            "reason": reason
        },
        request=request
    )

    return tenant


def switch_tenant_context(
    db: Session,
    *,
    tenant_id: int,
    actor_user,
    request
):
    # Validate tenant
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    if not tenant.is_active or tenant.is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is suspended or locked"
        )

    # Create new JWT with tenant context
    token_data = {
        "sub": str(actor_user.id),
        "is_platform_user": True,
        "tenant_id": tenant.id,
        "office_id": None,
        "roles": ["super_admin"],
        "switched_tenant": True
    }

    access_token = create_access_token(token_data)

    # Audit log
    log_audit(
        db=db,
        actor_user_id=actor_user.id,
        tenant_id=tenant.id,
        action="TENANT_CONTEXT_SWITCHED",
        resource_type="tenant",
        resource_id=tenant.id,
        metadata={
            "tenant_name": tenant.name
        },
        request=request
    )

    return access_token



def start_impersonation(
    db: Session,
    *,
    admin_user,
    target_user_id: int,
    request
):
    # Prevent nested impersonation
    if hasattr(admin_user, "impersonation"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already impersonating a user"
        )

    # Fetch target user
    target_user = db.query(User).filter(User.id == target_user_id).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not target_user.is_active or target_user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Target user is inactive or locked"
        )

    # Get target user roles
    roles = (
        db.query(UserRole)
        .filter(UserRole.user_id == target_user.id)
        .all()
    )

    role_names = [r.role.name for r in roles]

    # Create impersonation session
    session = ImpersonationSession(
        admin_user_id=admin_user.id,
        impersonated_user_id=target_user.id,
        ip_address=request.client.host if request else None,
        user_agent=request.headers.get("user-agent")
    )

    db.add(session)
    db.commit()

    # Create JWT
    token_payload = {
        "sub": str(target_user.id),
        "tenant_id": target_user.tenant_id,
        # "office_id": roles[0].office_id if roles else None,
        "roles": role_names,
        "impersonation": {
            "admin_user_id": admin_user.id,
            "session_id": session.id
        }
    }

    access_token = create_access_token(token_payload)

    # Audit
    log_audit(
        db=db,
        actor_user_id=admin_user.id,
        tenant_id=target_user.tenant_id,
        action="IMPERSONATION_STARTED",
        resource_type="user",
        resource_id=target_user.id,
        metadata={
            "session_id": session.id
        },
        request=request
    )

    return access_token, target_user.id



def stop_impersonation(
    db: Session,
    *,
    admin_user,
    impersonation_payload,
    request
):
    session_id = impersonation_payload.get("session_id")

    session = (
        db.query(ImpersonationSession)
        .filter(ImpersonationSession.id == session_id)
        .first()
    )

    if session:
        session.ended_at = db.func.now()
        db.commit()

    # Restore platform token
    token_payload = {
        "sub": str(admin_user.id),
        "is_platform_user": True,
        "roles": ["super_admin"]
    }

    access_token = create_access_token(token_payload)

    log_audit(
        db=db,
        actor_user_id=admin_user.id,
        tenant_id=None,
        action="IMPERSONATION_ENDED",
        resource_type="impersonation",
        resource_id=session_id,
        metadata={},
        request=request
    )

    return access_token




# from app.services.tenant_rbac_service import copy_rbac_roles_to_tenant

# def create_tenant(...):
    tenant = Tenant(...)
    db.add(tenant)
    db.flush()

    copy_rbac_roles_to_tenant(
        db,
        tenant_id=tenant.id,
        created_by=current_user.id
    )

    db.commit()
    return tenant
