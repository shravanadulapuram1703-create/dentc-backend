from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.roles.schemas import RoleCreate, RoleResponse
from app.api.v1.auth.dependencies import require_permission, get_current_user
from app.services.role_service import create_role

router = APIRouter(
    prefix="/roles",
    tags=["Roles"],
    dependencies=[Depends(require_permission("USER_MANAGE"))]
)


@router.post("/create", response_model=RoleResponse)
def create_role_api(
    payload: RoleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return create_role(
        db,
        name=payload.name,
        permission_ids=payload.permission_ids,
        level = payload.level,
        is_system = payload.is_system,
        tenant_id=current_user.tenant_id,
        created_by=current_user,
        request=request
    )
