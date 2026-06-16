"""Provider Setup routes (Setup -> Providers). Resolves provider dev-report gaps #1–#6.

Most endpoints are nested under ``/providers/{provider_id}/...`` and verify the
provider belongs to the authenticated tenant before any read/write. Carrier logins
are a top-level collection (``/provider-carrier-logins``, filter ``provider_id``) to
match the generated-client contract, with the password encrypted and returned masked.

NOTE: no ``from __future__ import annotations`` — FastAPI must resolve the
``body: <Schema>`` parameter annotations to real classes.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.db.models.provider_setup import ProviderCarrierLogin
from app.schemas.auth import UserRead
from app.schemas.common import ErrorResponse
from app.schemas.provider_setup import (
    AssignedOfficeRead,
    ProviderCarrierLoginCreate,
    ProviderCarrierLoginRead,
    ProviderCarrierLoginUpdate,
    ProviderHolidayCreate,
    ProviderHolidayRead,
    ProviderHolidayUpdate,
    ProviderUserLink,
    ProviderWatermarkRead,
    ProviderWatermarkUpdate,
    ReferralOfficesSet,
    ScheduleDayRead,
    ScheduleReplace,
)
from app.schemas.procedure_setup import AssignedProcedureCodeRead, ProcedureCodesSet
from app.services import procedure_setup_service as proc_svc
from app.services import provider_setup_service as svc

router = APIRouter(
    prefix="/providers",
    tags=["Provider Setup"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


def _provider_scope(provider_id: Annotated[str, Path()], tenant_id: TenantId, db: DbSession) -> str:
    svc.get_provider_in_tenant(db, provider_id, tenant_id)
    return provider_id


ProviderScope = Annotated[str, Depends(_provider_scope)]


# ── Gap #1 Schedule (weekly grid, per-day/office) ────────────────────────────
@router.get("/{provider_id}/schedule", response_model=list[ScheduleDayRead], operation_id="get_provider_schedule")
def get_provider_schedule(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId):
    return svc.get_schedule(db, provider_id)


@router.put("/{provider_id}/schedule", response_model=list[ScheduleDayRead], operation_id="set_provider_schedule")
def set_provider_schedule(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId, body: ScheduleReplace):
    return svc.replace_schedule(db, provider_id, tenant_id, [d.model_dump() for d in body.days])


# ── Gap #2 Holidays ──────────────────────────────────────────────────────────
@router.get("/{provider_id}/holidays", response_model=list[ProviderHolidayRead], operation_id="list_provider_holidays")
def list_provider_holidays(
    db: DbSession, provider_id: ProviderScope, tenant_id: TenantId,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
):
    return svc.list_holidays(db, provider_id, from_date, to_date)


@router.post("/{provider_id}/holidays", response_model=ProviderHolidayRead, status_code=status.HTTP_201_CREATED, operation_id="create_provider_holiday")
def create_provider_holiday(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId, body: ProviderHolidayCreate, current: CurrentUser):
    return svc.create_holiday(db, provider_id, tenant_id, body.model_dump(exclude_unset=True), current.id)


@router.patch("/{provider_id}/holidays/{holiday_id}", response_model=ProviderHolidayRead, operation_id="update_provider_holiday")
def update_provider_holiday(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId, holiday_id: int, body: ProviderHolidayUpdate):
    return svc.update_holiday(db, provider_id, holiday_id, body.model_dump(exclude_unset=True))


@router.delete("/{provider_id}/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="delete_provider_holiday")
def delete_provider_holiday(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId, holiday_id: int):
    svc.delete_holiday(db, provider_id, holiday_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Gap #3 Watermarks ────────────────────────────────────────────────────────
@router.get("/{provider_id}/watermarks", response_model=ProviderWatermarkRead, operation_id="get_provider_watermarks")
def get_provider_watermarks(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId):
    return svc.get_or_create_watermark(db, provider_id, tenant_id)


@router.put("/{provider_id}/watermarks", response_model=ProviderWatermarkRead, operation_id="set_provider_watermarks")
def set_provider_watermarks(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId, body: ProviderWatermarkUpdate, current: CurrentUser):
    return svc.update_watermark(db, provider_id, tenant_id, body.model_dump(exclude_unset=True), current.id)


@router.post("/{provider_id}/watermarks/image", response_model=ProviderWatermarkRead, operation_id="upload_provider_watermark_image")
async def upload_provider_watermark_image(
    db: DbSession, provider_id: ProviderScope, tenant_id: TenantId,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Query(description="watermark | signature")] = "watermark",
):
    data = await file.read()
    return svc.save_watermark_image(db, provider_id, tenant_id, kind, file.filename or "image", file.content_type or "", data)


@router.delete("/{provider_id}/watermarks/image", response_model=ProviderWatermarkRead, operation_id="delete_provider_watermark_image")
def delete_provider_watermark_image(
    db: DbSession, provider_id: ProviderScope, tenant_id: TenantId,
    kind: Annotated[str, Query(description="watermark | signature")] = "watermark",
):
    return svc.delete_watermark_image(db, provider_id, tenant_id, kind)


# ── Gap #4 Referral offices ──────────────────────────────────────────────────
@router.get("/{provider_id}/referral-offices", response_model=list[AssignedOfficeRead], operation_id="list_provider_referral_offices")
def list_provider_referral_offices(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId):
    return svc.get_referral_offices(db, provider_id)


@router.put("/{provider_id}/referral-offices", response_model=list[AssignedOfficeRead], operation_id="set_provider_referral_offices")
def set_provider_referral_offices(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId, body: ReferralOfficesSet):
    return svc.set_referral_offices(db, provider_id, tenant_id, body.office_ids)


# ── PROC-2 Provider procedure-code permissions ───────────────────────────────
@router.get("/{provider_id}/procedure-codes", response_model=list[AssignedProcedureCodeRead], operation_id="list_provider_procedure_codes")
def list_provider_procedure_codes(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId):
    return proc_svc.get_provider_codes(db, provider_id)


@router.put("/{provider_id}/procedure-codes", response_model=list[AssignedProcedureCodeRead], operation_id="set_provider_procedure_codes")
def set_provider_procedure_codes(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId, body: ProcedureCodesSet):
    return proc_svc.set_provider_codes(db, provider_id, tenant_id, body.codes)


# ── Gap #6 Provider ↔ user link ──────────────────────────────────────────────
@router.get("/{provider_id}/user", response_model=UserRead | None, operation_id="get_provider_user")
def get_provider_user(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId):
    provider = svc.get_provider_in_tenant(db, provider_id, tenant_id)
    return svc.get_linked_user(db, provider)


@router.put("/{provider_id}/user", response_model=UserRead | None, operation_id="set_provider_user")
def set_provider_user(db: DbSession, provider_id: ProviderScope, tenant_id: TenantId, body: ProviderUserLink):
    provider = svc.get_provider_in_tenant(db, provider_id, tenant_id)
    return svc.set_linked_user(db, provider, tenant_id, body.user_id)


# ── Gap #5 Carrier logins (top-level collection, filter provider_id) ─────────
carrier_router = APIRouter(
    prefix="/provider-carrier-logins",
    tags=["Provider Setup"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


def _carrier_read(row: ProviderCarrierLogin) -> ProviderCarrierLoginRead:
    out = ProviderCarrierLoginRead.model_validate(row)
    out.password_masked = svc.carrier_password_masked(row)
    return out


@carrier_router.get("", response_model=list[ProviderCarrierLoginRead], operation_id="list_provider_carrier_logins")
def list_provider_carrier_logins(
    db: DbSession, tenant_id: TenantId,
    provider_id: Annotated[str | None, Query()] = None,
):
    return [_carrier_read(r) for r in svc.list_carrier_logins(db, tenant_id, provider_id)]


@carrier_router.post("", response_model=ProviderCarrierLoginRead, status_code=status.HTTP_201_CREATED, operation_id="create_provider_carrier_login")
def create_provider_carrier_login(db: DbSession, tenant_id: TenantId, body: ProviderCarrierLoginCreate, current: CurrentUser):
    return _carrier_read(svc.create_carrier_login(db, tenant_id, body.model_dump(exclude_unset=True), current.id))


@carrier_router.patch("/{login_id}", response_model=ProviderCarrierLoginRead, operation_id="update_provider_carrier_login")
def update_provider_carrier_login(db: DbSession, tenant_id: TenantId, login_id: int, body: ProviderCarrierLoginUpdate, current: CurrentUser):
    return _carrier_read(svc.update_carrier_login(db, tenant_id, login_id, body.model_dump(exclude_unset=True), current.id))


@carrier_router.delete("/{login_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="delete_provider_carrier_login")
def delete_provider_carrier_login(db: DbSession, tenant_id: TenantId, login_id: int):
    svc.delete_carrier_login(db, tenant_id, login_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
