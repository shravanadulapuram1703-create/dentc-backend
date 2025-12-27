from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.users.schemas import UserCreate, UserResponse
from app.api.v1.auth.dependencies import require_permission, get_current_user, require_superuser
from app.services.user_service import create_user
from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(require_permission("USER_MANAGE"))]
)


@router.post("/create", response_model=UserResponse)
def create_user_api(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    tenant_id = current_user.tenant_id

    logger.info(f"current_user ------- > {current_user}")



    return create_user(
        db,
        email=payload.email,
        password=payload.password,
        tenant_id=tenant_id,
        role_ids=payload.role_ids,
        created_by=current_user,
        request=request
    )



@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "tenant_id": current_user.tenant_id,
        "role":current_user.role,
        "name":current_user.name,
        "isactive":current_user.is_active,
    }



# @router.post("/create")
# def create_user(
#     current_user: User = Depends(require_superuser)
# ):
#     return {"message": "Admin access granted"}

