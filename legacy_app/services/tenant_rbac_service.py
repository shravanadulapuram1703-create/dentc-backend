from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.role import Role
from app.models.role_permission import RolePermission
from app.services.audit_service import log_audit

TEMPLATE_TENANT_ID = 1  # your RBAC template tenant


def copy_rbac_roles_to_tenant(
    db: Session,
    *,
    tenant_id: int,
    created_by: int | None = None
):
    """
    Copies RBAC roles + permissions from template tenant into a new tenant.

    This function is:
    - Idempotent
    - Transaction-safe
    - SaaS-grade
    """

    try:
        # 1️⃣ Fetch template roles
        template_roles = (
            db.query(Role)
            .filter(
                Role.tenant_id == TEMPLATE_TENANT_ID,
                Role.is_system.is_(False),
            )
            .all()
        )

        if not template_roles:
            raise RuntimeError("No RBAC template roles found")

        role_id_map: dict[int, int] = {}

        # 2️⃣ Copy roles
        for role in template_roles:
            existing = db.query(Role).filter(
                Role.tenant_id == tenant_id,
                Role.name == role.name,
            ).first()

            if existing:
                role_id_map[role.id] = existing.id
                continue

            new_role = Role(
                tenant_id=tenant_id,
                name=role.name,
                level=role.level,
                is_system=False,
            )
            db.add(new_role)
            db.flush()  # get ID

            role_id_map[role.id] = new_role.id

        # 3️⃣ Copy role → permission mappings
        template_role_ids = list(role_id_map.keys())

        role_permissions = (
            db.query(RolePermission)
            .filter(RolePermission.role_id.in_(template_role_ids))
            .all()
        )

        for rp in role_permissions:
            new_role_id = role_id_map[rp.role_id]

            exists = db.query(RolePermission).filter(
                RolePermission.role_id == new_role_id,
                RolePermission.permission == rp.permission,
            ).first()

            if exists:
                continue

            db.add(
                RolePermission(
                    role_id=new_role_id,
                    permission=rp.permission,
                )
            )

        # 4️⃣ Audit
        log_audit(
            db=db,
            actor_id=created_by,
            action="TENANT_RBAC_COPIED",
            tenant_id=tenant_id,
            metadata={
                "source_tenant": TEMPLATE_TENANT_ID,
                "roles_copied": len(role_id_map),
            },
        )

        db.commit()
        return True

    except Exception:
        db.rollback()
        raise
