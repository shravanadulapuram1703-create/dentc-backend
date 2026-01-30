from sqlalchemy.orm import Session
from app.models.user_role import UserRole
from fastapi import HTTPException, status
from app.models.role import Role
from app.services.audit_service import log_audit


def get_actor_min_role_level(
    db: Session,
    *,
    actor_id: int,
    tenant_id: int,
    office_id: int | None
) -> int:
    """
    Returns the MOST powerful role level (lowest number) the actor has
    in the given tenant / office context.
    """
    q = (
        db.query(UserRole)
        .join(UserRole.role)
        .filter(
            UserRole.user_id == actor_id,
            UserRole.tenant_id == tenant_id,
        )
    )

    if office_id:
        q = q.filter(UserRole.office_id == office_id)

    roles = q.all()
    if not roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Actor has no role in this context"
        )

    return min(r.role.level for r in roles)



def assign_role_to_user(
    db: Session,
    *,
    actor_id: int,
    target_user_id: int,
    role_id: int,
    tenant_id: int,
    office_id: int
):
    """
    Assign a role to a user in an office (transactional).
    """

    try:
        actor_level = get_actor_min_role_level(
            db,
            actor_id=actor_id,
            tenant_id=tenant_id,
            office_id=office_id
        )

        role = db.query(Role).filter(
            Role.id == role_id,
            Role.tenant_id == tenant_id
        ).first()

        if not role:
            raise HTTPException(404, "Role not found")

        # 🔐 Privilege escalation prevention
        if role.level <= actor_level:
            raise HTTPException(
                status_code=403,
                detail="Cannot assign equal or higher privilege role"
            )

        # Prevent duplicate assignment
        exists = db.query(UserRole).filter_by(
            user_id=target_user_id,
            role_id=role_id,
            tenant_id=tenant_id,
            office_id=office_id
        ).first()

        if exists:
            raise HTTPException(400, "Role already assigned")

        user_role = UserRole(
            user_id=target_user_id,
            role_id=role_id,
            tenant_id=tenant_id,
            office_id=office_id
        )

        db.add(user_role)
        db.flush()  # ensures ID exists before audit

        log_audit(
            db=db,
            actor_id=actor_id,
            action="USER_ROLE_ASSIGNED",
            tenant_id=tenant_id,
            target_user_id=target_user_id,
            metadata={
                "role_id": role_id,
                "office_id": office_id
            }
        )

        db.commit()
        return user_role

    except Exception:
        db.rollback()
        raise


def update_user_role(
    db: Session,
    *,
    actor_id: int,
    user_role_id: int,
    new_role_id: int,
    tenant_id: int
):
    """
    Upgrade or downgrade a user's role safely.
    """

    try:
        user_role = db.query(UserRole).filter(
            UserRole.id == user_role_id,
            UserRole.tenant_id == tenant_id
        ).first()

        if not user_role:
            raise HTTPException(404, "User role not found")

        actor_level = get_actor_min_role_level(
            db,
            actor_id=actor_id,
            tenant_id=tenant_id,
            office_id=user_role.office_id
        )

        new_role = db.query(Role).filter(
            Role.id == new_role_id,
            Role.tenant_id == tenant_id
        ).first()

        if not new_role:
            raise HTTPException(404, "Target role not found")

        if new_role.level <= actor_level:
            raise HTTPException(
                status_code=403,
                detail="Insufficient privilege to assign this role"
            )

        old_role_id = user_role.role_id
        user_role.role_id = new_role_id

        log_audit(
            db=db,
            actor_id=actor_id,
            action="USER_ROLE_UPDATED",
            tenant_id=tenant_id,
            target_user_id=user_role.user_id,
            metadata={
                "old_role_id": old_role_id,
                "new_role_id": new_role_id,
                "office_id": user_role.office_id
            }
        )

        db.commit()
        return user_role

    except Exception:
        db.rollback()
        raise

def remove_user_role(
    db: Session,
    *,
    actor_id: int,
    user_role_id: int,
    tenant_id: int
):
    """
    Remove a role assignment from a user.
    """

    try:
        user_role = db.query(UserRole).filter(
            UserRole.id == user_role_id,
            UserRole.tenant_id == tenant_id
        ).first()

        if not user_role:
            raise HTTPException(404, "User role not found")

        actor_level = get_actor_min_role_level(
            db,
            actor_id=actor_id,
            tenant_id=tenant_id,
            office_id=user_role.office_id
        )

        if user_role.role.level <= actor_level:
            raise HTTPException(
                status_code=403,
                detail="Cannot remove equal or higher privilege role"
            )

        db.delete(user_role)

        log_audit(
            db=db,
            actor_id=actor_id,
            action="USER_ROLE_REMOVED",
            tenant_id=tenant_id,
            target_user_id=user_role.user_id,
            metadata={
                "role_id": user_role.role_id,
                "office_id": user_role.office_id
            }
        )

        db.commit()
        return True

    except Exception:
        db.rollback()
        raise

def list_user_roles(
    db: Session,
    *,
    user_id: int,
    tenant_id: int
):
    return db.query(UserRole).filter(
        UserRole.user_id == user_id,
        UserRole.tenant_id == tenant_id
    ).all()
