"""Audit-log read API (Phase 3 / HIPAA). Admin-only, read-only, tenant-scoped."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, PageParams, TenantId, require_roles
from app.crud.base import CRUDBase
from app.db.models.audit import AuditLog
from app.schemas.common import PaginatedResponse
from app.schemas.factory import build_schemas

_, _, AuditLogRead = build_schemas(AuditLog, "AuditLog")

_crud = CRUDBase(
    AuditLog,
    sortable_fields=("created_at", "id"),
    default_sort="created_at",
    soft_delete_field=None,
)

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get(
    "",
    response_model=PaginatedResponse[AuditLogRead],
    operation_id="list_audit_logs",
    summary="List audit-log entries (admin only)",
    dependencies=[Depends(require_roles("admin"))],
)
def list_audit_logs(
    db: DbSession,
    tenant_id: TenantId,
    page: PageParams,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
):
    # AUD-1: ``resource_id`` retrieves the full change history of one record, e.g.
    # ``?resource_type=insurance-claims&resource_id={id}``.
    items, total = _crud.list(
        db,
        tenant_id=tenant_id,
        page=page.page,
        size=page.size,
        sort=page.sort,
        order=page.order,
        filters={"user_id": user_id, "resource_type": resource_type, "resource_id": resource_id},
    )
    return PaginatedResponse.build(items, total, page.page, page.size)
