"""Account Information module routes (Setup -> Account Information).

All endpoints are nested under ``/tenants/{tenant_id}/...`` to match the frontend
contract; the path tenant must equal the authenticated/effective tenant (a
``super_admin`` may target another via ``X-Tenant-ID``). Tenancy is still enforced
in every service by ``tenant_id``.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.core.exceptions import ForbiddenError
from app.schemas.account import (
    AccountCommunicationsRead,
    AccountCommunicationsUpdate,
    AccountSettingsRead,
    AccountSettingsUpdate,
    ConsentCreate,
    ConsentPreview,
    ConsentRead,
    FederalHolidaysImport,
    HolidayBulkDelete,
    HolidayCreate,
    HolidayRangeCreate,
    HolidayRead,
    HolidayUpdate,
    LogoResult,
    PhoneAssignmentRead,
    PhoneAssignmentsReplace,
    TelecomVerifyResult,
)
from app.schemas.common import ErrorResponse
from app.services import (
    account_service,
    communications_service,
    consent_service,
    holiday_service,
)


def _account_tenant(tenant_id: Annotated[int, Path()], effective: TenantId) -> int:
    if tenant_id != effective:
        raise ForbiddenError("Path tenant does not match the authenticated tenant")
    return effective


AccountTenant = Annotated[int, Depends(_account_tenant)]

router = APIRouter(
    prefix="/tenants/{tenant_id}",
    tags=["Account Info"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


# ── Basic + Advanced settings ────────────────────────────────────────────────
@router.get("/account-settings", response_model=AccountSettingsRead, operation_id="get_account_settings")
def get_account_settings(db: DbSession, tenant_id: AccountTenant):
    return account_service.to_read(account_service.get_or_create_settings(db, tenant_id))


@router.patch("/account-settings", response_model=AccountSettingsRead, operation_id="update_account_settings")
def update_account_settings(
    db: DbSession, tenant_id: AccountTenant, body: AccountSettingsUpdate, current: CurrentUser
):
    row = account_service.update_settings(db, tenant_id, body.model_dump(exclude_unset=True), current.id)
    return account_service.to_read(row)


# ── Logo ─────────────────────────────────────────────────────────────────────
@router.post("/logo", response_model=LogoResult, operation_id="upload_account_logo")
async def upload_account_logo(db: DbSession, tenant_id: AccountTenant, file: Annotated[UploadFile, File()]):
    data = await file.read()
    url = account_service.save_logo(db, tenant_id, file.filename or "logo", file.content_type or "", data)
    return LogoResult(logo_url=url)


@router.delete("/logo", status_code=status.HTTP_204_NO_CONTENT, operation_id="delete_account_logo")
def delete_account_logo(db: DbSession, tenant_id: AccountTenant):
    account_service.delete_logo(db, tenant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Communications ───────────────────────────────────────────────────────────
def _comm_read(row) -> AccountCommunicationsRead:  # noqa: ANN001
    out = AccountCommunicationsRead.model_validate(row)
    out.ein_masked = communications_service.ein_masked(row)
    return out


@router.get("/communications", response_model=AccountCommunicationsRead, operation_id="get_account_communications")
def get_account_communications(db: DbSession, tenant_id: AccountTenant):
    return _comm_read(communications_service.get_or_create(db, tenant_id))


@router.patch("/communications", response_model=AccountCommunicationsRead, operation_id="update_account_communications")
def update_account_communications(
    db: DbSession, tenant_id: AccountTenant, body: AccountCommunicationsUpdate, current: CurrentUser
):
    return _comm_read(communications_service.update(db, tenant_id, body.model_dump(exclude_unset=True), current.id))


@router.post("/communications/verify-telecom", response_model=TelecomVerifyResult, operation_id="verify_account_telecom")
def verify_account_telecom(db: DbSession, tenant_id: AccountTenant, current: CurrentUser):
    row = communications_service.verify_telecom(db, tenant_id, current.id)
    return TelecomVerifyResult(
        telecom_status=row.telecom_status or "unknown",
        telecom_verified_at=row.telecom_verified_at.isoformat() if row.telecom_verified_at else None,
    )


# ── Phone assignments ────────────────────────────────────────────────────────
@router.get("/phone-assignments", response_model=list[PhoneAssignmentRead], operation_id="list_phone_assignments")
def list_phone_assignments(db: DbSession, tenant_id: AccountTenant):
    return communications_service.list_phone_assignments(db, tenant_id)


@router.put("/phone-assignments", response_model=list[PhoneAssignmentRead], operation_id="set_phone_assignments")
def set_phone_assignments(db: DbSession, tenant_id: AccountTenant, body: PhoneAssignmentsReplace):
    payload = [a.model_dump() for a in body.assignments]
    return communications_service.replace_phone_assignments(db, tenant_id, payload)


# ── Holidays ───────────────────────────────────────────────────────────────
@router.get("/holidays", response_model=list[HolidayRead], operation_id="list_account_holidays")
def list_account_holidays(
    db: DbSession,
    tenant_id: AccountTenant,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
):
    return holiday_service.list_holidays(db, tenant_id, from_date, to_date)


@router.post("/holidays", response_model=HolidayRead, status_code=status.HTTP_201_CREATED, operation_id="create_account_holiday")
def create_account_holiday(db: DbSession, tenant_id: AccountTenant, body: HolidayCreate, current: CurrentUser):
    return holiday_service.create_holiday(db, tenant_id, body.model_dump(exclude_unset=True), current.id)


@router.patch("/holidays/{holiday_id}", response_model=HolidayRead, operation_id="update_account_holiday")
def update_account_holiday(db: DbSession, tenant_id: AccountTenant, holiday_id: int, body: HolidayUpdate):
    return holiday_service.update_holiday(db, tenant_id, holiday_id, body.model_dump(exclude_unset=True))


@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="delete_account_holiday")
def delete_account_holiday(db: DbSession, tenant_id: AccountTenant, holiday_id: int):
    holiday_service.delete_holiday(db, tenant_id, holiday_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/holidays/bulk-delete", operation_id="bulk_delete_account_holidays")
def bulk_delete_account_holidays(db: DbSession, tenant_id: AccountTenant, body: HolidayBulkDelete) -> dict:
    deleted = holiday_service.bulk_delete(db, tenant_id, body.ids)
    return {"deleted": deleted}


@router.post("/holidays/federal", response_model=list[HolidayRead], operation_id="import_federal_holidays")
def import_federal_holidays(db: DbSession, tenant_id: AccountTenant, body: FederalHolidaysImport, current: CurrentUser):
    return holiday_service.import_federal(db, tenant_id, body.year, body.status, current.id)


@router.post("/holidays/range", response_model=list[HolidayRead], operation_id="create_holiday_range")
def create_holiday_range(db: DbSession, tenant_id: AccountTenant, body: HolidayRangeCreate, current: CurrentUser):
    return holiday_service.create_range(
        db, tenant_id, body.from_date, body.to_date, body.name, body.status, body.holiday_type, current.id
    )


# ── Online-registration consents ─────────────────────────────────────────────
@router.get("/consents", response_model=list[ConsentRead], operation_id="list_account_consents")
def list_account_consents(db: DbSession, tenant_id: AccountTenant):
    return consent_service.list_consents(db, tenant_id)


@router.get("/consents/active", response_model=ConsentRead, operation_id="get_active_consent")
def get_active_consent(db: DbSession, tenant_id: AccountTenant):
    return consent_service.get_active(db, tenant_id)


@router.post("/consents", response_model=ConsentRead, status_code=status.HTTP_201_CREATED, operation_id="create_account_consent")
def create_account_consent(db: DbSession, tenant_id: AccountTenant, body: ConsentCreate, current: CurrentUser):
    return consent_service.create_consent(db, tenant_id, body.header, body.body_html, body.effective_date, current.id)


@router.get("/consents/{consent_id}", response_model=ConsentRead, operation_id="get_account_consent")
def get_account_consent(db: DbSession, tenant_id: AccountTenant, consent_id: int):
    return consent_service.get_consent(db, tenant_id, consent_id)


@router.get("/consents/{consent_id}/preview", response_model=ConsentPreview, operation_id="preview_account_consent")
def preview_account_consent(db: DbSession, tenant_id: AccountTenant, consent_id: int):
    row = consent_service.get_consent(db, tenant_id, consent_id)
    return ConsentPreview(header=row.header, body_html=row.body_html)
