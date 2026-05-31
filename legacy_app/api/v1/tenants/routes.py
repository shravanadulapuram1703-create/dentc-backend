from fastapi import APIRouter, Depends, Request, status, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth.dependencies import require_platform_owner #require_permission, get_current_user, require_superuser,
from app.api.v1.tenants.schemas import (
    TenantCreateRequest,
    TenantResponse,
    TenantOwnerCreateRequest,
    TenantOwnerResponse,
    TenantStatusUpdateRequest,
    SwitchTenantRequest,
    SwitchTenantResponse,
    ImpersonateUserRequest,
    ImpersonateResponse
)
from app.api.v1.tenants.service import ( 
    create_tenant,
    create_tenant_owner, 
    update_tenant_status,
    switch_tenant_context,
    start_impersonation,
    stop_impersonation)

from app.models.user import User
from app.models.tenant import Tenant
from app.utils.token import get_token_payload # Not defined

from app.api.v1.users.schemas import UserCreate, UserUpdate, UserResponse

from app.core.logging import setup_logging

import logging
logger = setup_logging()
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/platform", tags=["Tenant Setup"])

@router.post(
    "/tenants",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED
)
def create_tenant_api(
    payload: TenantCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_owner),
):
    tenant = create_tenant(
        db,
        name=payload.name,
        code=payload.code,
        created_by=current_user.id,
        request=request
    )
    return tenant



@router.post(
    "/tenants/{tenant_id}/owner",
    response_model=TenantOwnerResponse,
    status_code=status.HTTP_201_CREATED
)
def create_tenant_owner_api(
    tenant_id: int,
    # payload: TenantOwnerCreateRequest,
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_owner),
):
    logger.info(f"Creating tenant owner for tenant_id: {tenant_id}")
    user = create_tenant_owner(
        db=db,
        tenant_id=tenant_id,
        # email=payload.email,
        # name=payload.name,
        # password=payload.password,
        payload=payload,
        created_by=current_user.id,
        request=request
    )

    return {
        "id": user.id,
        "email": user.email,
        # "name": user.name,
        "tenant_id": tenant_id,
        "role": "tenant_owner",
        "is_active": user.is_active
    }





@router.patch(
    "/tenants/{tenant_id}/status",
    status_code=status.HTTP_200_OK
)
def update_tenant_status_api(
    tenant_id: int,
    payload: TenantStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_owner),
):
    try:
        payload.validate_request()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    tenant = update_tenant_status(
        db=db,
        tenant_id=tenant_id,
        is_active=payload.is_active,
        is_locked=payload.is_locked,
        reason=payload.reason,
        actor_user_id=current_user.id,
        request=request
    )

    return {
        "tenant_id": tenant.id,
        "is_active": tenant.is_active,
        "is_locked": tenant.is_locked,
        "message": "Tenant status updated successfully"
    }



@router.post(
    "/switch-tenant",
    response_model=SwitchTenantResponse,
    status_code=status.HTTP_200_OK
)
def switch_tenant_api(
    payload: SwitchTenantRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_owner),
):
    access_token = switch_tenant_context(
        db=db,
        tenant_id=payload.tenant_id,
        actor_user=current_user,
        request=request
    )

    return {
        "access_token": access_token,
        "tenant_id": payload.tenant_id,
        "message": "Tenant context switched successfully"
    }




@router.post(
    "/impersonate",
    response_model=ImpersonateResponse,
    status_code=status.HTTP_200_OK
)
def impersonate_user_api(
    payload: ImpersonateUserRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_owner),
):
    token, user_id = start_impersonation(
        db=db,
        admin_user=current_user,
        target_user_id=payload.user_id,
        request=request
    )

    return {
        "access_token": token,
        "impersonating": True,
        "user_id": user_id,
        "message": "Impersonation started"
    }


@router.post("/impersonate/exit")
def exit_impersonation_api(
    request: Request,
    db: Session = Depends(get_db),
    token_payload=Depends(get_token_payload),
):
    if "impersonation" not in token_payload:
        return {"message": "Not impersonating"}

    access_token = stop_impersonation(
        db=db,
        admin_user_id=token_payload["impersonation"]["admin_user_id"],
        impersonation_payload=token_payload["impersonation"],
        request=request
    )

    return {
        "access_token": access_token,
        "message": "Exited impersonation"
    }


@router.get("/debug/token")
def debug_token(payload=Depends(get_token_payload)):
    return payload





# @router.get("/all-tenants")
# def get_all_tenants(
#     db: Session = Depends(get_db),
#     current_user: User = Depends(require_platform_owner),
# ):

#     tenants = db.query(Tenant).all()
#     return [
#         {
#             "id": tenant.id,
#             "name": tenant.name,
#             "code": tenant.code,
#             "is_active": tenant.is_active,
#             "is_locked": tenant.is_locked,
#             "created_at": tenant.created_at,
#             "updated_at": tenant.updated_at
#         }
#         for tenant in tenants
#     ]
