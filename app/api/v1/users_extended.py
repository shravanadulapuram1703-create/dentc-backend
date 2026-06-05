"""Security -> Users — extended endpoints (Gaps 1,2,3,4,5,7).

Mounted BEFORE the base ``users`` router so literal paths (e.g. /users/setup-metadata)
win over /users/{user_id}. Admin-guarded except /users/me/change-password, which any
authenticated user may call for themselves.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user, require_roles
from app.schemas.auth import UserRead
from app.schemas.common import ErrorResponse
from app.schemas.user_admin import (
    ChangePasswordRequest,
    Option,
    SecuritySettings,
    SecuritySettingsRead,
    TimeClockConfig,
    TimeClockConfigRead,
    UserCompleteCreate,
    UserCompleteUpdate,
    UserSetupMetadata,
)
from app.services import user_admin_service as svc

_admin = Depends(require_roles("admin"))

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


# ── Gap 2: setup metadata (literal path — must precede /{user_id}) ───────────
@router.get("/setup-metadata", response_model=UserSetupMetadata, operation_id="get_user_setup_metadata",
            dependencies=[_admin], summary="Dropdown metadata for the Add/Edit User form")
def get_setup_metadata(db: DbSession, tenant_id: TenantId):
    return svc.get_setup_metadata(db, tenant_id)


# ── Gap 7: self-service password change (any authenticated user) ─────────────
@router.post("/me/change-password", status_code=status.HTTP_204_NO_CONTENT,
             operation_id="change_my_password", summary="Change your own password")
def change_my_password(db: DbSession, current_user: CurrentUser, body: ChangePasswordRequest):
    svc.change_password(db, current_user, body.current_password, body.new_password)


# ── Gap 1: compound atomic create / update ───────────────────────────────────
@router.post("/complete", response_model=UserRead, status_code=status.HTTP_201_CREATED,
             operation_id="create_user_complete", dependencies=[_admin],
             responses={409: {"model": ErrorResponse}},
             summary="Create a fully-configured user in one transaction")
def create_user_complete(db: DbSession, tenant_id: TenantId, body: UserCompleteCreate, current: CurrentUser):
    return svc.create_complete(db, tenant_id, body.model_dump(), current.id)


@router.put("/{user_id}/complete", response_model=UserRead, operation_id="update_user_complete",
            dependencies=[_admin], responses={409: {"model": ErrorResponse}},
            summary="Update a fully-configured user in one transaction")
def update_user_complete(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()], body: UserCompleteUpdate):
    return svc.update_complete(db, tenant_id, user_id, body.model_dump(exclude_unset=True))


# ── Gap 3: time-clock config ─────────────────────────────────────────────────
@router.get("/{user_id}/time-clock-config", response_model=TimeClockConfigRead,
            operation_id="get_user_time_clock_config", dependencies=[_admin])
def get_time_clock(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()]):
    return svc.get_time_clock(db, user_id, tenant_id)


@router.put("/{user_id}/time-clock-config", response_model=TimeClockConfigRead,
            operation_id="set_user_time_clock_config", dependencies=[_admin])
def set_time_clock(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()], body: TimeClockConfig):
    return svc.set_time_clock(db, user_id, tenant_id, body.model_dump(exclude_unset=True))


# ── Gap 4: login restrictions + patient access level ─────────────────────────
@router.get("/{user_id}/security-settings", response_model=SecuritySettingsRead,
            operation_id="get_user_security_settings", dependencies=[_admin])
def get_security_settings(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()]):
    return svc.get_security_settings(db, user_id, tenant_id)


@router.put("/{user_id}/security-settings", response_model=SecuritySettingsRead,
            operation_id="set_user_security_settings", dependencies=[_admin])
def set_security_settings(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()], body: SecuritySettings):
    return svc.set_security_settings(db, user_id, tenant_id, body.model_dump(exclude_unset=True))


# ── Gap 5: roles catalog (permissions deferred to Phase-4 RBAC) ──────────────
roles_router = APIRouter(prefix="/roles", tags=["Security"], dependencies=[Depends(get_current_user)])


@roles_router.get("", response_model=list[Option], operation_id="list_roles", summary="List assignable roles")
def list_roles(db: DbSession, tenant_id: TenantId):
    return svc.list_roles(db, tenant_id)
