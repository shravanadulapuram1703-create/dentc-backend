from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.role import Role
from app.models.permission import Permission
from app.services.audit_service import log_audit


def create_role(
    db: Session,
    *,
    name: str,
    permission_ids: list[int],
    level: int,
    is_system : bool,
    tenant_id: int,
    created_by,
    request
):
    if db.query(Role).filter(
        Role.name == name,
        Role.tenant_id == tenant_id
    ).first():
        raise HTTPException(
            status_code=400,
            detail="Role already exists"
        )

    permissions = db.query(Permission).filter(
        Permission.id.in_(permission_ids)
    ).all()

    role = Role(name=name, tenant_id=tenant_id)
    role.permissions = permissions
    role.level = level
    role.is_system = is_system

    db.add(role)
    db.commit()
    db.refresh(role)

    log_audit(
        db,
        action="ROLE_CREATE",
        success=True,
        tenant_id=tenant_id,
        user_id=created_by.id,
        resource="ROLE",
        resource_id=str(role.id),
        request=request
    )

    return role
