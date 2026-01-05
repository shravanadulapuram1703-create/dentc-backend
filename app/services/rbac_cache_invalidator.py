from app.core.redis import redis_client


def invalidate_user_permissions(
    *,
    tenant_id: int,
    user_id: int,
    office_id: int | None = None,
):
    if office_id:
        key = f"rbac:perms:{tenant_id}:{office_id}:{user_id}"
        redis_client.delete(key)
    else:
        pattern = f"rbac:perms:{tenant_id}:*:{user_id}"
        for key in redis_client.scan_iter(pattern):
            redis_client.delete(key)
