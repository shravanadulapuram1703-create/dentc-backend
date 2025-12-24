from app.models.user import User
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
