from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import get_current_user
from app.api.v1.setup.schemas import (
    AccountSetupConfigResponse,
    AccountSetupMetadataResponse,
    AccountSetupUpdateRequest,
    AccountSetupUpdateResponse,
)
from app.api.v1.setup.service import (
    get_account_setup_config,
    get_account_setup_metadata,
    update_account_setup,
)
from app.core.database import get_db
from app.models.user import User

router = APIRouter(prefix="/setup", tags=["Setup"])


@router.get("/account", response_model=AccountSetupConfigResponse)
def get_account_setup(
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_account_setup_config(
        db=db,
        current_user=current_user,
        account_id=account_id,
    )


@router.put("/account", response_model=AccountSetupUpdateResponse)
def put_account_setup(
    payload: AccountSetupUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return update_account_setup(
        db=db,
        current_user=current_user,
        payload_values=payload.values,
    )


@router.get("/account/metadata", response_model=AccountSetupMetadataResponse)
def get_account_metadata(
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_account_setup_metadata(
        db=db,
        current_user=current_user,
        account_id=account_id,
    )
