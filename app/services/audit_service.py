from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from fastapi import Request


def log_audit(
    db: Session,
    *,
    action: str,
    success: bool,
    tenant_id: int | None = None,
    user_id: int | None = None,
    resource: str | None = None,
    resource_id: str | None = None,
    reason: str | None = None,
    request: Request | None = None
):
    ip_address = None
    user_agent = None

    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    log = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        success=success,
        reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.add(log)
    db.commit()
