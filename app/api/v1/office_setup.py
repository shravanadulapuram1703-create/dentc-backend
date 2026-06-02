"""Office Setup routes (Setup -> Offices). Resolves backend gaps #10–#17.

`GET /offices/metadata` is a flat aggregate; the rest are nested under
`/offices/{office_id}/...` and verify the office belongs to the authenticated
tenant before any read/write.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.db.models.office_setup import (
    OfficeAdvancedSettings,
    OfficeIntegrations,
    OfficeStatementSettings,
)
from app.schemas.account import (
    FederalHolidaysImport,
    HolidayBulkDelete,
    HolidayCreate,
    HolidayRangeCreate,
    HolidayRead,
    HolidayUpdate,
    LogoResult,
)
from app.schemas.common import ErrorResponse
from app.schemas.office_setup import (
    AdvancedSettingsRead,
    AdvancedSettingsUpdate,
    OfficeIntegrationsRead,
    OfficeIntegrationsUpdate,
    OfficeMetadata,
    ScheduleDayRead,
    ScheduleReplace,
    SmartAssistRead,
    SmartAssistUpdate,
    StatementSettingsRead,
    StatementSettingsUpdate,
)
from app.services import holiday_service, office_setup_service as svc

router = APIRouter(
    prefix="/offices",
    tags=["Office Setup"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


def _office_scope(office_id: Annotated[int, Path()], tenant_id: TenantId, db: DbSession) -> int:
    svc.get_office_in_tenant(db, office_id, tenant_id)
    return office_id


OfficeScope = Annotated[int, Depends(_office_scope)]


# ── #10 metadata aggregate (flat; declared before /{office_id}) ──────────────
@router.get("/metadata", response_model=OfficeMetadata, operation_id="get_office_metadata")
def get_office_metadata(db: DbSession, tenant_id: TenantId):
    return svc.metadata(db, tenant_id)


# ── #12 Statement settings + logo ────────────────────────────────────────────
@router.get("/{office_id}/statement-settings", response_model=StatementSettingsRead, operation_id="get_office_statement_settings")
def get_statement_settings(db: DbSession, office_id: OfficeScope, tenant_id: TenantId):
    return svc.get_or_create_singleton(db, OfficeStatementSettings, office_id, tenant_id)


@router.patch("/{office_id}/statement-settings", response_model=StatementSettingsRead, operation_id="update_office_statement_settings")
def update_statement_settings(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: StatementSettingsUpdate, current: CurrentUser):
    return svc.update_singleton(db, OfficeStatementSettings, office_id, tenant_id, body.model_dump(exclude_unset=True), current.id)


@router.post("/{office_id}/statement-logo", response_model=LogoResult, operation_id="upload_office_statement_logo")
async def upload_statement_logo(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, file: Annotated[UploadFile, File()]):
    data = await file.read()
    url = svc.save_statement_logo(db, office_id, tenant_id, file.filename or "logo", file.content_type or "", data)
    return LogoResult(logo_url=url)


@router.delete("/{office_id}/statement-logo", status_code=status.HTTP_204_NO_CONTENT, operation_id="delete_office_statement_logo")
def delete_statement_logo(db: DbSession, office_id: OfficeScope, tenant_id: TenantId):
    svc.delete_statement_logo(db, office_id, tenant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── #13 Integrations ─────────────────────────────────────────────────────────
def _integrations_read(row: OfficeIntegrations) -> OfficeIntegrationsRead:
    out = OfficeIntegrationsRead.model_validate(row)
    out.dosespot_key_masked = svc.dosespot_key_masked(row)
    return out


@router.get("/{office_id}/integrations", response_model=OfficeIntegrationsRead, operation_id="get_office_integrations")
def get_integrations(db: DbSession, office_id: OfficeScope, tenant_id: TenantId):
    return _integrations_read(svc.get_or_create_singleton(db, OfficeIntegrations, office_id, tenant_id))


@router.patch("/{office_id}/integrations", response_model=OfficeIntegrationsRead, operation_id="update_office_integrations")
def update_integrations(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: OfficeIntegrationsUpdate, current: CurrentUser):
    return _integrations_read(svc.update_integrations(db, office_id, tenant_id, body.model_dump(exclude_unset=True), current.id))


# ── #14 Schedule (weekly grid) ───────────────────────────────────────────────
@router.get("/{office_id}/schedule", response_model=list[ScheduleDayRead], operation_id="get_office_schedule")
def get_schedule(db: DbSession, office_id: OfficeScope, tenant_id: TenantId):
    return svc.get_schedule(db, office_id, tenant_id)


@router.put("/{office_id}/schedule", response_model=list[ScheduleDayRead], operation_id="set_office_schedule")
def set_schedule(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: ScheduleReplace):
    return svc.replace_schedule(db, office_id, tenant_id, [d.model_dump() for d in body.days])


# ── #15 Office-scoped holidays (reuse holiday_service) ───────────────────────
@router.get("/{office_id}/holidays", response_model=list[HolidayRead], operation_id="list_office_holidays")
def list_office_holidays(db: DbSession, office_id: OfficeScope, tenant_id: TenantId,
                         from_date: Annotated[str | None, Query()] = None,
                         to_date: Annotated[str | None, Query()] = None):
    from datetime import date as _d
    f = _d.fromisoformat(from_date) if from_date else None
    t = _d.fromisoformat(to_date) if to_date else None
    return holiday_service.list_holidays(db, tenant_id, f, t, office_id=office_id)


@router.post("/{office_id}/holidays", response_model=HolidayRead, status_code=status.HTTP_201_CREATED, operation_id="create_office_holiday")
def create_office_holiday(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: HolidayCreate, current: CurrentUser):
    return holiday_service.create_holiday(db, tenant_id, body.model_dump(exclude_unset=True), current.id, office_id=office_id)


@router.patch("/{office_id}/holidays/{holiday_id}", response_model=HolidayRead, operation_id="update_office_holiday")
def update_office_holiday(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, holiday_id: int, body: HolidayUpdate):
    return holiday_service.update_holiday(db, tenant_id, holiday_id, body.model_dump(exclude_unset=True), office_id=office_id)


@router.delete("/{office_id}/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="delete_office_holiday")
def delete_office_holiday(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, holiday_id: int):
    holiday_service.delete_holiday(db, tenant_id, holiday_id, office_id=office_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{office_id}/holidays/bulk-delete", operation_id="bulk_delete_office_holidays")
def bulk_delete_office_holidays(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: HolidayBulkDelete) -> dict:
    return {"deleted": holiday_service.bulk_delete(db, tenant_id, body.ids, office_id=office_id)}


@router.post("/{office_id}/holidays/federal", response_model=list[HolidayRead], operation_id="import_office_federal_holidays")
def import_office_federal_holidays(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: FederalHolidaysImport, current: CurrentUser):
    return holiday_service.import_federal(db, tenant_id, body.year, body.status, current.id, office_id=office_id)


@router.post("/{office_id}/holidays/range", response_model=list[HolidayRead], operation_id="create_office_holiday_range")
def create_office_holiday_range(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: HolidayRangeCreate, current: CurrentUser):
    return holiday_service.create_range(
        db, tenant_id, body.from_date, body.to_date, body.name, body.status, body.holiday_type, current.id, office_id=office_id
    )


# ── #16 Advanced settings ─────────────────────────────────────────────────────
@router.get("/{office_id}/advanced-settings", response_model=AdvancedSettingsRead, operation_id="get_office_advanced_settings")
def get_advanced_settings(db: DbSession, office_id: OfficeScope, tenant_id: TenantId):
    return svc.get_or_create_singleton(db, OfficeAdvancedSettings, office_id, tenant_id)


@router.patch("/{office_id}/advanced-settings", response_model=AdvancedSettingsRead, operation_id="update_office_advanced_settings")
def update_advanced_settings(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: AdvancedSettingsUpdate, current: CurrentUser):
    return svc.update_singleton(db, OfficeAdvancedSettings, office_id, tenant_id, body.model_dump(exclude_unset=True), current.id)


# ── #17 SmartAssist ───────────────────────────────────────────────────────────
@router.get("/{office_id}/smart-assist", response_model=SmartAssistRead, operation_id="get_office_smart_assist")
def get_smart_assist(db: DbSession, office_id: OfficeScope, tenant_id: TenantId):
    return svc.get_smart_assist(db, office_id, tenant_id)


@router.patch("/{office_id}/smart-assist", response_model=SmartAssistRead, operation_id="update_office_smart_assist")
def update_smart_assist(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: SmartAssistUpdate, current: CurrentUser):
    items = [i.model_dump() for i in body.items] if body.items is not None else None
    return svc.update_smart_assist(db, office_id, tenant_id, body.enabled, items, current.id)
