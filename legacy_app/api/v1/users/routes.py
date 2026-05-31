from fastapi import APIRouter, Depends, Request, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.api.v1.users.schemas import UserUpdate, UserResponse
from app.api.v1.users.schemas import UserOfficeBulkUpdate
from app.api.v1.users.schemas import UserIPRuleBulkUpdate
# from app.api.v1.users.schemas import UserGroupBulkUpdate
from app.api.v1.users.schemas import UserTimeClockBase
from app.api.v1.users.schemas import UserPreferenceBase
from app.api.v1.users.schemas import UserCreate, UserUpdate, UserResponse
from app.api.v1.users.schemas import (
    UserCreateRequest,
    UserUpdateRequest,
    UserEditResponse,
    UserCreateResponse,
    UserUpdateResponse,
    UserSetupResponse,
)

from app.api.v1.users.service import create_user,update_user, save_user_offices, save_user_ip_rules, save_user_time_clock, save_user_preferences, load_user_setup_data, delete_user  

from app.api.v1.auth.dependencies import get_current_user
from app.api.v1.users.service import list_users_with_home_office
from app.api.v1.users.schemas import UserWithHomeOfficeResponse
from app.models.user import User
from app.api.v1.users.service_user_details import (
    get_user_details,
    get_user_ip_rules_details,
    get_user_groups_details,
    get_user_time_clock_details,
    get_user_preferences_details,
    get_group_memberships_metadata,
)
from app.api.v1.users.schemas import (
    UserDetailResponse,
    UserIPRuleDetailResponse,
    UserGroupDetailResponse,
    UserTimeClockDetailResponse,
    UserPreferencesDetailResponse,
    GroupMembershipsMetadataResponse,
)
from typing import List, Optional

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


from app.api.v1.auth.dependencies import get_current_user, get_current_user_full
from app.models.tenant import Tenant
from app.models.offices import Office
from app.api.v1.users.schemas import TenantListResponse, OfficeListResponse

# ==================================================
# STATIC ROUTES (must come before dynamic routes)
# ==================================================

@router.get("/groups-metadata", response_model=GroupMembershipsMetadataResponse)
def get_groups_metadata(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Metadata API: Return all available group memberships for the current tenant.
    """
    return get_group_memberships_metadata(db, current_user.tenant_id)


@router.get("/all-tenants", response_model=List[TenantListResponse])
def get_all_tenants(
    tenant_id: Optional[int] = Query(None, alias="organization_id", description="Filter by tenant/organization ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_full),
):
    """
    Get list of all tenants/practice groups available to the current user.
    Accepts tenant_id or organization_id query parameter (both are aliases).
    If not provided, uses tenant_id from authenticated user's token.
    """

    logger.info("ENTERED get_all_tenants")


    # Determine tenant_id: query param > token > current_user dict
    target_tenant_id = tenant_id or current_user.get("pgid")
    target_tenant_id = current_user.get("pgid")
    
    # SUPER_ADMIN → see all tenants
    if "SUPER_ADMIN" in current_user.get("roles", []) or "Practice Owner" in current_user.get("roles", []):
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
    else:
        # Normal users → only their tenant
        if target_tenant_id:
            tenants = db.query(Tenant).filter(
                Tenant.id == target_tenant_id,
                Tenant.is_active == True
            ).all()
        else:
            # Fallback to user's tenant from token
            tenants = db.query(Tenant).filter(
                Tenant.id == current_user.get("pgid"),
                Tenant.is_active == True
            ).all()
    
    return [
        TenantListResponse(
            id=t.id,
            name=t.name,
            code=t.code
        )
        for t in tenants
    ]


@router.get("/my-tenant")
def get_my_tenant(  
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_full),
):
    return (
        db.query(Tenant)
        .filter(Tenant.id == current_user.get("pgid"))
        .first()
    )   



@router.get("/all-offices", response_model=List[OfficeListResponse])
def get_all_offices(
    # tenant_id: Optional[int] = Query(None, alias="organization_id", description="Filter by tenant/organization ID"),
    # office_id: Optional[int] = Query(None, description="Filter by specific office ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_full),
):
    """
    Get list of all offices available to the current user.
    Accepts tenant_id/organization_id and office_id query parameters.
    If tenant_id not provided, uses tenant_id from authenticated user's token.
    """
    # Determine tenant_id: query param > token > current_user dict
    # target_tenant_id = tenant_id or current_user.get("pgid")
    target_tenant_id = current_user.get("pgid")

    
    # Build query
    query = db.query(Office).filter(Office.is_active == True)
    
    # SUPER_ADMIN / Practice Owner → see all offices across tenant
    if (
        "SUPER_ADMIN" in current_user.get("roles", [])
        or "Practice Owner" in current_user.get("roles", [])
    ):
        if target_tenant_id:
            query = query.filter(Office.tenant_id == target_tenant_id)
        # If no tenant_id filter, show all (for super admin)
    else:
        # Normal users → only assigned offices
        if target_tenant_id:
            query = query.filter(Office.tenant_id == target_tenant_id)
        else:
            # Fallback to user's tenant
            query = query.filter(Office.tenant_id == current_user.get("pgid"))
        
        # Filter by assigned offices for normal users
        assigned_office_ids = [
            o.get("office_id") if isinstance(o, dict) else (o.office_id if hasattr(o, 'office_id') else o.id)
            for o in (current_user.get("assigned_offices") or [])
        ]
        
        # Safety fallback → home office only
        if not assigned_office_ids and current_user.get("home_office_id"):
            assigned_office_ids = [current_user.get("home_office_id")]
        
        if assigned_office_ids:
            query = query.filter(Office.id.in_(assigned_office_ids))
    
    # Filter by specific office_id if provided
    # if office_id:
    #     query = query.filter(Office.id == office_id)
    
    offices = query.all()
    
    return [
        OfficeListResponse(
            id=o.id,
            officeId=o.id,
            officeCode=o.office_code,
            officeName=o.office_name or "",
            city=o.city,
            state=o.state,
            phone1=o.phone1,
            tenantId=o.tenant_id,
            timezone=o.timezone,
            isActive=o.is_active,
            createdAt=o.created_at,
            updatedAt=o.updated_at
        )
        for o in offices
    ]




@router.get("/tenant-offices")
def get_tenant_offices(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_full),
):
    return (
        db.query(Office)
        .filter(Office.tenant_id == current_user.get("pgid"))
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


@router.get("/setup", response_model=UserSetupResponse)
def get_user_setup(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch all metadata and configuration options needed for Add/Edit User form.
    Returns data scoped to the authenticated user's tenant.
    """
    from app.api.v1.users.service_setup import get_user_setup_metadata
    return get_user_setup_metadata(db, current_user.tenant_id)


@router.get(
    "/list-with-home-office",
    response_model=List[UserWithHomeOfficeResponse]
)
def get_users_with_home_office(
    tenant_id: Optional[int] = Query(None, alias="organization_id", description="Filter by tenant/organization ID"),
    office_id: Optional[int] = Query(None, description="Filter by specific office ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get list of all users with their home office information.
    Accepts tenant_id/organization_id and office_id query parameters.
    If tenant_id not provided, uses tenant_id from authenticated user's token.
    """
    # Determine tenant_id: query param > current_user.tenant_id
    target_tenant_id = tenant_id or current_user.tenant_id
    
    if not target_tenant_id:
        raise HTTPException(
            status_code=422,
            detail="tenant_id is required. Provide it as query parameter or ensure user has tenant_id in token."
        )
    
    # Get users for the tenant
    users = list_users_with_home_office(
        db=db,
        tenant_id=target_tenant_id,
    )
    
    # Filter by office_id if provided
    if office_id:
        users = [
            u for u in users
            if office_id in u.get("assigned_office_ids", []) or u.get("home_office_id") == office_id
        ]
    
    return users


#     example_output = {
#                         "organization": {
#                             "pgid": "PG-108",
#                             "pgid_name": "Cranberry Dental Arts Corporation",
#                             "tenant_id": "TENANT-001"
#                         },

#                         "offices": [
#                             {
#                             "office_id": 101,
#                             "office_oid": "O-001",
#                             "office_name": "Cranberry Main",
#                             "is_active": True
#                             },
#                             {
#                             "office_id": 102,
#                             "office_oid": "O-002",
#                             "office_name": "Cranberry North",
#                             "is_active": True
#                             },
#                             {
#                             "office_id": 103,
#                             "office_oid": "O-003",
#                             "office_name": "Downtown Pittsburgh",
#                             "is_active": True
#                             },
#                             {
#                             "office_id": 104,
#                             "office_oid": "O-004",
#                             "office_name": "Shadyside",
#                             "is_active": False
#                             }
#                         ],

#                         "security_groups": [
#                             {
#                             "code": "ADMIN",
#                             "name": "Administrators",
#                             "description": "Full system access"
#                             },
#                             {
#                             "code": "FRONT_DESK",
#                             "name": "Front Desk",
#                             "description": "Scheduling and patient check-in"
#                             },
#                             {
#                             "code": "BILLING",
#                             "name": "Billing",
#                             "description": "Claims and payments"
#                             },
#                             {
#                             "code": "CLINICAL",
#                             "name": "Clinical",
#                             "description": "Clinical access only"
#                             }
#                         ],

#                         "roles": [
#                             {
#                             "code": "ADMIN",
#                             "label": "Administrator"
#                             },
#                             {
#                             "code": "OFFICE_MANAGER",
#                             "label": "Office Manager"
#                             },
#                             {
#                             "code": "DENTIST",
#                             "label": "Dentist"
#                             },
#                             {
#                             "code": "HYGIENIST",
#                             "label": "Hygienist"
#                             },
#                             {
#                             "code": "FRONT_DESK",
#                             "label": "Front Desk"
#                             }
#                         ],

#                         "patient_access_levels": [
#                             {
#                             "code": "all",
#                             "label": "Search patients in all offices"
#                             },
#                             {
#                             "code": "assigned",
#                             "label": "Search patients in assigned offices only"
#                             }
#                         ],

#                         "time_clock": {
#                             "enabled": True,
#                             "overtime_methods": [
#                             {
#                                 "code": "daily",
#                                 "label": "Daily"
#                             },
#                             {
#                                 "code": "weekly",
#                                 "label": "Weekly"
#                             },
#                             {
#                                 "code": "none",
#                                 "label": "None"
#                             }
#                             ],
#                             "overtime_rates": [
#                             {
#                                 "value": 1.0,
#                                 "label": "1.0x (Regular Rate)"
#                             },
#                             {
#                                 "value": 1.5,
#                                 "label": "1.5x (Time and a Half)"
#                             },
#                             {
#                                 "value": 2.0,
#                                 "label": "2.0x (Double Time)"
#                             }
#                             ]
#                         },

#                         "login_restrictions": {
#                             "allow_24x7_default": True,
#                             "allowed_days": [
#                             "Mon",
#                             "Tue",
#                             "Wed",
#                             "Thu",
#                             "Fri"
#                             ],
#                             "default_allowed_from": "08:00",
#                             "default_allowed_until": "18:00"
#                         },

#                         "user_preferences_schema": {
#                             "startup_screen": {
#                             "type": "enum",
#                             "options": ["Dashboard", "Scheduler", "Patient"]
#                             },
#                             "default_perio_screen": {
#                             "type": "enum",
#                             "options": ["Standard", "Advanced"]
#                             },
#                             "default_navigation_search": {
#                             "type": "enum",
#                             "options": ["Patient", "Appointment", "Claim"]
#                             },
#                             "default_search_by": {
#                             "type": "enum",
#                             "options": ["lastName", "firstName", "patientId", "chartNumber"]
#                             },
#                             "default_referral_view": {
#                             "type": "enum",
#                             "options": ["All", "Active", "Pending"]
#                             },
#                             "flags": {
#                             "show_production_view": True,
#                             "hide_provider_time": False,
#                             "print_labels_for_appointments": False,
#                             "prompt_for_entry_date": False,
#                             "include_inactive_patients_in_search": False,
#                             "hipaa_compliant_scheduler": False,
#                             "is_ortho_assistant": False
#                             }
#                         }
#                         }

#     return example_output


# @router.get("/test")
# def test():
#     return [
#   {
#     "id": "ORG-001",
#     "name": "Cranberry Dental Group",
#     "code": "CDG",
#     "offices": [
#       {
#         "id": "OFF-101",
#         "name": "Cranberry Main",
#         "code": "108",
#         "address": "123 Main St, Cranberry, PA 16066",
#         "displayName": "Cranberry Main [108]"
#       },
#       {
#         "id": "OFF-102",
#         "name": "Cranberry North",
#         "code": "109",
#         "address": "456 North Ave, Cranberry, PA 16066",
#         "displayName": "Cranberry North [109]"
#       },
#       {
#         "id": "OFF-103",
#         "name": "Cranberry South",
#         "code": "110",
#         "address": "789 South Blvd, Cranberry, PA 16066",
#         "displayName": "Cranberry South [110]"
#       }
#     ]
#   },
#   {
#     "id": "ORG-002",
#     "name": "Pittsburgh Dental Partners",
#     "code": "PDP",
#     "offices": [
#       {
#         "id": "OFF-201",
#         "name": "Downtown Pittsburgh",
#         "code": "201",
#         "address": "100 Liberty Ave, Pittsburgh, PA 15222",
#         "displayName": "Downtown Pittsburgh [201]"
#       },
#       {
#         "id": "OFF-202",
#         "name": "Shadyside",
#         "code": "202",
#         "address": "200 Walnut St, Pittsburgh, PA 15232",
#         "displayName": "Shadyside [202]"
#       }
#     ]
#   },
#   {
#     "id": "ORG-003",
#     "name": "Wexford Family Dentistry",
#     "code": "WFD",
#     "offices": [
#       {
#         "id": "OFF-301",
#         "name": "Wexford Center",
#         "code": "301",
#         "address": "300 Perry Hwy, Wexford, PA 15090",
#         "displayName": "Wexford Center [301]"
#       }
#     ]
#   }
# ]


# ==================================================
# DYNAMIC ROUTES (must come after static routes)
# ==================================================

@router.get("/{user_id}", response_model=UserEditResponse)
def get_user_for_edit(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get user data for editing in Add/Edit User modal.
    This endpoint is used by the Add/Edit User screen to fetch user details.
    """
    from app.api.v1.users.service_add_edit import get_user_for_edit as get_user_edit
    return get_user_edit(db, current_user.tenant_id, user_id, current_user)


@router.get("/{user_id}/ip-rules", response_model=List[UserIPRuleDetailResponse])
def get_user_ip_rules_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get IP rules for a user.
    """
    return get_user_ip_rules_details(db, current_user.tenant_id, user_id)


@router.get("/{user_id}/groups", response_model=List[UserGroupDetailResponse])
def get_user_groups_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get security group memberships for a user.
    """
    return get_user_groups_details(db, current_user.tenant_id, user_id)


@router.get("/{user_id}/time-clock", response_model=UserTimeClockDetailResponse)
def get_user_time_clock_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get time clock configuration and recent entries for a user.
    """
    return get_user_time_clock_details(db, current_user.tenant_id, user_id)


@router.get("/{user_id}/preferences", response_model=UserPreferencesDetailResponse)
def get_user_preferences_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get user preferences and settings.
    """
    return get_user_preferences_details(db, current_user.tenant_id, user_id)


# -------------------------------
# LOGIN INFO
# -------------------------------

@router.put("/{user_id}", response_model=UserUpdateResponse)
def update_user_full(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update an existing user with all related data.
    This endpoint is used by the Edit User screen.
    """
    from app.api.v1.users.service_add_edit import update_user_full as update_user_new
    return update_user_new(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=user_id,
        payload=payload,
        current_user=current_user,
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

# @router.get("/{tenant_id}/{user_id}/setup")
# def load_user_setup(
#     user_id: int,
#     tenant_id:int,
#     request: Request,
#     db: Session = Depends(get_db),
# ):
#     return load_user_setup_data(
#         db=db,
#         tenant_id=tenant_id,
#         user_id=user_id
# #     )
#     example_output = {
#                         "organization": {
#                             "pgid": "PG-108",
#                             "pgid_name": "Cranberry Dental Arts Corporation",
#                             "tenant_id": "TENANT-001"
#                         },

#                         "offices": [
#                             {
#                             "office_id": 101,
#                             "office_oid": "O-001",
#                             "office_name": "Cranberry Main",
#                             "is_active": True
#                             },
#                             {
#                             "office_id": 102,
#                             "office_oid": "O-002",
#                             "office_name": "Cranberry North",
#                             "is_active": True
#                             },
#                             {
#                             "office_id": 103,
#                             "office_oid": "O-003",
#                             "office_name": "Downtown Pittsburgh",
#                             "is_active": True
#                             },
#                             {
#                             "office_id": 104,
#                             "office_oid": "O-004",
#                             "office_name": "Shadyside",
#                             "is_active": False
#                             }
#                         ],

#                         "security_groups": [
#                             {
#                             "code": "ADMIN",
#                             "name": "Administrators",
#                             "description": "Full system access"
#                             },
#                             {
#                             "code": "FRONT_DESK",
#                             "name": "Front Desk",
#                             "description": "Scheduling and patient check-in"
#                             },
#                             {
#                             "code": "BILLING",
#                             "name": "Billing",
#                             "description": "Claims and payments"
#                             },
#                             {
#                             "code": "CLINICAL",
#                             "name": "Clinical",
#                             "description": "Clinical access only"
#                             }
#                         ],

#                         "roles": [
#                             {
#                             "code": "ADMIN",
#                             "label": "Administrator"
#                             },
#                             {
#                             "code": "OFFICE_MANAGER",
#                             "label": "Office Manager"
#                             },
#                             {
#                             "code": "DENTIST",
#                             "label": "Dentist"
#                             },
#                             {
#                             "code": "HYGIENIST",
#                             "label": "Hygienist"
#                             },
#                             {
#                             "code": "FRONT_DESK",
#                             "label": "Front Desk"
#                             }
#                         ],

#                         "patient_access_levels": [
#                             {
#                             "code": "all",
#                             "label": "Search patients in all offices"
#                             },
#                             {
#                             "code": "assigned",
#                             "label": "Search patients in assigned offices only"
#                             }
#                         ],

#                         "time_clock": {
#                             "enabled": True,
#                             "overtime_methods": [
#                             {
#                                 "code": "daily",
#                                 "label": "Daily"
#                             },
#                             {
#                                 "code": "weekly",
#                                 "label": "Weekly"
#                             },
#                             {
#                                 "code": "none",
#                                 "label": "None"
#                             }
#                             ],
#                             "overtime_rates": [
#                             {
#                                 "value": 1.0,
#                                 "label": "1.0x (Regular Rate)"
#                             },
#                             {
#                                 "value": 1.5,
#                                 "label": "1.5x (Time and a Half)"
#                             },
#                             {
#                                 "value": 2.0,
#                                 "label": "2.0x (Double Time)"
#                             }
#                             ]
#                         },

#                         "login_restrictions": {
#                             "allow_24x7_default": True,
#                             "allowed_days": [
#                             "Mon",
#                             "Tue",
#                             "Wed",
#                             "Thu",
#                             "Fri"
#                             ],
#                             "default_allowed_from": "08:00",
#                             "default_allowed_until": "18:00"
#                         },

#                         "user_preferences_schema": {
#                             "startup_screen": {
#                             "type": "enum",
#                             "options": ["Dashboard", "Scheduler", "Patient"]
#                             },
#                             "default_perio_screen": {
#                             "type": "enum",
#                             "options": ["Standard", "Advanced"]
#                             },
#                             "default_navigation_search": {
#                             "type": "enum",
#                             "options": ["Patient", "Appointment", "Claim"]
#                             },
#                             "default_search_by": {
#                             "type": "enum",
#                             "options": ["lastName", "firstName", "patientId", "chartNumber"]
#                             },
#                             "default_referral_view": {
#                             "type": "enum",
#                             "options": ["All", "Active", "Pending"]
#                             },
#                             "flags": {
#                             "show_production_view": True,
#                             "hide_provider_time": False,
#                             "print_labels_for_appointments": False,
#                             "prompt_for_entry_date": False,
#                             "include_inactive_patients_in_search": False,
#                             "hipaa_compliant_scheduler": False,
#                             "is_ortho_assistant": False
#                             }
#                         }
#                         }

#     return example_output





@router.post("", response_model=UserCreateResponse, status_code=201)
def create_user_full(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new user with all related data (offices, roles, IPs, time_clock, preferences).
    This endpoint is used by the Add User screen.
    """
    from app.api.v1.users.service_add_edit import create_user_full as create_user_new
    return create_user_new(
        db=db,
        tenant_id=current_user.tenant_id,
        payload=payload,
        current_user=current_user,
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
