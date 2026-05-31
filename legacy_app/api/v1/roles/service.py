from app.services.rbac_cache_invalidator import invalidate_user_permissions

invalidate_user_permissions(
    tenant_id=tenant_id,
    user_id=target_user_id,
    office_id=office_id,
)
