"""Office Setup routes (Setup -> Offices). Resolves backend gaps #10–#17.

`GET /offices/metadata` is a flat aggregate; the rest are nested under
`/offices/{office_id}/...` and verify the office belongs to the authenticated
tenant before any read/write.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Request, Response, UploadFile, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

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
    ServiceEmailConfirm,
    ServiceEmailVerifyResult,
    SmartAssistCatalogItem,
    SmartAssistRead,
    SmartAssistSmsTemplate,
    SmartAssistUpdate,
    StatementSettingsRead,
    StatementSettingsUpdate,
)
from app.core import concurrency
from app.services import holiday_service, office_calendar_service, office_lifecycle_service, office_rules
from app.services import office_setup_service as svc

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


class FeeDefaultsUpdate(BaseModel):
    """Only the fields present are applied; a schedule pointer may be set to null
    to clear it. Pricing hierarchy §3.5."""

    default_ucr_fee_schedule_id: int | None = None
    default_fee_schedule_id: int | None = None
    unpriced_charge_policy: str | None = None


@router.patch(
    "/{office_id}/fee-defaults",
    operation_id="update_office_fee_defaults",
    summary="Set the office UCR list, default patient list and unpriced-charge policy",
)
def update_office_fee_defaults(
    db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: FeeDefaultsUpdate,
):
    return svc.set_fee_defaults(
        db, office_id, tenant_id, body.model_dump(exclude_unset=True),
    )


# ── #10 metadata aggregate (flat; declared before /{office_id}) ──────────────
@router.get("/metadata", response_model=OfficeMetadata, operation_id="get_office_metadata")
def get_office_metadata(db: DbSession, tenant_id: TenantId):
    return svc.metadata(db, tenant_id)


@router.get("/setup-rules", operation_id="get_office_setup_rules",
            summary="Office Setup vocabularies + format rules the server enforces")
def get_office_setup_rules() -> dict:
    """OFF-QA-2/4/5/8/9: the same table the write paths validate against."""
    return office_rules.rules_metadata()


@router.get("/smart-assist/catalog", response_model=list[SmartAssistCatalogItem],
            operation_id="get_smart_assist_catalog")
def get_smart_assist_catalog():
    """OFF-QA-6: the default SmartAssist item set (an unconfigured office reads it
    as its grid until the first save)."""
    return svc.smart_assist_catalog()


# ── OFF-QA-15/16/17 delete / impact ──────────────────────────────────────────
@router.get("/{office_id}/delete-impact", operation_id="get_office_delete_impact",
            summary="What still depends on this office (the Delete dialog's counts)")
def get_office_delete_impact(db: DbSession, office_id: OfficeScope, tenant_id: TenantId) -> dict:
    """``blocking`` names the counts that make a plain DELETE a 409
    (``future_appointments``, ``users_with_no_other_office``)."""
    return office_lifecycle_service.delete_impact(db, svc.get_office_in_tenant(db, office_id, tenant_id))


@router.delete(
    "/{office_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="delete_office",
    tags=["Organization"], summary="Delete office",
    responses={409: {"model": ErrorResponse}, 412: {"model": ErrorResponse}},
)
def delete_office(
    db: DbSession, office_id: OfficeScope, tenant_id: TenantId, current: CurrentUser, request: Request,
    force: Annotated[bool, Query(description="Delete despite upcoming appointments / users left "
                                             "with no office (OFF-QA-15).")] = False,
    hard: Annotated[bool, Query(description="Admin only: permanently remove an office nothing "
                                            "references, with its own settings (OFF-QA-17).")] = False,
):
    """Soft delete (default): 409 ``office_in_use`` while upcoming appointments or
    stranded users remain, unless ``force``; deactivates the office's operatories
    and stamps ``deleted_at``/``deleted_by``. Honours ``If-Match``."""
    concurrency.reset()
    concurrency.from_headers(request.headers)
    office = svc.get_office_in_tenant(db, office_id, tenant_id)
    concurrency.check(office, concurrency.snapshot(), db=db, resource="offices")
    if hard:
        office_lifecycle_service.hard_delete(db, office, current)
    else:
        office_lifecycle_service.soft_delete(db, office, current.id, force=force)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    # EDIT-PLAN-7: sync DB + storage work must not run on the event loop.
    url = await run_in_threadpool(
        svc.save_statement_logo, db, office_id, tenant_id, file.filename or "logo", file.content_type or "", data,
    )
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


@router.post("/{office_id}/integrations/verify-email", response_model=ServiceEmailVerifyResult,
             operation_id="send_office_service_email_verification")
def send_service_email_verification(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, current: CurrentUser):
    """OFF-QA-5: mail a 6-digit code to the saved ``service_email`` (24 h)."""
    return svc.send_service_email_verification(db, office_id, tenant_id, current.id)


@router.post("/{office_id}/integrations/verify-email/confirm", response_model=OfficeIntegrationsRead,
             operation_id="confirm_office_service_email_verification")
def confirm_service_email_verification(db: DbSession, office_id: OfficeScope, tenant_id: TenantId,
                                       body: ServiceEmailConfirm, current: CurrentUser):
    """OFF-QA-5: sets ``service_email_verified`` when the code matches."""
    return _integrations_read(svc.confirm_service_email_verification(db, office_id, tenant_id, body.code, current.id))


# ── #14 Schedule (weekly grid) ───────────────────────────────────────────────
@router.get("/{office_id}/schedule", response_model=list[ScheduleDayRead], operation_id="get_office_schedule")
def get_schedule(db: DbSession, office_id: OfficeScope, tenant_id: TenantId):
    return svc.get_schedule(db, office_id, tenant_id)


@router.put("/{office_id}/schedule", response_model=list[ScheduleDayRead], operation_id="set_office_schedule")
def set_schedule(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: ScheduleReplace):
    return svc.replace_schedule(db, office_id, tenant_id, [d.model_dump() for d in body.days])


@router.get("/{office_id}/calendar", operation_id="get_office_calendar",
            summary="Open windows, lunch and holidays per date")
def get_office_calendar(db: DbSession, office_id: OfficeScope, tenant_id: TenantId,
                        from_date: Annotated[date, Query()], to_date: Annotated[date, Query()]) -> dict:
    """OFF-QA-7: the calendar the appointment write path enforces (``409
    office_closed``), so the scheduler can grey out the same slots."""
    office = svc.get_office_in_tenant(db, office_id, tenant_id)
    return office_calendar_service.calendar(db, office, from_date, to_date)


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
    return holiday_service.import_federal(db, tenant_id, body.year, body.status, current.id, office_id=office_id,
                                         observed=body.observed)


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


@router.get("/{office_id}/smart-assist/sms-templates", response_model=list[SmartAssistSmsTemplate],
            operation_id="list_office_smart_assist_sms_templates")
def list_smart_assist_sms_templates(db: DbSession, office_id: OfficeScope, tenant_id: TenantId):
    """OFF-QA-6: the SMS templates a SmartAssist row may point at (this office's
    + the tenant-shared ones); ``sms_template_id`` is validated against it."""
    return svc.smart_assist_sms_templates(db, office_id, tenant_id)


@router.patch("/{office_id}/smart-assist", response_model=SmartAssistRead, operation_id="update_office_smart_assist")
def update_smart_assist(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: SmartAssistUpdate, current: CurrentUser):
    items = [i.model_dump() for i in body.items] if body.items is not None else None
    return svc.update_smart_assist(db, office_id, tenant_id, body.enabled, items, current.id)
