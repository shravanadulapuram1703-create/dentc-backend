# ==================================================
# USER DETAILS API SERVICES
# ==================================================
# Services for View User Details modal endpoints

from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import List, Optional
from datetime import datetime, date, time
from app.models.user import User
from app.models.tenant import Tenant
from app.models.offices import Office
from app.models.user_office import UserOffice
from app.models.user_ip_rules import UserIPRule
from app.models.ip_addresses import IPAddress
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.user_time_clock import UserTimeClock
from app.models.group import Group
from app.models.user_preferences import UserPreference
from app.api.v1.users.schemas import (
    UserDetailResponse,
    UserIPRuleDetailResponse,
    UserGroupDetailResponse,
    UserTimeClockDetailResponse,
    TimeClockEntryResponse,
    UserPreferencesDetailResponse,
    GroupMembershipOption,
    GroupMembershipsMetadataResponse,
)


def get_user_details(db: Session, tenant_id: int, user_id: int) -> UserDetailResponse:
    """
    Get complete user details for the View User Details modal.
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get tenant information
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    pgid_name = tenant.name if tenant else "Unknown"
    pgid = f"P-{tenant_id}" if tenant else None
    
    # Get home office
    home_office = db.query(UserOffice).filter(
        UserOffice.user_id == user_id,
        UserOffice.is_primary == True
    ).first()
    
    home_office_id = home_office.office_id if home_office else None
    home_office_name = None
    if home_office_id:
        office = db.query(Office).filter(Office.id == home_office_id).first()
        home_office_name = office.office_name if office else None
    
    # Get all assigned offices
    assigned_offices = db.query(UserOffice).filter(
        UserOffice.user_id == user_id
    ).all()
    
    assigned_office_ids = [uo.office_id for uo in assigned_offices]
    assigned_office_names = []
    for office_id in assigned_office_ids:
        office = db.query(Office).filter(Office.id == office_id).first()
        if office:
            assigned_office_names.append(office.office_name)
    
    # Get primary role (from user_roles)
    primary_role = None
    security_group = None
    user_role = db.query(UserRole).filter(
        UserRole.user_id == user_id
    ).first()
    
    if user_role:
        role = db.query(Role).filter(Role.id == user_role.role_id).first()
        if role:
            primary_role = role.name
            security_group = role.scope  # Using scope as security_group
    
    # Get creator username
    created_by_username = None
    if user.created_by:
        creator = db.query(User).filter(User.id == user.created_by).first()
        created_by_username = creator.username if creator else None
    
    # Check if IP check is required (has IP rules)
    require_ip_check = db.query(UserIPRule).filter(
        UserIPRule.user_id == user_id
    ).count() > 0
    
    # Check time clock settings
    time_clock_settings = db.query(UserTimeClock).filter(
        UserTimeClock.user_id == user_id
    ).first()
    time_clock_enabled = time_clock_settings is not None
    clock_in_required = time_clock_enabled  # Default to enabled if settings exist
    
    return UserDetailResponse(
        user_id=user.id,
        id=f"U-{user.id}",
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        tenant_id=user.tenant_id,
        pgid=pgid,
        pgid_name=pgid_name,
        home_office_id=home_office_id,
        home_office_name=home_office_name,
        assigned_office_ids=assigned_office_ids,
        assigned_office_names=assigned_office_names,
        role=primary_role or user.role,  # Fallback to legacy role field
        security_group=security_group,
        password_last_changed=None,  # Not tracked in current schema
        must_change_password=False,  # Not tracked in current schema
        account_locked_until=None if not user.is_locked else datetime.utcnow(),  # Simplified
        failed_login_attempts=0,  # Not tracked in current schema
        require_ip_check=require_ip_check,
        time_clock_enabled=time_clock_enabled,
        clock_in_required=clock_in_required,
        created_by=created_by_username,
        created_at=user.created_at,
        updated_by=user.updated_by,
        updated_at=user.updated_at,
    )


def get_user_ip_rules_details(
    db: Session,
    tenant_id: int,
    user_id: int
) -> List[UserIPRuleDetailResponse]:
    """
    Get IP rules for a user.
    """
    # Verify user exists
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    rows = (
        db.query(
            UserIPRule.id,
            UserIPRule.is_active,
            UserIPRule.created_at,
            IPAddress.ip_address,
            IPAddress.description,
            IPAddress.id.label("ip_address_id"),
        )
        .join(IPAddress, IPAddress.id == UserIPRule.ip_id)
        .filter(
            UserIPRule.tenant_id == tenant_id,
            UserIPRule.user_id == user_id,
        )
        .order_by(IPAddress.ip_address)
        .all()
    )
    
    result = []
    for idx, row in enumerate(rows, start=1):
        result.append(UserIPRuleDetailResponse(
            id=f"IP-{row.id:03d}",
            ip_address=row.ip_address,
            description=row.description,
            active=row.is_active,
            created_at=row.created_at,
            updated_at=None,  # Not tracked in current schema
        ))
    
    return result


def get_user_groups_details(
    db: Session,
    tenant_id: int,
    user_id: int
) -> List[UserGroupDetailResponse]:
    """
    Get security group memberships for a user.
    Uses roles as security groups.
    """
    # Verify user exists
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_roles = (
        db.query(UserRole, Role)
        .join(Role, Role.id == UserRole.role_id)
        .filter(
            UserRole.user_id == user_id,
            UserRole.tenant_id == tenant_id,
        )
        .all()
    )
    
    result = []
    for idx, (user_role, role) in enumerate(user_roles, start=1):
        # Get created_at from user_role if available, otherwise use user.created_at
        joined_date = user.created_at
        if hasattr(user_role, 'created_at') and user_role.created_at:
            joined_date = user_role.created_at
        
        result.append(UserGroupDetailResponse(
            group_id=f"GRP-{role.id:03d}",
            group_name=role.name,
            description=f"Security group: {role.scope}",
            joined_date=joined_date,
            role="Member",  # Default role within group
        ))
    
    return result


def get_group_memberships_metadata(
    db: Session,
    tenant_id: int,
) -> GroupMembershipsMetadataResponse:
    """
    Get full list of available group memberships for the current tenant.
    """
    groups = (
        db.query(Group)
        .filter(
            Group.tenant_id == tenant_id,
            Group.is_active == True,
        )
        .order_by(Group.name)
        .all()
    )

    items = [
        GroupMembershipOption(
            code=g.code,
            name=g.name,
            description=g.description,
        )
        for g in groups
    ]

    return GroupMembershipsMetadataResponse(groups=items)


def get_user_time_clock_details(
    db: Session,
    tenant_id: int,
    user_id: int
) -> UserTimeClockDetailResponse:
    """
    Get time clock configuration and recent entries for a user.
    """
    # Verify user exists
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    time_clock_settings = db.query(UserTimeClock).filter(
        UserTimeClock.user_id == user_id
    ).first()
    
    enabled = time_clock_settings is not None
    clock_in_required = enabled  # Default to required if enabled
    
    # Get recent time clock entries
    # Note: This requires the time_clock_entries table created via migration
    from sqlalchemy import text
    recent_entries: List[TimeClockEntryResponse] = []
    
    try:
        entries_query = text("""
            SELECT 
                id,
                entry_date,
                clock_in_time,
                clock_out_time,
                total_hours,
                notes
            FROM public.time_clock_entries
            WHERE user_id = :user_id
            ORDER BY entry_date DESC, clock_in_time DESC
            LIMIT 20
        """)
        
        entries = db.execute(entries_query, {"user_id": user_id}).fetchall()
        
        for entry in entries:
            clock_in_str = str(entry.clock_in_time) if entry.clock_in_time else "00:00:00"
            clock_out_str = str(entry.clock_out_time) if entry.clock_out_time else None
            total_hours_str = f"{float(entry.total_hours):.1f}" if entry.total_hours else "0.0"
            
            recent_entries.append(TimeClockEntryResponse(
                id=f"TC-{entry.id:03d}",
                date=str(entry.entry_date),
                clock_in=clock_in_str,
                clock_out=clock_out_str,
                total_hours=total_hours_str,
                notes=entry.notes,
            ))
    except Exception:
        # Table doesn't exist yet or error - return empty list
        pass
    
    return UserTimeClockDetailResponse(
        enabled=enabled,
        clock_in_required=clock_in_required,
        recent_entries=recent_entries,
    )


def get_user_preferences_details(
    db: Session,
    tenant_id: int,
    user_id: int
) -> UserPreferencesDetailResponse:
    """
    Get user preferences and settings.
    """
    # Verify user exists
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    preferences = db.query(UserPreference).filter(
        UserPreference.user_id == user_id
    ).first()
    
    if not preferences:
        # Return defaults
        return UserPreferencesDetailResponse(
            theme="Light",
            language="en-US",
            date_format="MM/DD/YYYY",
            time_format="12-hour",
            email_notifications=True,
            sms_notifications=False,
            default_view=preferences.startup_screen if preferences else "Dashboard",
            startup_screen=preferences.startup_screen if preferences else "Dashboard",
            items_per_page=50,
        )
    
    # Map existing preferences to new schema
    return UserPreferencesDetailResponse(
        theme="Light",  # Not in current schema
        language="en-US",  # Not in current schema
        date_format="MM/DD/YYYY",  # Not in current schema
        time_format="12-hour",  # Not in current schema
        email_notifications=True,  # Not in current schema
        sms_notifications=False,  # Not in current schema
        default_view=preferences.startup_screen or "Dashboard",
        startup_screen=preferences.startup_screen or "Dashboard",
        items_per_page=50,  # Not in current schema
    )
