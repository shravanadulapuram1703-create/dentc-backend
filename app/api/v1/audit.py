"""Audit-log read API (Phase 3 / HIPAA).

Two reads:

* ``GET /audit-logs`` — the tenant-wide log. Admin-only, tenant-scoped.
* ``GET /patients/{patient_id}/audit-logs`` (MH-19) — everything that happened
  to one chart. Open to any authenticated user of the tenant: a front-desk user
  rendering the Medical History change log cannot be an admin, and the row set
  is already narrowed to the patient they are looking at.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select

from app.api.deps import DbSession, PageParams, TenantId, get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.crud.base import CRUDBase
from app.db.models import Patient
from app.db.models.audit import AuditLog
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.factory import build_schemas

_, _, AuditLogRead = build_schemas(AuditLog, "AuditLog")

_crud = CRUDBase(
    AuditLog,
    sortable_fields=("created_at", "id"),
    default_sort="created_at",
    soft_delete_field=None,
)

router = APIRouter(prefix="/audit-logs", tags=["Audit"])

patient_router = APIRouter(
    prefix="/patients",
    tags=["Audit"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


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
    patient_id: Annotated[int | None, Query(description="MH-19: only entries for this chart")] = None,
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
        filters={
            "user_id": user_id, "resource_type": resource_type,
            "resource_id": resource_id, "patient_id": patient_id,
        },
    )
    return PaginatedResponse.build(items, total, page.page, page.size)


@patient_router.get(
    "/{patient_id}/audit-logs",
    response_model=PaginatedResponse[AuditLogRead],
    operation_id="list_patient_audit_logs",
    summary="Audit-log entries for one patient's chart (MH-19, any authenticated user)",
)
def list_patient_audit_logs(
    db: DbSession,
    tenant_id: TenantId,
    page: PageParams,
    patient_id: Annotated[int, Path(description="patient identifier")],
    resource_type: Annotated[
        str | None,
        Query(description="e.g. patient-medical-alerts, patient-questionnaire-responses, patients"),
    ] = None,
    resource_id: str | None = None,
    user_id: int | None = None,
):
    """Every audited mutation whose ``patient_id`` resolved to this chart, newest
    first, with the ``details`` block (``row_id`` / ``before`` / ``after``) the
    CRUD engine recorded. Entries older than the MH-19 change carry no
    ``patient_id`` and are not listed here — the Medical History screen's own
    field-level log (``/medical-history/changes``) covers those answers."""
    exists = db.execute(
        select(Patient.id).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if exists is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    items, total = _crud.list(
        db,
        tenant_id=tenant_id,
        page=page.page,
        size=page.size,
        sort=page.sort,
        order=page.order,
        filters={
            "patient_id": patient_id, "resource_type": resource_type,
            "resource_id": resource_id, "user_id": user_id,
        },
    )
    return PaginatedResponse.build(items, total, page.page, page.size)
