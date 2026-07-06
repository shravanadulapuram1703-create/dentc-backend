"""Security -> Users — extended endpoints (Gaps 1,2,3,4,5,7).

Mounted BEFORE the base ``users`` router so literal paths (e.g. /users/setup-metadata)
win over /users/{user_id}. Admin-guarded except /users/me/change-password, which any
authenticated user may call for themselves.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.schemas.auth import LastPatientRead, LastPatientUpdate, UserRead
from app.schemas.my_page import (
    NotificationList,
    NotificationRead,
    PreferencesBlob,
    UserSelfUpdate,
    UserTaskCreate,
    UserTaskRead,
    UserTaskUpdate,
)
from app.services import my_page_service, patient_context_service
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
    UserImageResult,
    UserSetupMetadata,
    UserSignatureRead,
    UserSignatureUpdate,
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


# ── MP-1: self-service profile update ────────────────────────────────────────
@router.patch("/me", response_model=UserRead, operation_id="update_my_profile",
              responses={409: {"model": ErrorResponse}},
              summary="Update your own name / phone / email (MP-1)")
def update_my_profile(db: DbSession, current: CurrentUser, body: UserSelfUpdate):
    user = my_page_service.update_self(db, current, body.model_dump(exclude_unset=True))
    svc.attach_audit_names(db, user)
    return user


# ── MP-2: self-service profile photo ─────────────────────────────────────────
@router.post("/me/photo", response_model=UserImageResult, operation_id="upload_my_photo",
             responses={422: {"model": ErrorResponse}}, summary="Upload your own avatar (MP-2)")
async def upload_my_photo(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                          file: Annotated[UploadFile, File()]):
    user = svc.save_user_image(db, current.id, tenant_id, file.filename or "avatar",
                               file.content_type or "", await file.read(), updated_by=current.id)
    return UserImageResult(image_url=user.image_url)


@router.delete("/me/photo", status_code=status.HTTP_204_NO_CONTENT,
               operation_id="delete_my_photo", summary="Remove your own avatar (MP-2)")
def delete_my_photo(db: DbSession, tenant_id: TenantId, current: CurrentUser):
    svc.delete_user_image(db, current.id, tenant_id, updated_by=current.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── MP-3: personal tasks ──────────────────────────────────────────────────────
@router.get("/me/tasks", response_model=list[UserTaskRead], operation_id="list_my_tasks",
            summary="List your personal tasks (MP-3)")
def list_my_tasks(db: DbSession, current: CurrentUser):
    return my_page_service.list_tasks(db, current)


@router.post("/me/tasks", response_model=UserTaskRead, status_code=status.HTTP_201_CREATED,
             operation_id="create_my_task", summary="Create a personal task (MP-3)")
def create_my_task(db: DbSession, current: CurrentUser, body: UserTaskCreate):
    return my_page_service.create_task(db, current, body.model_dump())


@router.patch("/me/tasks/{task_id}", response_model=UserTaskRead, operation_id="update_my_task",
              responses={404: {"model": ErrorResponse}}, summary="Update a personal task (MP-3)")
def update_my_task(db: DbSession, current: CurrentUser, task_id: Annotated[int, Path()],
                   body: UserTaskUpdate):
    return my_page_service.update_task(db, current, task_id, body.model_dump(exclude_unset=True))


@router.delete("/me/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT,
               operation_id="delete_my_task", responses={404: {"model": ErrorResponse}},
               summary="Delete a personal task (MP-3)")
def delete_my_task(db: DbSession, current: CurrentUser, task_id: Annotated[int, Path()]):
    my_page_service.delete_task(db, current, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── MP-4: preferences blob ────────────────────────────────────────────────────
@router.get("/me/preferences", response_model=PreferencesBlob, operation_id="get_my_preferences",
            summary="Get your UI preferences blob (MP-4)")
def get_my_preferences(db: DbSession, current: CurrentUser):
    return PreferencesBlob(preferences=my_page_service.get_preferences(db, current))


@router.put("/me/preferences", response_model=PreferencesBlob, operation_id="set_my_preferences",
            summary="Replace your UI preferences blob (MP-4)")
def set_my_preferences(db: DbSession, current: CurrentUser, body: PreferencesBlob):
    return PreferencesBlob(preferences=my_page_service.set_preferences(db, current, body.preferences))


# ── MP-6: notifications inbox ─────────────────────────────────────────────────
@router.get("/me/notifications", response_model=NotificationList, operation_id="list_my_notifications",
            summary="List your notifications with unread count (MP-6)")
def list_my_notifications(db: DbSession, current: CurrentUser,
                          unread_only: Annotated[bool, Query()] = False,
                          limit: Annotated[int, Query(ge=1, le=200)] = 50):
    return my_page_service.list_notifications(db, current, unread_only=unread_only, limit=limit)


@router.post("/me/notifications/{notification_id}/read", response_model=NotificationRead,
             operation_id="mark_my_notification_read", responses={404: {"model": ErrorResponse}},
             summary="Mark a notification read (MP-6)")
def mark_my_notification_read(db: DbSession, current: CurrentUser,
                              notification_id: Annotated[int, Path()]):
    return my_page_service.mark_notification_read(db, current, notification_id)


@router.post("/me/notifications/read-all", operation_id="mark_all_my_notifications_read",
             summary="Mark all your notifications read (MP-6)")
def mark_all_my_notifications_read(db: DbSession, current: CurrentUser):
    return {"marked_read": my_page_service.mark_all_read(db, current)}


# ── PDP-1/2: persistent default patient (self-service) ───────────────────────
@router.get("/me/last-patient", response_model=LastPatientRead, operation_id="get_my_last_patient",
            summary="Get the caller's persistent default patient")
def get_my_last_patient(db: DbSession, tenant_id: TenantId, current: CurrentUser):
    return LastPatientRead(patient_id=patient_context_service.resolve_last_patient(db, current, tenant_id))


@router.put("/me/last-patient", response_model=LastPatientRead, operation_id="set_my_last_patient",
            responses={404: {"model": ErrorResponse}},
            summary="Set (or clear with null) the caller's default patient")
def set_my_last_patient(db: DbSession, tenant_id: TenantId, current: CurrentUser, body: LastPatientUpdate):
    pid = patient_context_service.set_last_patient(db, current, tenant_id, body.patient_id)
    return LastPatientRead(patient_id=pid)


@router.delete("/me/last-patient", status_code=status.HTTP_204_NO_CONTENT,
               operation_id="clear_my_last_patient", summary="Clear the caller's default patient")
def clear_my_last_patient(db: DbSession, tenant_id: TenantId, current: CurrentUser):
    patient_context_service.set_last_patient(db, current, tenant_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── PN-1: per-user signature ("Load My Signature") ───────────────────────────
def _signature_read(user) -> UserSignatureRead:  # noqa: ANN001
    return UserSignatureRead(
        user_id=user.id, signature_data=user.signature_data,
        signature_len=user.signature_len, device_source=user.signature_device_source,
        updated_at=user.signature_updated_at,
    )


# /me/signature (literal) MUST precede /{user_id}/signature so "me" isn't parsed as an id.
@router.get("/me/signature", response_model=UserSignatureRead, operation_id="get_my_signature",
            responses={404: {"model": ErrorResponse}}, summary="Get the logged-in user's signature")
def get_my_signature(db: DbSession, tenant_id: TenantId, current: CurrentUser):
    user = svc.get_user_signature(db, current.id, tenant_id)
    if not user.signature_data:
        raise NotFoundError("No signature on file for this user")
    return _signature_read(user)


@router.put("/me/signature", response_model=UserSignatureRead, operation_id="set_my_signature",
            summary="Save the logged-in user's signature")
def set_my_signature(db: DbSession, tenant_id: TenantId, current: CurrentUser, body: UserSignatureUpdate):
    user = svc.set_user_signature(
        db, current.id, tenant_id, signature_data=body.signature_data,
        signature_len=body.signature_len, device_source=body.device_source,
    )
    return _signature_read(user)


@router.get("/{user_id}/signature", response_model=UserSignatureRead, dependencies=[_admin],
            operation_id="get_user_signature", responses={404: {"model": ErrorResponse}},
            summary="Get a user's signature")
def get_user_signature(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()]):
    user = svc.get_user_signature(db, user_id, tenant_id)
    if not user.signature_data:
        raise NotFoundError("No signature on file for this user")
    return _signature_read(user)


@router.put("/{user_id}/signature", response_model=UserSignatureRead, dependencies=[_admin],
            operation_id="set_user_signature", summary="Save a user's signature")
def set_user_signature(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()],
                       body: UserSignatureUpdate):
    user = svc.set_user_signature(
        db, user_id, tenant_id, signature_data=body.signature_data,
        signature_len=body.signature_len, device_source=body.device_source,
    )
    return _signature_read(user)


# ── Gap 1: compound atomic create / update ───────────────────────────────────
@router.post("/complete", response_model=UserRead, status_code=status.HTTP_201_CREATED,
             operation_id="create_user_complete", dependencies=[_admin],
             responses={409: {"model": ErrorResponse}},
             summary="Create a fully-configured user in one transaction")
def create_user_complete(db: DbSession, tenant_id: TenantId, body: UserCompleteCreate, current: CurrentUser):
    user = svc.create_complete(db, tenant_id, body.model_dump(), current.id)
    svc.attach_audit_names(db, user)  # gap #8
    return user


@router.put("/{user_id}/complete", response_model=UserRead, operation_id="update_user_complete",
            dependencies=[_admin], responses={409: {"model": ErrorResponse}},
            summary="Update a fully-configured user in one transaction")
def update_user_complete(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()],
                         body: UserCompleteUpdate, current: CurrentUser):
    user = svc.update_complete(db, tenant_id, user_id, body.model_dump(exclude_unset=True),
                               updated_by=current.id)  # gap #8
    svc.attach_audit_names(db, user)
    return user


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
def set_security_settings(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()],
                          body: SecuritySettings, current: CurrentUser):
    return svc.set_security_settings(db, user_id, tenant_id, body.model_dump(exclude_unset=True),
                                     updated_by=current.id)


# ── User image / avatar (users_missing_fields dev-report gap #5) ─────────────
@router.post("/{user_id}/image", response_model=UserImageResult, dependencies=[_admin],
             operation_id="upload_user_image", responses={422: {"model": ErrorResponse}},
             summary="Upload a user avatar image")
async def upload_user_image(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()],
                            file: Annotated[UploadFile, File()], current: CurrentUser):
    data = await file.read()
    user = svc.save_user_image(db, user_id, tenant_id, file.filename or "avatar",
                               file.content_type or "", data, updated_by=current.id)
    return UserImageResult(image_url=user.image_url)


@router.delete("/{user_id}/image", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[_admin], operation_id="delete_user_image",
               summary="Remove a user avatar image")
def delete_user_image(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()],
                      current: CurrentUser):
    svc.delete_user_image(db, user_id, tenant_id, updated_by=current.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Gap 5: roles catalog (permissions deferred to Phase-4 RBAC) ──────────────
roles_router = APIRouter(prefix="/roles", tags=["Security"], dependencies=[Depends(get_current_user)])


@roles_router.get("", response_model=list[Option], operation_id="list_roles", summary="List assignable roles")
def list_roles(db: DbSession, tenant_id: TenantId):
    return svc.list_roles(db, tenant_id)
