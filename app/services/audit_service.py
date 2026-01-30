# app/utils/audit.py

from sqlalchemy.orm import Session
from fastapi import Request
from app.models.audit_log import AuditLog


def log_audit(
    db: Session,
    *,
    action: str,
    success: bool = True,

    tenant_id: int | None = None,
    actor_user_id: int | None = None,

    resource: str | None = None,
    resource_id: str | None = None,
    resource_type: str | None = None,
    resource_pk: str | None = None,

    reason: str | None = None,
    metadata: dict | None = None,

    impersonated_user_id: int | None = None,
    office_id: int | None = None,

    request: Request | None = None,
):
    ip_address = None
    user_agent = None

    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    log = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        resource_type=resource_type,
        resource_pk=resource_pk,
        success=success,
        reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
        impersonated_user_id=impersonated_user_id,
        office_id=office_id,
        metadata=metadata,
    )

    db.add(log)
    db.commit()
