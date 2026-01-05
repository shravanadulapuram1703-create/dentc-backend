from sqlalchemy.orm import Session
from app.core.redis import redis_client
from app.services.rbac_service import get_user_permissions

CACHE_TTL_SECONDS = 300  # 5 minutes


def get_cached_permissions(
    db: Session,
    *,
    user_id: int,
    tenant_id: int,
    office_id: int | None,
) -> set[str]:
    key = f"rbac:perms:{tenant_id}:{office_id or 'null'}:{user_id}"

    cached = redis_client.get(key)
    if cached:
        return set(cached.split(","))

    # Cache miss → DB
    perms = get_user_permissions(
        db,
        user_id=user_id,
        tenant_id=tenant_id,
        office_id=office_id,
    )

    if perms:
        redis_client.setex(
            key,
            CACHE_TTL_SECONDS,
            ",".join(perms),
        )

    return perms
