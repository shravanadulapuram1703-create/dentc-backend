from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.users.schemas import UserUpdate, UserResponse
from app.api.v1.users.schemas import UserOfficeBulkUpdate
from app.api.v1.users.schemas import UserIPRuleBulkUpdate
# from app.api.v1.users.schemas import UserGroupBulkUpdate
from app.api.v1.users.schemas import UserTimeClockBase
from app.api.v1.users.schemas import UserPreferenceBase
from app.api.v1.users.schemas import UserCreate, UserUpdate, UserResponse

from app.api.v1.users.service import create_user,update_user, save_user_offices, save_user_ip_rules, save_user_time_clock, save_user_preferences, load_user_setup_data, delete_user  

from app.api.v1.auth.dependencies import get_current_user
from app.api.v1.users.service import list_users_with_home_office
from app.api.v1.users.schemas import UserWithHomeOfficeResponse
from app.models.user import User

from app.api.v1.users.schemas import (
    UserIPRuleListResponse,
    UserIPRuleBulkUpdate,
)
from app.api.v1.users.service import (
    get_user_ip_rules,
    save_user_ip_rules,
)
import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)


# import app.api.v1.users.service as service

router = APIRouter(prefix="/users", tags=["User Setup"])


# -------------------------------
# LOGIN INFO
# -------------------------------

@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    return update_user(
        db=db,
        tenant_id=request.state.tenant_id,
        user_id=user_id,
        payload=payload,
        request=request
    )


# -------------------------------
# OFFICE ACCESS
# -------------------------------

@router.put("/{user_id}/offices")
def save_offices(
    user_id: int,
    payload: UserOfficeBulkUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    save_user_offices(db, request.state.tenant_id, user_id, payload, request)
    return {"status": "success"}


# -------------------------------
# PERMITTED IPs
# -------------------------------

@router.put("/{user_id}/ip-rules")
def save_ip_rules(
    user_id: int,
    payload: UserIPRuleBulkUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    save_user_ip_rules(db, request.state.tenant_id, user_id, payload, request)
    return {"status": "success"}


# -------------------------------
# GROUP MEMBERSHIPS
# -------------------------------

# @router.put("/{user_id}/groups")
# def save_groups(
#     user_id: int,
#     payload: UserGroupBulkUpdate,
#     request: Request,
#     db: Session = Depends(get_db),
# ):
#     save_user_groups(db, request.state.tenant_id, user_id, payload, request)
#     return {"status": "success"}


# -------------------------------
# TIME CLOCK
# -------------------------------

@router.put("/{user_id}/time-clock")
def save_time_clock(
    user_id: int,
    payload: UserTimeClockBase,
    request: Request,
    db: Session = Depends(get_db),
):
    save_user_time_clock(db, request.state.tenant_id, user_id, payload, request)
    return {"status": "success"}


# -------------------------------
# USER PREFERENCES
# -------------------------------

@router.put("/{user_id}/preferences")
def save_preferences(
    user_id: int,
    payload: UserPreferenceBase,
    request: Request,
    db: Session = Depends(get_db),
):
    save_user_preferences(db, request.state.tenant_id, user_id, payload, request)
    return {"status": "success"}


# -------------------------------
#  BULK LOAD USER SETUP
# -------------------------------

@router.get("/{tenant_id}/{user_id}/setup")
def load_user_setup(
    user_id: int,
    tenant_id:int,
    request: Request,
    db: Session = Depends(get_db),
):
    return load_user_setup_data(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id
    )

@router.post("", response_model=UserResponse)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    return create_user(
        db=db,
        tenant_id=request.state.tenant_id,
        payload=payload,
        request=request
    )


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    delete_user(
        db=db,
        tenant_id=request.state.tenant_id,
        user_id=user_id,
        request=request
    )
    return {"status": "deleted"}




# from app.api.v1.users.service import list_users_with_home_office
# from app.api.v1.users.schemas import UserWithOfficeAccessResponse


# @router.get(
#     "/list-with-home-office",
#     response_model=list[UserWithOfficeAccessResponse],
# )
# def get_users_with_home_office(
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     """
#     Returns all users for the current tenant along with their home office.
#     """

#     return list_users_with_home_office(
#         db=db,
#         tenant_id=current_user.tenant_id,
#     )


@router.get(
    "/list-with-home-office",
    response_model=list[UserWithHomeOfficeResponse]
)
def get_users_with_home_office(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_users_with_home_office(
        db=db,
        tenant_id=current_user.tenant_id,
    )


@router.get(
    "/{tenant_id}/{user_id}/ip-rules",
    response_model=UserIPRuleListResponse,
)
def get_ip_rules(
    user_id: int,
    tenant_id:int,
    request: Request,
    db: Session = Depends(get_db),
):
    logger.info(f"state : {request.state}")
    return get_user_ip_rules(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
    )


@router.put("/{user_id}/ip-rules")
def save_ip_rules(
    user_id: int,
    payload: UserIPRuleBulkUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    save_user_ip_rules(
        db,
        request.state.tenant_id,
        user_id,
        payload,
        request,
    )
    return {"status": "success"}

from app.api.v1.auth.dependencies import get_current_user, get_current_user_full
from app.models.tenant import Tenant
from app.models.office import Office

@router.get("/all-tenants")
def get_all_tenants(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_full),
):
    # SUPER_ADMIN → see all tenants
    logger.info(f"Current user roles: {current_user['roles']}")
    if "SUPER_ADMIN" in current_user["roles"] or "Practice Owner" in current_user["roles"]:
        return db.query(Tenant).all()

    # Normal users → only their tenant
    return (
        db.query(Tenant)
        .filter(Tenant.id == current_user["pgid"])
        .all()
    )


@router.get("/my-tenant")
def get_my_tenant(  
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_full),
):
    return (
        db.query(Tenant)
        .filter(Tenant.id == current_user.tenant_id)
        .first()
    )   



@router.get("/all-offices")
def get_all_offices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_full),
):
    logger.info(f"Current user roles: {current_user['roles']}")
    logger.info(f"Current user tenant: {current_user['pgid']}")

    # SUPER_ADMIN / Practice Owner → see all offices across tenant
    if (
        "SUPER_ADMIN" in current_user["roles"]
        or "Practice Owner" in current_user["roles"]
    ):
        return (
            db.query(Office)
            .filter(Office.tenant_id == current_user["pgid"])
            .all()
        )

    # Normal users → only assigned offices
    assigned_office_ids = [
        o["id"] if isinstance(o, dict) else o.id
        for o in (current_user.get("assigned_offices") or [])
    ]

    # Safety fallback → home office only
    if not assigned_office_ids and current_user.get("home_office_id"):
        assigned_office_ids = [current_user["home_office_id"]]

    return (
        db.query(Office)
        .filter(
            Office.tenant_id == current_user["pgid"],
            Office.id.in_(assigned_office_ids),
        )
        .all()
    )




@router.get("/tenant-offices")
def get_tenant_offices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_full),
):
    return (
        db.query(Office)
        .filter(Office.tenant_id == current_user["pgid"])
        .all()
    )




from app.api.v1.users.schemas import UserAccessResponse,OrganizationAccessUI
from app.api.v1.users.service import get_user_access_context




# @router.get("/me/access", response_model=UserAccessResponse)
# def get_my_access_context(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_full),
# ):
#     result = get_user_access_context(
#         db=db,
#         user_id=current_user["user_id"],
#         tenant_id=current_user["pgid"],  # None → super admin
#     )

#     return {
#         "is_super_admin": result["is_super_admin"],
#         "current_organization_id": result["current_organization_id"],
#         "current_office_id": result["current_office_id"],
#         "organizations": [
#             {"id": o.id, "name": o.name} for o in result["organizations"]
#         ],
#         "offices": [
#             {
#                 "id": o.id,
#                 "name": o.office_name,
#                 "tenant_id": o.tenant_id,
#             }
#             for o in result["offices"]
#         ],
#     }



@router.get(
    "/me/access",
    response_model=list[OrganizationAccessUI],
)
def get_my_access_context(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_full),
):
    return get_user_access_context(
        db=db,
        user_id=current_user["user_id"],
        tenant_id=current_user["pgid"],  # None → super admin
    )



@router.get("/test")
def test():
    return [
  {
    "id": "ORG-001",
    "name": "Cranberry Dental Group",
    "code": "CDG",
    "offices": [
      {
        "id": "OFF-101",
        "name": "Cranberry Main",
        "code": "108",
        "address": "123 Main St, Cranberry, PA 16066",
        "displayName": "Cranberry Main [108]"
      },
      {
        "id": "OFF-102",
        "name": "Cranberry North",
        "code": "109",
        "address": "456 North Ave, Cranberry, PA 16066",
        "displayName": "Cranberry North [109]"
      },
      {
        "id": "OFF-103",
        "name": "Cranberry South",
        "code": "110",
        "address": "789 South Blvd, Cranberry, PA 16066",
        "displayName": "Cranberry South [110]"
      }
    ]
  },
  {
    "id": "ORG-002",
    "name": "Pittsburgh Dental Partners",
    "code": "PDP",
    "offices": [
      {
        "id": "OFF-201",
        "name": "Downtown Pittsburgh",
        "code": "201",
        "address": "100 Liberty Ave, Pittsburgh, PA 15222",
        "displayName": "Downtown Pittsburgh [201]"
      },
      {
        "id": "OFF-202",
        "name": "Shadyside",
        "code": "202",
        "address": "200 Walnut St, Pittsburgh, PA 15232",
        "displayName": "Shadyside [202]"
      }
    ]
  },
  {
    "id": "ORG-003",
    "name": "Wexford Family Dentistry",
    "code": "WFD",
    "offices": [
      {
        "id": "OFF-301",
        "name": "Wexford Center",
        "code": "301",
        "address": "300 Perry Hwy, Wexford, PA 15090",
        "displayName": "Wexford Center [301]"
      }
    ]
  }
]
