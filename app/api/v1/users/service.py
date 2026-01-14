from sqlalchemy.orm import Session
from fastapi import HTTPException, Request

from app.models.user import User
from app.models.role import Role
from app.utils.password import hash_password
from app.models.user_office import UserOffice
# from app.models.user_ip_rule import UserIPRule
# from app.models.user_group import UserGroup
# from app.models.group import Group
from app.models.user_time_clock import UserTimeClock
# from app.models.user_preference import UserPreference
from app.services.audit_service import log_audit
from app.models.user_role import UserRole
from app.utils.password import hash_password

from app.api.v1.users.schemas import UserCreate, UserUpdate, UserResponse

from sqlalchemy import and_

from app.models.user import User
from app.models.user_office import UserOffice


from app.models.user_ip_rules import UserIPRule
from app.models.ip_addresses import IPAddress

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)

# -------------------------------
# LOGIN INFO
# -------------------------------

def get_user(db: Session, tenant_id: int, user_id: int):
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user


def update_user(db: Session, tenant_id: int, user_id: int, payload, request: Request):
    user = get_user(db, tenant_id, user_id)

    for k, v in payload.dict(exclude_unset=True).items():
        setattr(user, k, v)

    db.commit()
    db.refresh(user)

    log_audit(
        tenant_id=tenant_id,
        action="UPDATE_USER_LOGIN_INFO",
        resource="users",
        resource_id=str(user_id),
        request=request
    )
    return user


# -------------------------------
# OFFICE ACCESS
# -------------------------------

def save_user_offices(db: Session, tenant_id: int, user_id: int, payload, request: Request):
    db.query(UserOffice).filter(UserOffice.user_id == user_id).delete()

    for office_id in payload.office_ids:
        db.add(
            UserOffice(
                user_id=user_id,
                office_id=office_id,
                is_home=(office_id == payload.home_office_id)
            )
        )

    db.commit()

    log_audit(
        tenant_id=tenant_id,
        action="UPDATE_USER_OFFICES",
        resource="user_offices",
        resource_id=str(user_id),
        request=request
    )


# -------------------------------
# PERMITTED IPs
# -------------------------------

def save_user_ip_rules(db: Session, tenant_id: int, user_id: int, payload, request: Request):
    db.query(UserIPRule).filter(UserIPRule.user_id == user_id).delete()

    if not payload.allow_all:
        for ip in payload.ips:
            db.add(UserIPRule(user_id=user_id, ip_address=ip))

    db.commit()

    log_audit(
        tenant_id=tenant_id,
        action="UPDATE_USER_IP_RULES",
        resource="user_ip_rules",
        resource_id=str(user_id),
        request=request
    )


# -------------------------------
# GROUP MEMBERSHIPS
# -------------------------------

# def save_user_groups(db: Session, tenant_id: int, user_id: int, payload, request: Request):
#     db.query(UserGroup).filter(UserGroup.user_id == user_id).delete()

#     for group_id in payload.group_ids:
#         db.add(UserGroup(user_id=user_id, group_id=group_id))

#     db.commit()

#     log_audit(
#         tenant_id=tenant_id,
#         action="UPDATE_USER_GROUPS",
#         resource="user_groups",
#         resource_id=str(user_id),
#         request=request
#     )


# -------------------------------
# TIME CLOCK
# -------------------------------

def save_user_time_clock(db: Session, tenant_id: int, user_id: int, payload, request: Request):
    record = db.query(UserTimeClock).filter(
        UserTimeClock.user_id == user_id
    ).first()

    if not record:
        record = UserTimeClock(user_id=user_id)
        db.add(record)

    for k, v in payload.dict(exclude_unset=True).items():
        setattr(record, k, v)

    db.commit()

    log_audit(
        tenant_id=tenant_id,
        action="UPDATE_USER_TIME_CLOCK",
        resource="user_time_clock",
        resource_id=str(user_id),
        request=request
    )


# -------------------------------
# USER PREFERENCES
# -------------------------------

def save_user_preferences(db: Session, tenant_id: int, user_id: int, payload, request: Request):
    prefs = db.query(UserPreference).filter(
        UserPreference.user_id == user_id
    ).first()

    if not prefs:
        prefs = UserPreference(user_id=user_id)
        db.add(prefs)

    for k, v in payload.dict(exclude_unset=True).items():
        setattr(prefs, k, v)

    db.commit()

    log_audit(
        tenant_id=tenant_id,
        action="UPDATE_USER_PREFERENCES",
        resource="user_preferences",
        resource_id=str(user_id),
        request=request
    )


# -------------------------------
# BULK LOAD USER SETUP ( KEY PART)
# -------------------------------

def load_user_setup_data(db: Session, tenant_id: int, user_id: int):
    user = get_user(db, tenant_id, user_id)

    # Group = Role

    offices = db.query(UserOffice).filter(
        UserOffice.user_id == user_id
    ).all()

    ip_rules = db.query(UserIPRule).filter(
        UserIPRule.user_id == user_id
    ).all()

    # groups = (
    #     db.query(UserRole)
    #     .join(UserRole, UserRole.user_id == user_id)
    #     .filter(UserRole.user_id == user_id)
    #     .all()
    # )

    groups = (
        db.query(Role.scope)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(
            UserRole.user_id == user_id,
            UserRole.tenant_id == tenant_id,
            Role.tenant_id == tenant_id,
        )
        .distinct()
        .all()
    )

    groups = [g.scope for g in groups]


    time_clock = db.query(UserTimeClock).filter(
        UserTimeClock.user_id == user_id
    ).first()

    preferences = db.query(UserPreference).filter(
        UserPreference.user_id == user_id
    ).first()

    return {
        "user": user,
        "offices": offices,
        "ip_rules": ip_rules,
        "groups": groups,
        "time_clock": time_clock,
        "preferences": preferences
    }





def create_user(
    db: Session,
    # tenant_id: int,
    payload: UserCreate,
    request: Request
):
    # Check uniqueness per tenant
    existing = db.query(User).filter(
        User.username == payload.username,
        User.tenant_id == payload.tenant_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    roles = db.query(Role).filter(
        Role.id.in_(payload.role_ids),
        Role.tenant_id == payload.tenant_id
    ).all()
    logger.info(f"roles >>>>>>>>>> {len(roles)}")
    # if len(roles) == len(payload.role_ids):
    #     pass
    # else:
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail="Invalid roles for tenant"
    #     )
    # logger.info(f"roles name >>>>>>>>>> {roles}")

    user = User(
        tenant_id=payload.tenant_id,
        username=payload.username,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        short_id=payload.short_id,
        email=payload.email,
        phone=payload.phone,
        patient_access_level=payload.patient_access_level,
        allowed_days=payload.allowed_days,
        allowed_from=payload.allowed_from,
        allowed_until=payload.allowed_until,
        is_active=True,
        role="Read Only",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # log_audit(db,
    #     tenant_id=payload.tenant_id,
    #     action="CREATE_USER",
    #     resource="users",
    #     resource_id=str(user.id),
    #     request=request
    # )
    
    log_audit(
        db,
        action="CREATE_USER",
        success=True,
        # tenant_id=tenant_id,
        actor_user_id=user.id,
        resource="auth",
        resource_id=str(user.id),
        resource_pk=str(user.id),
        reason="USER CREATED SUCCESSFULLY",
    )

    return user


def delete_user(
    db: Session,
    tenant_id: int,
    user_id: int,
    request: Request
):
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()

    log_audit(
        tenant_id=tenant_id,
        action="DELETE_USER",
        resource="users",
        resource_id=str(user_id),
        request=request
    )



# def list_users_with_home_office(
#     db: Session,
#     tenant_id: int
# ):
#     """
#     Returns all users for a tenant along with their home office id.
#     Home office = user_offices.is_primary = true
#     """

#     # results = (
#     #     db.query(
#     #         User.id,
#     #         User.email,
#     #         User.first_name,
#     #         User.last_name,
#     #         (User.first_name + " " + User.last_name).label("full_name"),
#     #         User.is_active,
#     #         UserOffice.office_id.label("home_office_id"),
#     #     )
#     #     .outerjoin(
#     #         UserOffice,
#     #         and_(
#     #             UserOffice.user_id == User.id,
#     #             UserOffice.is_primary.is_(True),
#     #         )
#     #     )
#     #     .filter(User.tenant_id == tenant_id)
#     #     .order_by(User.id)
#     #     .all()
#     # )
#     results = (
#     db.query(
#         User.id,
#         User.tenant_id,                 # ADD THIS
#         User.email,
#         User.role,
#         User.is_active,
#         User.created_at,
#         User.is_platform_user,
#         User.is_locked,
#         User.created_by,
#         User.last_login_at,
#         User.username,
#         User.first_name,
#         User.last_name,
#         User.short_id,
#         User.phone,
#         User.patient_access_level,
#         User.allowed_days,
#         User.allowed_from,
#         User.allowed_until,
#         User.updated_at,
#         UserOffice.office_id.label("home_office_id"),
#     )
#     .outerjoin(
#         UserOffice,
#         and_(
#             UserOffice.user_id == User.id,
#             # UserOffice.is_primary.is_(True),
#         )
#     )
#     .filter(User.tenant_id == tenant_id)
#     .all())


#     # return [
#     #     {
#     #         "id": row.id,
#     #         "email": row.email,
#     #         "full_name": row.full_name,
#     #         "is_active": row.is_active,
#     #         "home_office_id": row.home_office_id,
#     #     }
#     #     for row in results

#     # ]

#     logger.info(f"results >>>>> {[row for row in results]}")
#     return [{
#                         "id": row.id,
#                         "tenant_id": row.tenant_id,
#                         "email": row.email,
#                         "role": row.role,
#                         "is_active": row.is_active,
#                         "created_at": row.created_at,
#                         "is_platform_user": row.is_platform_user,
#                         "is_locked": row.is_locked,
#                         "created_by": row.created_by,
#                         "last_login_at": row.last_login_at,
#                         "username": row.username,
#                         "first_name": row.first_name,
#                         "last_name": row.last_name,
#                         "short_id": row.short_id,
#                         "phone": row.phone,
#                         "patient_access_level": row.patient_access_level,
#                         "allowed_days": row.allowed_days,
#                         "allowed_from": row.allowed_from,
#                         "allowed_until": row.allowed_until,
#                         "updated_at": row.updated_at,
#                         "home_office_id": row.home_office_id,
#                     }
#                     for row in results
#                 ]

# from sqlalchemy.orm import Session
# from sqlalchemy import and_

# def list_users_with_home_office(
#     db: Session,
#     tenant_id: int
# ):
#     """
#     Returns all users for a tenant.
#     home_office_id = office_id where is_primary = true
#     If no primary office exists → home_office_id = None
#     """

#     results = (
#         db.query(
#             User.id,
#             User.tenant_id,
#             User.email,
#             User.role,
#             User.is_active,
#             User.created_at,
#             User.is_platform_user,
#             User.is_locked,
#             User.created_by,
#             User.last_login_at,
#             User.username,
#             User.first_name,
#             User.last_name,
#             User.short_id,
#             User.phone,
#             User.patient_access_level,
#             User.allowed_days,
#             User.allowed_from,
#             User.allowed_until,
#             User.updated_at,
#             UserOffice.office_id.label("home_office_id"),
#         )
#         .outerjoin(
#             UserOffice,
#             and_(
#                 UserOffice.user_id == User.id,
#                 UserOffice.is_primary.is_(True),   #  THIS IS THE FIX
#             )
#         )
#         .filter(User.tenant_id == tenant_id)
#         .order_by(User.id)
#         .all()
#     )

#     return [
#         {
#             "id": row.id,
#             "tenant_id": row.tenant_id,
#             "email": row.email,
#             "role": row.role,
#             "is_active": row.is_active,
#             "created_at": row.created_at,
#             "is_platform_user": row.is_platform_user,
#             "is_locked": row.is_locked,
#             "created_by": row.created_by,
#             "last_login_at": row.last_login_at,
#             "username": row.username,
#             "first_name": row.first_name,
#             "last_name": row.last_name,
#             "short_id": row.short_id,
#             "phone": row.phone,
#             "patient_access_level": row.patient_access_level,
#             "allowed_days": row.allowed_days,
#             "allowed_from": row.allowed_from,
#             "allowed_until": row.allowed_until,
#             "updated_at": row.updated_at,
#             "home_office_id": row.home_office_id,  #  None if no primary office
#         }
#         for row in results
#     ]


from sqlalchemy.orm import Session
from sqlalchemy import and_
from collections import defaultdict

from app.models.user import User
from app.models.user_office import UserOffice
from app.models.offices import Office
from app.models.tenant import Tenant
from app.models.role import Role

from app.models.user_ip_rules import UserIPRule
from app.models.ip_addresses import IPAddress
from app.models.user_preferences import UserPreference


# def list_users_with_home_office(db: Session, tenant_id: int):
#     """
#     Returns users with:
#     - home office (id + name)
#     - assigned offices (ids + names)
#     - pgid + pgid_name
#     - security group (role name)
#     """

#     rows = (
#         db.query(
#             User.id.label("user_id"),
#             User.tenant_id.label("pgid"),
#             User.email,
#             User.username,
#             User.first_name,
#             User.last_name,
#             User.role,
#             User.is_active,
#             User.is_platform_user,
#             User.is_locked,
#             User.created_at,
#             User.updated_at,
#             User.last_login_at,
#             User.created_by,
#             User.patient_access_level,
#             User.allowed_days,
#             User.allowed_from,
#             User.allowed_until,
#             User.short_id,
#             User.phone,


#             Tenant.name.label("pgid_name"),

#             UserOffice.office_id,
#             UserOffice.is_primary,
#             Role.name.label("role"),
#             Role.scope.label("security_group"),

#             Office.office_name.label("office_name"),
#         )
#         .join(Tenant, Tenant.id == User.tenant_id)
#         .outerjoin(UserOffice, UserOffice.user_id == User.id)
#         .outerjoin(Role, Role.id == UserOffice.role_id)
#         .outerjoin(Office, Office.id == UserOffice.office_id)
#         .filter(User.tenant_id == tenant_id)
#         .order_by(User.id)
#         .all()
#     )

#     users = {}

#     for row in rows:
#         uid = row.user_id

#         if uid not in users:
#             users[uid] = {
#                 "user_id": uid,
#                 "pgid": row.pgid,
#                 "email": row.email,
#                 "username": row.username,
#                 "first_name": row.first_name,
#                 "last_name": row.last_name,
#                 "role": row.role,
#                 "security_group": row.security_group,
#                 "is_active": row.is_active,
#                 "is_platform_user": row.is_platform_user,
#                 "is_locked": row.is_locked,
#                 "created_at": row.created_at,
#                 "updated_at": row.updated_at,
#                 "last_login_at": row.last_login_at,
#                 "created_by": row.created_by,

#                 # PGID
#                 # "pgid": row.tenant_id,
#                 "pgid_name": row.pgid_name,

#                 # Office access
#                 "home_office_id": None,
#                 "home_office_name": None,
#                 "assigned_office_ids": [],
#                 "assigned_office_names": [],

#                 # Constraints
#                 "patient_access_level": row.patient_access_level,
#                 "allowed_days": row.allowed_days,
#                 "allowed_from": row.allowed_from,
#                 "allowed_until": row.allowed_until,
#             }

#         # Assigned offices
#         if row.office_id:
#             if row.office_id not in users[uid]["assigned_office_ids"]:
#                 users[uid]["assigned_office_ids"].append(row.office_id)
#                 users[uid]["assigned_office_names"].append(row.office_name)

#         # Home office
#         if row.is_primary:
#             users[uid]["home_office_id"] = row.office_id
#             users[uid]["home_office_name"] = row.office_name

#     return list(users.values())

def list_users_with_home_office(db: Session, tenant_id: int):
    """
    Returns UI-ready users with:
    - PGID + name
    - Home office
    - Assigned offices
    - Permitted IPs
    - Group memberships
    - User preferences
    - Time clock placeholders
    """

    rows = (
        db.query(
            User.id.label("user_id"),
            User.tenant_id.label("pgid"),
            User.email,
            User.username,
            User.first_name,
            User.last_name,
            User.role,
            User.is_active,
            User.is_platform_user,
            User.is_locked,
            User.created_at,
            User.updated_at,
            User.last_login_at,
            User.created_by,
            User.updated_by, 
            User.patient_access_level,
            User.allowed_days,
            User.allowed_from,
            User.allowed_until,
            User.short_id,
            User.phone,

            Tenant.name.label("pgid_name"),

            UserOffice.office_id,
            UserOffice.is_primary,
            Role.scope.label("security_group"),
            Office.office_name,

            # Preferences
            UserPreference.startup_screen,
            UserPreference.perio_template,
            UserPreference.default_navigation_search,
            UserPreference.default_search_by,
            UserPreference.production_view,
            UserPreference.hide_provider_time,
            UserPreference.default_perio_screen,
            UserPreference.show_production_colors,
            UserPreference.print_labels,
            UserPreference.prompt_entry_date,
            UserPreference.include_inactive_patients,
            UserPreference.referral_view,
            UserPreference.user_role_type,

        )
        .join(Tenant, Tenant.id == User.tenant_id)
        .outerjoin(UserOffice, UserOffice.user_id == User.id)
        .outerjoin(Role, Role.id == UserOffice.role_id)
        .outerjoin(Office, Office.id == UserOffice.office_id)
        .outerjoin(UserPreference, UserPreference.user_id == User.id)
        .filter(User.tenant_id == tenant_id)
        .order_by(User.id)
        .all()
    )


    users = {}

    for row in rows:
        uid = row.user_id

        if uid not in users:
            users[uid] = {
                "user_id": uid,
                "pgid": row.pgid,
                "email": row.email,
                "username": row.username,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "role": row.role,
                "security_group": row.security_group,
                "is_active": row.is_active,
                "is_platform_user": row.is_platform_user,
                "is_locked": row.is_locked,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "last_login_at": row.last_login_at,
                "created_by": row.created_by,
                "updated_by":row.updated_by,

                # PGID
                "pgid_name": row.pgid_name,

                # Office access
                "home_office_id": None,
                "home_office_name": None,
                "assigned_office_ids": [],
                "assigned_office_names": [],

                # Constraints
                "patient_access_level": row.patient_access_level,
                "allowed_days": row.allowed_days,
                "allowed_from": row.allowed_from,
                "allowed_until": row.allowed_until,

                # NEW FIELDS
                "permittedIPs": [],
                "groupMemberships": set(),

                "recentTimeEntries": (
                    [row.last_login_at] if row.last_login_at else []
                ),
                "timeClockEnabled": False,
                "clockInRequired": False,

                # Preferences (fallbacks handled)
                # "theme": row.theme or "Light Mode",
                # "language": row.language or "English (US)",
                # "dateFormat": row.date_format or "MM/DD/YYYY",
                # "timeFormat": row.time_format or "12-hour",
                # "emailNotifications": (
                #     row.email_notifications
                #     if row.email_notifications is not None
                #     else True
                # ),
                # "smsNotifications": (
                #     row.sms_notifications
                #     if row.sms_notifications is not None
                #     else False
                # ),
                # "defaultView": row.default_view or "Dashboard",
                # "itemsPerPage": row.items_per_page or 50,

                "startupScreen": row.startup_screen or "Dashboard",
                "perioTemplate": row.perio_template,
                "defaultNavigationSearch": (
                    row.default_navigation_search
                    if row.default_navigation_search is not None
                    else True
                ),
                "defaultSearchBy": row.default_search_by or "Patient Name",
                "productionView": row.production_view or "Daily",
                "hideProviderTime": row.hide_provider_time or False,
                "defaultView": row.default_perio_screen or "Dashboard",
                "showProductionColors": (
                    row.show_production_colors
                    if row.show_production_colors is not None
                    else True
                ),
                "printLabels": row.print_labels or False,
                "promptEntryDate": (
                    row.prompt_entry_date
                    if row.prompt_entry_date is not None
                    else True
                ),
                "includeInactivePatients": row.include_inactive_patients or False,
                "referralView": row.referral_view,
                "userRoleType": row.user_role_type,
                }

        # Assigned offices
        if row.office_id:
            if row.office_id not in users[uid]["assigned_office_ids"]:
                users[uid]["assigned_office_ids"].append(row.office_id)
                users[uid]["assigned_office_names"].append(row.office_name)

        # Home office
        if row.is_primary:
            users[uid]["home_office_id"] = row.office_id
            users[uid]["home_office_name"] = row.office_name

        # Group memberships (via roles.scope)
        if row.security_group:
            users[uid]["groupMemberships"].add(row.security_group)

    # Load permitted IPs in ONE query (important for performance)
    ip_rows = (
        db.query(
            UserIPRule.user_id,
            IPAddress.ip_address,
        )
        .join(IPAddress, IPAddress.id == UserIPRule.ip_id)
        .filter(UserIPRule.tenant_id == tenant_id)
        .all()
    )

    for user_id, ip in ip_rows:
        if user_id in users:
            users[user_id]["permittedIPs"].append(ip)

    # Convert sets → lists
    for user in users.values():
        user["groupMemberships"] = list(user["groupMemberships"])

    return list(users.values())



def get_user_ip_rules(
    db: Session,
    tenant_id: int,
    user_id: int,
):
    rows = (
        db.query(
            UserIPRule.id,
            UserIPRule.ip_id,
            IPAddress.ip_address,
            IPAddress.name,
            IPAddress.description,
            UserIPRule.is_active,
            UserIPRule.created_at,
        )
        .join(IPAddress, IPAddress.id == UserIPRule.ip_id)
        .filter(
            UserIPRule.tenant_id == tenant_id,
            UserIPRule.user_id == user_id,
        )
        .order_by(IPAddress.ip_address)
        .all()
    )

    return {
        "user_id": user_id,
        "total": len(rows),
        "items": rows,
    }


def save_user_ip_rules(
    db: Session,
    tenant_id: int,
    user_id: int,
    payload,
    request,
):
    # delete existing
    db.query(UserIPRule).filter(
        UserIPRule.tenant_id == tenant_id,
        UserIPRule.user_id == user_id,
    ).delete()

    # insert new
    for ip_id in payload.ip_ids:
        db.add(
            UserIPRule(
                tenant_id=tenant_id,
                user_id=user_id,
                ip_id=ip_id,
                is_active=True,
            )
        )

    db.commit()


from sqlalchemy.orm import Session
from typing import Optional
from app.models import User, Tenant, Office, UserOffice


# def get_user_access_context(
#     db: Session,
#     user_id: int,
#     tenant_id: Optional[int],
# ):
#     is_super_admin = tenant_id is None

#     #  SUPER ADMIN → all tenants & offices
#     if is_super_admin:
#         organizations = (
#             db.query(Tenant.id, Tenant.name)
#             .filter(Tenant.is_active == True)
#             .all()
#         )

#         offices = (
#             db.query(Office.id, Office.office_name, Office.tenant_id)
#             .filter(Office.is_active == True)
#             .all()
#         )

#         return {
#             "is_super_admin": True,
#             "organizations": organizations,
#             "offices": offices,
#             "current_organization_id": None,
#             "current_office_id": None,
#         }

#     #  NORMAL USER
#     user = (
#         db.query(User)
#         .filter(User.id == user_id, User.is_active == True)
#         .first()
#     )

#     # Organization (single tenant)
#     organizations = (
#         db.query(Tenant.id, Tenant.name)
#         .filter(Tenant.id == tenant_id)
#         .all()
#     )

#     # Offices user has access to
#     office_rows = (
#         db.query(
#             Office.id,
#             Office.office_name,
#             Office.tenant_id,
#             UserOffice.is_primary,
#         )
#         .join(UserOffice, UserOffice.office_id == Office.id)
#         .filter(UserOffice.user_id == user_id)
#         .all()
#     )

#     current_office_id = None
#     for o in office_rows:
#         if o.is_primary:
#             current_office_id = o.id
#             break

#     return {
#         "is_super_admin": False,
#         "organizations": organizations,
#         "offices": office_rows,
#         "current_organization_id": tenant_id,
#         "current_office_id": current_office_id,
#     }


def get_user_access_context(
    db: Session,
    user_id: int,
    tenant_id: Optional[int],
):
    is_super_admin = tenant_id is None

    # ---------------------------
    # SUPER ADMIN
    # ---------------------------
    if is_super_admin:
        tenants = (
            db.query(Tenant)
            .filter(Tenant.is_active == True)
            .all()
        )

        offices = (
            db.query(Office)
            .filter(Office.is_active == True)
            .all()
        )

        office_map = {}
        for o in offices:
            office_map.setdefault(o.tenant_id, []).append(o)

        response = []

        for t in tenants:
            response.append({
                "id": f"ORG-{t.id:03d}",
                "name": t.name,
                "code": t.code,
                "offices": [
                    {
                        "id": f"OFF-{o.id}",
                        "name": o.office_name,
                        "code": str(o.office_code),
                        "address": o.address_line1,
                        "displayName": f"{o.office_name} [{o.office_code}]",
                        "is_current": False,
                    }
                    for o in office_map.get(t.id, [])
                ],
            })

        return response

    # ---------------------------
    # NORMAL USER
    # ---------------------------
    user_offices = (
        db.query(
            Office,
            UserOffice.is_primary,
        )
        .join(UserOffice, UserOffice.office_id == Office.id)
        .filter(
            UserOffice.user_id == user_id,
            Office.is_active == True,
        )
        .all()
    )

    tenants = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id)
        .all()
    )

    # Map tenant → offices
    office_map = {}
    for office, is_primary in user_offices:
        office_map.setdefault(office.tenant_id, []).append(
            (office, is_primary)
        )

    response = []

    for t in tenants:
        offices_ui = []

        for office, is_primary in office_map.get(t.id, []):
            offices_ui.append({
                "id": f"OFF-{office.id}",
                "name": office.office_name,
                "code": str(office.office_code),
                "address": office.address_line1,
                "displayName": f"{office.office_name} [{office.office_code}]",
                "is_current": is_primary,
            })

        response.append({
            "id": f"ORG-{t.id:03d}",
            "name": t.name,
            "code": t.code,
            "offices": offices_ui,
        })

    return response



