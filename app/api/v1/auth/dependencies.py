from fastapi import Request, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.utils.token import decode_access_token
from app.models.user import User
from app.services.rbac_service import user_has_permission, get_user_permissions
from app.services.audit_service import log_audit

from app.core.permissions import Permission
# from app.core.security import get_current_context


from app.models.user_role import UserRole
from app.models.role import Role

from app.services.rbac_cache_service import get_cached_permissions

from app.core.security import is_access_token_blacklisted

# if is_access_token_blacklisted(token_jti):
#     raise HTTPException(status_code=401, detail="Token revoked")



from app.models.user_office import UserOffice
from app.models.office_role_permission import OfficeRolePermission
from app.models.office_permission import OfficePermission


from app.models.tenant import Tenant
from app.models.user import User
from app.models.office import Office
from app.models.user_ip_rules import UserIPRule
from app.models.ip_addresses import IPAddress
from app.models.user_preferences import UserPreference



import logging
import re
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login-swager")

def name_from_email(email: str) -> str:
    # Take part before @
    local_part = email.split("@")[0]

    # Replace separators with space
    local_part = re.sub(r"[._\-]+", " ", local_part)

    # Remove digits and extra spaces
    local_part = re.sub(r"\d+", "", local_part).strip()

    logger.info(f"local_part ===>  {local_part.title()}")

    # Convert to proper case
    return local_part.title()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    payload = decode_access_token(token)

    # if is_access_token_blacklisted(token_jti):
    #     raise HTTPException(status_code=401, detail="Token revoked")

    user_id: str | None = payload.get("sub")
    tenant_id: int | None = payload.get("tenant_id")

    logger.info(f"user_id {user_id}, tenant_id : {tenant_id}")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )

    user = (
        db.query(User)
        .filter(
            User.id == int(user_id),
            User.tenant_id == tenant_id,
            # User.is_active == True
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    logger.info(f"user ----> {type(user)}")
    # user.name = name_from_email(user.email)

    return user


def require_superuser(
    current_user: User = Depends(get_current_user)
) -> User:
    logger.info(f"current_user {current_user}")
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return current_user


def enforce_tenant(
    tenant_id: int,
    current_user: User = Depends(get_current_user)
):
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access violation"
        )


def require_permission(permission_code: str):
    def dependency(
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
    ):
        if not user_has_permission(current_user, permission_code):

            log_audit(
                db,
                action="RBAC_DENIED",
                success=False,
                tenant_id=current_user.tenant_id,
                actor_user_id=current_user.id,
                resource="PERMISSION",
                resource_id=permission_code,
                resource_type="users",
                resource_pk=str(user.id),
                office_id=current_user.office_id,
                reason="Permission denied",
                metadata={"email": user.email},
                request=request
            )

            # log_audit(
            #     db,
            #     action="RBAC_DENIED",
            #     success=False,
            #     tenant_id=current_user.tenant_id,
            #     user_id=current_user.id,
            #     resource="PERMISSION",
            #     resource_id=permission_code,
            #     reason="Permission denied",
            #     request=request
            # )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )

        return current_user

    return dependency


def require_office_access(request: Request, db: Session = Depends(get_db)):
    user_id = request.state.user_id
    office_id = request.state.office_id

    user_roles = (
        db.query(UserRole, Role)
        .join(Role, Role.id == UserRole.role_id)
        .filter(
            UserRole.user_id == user_id,
            UserRole.is_active == True
        )
        .all()
    )

    if not has_office_access(user_roles, office_id):
        raise HTTPException(status_code=403, detail="Office access denied")


def require_platform_owner(
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_platform_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform access required"
        )
    return current_user


def require_permission_2(permission: Permission):
    def checker(
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
        context=Depends(get_current_context),
    ):
        permissions = get_user_permissions(
            db,
            user_id=user.id,
            tenant_id=context.tenant_id,
            office_id=context.office_id,
        )

        if permission.value not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )

        return True

    return checker


def ensure_office_access(
    db: Session,
    *,
    actor_id: int,
    office_id: int,
    tenant_id: int
):
    exists = db.query(UserRole).filter(
        UserRole.user_id == actor_id,
        UserRole.office_id == office_id,
        UserRole.tenant_id == tenant_id
    ).first()

    if not exists:
        raise HTTPException(
            status_code=403,
            detail="No access to target office"
        )



def get_current_context(request: Request):
    tenant_id = request.headers.get("X-Tenant-ID")
    office_id = request.headers.get("X-Office-ID")

    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context missing")

    return type(
        "Context",
        (),
        {
            "tenant_id": int(tenant_id),
            "office_id": int(office_id) if office_id else None,
        }
    )



def require_permission(permission: Permission):
    def checker(
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
        context=Depends(get_current_context),
    ):
        perms = get_cached_permissions(
            db,
            user_id=user.id,
            tenant_id=context.tenant_id,
            office_id=context.office_id,
        )

        if permission.value not in perms:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions",
            )

        return True

    return checker

# def require_office_permission_2(permission_code: str):
#     def checker(
#         user: User = Depends(get_current_user),
#         office_id: int = Depends(get_current_office_id),
#         db: Session = Depends(get_db),
#     ):
#         role = (
#             db.query(OfficeRole)
#             .join(UserOffice)
#             .join(OfficeRolePermission)
#             .join(OfficePermission)
#             .filter(
#                 UserOffice.user_id == user.id,
#                 UserOffice.office_id == office_id,
#                 OfficePermission.code == permission_code
#             )
#             .first()
#         )

#         if not role:
#             raise HTTPException(status_code=403, detail="Access denied")

#         return True

#     return checker


# def require_office_permission(permission_code: str):
#     def checker(
#         office_id: int,
#         db: Session = Depends(get_db),
#         user = Depends(get_current_user),
#     ):
#         allowed = (
#             db.query(OfficePermission)
#             .join(OfficeRolePermission.office_id)
#             .join(UserOffice, UserOffice.role_id == OfficeRolePermission.role_id)
#             .filter(
#                 UserOffice.user_id == user.id,
#                 UserOffice.office_id == office_id,
#                 UserOffice.is_active.is_(True),
#                 OfficePermission.code == permission_code
#             )
#             .first()
#         )

#         if not allowed:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Insufficient office permissions"
#             )

#         return True

#     return checker



def require_office_permission(permission_code: str):
    def checker(
        office_id: int,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        allowed = (
            db.query(OfficePermission)
            .select_from(OfficePermission)
            .join(
                OfficeRolePermission,
                OfficeRolePermission.permission_id == OfficePermission.id
            )
            .join(
                UserOffice,
                UserOffice.role_id == OfficeRolePermission.role_id
            )
            .filter(
                UserOffice.user_id == user.id,
                UserOffice.office_id == office_id,
                UserOffice.is_active.is_(True),
                OfficePermission.code == permission_code
            )
            .first()
        )

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient office permissions"
            )

        return True

    return checker



def get_current_office_id(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> int:
    user_office = (
        db.query(UserOffice)
        .filter(
            UserOffice.user_id == user.id,
            UserOffice.is_primary.is_(True),
            UserOffice.is_active.is_(True)
        )
        .first()
    )

    if not user_office:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no primary active office"
        )

    return user_office.office_id   



def get_current_tenant_id(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> int:
    """
    Resolve tenant_id from logged-in user.
    This is the default for 99% of requests.
    """

    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with any tenant"
        )

    tenant = (
        db.query(Tenant)
        .filter(
            Tenant.id == user.tenant_id,
            Tenant.is_active == True
        )
        .first()
    )

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is inactive or does not exist"
        )

    return tenant.id


# def get_current_user_full(
#     db: Session = Depends(get_db),
#     token: str = Depends(oauth2_scheme),
#     # user_id: int,
#     # tenant_id: int,
# )-> dict:
#     payload = decode_access_token(token)
    
#     user_id: str | None = payload.get("sub")
#     tenant_id: int | None = payload.get("tenant_id")

#     logger.info(f"user_id {user_id}, tenant_id : {tenant_id}")

#     if not user_id:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid 
#             authentication token"
#         )

#     # is_super_admin = User.tenant_id is None


#     # 1 Base user + tenant

#     user = (
#         db.query(User, Tenant.name.label("pgid_name"))
#         .join(Tenant, Tenant.id == User.tenant_id)
#         .filter(
#             User.id == user_id,
#             User.tenant_id == tenant_id,
#             User.is_active == True,
#         )
#         .first()
#     )

#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="User not found or inactive",
#         )

#     user_obj, pgid_name = user

#     # 2 Offices + roles
#     office_rows = (
#         db.query(
#             UserOffice.office_id,
#             Office.office_name,
#             Role.name.label("role"),
#             Role.scope.label("security_group"),
#             UserOffice.is_primary,
#         )
#         .join(Office, Office.id == UserOffice.office_id)
#         .outerjoin(Role, Role.id == UserOffice.role_id)
#         .filter(
#             UserOffice.user_id == user_id,
#             # UserOffice.tenant_id == tenant_id,
#         )
#         .all()
#     )

#     home_office_id = None
#     home_office_name = None
#     assigned_offices = []
#     roles = set()
#     security_groups = set()

#     for row in office_rows:
#         assigned_offices.append({
#             "office_id": row.office_id,
#             "office_name": row.office_name,
#             "role": row.role,
#             "security_group": row.security_group,
#         })

#         if row.is_primary:
#             home_office_id = row.office_id
#             home_office_name = row.office_name

#         if row.role:
#             roles.add(row.role)
#         if row.security_group:
#             security_groups.add(row.security_group)

#     # 3 Permitted IPs
#     ip_rows = (
#         db.query(IPAddress.ip_address)
#         .join(UserIPRule, UserIPRule.ip_id == IPAddress.id)
#         .filter(
#             UserIPRule.user_id == user_id,
#             UserIPRule.tenant_id == tenant_id,
#         )
#         .all()
#     )

#     permitted_ips = [ip.ip_address for ip in ip_rows]

#     # 4 Preferences
#     prefs = (
#         db.query(UserPreference)
#         .filter(UserPreference.user_id == user_id)
#         .first()
#     )

#     preferences = {
#         "startupScreen": prefs.startup_screen if prefs else "Dashboard",
#         "defaultView": prefs.default_view if prefs else "Dashboard",
#         "productionView": prefs.production_view if prefs else "Daily",
#     }

#     # 5 Final hydrated object
#     return {
#         "user_id": user_obj.id,
#         "email": user_obj.email,
#         "username": user_obj.username,
#         "first_name": user_obj.first_name,
#         "last_name": user_obj.last_name,

#         "pgid": user_obj.tenant_id,
#         "pgid_name": pgid_name,

#         "home_office_id": home_office_id,
#         "home_office_name": home_office_name,

#         "assigned_offices": assigned_offices,

#         "roles": list(roles),
#         "security_groups": list(security_groups),

#         "permitted_ips": permitted_ips,
#         "preferences": preferences,
#     }


def get_current_user_full(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> dict:
    payload = decode_access_token(token)

    user_id: int | None = payload.get("sub")
    tenant_id: int | None = payload.get("tenant_id")

    logger.info(f"user_id={user_id}, tenant_id={tenant_id}")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    # ------------------------------------------------------------------
    # 0️⃣ SUPER ADMIN CHECK (tenant_id IS NULL)
    # ------------------------------------------------------------------
    is_super_admin = tenant_id is None

    # ------------------------------------------------------------------
    # 1 BASE USER
    # ------------------------------------------------------------------
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.is_active.is_(True),
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # ------------------------------------------------------------------
    # 2 TENANT NAME
    # ------------------------------------------------------------------
    if is_super_admin:
        pgid = None
        pgid_name = "ALL TENANTS"
    else:
        tenant = (
            db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .first()
        )

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant not found",
            )

        pgid = tenant.id
        pgid_name = tenant.name

    # ------------------------------------------------------------------
    # 3 OFFICES + ROLES
    # ------------------------------------------------------------------
    office_query = (
        db.query(
            Office.id.label("office_id"),
            Office.office_name,
            Role.name.label("role"),
            Role.scope.label("security_group"),
            UserOffice.is_primary,
        )
        .join(UserOffice, UserOffice.office_id == Office.id)
        .outerjoin(Role, Role.id == UserOffice.role_id)
        .filter(UserOffice.user_id == user_id)
    )

    # Tenant filter ONLY for non-super-admin
    if not is_super_admin:
        office_query = office_query.filter(
            Office.tenant_id == tenant_id
        )

    office_rows = office_query.all()

    home_office_id = None
    home_office_name = None
    assigned_offices = []
    roles = set()
    security_groups = set()

    for row in office_rows:
        assigned_offices.append({
            "office_id": row.office_id,
            "office_name": row.office_name,
            "role": row.role,
            "security_group": row.security_group,
        })

        if row.is_primary:
            home_office_id = row.office_id
            home_office_name = row.office_name

        if row.role:
            roles.add(row.role)
        if row.security_group:
            security_groups.add(row.security_group)

    # ------------------------------------------------------------------
    # 4 PERMITTED IPs
    # ------------------------------------------------------------------
    ip_query = (
        db.query(IPAddress.ip_address)
        .join(UserIPRule, UserIPRule.ip_id == IPAddress.id)
        .filter(UserIPRule.user_id == user_id)
    )

    # Tenant filter ONLY for non-super-admin
    if not is_super_admin:
        ip_query = ip_query.filter(
            UserIPRule.tenant_id == tenant_id
        )

    permitted_ips = [ip.ip_address for ip in ip_query.all()]

    # ------------------------------------------------------------------
    # 5 PREFERENCES
    # ------------------------------------------------------------------
    prefs = (
        db.query(UserPreference)
        .filter(UserPreference.user_id == user_id)
        .first()
    )

    preferences = {
        "startupScreen": prefs.startup_screen if prefs else "Dashboard",
        "defaultView": prefs.default_perio_screen if prefs else "Dashboard",
        "productionView": prefs.production_view if prefs else "Daily",
    }

    # ------------------------------------------------------------------
    # 6 FINAL RESPONSE
    # ------------------------------------------------------------------
    return {
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,

        #  SUPER ADMIN SAFE
        "pgid": pgid,
        "pgid_name": pgid_name,

        "home_office_id": home_office_id,
        "home_office_name": home_office_name,

        "assigned_offices": assigned_offices,

        "roles": list(roles),
        "security_groups": list(security_groups),

        "permitted_ips": permitted_ips,
        "preferences": preferences,
    }





# def get_current_user(
#     token: str = Depends(oauth2_scheme),
#     db: Session = Depends(get_db)
# ) -> User:
#     payload = decode_access_token(token)

#     # if is_access_token_blacklisted(token_jti):
#     #     raise HTTPException(status_code=401, detail="Token revoked")

#     user_id: str | None = payload.get("sub")
#     tenant_id: int | None = payload.get("tenant_id")

#     logger.info(f"user_id {user_id}, tenant_id : {tenant_id}")

#     if not user_id:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid authentication token"
#         )

#     user = (
#         db.query(User)
#         .filter(
#             User.id == int(user_id),
#             User.tenant_id == tenant_id,
#             # User.is_active == True
#         )
#         .first()
#     )

#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="User not found or inactive"
#         )
#     logger.info(f"user ----> {type(user)}")
#     # user.name = name_from_email(user.email)

#     return user

