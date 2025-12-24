from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from app.core.database import get_db
from app.api.v1.auth.schemas import (
    LoginRequest,
    RefreshTokenRequest,
    TokenPairResponse,
     SignupRequest, 
     SignupResponse
)
from app.api.v1.auth.service import (
    login_user,
    refresh_access_token,
    logout
)
from app.services.auth_service import signup_user
from app.models.user import User


import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)
logger.info("Inside app auth routes +++++++++++++++++++++++++++++")


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/signup", response_model=SignupResponse)
def signup(
    payload: SignupRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    logger.info(f"Inside app auth payload : email {payload.email} password : {payload.password} tenant_id : {payload.tenant_id} request : {request}")
    signup_user(
        db,
        email=payload.email,
        password=payload.password,
        tenant_id=payload.tenant_id,
        request=request
    )

    return {"message": "Signup successful. Please login."}

@router.post("/login", response_model=TokenPairResponse)
def login(payload: LoginRequest,request: Request, db: Session = Depends(get_db)):
    access, refresh = login_user(
        db,
        payload.email,
        payload.password,
        payload.tenant_id,
        request=request
    )
    return {"access_token": access, "refresh_token": refresh}

@router.post("/refresh", response_model=dict)
def refresh(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    access = refresh_access_token(db, payload.refresh_token)
    return {"access_token": access}

@router.post("/logout")
def logout_user(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    logout(db, payload.refresh_token)
    return {"message": "Logged out successfully"}



@router.post("/login-swager", response_model=TokenPairResponse, tags=["Auth"])
def swagger_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    db: Session = Depends(get_db),
):
    # map username → email
    access, refresh = login_user(
        db,
        email=form_data.username,
        password=form_data.password,
        tenant_id=1,  # 👈 TEMPORARY (see note below)
        request=request
    )

    return {
        "access_token": access,
        "refresh_token": refresh
    }


# from app.api.v1.auth.dependencies import require_superuser,get_current_user
# router = APIRouter(prefix="/users", tags=["Users"])

# @router.get("/me")
# def get_me(current_user: User = Depends(get_current_user)):
#     return {
#         "id": current_user.id,
#         "email": current_user.email,
#         "tenant_id": current_user.tenant_id
#     }

# @router.post("/create")
# def create_user(
#     current_user: User = Depends(require_superuser)
# ):
#     return {"message": "Admin access granted"}


