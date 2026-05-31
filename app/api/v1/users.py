"""User management routes.

Hand-written (not generated) because passwords must be hashed on write and never
serialised on read. Guarded to admin / super_admin.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import DbSession, PageParams, TenantId, require_roles
from app.core.security import hash_password
from app.crud.base import CRUDBase
from app.db.models import User
from app.schemas.auth import UserRead
from app.schemas.common import ErrorResponse, PaginatedResponse

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(require_roles("admin"))],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)

_crud = CRUDBase(
    User,
    search_fields=("username", "email", "first_name", "last_name"),
    sortable_fields=("created_at", "id", "username", "last_login_at"),
)


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=8)
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    role: str = "staff"
    must_change_password: bool = False


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


@router.get("", response_model=PaginatedResponse[UserRead], operation_id="list_users",
            summary="List users")
def list_users(db: DbSession, tenant_id: TenantId, page: PageParams):
    items, total = _crud.list(
        db, tenant_id=tenant_id, page=page.page, size=page.size,
        sort=page.sort, order=page.order, search=page.search,
    )
    return PaginatedResponse.build(items, total, page.page, page.size)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED,
             operation_id="create_user", summary="Create a user")
def create_user(db: DbSession, tenant_id: TenantId, body: UserCreate):
    data = body.model_dump(exclude={"password"})
    data["password_hash"] = hash_password(body.password)
    return _crud.create(db, data, tenant_id=tenant_id)


@router.get("/{user_id}", response_model=UserRead, operation_id="get_user",
            summary="Get a user by id")
def get_user(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()]):
    return _crud.get(db, user_id, tenant_id=tenant_id)


@router.patch("/{user_id}", response_model=UserRead, operation_id="update_user",
              summary="Update a user")
def update_user(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()], body: UserUpdate):
    data = body.model_dump(exclude_unset=True)
    if "password" in data:
        data["password_hash"] = hash_password(data.pop("password"))
    return _crud.update(db, user_id, data, tenant_id=tenant_id)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT,
               operation_id="deactivate_user", summary="Deactivate a user")
def deactivate_user(db: DbSession, tenant_id: TenantId, user_id: Annotated[int, Path()]):
    _crud.delete(db, user_id, tenant_id=tenant_id)
