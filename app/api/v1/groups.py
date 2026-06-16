"""Security -> Groups supplemental routes (rights catalog, assignment, copy).

Resolves docs/users/groups_backend_devreport.md gaps #1–#3. Mounted BEFORE the
generated ``user-groups`` CRUD router so literal sub-paths (``/{id}/rights``,
``/{id}/copy``) win over the generic ``/user-groups/{item_id}`` route.

NOTE: no ``from __future__ import annotations`` is required here (no dynamic body
annotations), but kept simple and explicit regardless.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.api.deps import DbSession, TenantId, get_current_user, require_roles
from app.schemas.common import ErrorResponse
from app.schemas.groups import GroupRead, GroupRightsSet, PermissionRead
from app.services import group_rights_service as svc

_admin = Depends(require_roles("admin"))

# ── Rights catalog (gap #1) — its own /permissions prefix ────────────────────
permissions_router = APIRouter(
    prefix="/permissions",
    tags=["Security"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}},
)


@permissions_router.get("", response_model=list[PermissionRead], operation_id="list_permissions",
                        summary="List the assignable rights catalog")
def list_permissions(db: DbSession, tenant_id: TenantId):
    return svc.list_permissions(db)


# ── Group -> rights assignment + copy (gaps #2, #3) ──────────────────────────
groups_router = APIRouter(
    prefix="/user-groups",
    tags=["Security"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@groups_router.get("/{group_id}/rights", response_model=list[str], dependencies=[_admin],
                   operation_id="get_user_group_rights", summary="List a group's assigned right codes")
def get_group_rights(db: DbSession, tenant_id: TenantId, group_id: Annotated[int, Path()]):
    return svc.get_group_rights(db, group_id, tenant_id)


@groups_router.put("/{group_id}/rights", response_model=list[str], dependencies=[_admin],
                   operation_id="set_user_group_rights", responses={422: {"model": ErrorResponse}},
                   summary="Replace a group's assigned rights (full set)")
def set_group_rights(db: DbSession, tenant_id: TenantId, group_id: Annotated[int, Path()], body: GroupRightsSet):
    return svc.set_group_rights(db, group_id, tenant_id, body.right_codes)


@groups_router.post("/{group_id}/copy", response_model=GroupRead, status_code=status.HTTP_201_CREATED,
                    dependencies=[_admin], operation_id="copy_user_group",
                    summary="Duplicate a group together with its rights")
def copy_group(db: DbSession, tenant_id: TenantId, group_id: Annotated[int, Path()]):
    return svc.copy_group(db, group_id, tenant_id)
