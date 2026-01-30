from app.models.user import User
from sqlalchemy.orm import Session
from app.models.user_role import UserRole
from app.models.role_permission import RolePermission

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)


def user_has_permission(user, permission_code: str) -> bool:
    if user.role == "super_admin":
        logger.info(
            "Superuser permission bypass",
            extra={"permission": permission_code}
        )
        return True

    for role in user.roles:

        logger.info(f"role : -----> {role}")

        for perm in role.permissions:
            logger.info(f"perm : -----> {perm}")
            logger.info(f"perm.code : -----> {perm.code}")
            logger.info(f"perm.code : {perm.code} : -----> permission_code : {permission_code}")
            if perm.code == permission_code:
                logger.info(
                    "Permission granted",
                    extra={
                        "permission": permission_code,
                        "role": role.name
                    }
                )
                return True

    logger.warning(
        "Permission denied",
        extra={"permission": permission_code}
    )
    return False






def get_user_permissions(
    db: Session,
    *,
    user_id: int,
    tenant_id: int,
    office_id: int | None
) -> set[str]:
    """
    Resolve effective permissions for a user in a given tenant + office context
    """

    query = (
        db.query(RolePermission.permission)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .filter(
            UserRole.user_id == user_id,
            UserRole.tenant_id == tenant_id,
        )
    )

    if office_id:
        query = query.filter(UserRole.office_id == office_id)

    permissions = {row.permission for row in query.all()}
    return permissions
