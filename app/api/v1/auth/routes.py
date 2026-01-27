from fastapi import APIRouter, Depends, Request, Form
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
    logout,
    signup_user
)

from app.models.user import User

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)
logger.info("Inside app auth routes +++++++++++++++++++++++++++++")
from app.api.v1.users.schemas import UserUpdate, UserResponse
from app.api.v1.users.schemas import UserCreate, UserUpdate, UserResponse
from app.api.v1.users.service import create_user

from app.api.v1.auth.dependencies import get_current_user, get_current_user_full

router = APIRouter(prefix="/auth", tags=["Auth"])


# @router.post("/signup", response_model=SignupResponse)
# def signup(
#     payload: SignupRequest,
#     request: Request,
#     db: Session = Depends(get_db)
# ):
#     logger.info(f"Inside app auth payload : email {payload.email} password : {payload.password} request : {request}")
#     signup_user(
#         db,
#         email=payload.email,
#         password=payload.password,
#         # tenant_id=payload.tenant_id,
#         request=request
#     )

    # return {"message": "Signup successful. Please login."}

@router.post("/signup", response_model=UserResponse)
def signup(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    return create_user(
        db=db,
        # tenant_id=request.state.tenant_id,
        payload=payload,
        request=request
    )




# @router.post("/login", response_model=TokenPairResponse)
# def login(payload: LoginRequest,request: Request, db: Session = Depends(get_db)):
#     logger.info(f"Inside app auth login payload : email {payload.email} password : {payload.password} request : {request}")
#     access, refresh = login_user(
#         db,
#         payload.email,
#         payload.password,
#         # payload.tenant_id,
#         request=request
#     )
#     return {"access_token": access, "refresh_token": refresh}


@router.post("/login", response_model=TokenPairResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    logger.info(
        f"Inside auth login payload : identifier={payload.identifier} request={request}"
    )

    access, refresh = login_user(
        db=db,
        identifier=payload.identifier,
        password=payload.password,
        request=request
    )

    return {
        "access_token": access,
        "refresh_token": refresh
    }



@router.post("/refresh", response_model=dict)
def refresh(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    access = refresh_access_token(db, payload.refresh_token)
    return {"access_token": access}

@router.post("/logout")
def logout_user(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Logout endpoint - optimized to use user_id from access token.
    This makes logout much faster by only checking tokens for the current user.
    Also handles automatic logout on token expiration via 401 response.
    """
    # Use user_id from access token to optimize the query (much faster)
    logout(db, payload.refresh_token, user_id=current_user.id, tenant_id=current_user.tenant_id)
    return {"message": "Logged out successfully"}




@router.post("/login-swager", response_model=TokenPairResponse, tags=["Auth"])
def swagger_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    # email: str = Form(...),
    # password: str = Form(...),
    # tenant_id: int = Form(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    access, refresh = login_user(
        db,
        identifier=form_data.username,
        password=form_data.password,
        # tenant_id=tenant_id,
        request=request
    )

    return {
        "access_token": access,
        "refresh_token": refresh
    }



from app.api.v1.users.service import list_users_with_home_office
from app.api.v1.users.schemas import UserWithHomeOfficeResponse


@router.get(
    "/list-with-home-office",
    response_model=list[UserWithHomeOfficeResponse],
)
def get_users_with_home_office(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns all users for the current tenant along with their home office.
    """

    return list_users_with_home_office(
        db=db,
        tenant_id=current_user.tenant_id,
    )



# from app.api.v1.auth.dependencies import require_superuser,get_current_user
# router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "tenant_id": current_user.tenant_id
    }


@router.get("/me-full")
def get_me(current_user: User = Depends(get_current_user_full)):
    return {
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "username": current_user["username"],
        "first_name": current_user["first_name"],
        "last_name": current_user["last_name"],

        "pgid": current_user["pgid"],
        "pgid_name": current_user["pgid_name"],

        "home_office_id": current_user["home_office_id"],
        "home_office_name": current_user["home_office_name"],

        "assigned_offices": current_user["assigned_offices"],

        "roles": list(current_user["roles"]),
        "security_groups": list(current_user["security_groups"]),

        "permitted_ips": current_user["permitted_ips"],
        "preferences": current_user["preferences"],
    }

# @router.post("/create")
# def create_user(
#     current_user: User = Depends(require_superuser)
# ):
#     return {"message": "Admin access granted"}


