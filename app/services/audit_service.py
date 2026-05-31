"""Audit-log writer.

Kept tiny and exception-safe: auditing must never break the request it records.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.db.models.audit import AuditLog
from app.db.session import SessionLocal

logger = get_logger(__name__)

# Methods that mutate state and are therefore audited.
AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def write_audit(
    *,
    tenant_id: int | None,
    user_id: int | None,
    method: str,
    path: str,
    status_code: int,
    ip_address: str | None,
    request_id: str | None,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            AuditLog(
                tenant_id=tenant_id,
                user_id=user_id,
                action=method,
                resource_type=resource_type,
                resource_id=resource_id,
                method=method,
                path=path,
                status_code=status_code,
                ip_address=ip_address,
                request_id=request_id,
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - auditing must not raise
        db.rollback()
        logger.warning("Failed to write audit log for %s %s: %s", method, path, exc)
    finally:
        db.close()
