"""
Service functions for Add/Edit User API endpoints.
Implements create_user_full, update_user_full, and get_user_for_edit.
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.user_office import UserOffice
from app.models.offices import Office
from app.models.user_ip_rules import UserIPRule
from app.models.ip_addresses import IPAddress
from app.models.user_time_clock import UserTimeClock
from app.models.user_preferences import UserPreference
from app.models.group import Group, UserGroupMembership
from app.utils.password import hash_password
from app.services.audit_service import log_audit

from app.api.v1.users.schemas import (
    UserCreateRequest,
    UserUpdateRequest,
    UserEditResponse,
    UserCreateResponse,
    UserUpdateResponse,
    UserTimeClockConfig,
    UserPreferencesConfig,
    UserLoginRestrictions,
)
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import time as dt_time

import logging
logger = logging.getLogger(__name__)


def get_user_for_edit(
    db: Session,
    tenant_id: int,
    user_id: int,
    current_user: User
) -> UserEditResponse:
    """
    Get user data for editing in Add/Edit User modal.
    Returns data in the format required by the API contract.
    """
    # Get user
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    
    # Get home office
    home_office = db.query(UserOffice).filter(
        UserOffice.user_id == user_id,
        UserOffice.is_primary == True
    ).first()
    
    home_office_id = home_office.office_id if home_office else None
    
    # Get all assigned offices
    assigned_offices = db.query(UserOffice).filter(
        UserOffice.user_id == user_id
    ).all()
    assigned_office_ids = [uo.office_id for uo in assigned_offices]
    
    # Get roles (from user_roles) and derive security groups & group memberships
    user_roles = (
        db.query(UserRole, Role)
        .join(Role, Role.id == UserRole.role_id)
        .filter(
            UserRole.user_id == user_id,
            UserRole.tenant_id == tenant_id
        )
        .all()
    )
    roles = [role.name for _, role in user_roles]
    security_groups = list({role.scope for _, role in user_roles if role.scope})
    
    # Get group memberships from database
    user_group_memberships = (
        db.query(UserGroupMembership, Group)
        .join(Group, Group.id == UserGroupMembership.group_id)
        .filter(
            UserGroupMembership.user_id == user_id,
            UserGroupMembership.tenant_id == tenant_id,
            Group.is_active == True
        )
        .all()
    )
    group_memberships = [group.code for _, group in user_group_memberships]
    
    # Get permitted IPs
    ip_rules = (
        db.query(UserIPRule, IPAddress)
        .join(IPAddress, IPAddress.id == UserIPRule.ip_id)
        .filter(UserIPRule.user_id == user_id)
        .all()
    )
    permitted_ips = [ip.ip_address for _, ip in ip_rules]
    
    # Get time clock config
    time_clock_settings = db.query(UserTimeClock).filter(
        UserTimeClock.user_id == user_id
    ).first()
    
    time_clock = None
    if time_clock_settings:
        time_clock = UserTimeClockConfig(
            pay_rate=time_clock_settings.pay_rate,
            overtime_method=time_clock_settings.overtime_method,
            overtime_rate=time_clock_settings.overtime_rate
        )
    
    # Get preferences
    preferences_obj = db.query(UserPreference).filter(
        UserPreference.user_id == user_id
    ).first()
    
    preferences = None
    if preferences_obj:
        # default_navigation_search is stored as boolean in DB, but API expects string
        # If True, default to "Patient", if False or None, return None
        default_nav_search = None
        if preferences_obj.default_navigation_search:
            default_nav_search = "Patient"  # Default value when enabled
        
        preferences = UserPreferencesConfig(
            startup_screen=preferences_obj.startup_screen,
            default_perio_screen=preferences_obj.default_perio_screen,
            default_navigation_search=default_nav_search,
            default_search_by=preferences_obj.default_search_by,
            default_referral_view=preferences_obj.referral_view,
            show_production_view=preferences_obj.show_production_colors,
            hide_provider_time=preferences_obj.hide_provider_time,
            print_labels=preferences_obj.print_labels,
            prompt_entry_date=preferences_obj.prompt_entry_date,
            include_inactive_patients=preferences_obj.include_inactive_patients,
            hipaa_compliant_scheduler=getattr(preferences_obj, 'hipaa_compliant_scheduler', None),
            is_ortho_assistant=getattr(preferences_obj, 'is_ortho_assistant', None)
        )
    
    # Get patient_access_level (from user.patient_access_level)
    patient_access_level = user.patient_access_level or "all"
    # Map "all_offices" to "all" and "home_office" to "assigned" if needed
    if patient_access_level == "all_offices":
        patient_access_level = "all"
    elif patient_access_level == "home_office":
        patient_access_level = "assigned"
    
    # Build login_restrictions from user fields
    login_restrictions = None
    if user.allowed_days is None and user.allowed_from is None and user.allowed_until is None:
        # 24/7 access
        login_restrictions = UserLoginRestrictions(
            use_24x7_access=True,
            allowed_days=None,
            allowed_from=None,
            allowed_until=None
        )
    else:
        # Restricted access
        allowed_from_str = None
        allowed_until_str = None
        if user.allowed_from:
            allowed_from_str = user.allowed_from.strftime("%H:%M")
        if user.allowed_until:
            allowed_until_str = user.allowed_until.strftime("%H:%M")
        
        login_restrictions = UserLoginRestrictions(
            use_24x7_access=False,
            allowed_days=user.allowed_days or [],
            allowed_from=allowed_from_str,
            allowed_until=allowed_until_str
        )
    
    return UserEditResponse(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        home_office_id=home_office_id or 0,
        assigned_offices=assigned_office_ids,
        roles=roles,
        security_groups=security_groups,
        permitted_ips=permitted_ips,
        patient_access_level=patient_access_level,
        group_memberships=group_memberships,
        login_restrictions=login_restrictions,
        time_clock=time_clock,
        preferences=preferences
    )


def create_user_full(
    db: Session,
    tenant_id: int,
    payload: UserCreateRequest,
    current_user: User,
    request
) -> UserCreateResponse:
    """
    Create a new user with all related data (offices, roles, IPs, time_clock, preferences).
    """
    # Validation: Check username uniqueness
    existing_user = db.query(User).filter(
        User.username == payload.username
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "username"],
                "msg": "Username already exists",
                "type": "value_error"
            }]
        )
    
    # Validation: Check email uniqueness
    existing_email = db.query(User).filter(
        User.email == payload.email
    ).first()
    if existing_email:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "email"],
                "msg": "Email already exists",
                "type": "value_error"
            }]
        )
    
    # Validation: Password strength
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "password"],
                "msg": "Password must be at least 8 characters",
                "type": "value_error"
            }]
        )
    
    # Validation: Home office must be in assigned_offices
    if payload.home_office_id not in payload.assigned_offices:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "home_office_id"],
                "msg": "Home office must be included in assigned_offices",
                "type": "value_error"
            }]
        )
    
    # Validation: Verify all offices exist and are active
    offices = db.query(Office).filter(
        Office.id.in_(payload.assigned_offices),
        Office.tenant_id == tenant_id,
        Office.is_active == True
    ).all()
    
    if len(offices) != len(payload.assigned_offices):
        raise HTTPException(
            status_code=400,
            detail="One or more office IDs are invalid or inactive"
        )
    
    # Validation: Verify all roles exist
    roles = db.query(Role).filter(
        Role.name.in_(payload.roles),
        Role.tenant_id == tenant_id
    ).all()
    
    if len(roles) != len(payload.roles):
        raise HTTPException(
            status_code=400,
            detail="One or more role names are invalid"
        )
    
    # Validation: Verify all security groups exist (using role.scope)
    valid_scopes = db.query(Role.scope).filter(
        Role.tenant_id == tenant_id
    ).distinct().all()
    valid_scopes = [s[0] for s in valid_scopes]
    
    invalid_groups = [sg for sg in payload.security_groups if sg not in valid_scopes]
    if invalid_groups:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid security groups: {', '.join(invalid_groups)}"
        )
    
    # Validation: Verify all group memberships exist
    if payload.group_memberships:
        groups = db.query(Group).filter(
            Group.code.in_(payload.group_memberships),
            Group.tenant_id == tenant_id,
            Group.is_active == True
        ).all()
        
        found_codes = {g.code for g in groups}
        invalid_group_codes = [code for code in payload.group_memberships if code not in found_codes]
        
        if invalid_group_codes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid group membership codes: {', '.join(invalid_group_codes)}"
            )
    
    # Handle patient_access_level
    patient_access_level_db = payload.patient_access_level or "all"
    if patient_access_level_db == "all":
        patient_access_level_db = "all_offices"
    elif patient_access_level_db == "assigned":
        patient_access_level_db = "home_office"
    
    # Handle login_restrictions
    allowed_days = None
    allowed_from = None
    allowed_until = None
    if payload.login_restrictions:
        if payload.login_restrictions.use_24x7_access:
            # 24/7 access - set all to None
            allowed_days = None
            allowed_from = None
            allowed_until = None
        else:
            # Restricted access
            allowed_days = payload.login_restrictions.allowed_days
            if payload.login_restrictions.allowed_from:
                # Parse HH:MM string to time object
                time_parts = payload.login_restrictions.allowed_from.split(":")
                allowed_from = dt_time(int(time_parts[0]), int(time_parts[1]))
            if payload.login_restrictions.allowed_until:
                # Parse HH:MM string to time object
                time_parts = payload.login_restrictions.allowed_until.split(":")
                allowed_until = dt_time(int(time_parts[0]), int(time_parts[1]))
    
    # Create user
    user = User(
        tenant_id=tenant_id,
        username=payload.username,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone=payload.phone,
        is_active=payload.is_active,
        role=payload.roles[0] if payload.roles else "User",  # Legacy field
        created_by=current_user.id if current_user else None,
        patient_access_level=patient_access_level_db,
        allowed_days=allowed_days,
        allowed_from=allowed_from,
        allowed_until=allowed_until
    )
    
    db.add(user)
    db.flush()  # Get user.id
    
    # Create user offices
    for office_id in payload.assigned_offices:
        user_office = UserOffice(
            user_id=user.id,
            office_id=office_id,
            is_primary=(office_id == payload.home_office_id),
            is_active=True
        )
        db.add(user_office)
    
    # Create user roles
    for role in roles:
        user_role = UserRole(
            user_id=user.id,
            role_id=role.id,
            tenant_id=tenant_id,
            assigned_by=current_user.id if current_user else None,
        )
        db.add(user_role)
    
    # Create group memberships
    group_memberships: list[str] = []
    if payload.group_memberships:
        groups = db.query(Group).filter(
            Group.code.in_(payload.group_memberships),
            Group.tenant_id == tenant_id
        ).all()
        
        for group in groups:
            user_group_membership = UserGroupMembership(
                user_id=user.id,
                group_id=group.id,
                tenant_id=tenant_id,
                assigned_by=current_user.id if current_user else None
            )
            db.add(user_group_membership)
            group_memberships.append(group.code)
    
    # Create IP rules
    if payload.permitted_ips:
        for ip_address_str in payload.permitted_ips:
            # Check if IP address exists, create if not
            ip_address = db.query(IPAddress).filter(
                IPAddress.ip_address == ip_address_str
            ).first()
            
            if not ip_address:
                ip_address = IPAddress(
                    ip_address=ip_address_str,
                    name=f"IP for {user.username}",
                    is_active=True
                )
                db.add(ip_address)
                db.flush()
            
            # Create user IP rule
            user_ip_rule = UserIPRule(
                user_id=user.id,
                ip_id=ip_address.id,
                tenant_id=tenant_id,
                is_active=True
            )
            db.add(user_ip_rule)
    
    # Create time clock settings
    if payload.time_clock:
        time_clock = UserTimeClock(
            user_id=user.id,
            pay_rate=payload.time_clock.pay_rate,
            overtime_method=payload.time_clock.overtime_method,
            overtime_rate=payload.time_clock.overtime_rate
        )
        db.add(time_clock)
    
    # Create preferences
    if payload.preferences:
        prefs = payload.preferences
        # Convert string default_navigation_search to boolean
        # API sends string ("Patient", "Appointment", "Claim"), DB stores boolean
        # If string is provided, set to True, otherwise False
        default_nav_search = bool(prefs.default_navigation_search) if prefs.default_navigation_search else False
        
        user_pref = UserPreference(
            user_id=user.id,
            startup_screen=prefs.startup_screen,
            default_perio_screen=prefs.default_perio_screen,
            default_navigation_search=default_nav_search,
            default_search_by=prefs.default_search_by,
            referral_view=prefs.default_referral_view,
            show_production_colors=prefs.show_production_view,
            hide_provider_time=prefs.hide_provider_time,
            print_labels=prefs.print_labels,
            prompt_entry_date=prefs.prompt_entry_date,
            include_inactive_patients=prefs.include_inactive_patients
        )
        db.add(user_pref)
    
    db.commit()
    db.refresh(user)
    
    # Log audit
    log_audit(
        db,
        action="CREATE_USER",
        success=True,
        tenant_id=tenant_id,
        actor_user_id=current_user.id if current_user else None,
        resource="users",
        resource_id=str(user.id),
        resource_pk=str(user.id),
        reason="User created via Add/Edit User API",
    )
    
    # Build response
    created_by_username = current_user.username if current_user else None
    
    return UserCreateResponse(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        home_office_id=payload.home_office_id,
        assigned_offices=payload.assigned_offices,
        roles=payload.roles,
        security_groups=payload.security_groups,
        group_memberships=group_memberships,
        permitted_ips=payload.permitted_ips or [],
        patient_access_level=payload.patient_access_level or "all",
        time_clock=payload.time_clock,
        preferences=payload.preferences,
        created_at=user.created_at,
        created_by=created_by_username
    )


def update_user_full(
    db: Session,
    tenant_id: int,
    user_id: int,
    payload: UserUpdateRequest,
    current_user: User,
    request
) -> UserUpdateResponse:
    """
    Update an existing user with all related data.
    """
    # Get user
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    
    # Validation: Check username uniqueness (exclude current user)
    existing_user = db.query(User).filter(
        User.username == payload.username,
        User.id != user_id
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "username"],
                "msg": "Username already exists",
                "type": "value_error"
            }]
        )
    
    # Validation: Check email uniqueness (exclude current user)
    existing_email = db.query(User).filter(
        User.email == payload.email,
        User.id != user_id
    ).first()
    if existing_email:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "email"],
                "msg": "Email already exists",
                "type": "value_error"
            }]
        )
    
    # Validation: Password strength (if provided)
    if payload.password and len(payload.password) < 8:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "password"],
                "msg": "Password must be at least 8 characters",
                "type": "value_error"
            }]
        )
    
    # Validation: Home office must be in assigned_offices
    if payload.home_office_id not in payload.assigned_offices:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "home_office_id"],
                "msg": "Home office must be included in assigned_offices",
                "type": "value_error"
            }]
        )
    
    # Validation: Verify all offices exist and are active
    offices = db.query(Office).filter(
        Office.id.in_(payload.assigned_offices),
        Office.tenant_id == tenant_id,
        Office.is_active == True
    ).all()
    
    if len(offices) != len(payload.assigned_offices):
        raise HTTPException(
            status_code=400,
            detail="One or more office IDs are invalid or inactive"
        )
    
    # Validation: Verify all roles exist
    roles = db.query(Role).filter(
        Role.name.in_(payload.roles),
        Role.tenant_id == tenant_id
    ).all()
    
    if len(roles) != len(payload.roles):
        raise HTTPException(
            status_code=400,
            detail="One or more role names are invalid"
        )
    
    # Validation: Verify all security groups exist
    valid_scopes = db.query(Role.scope).filter(
        Role.tenant_id == tenant_id
    ).distinct().all()
    valid_scopes = [s[0] for s in valid_scopes]
    
    invalid_groups = [sg for sg in payload.security_groups if sg not in valid_scopes]
    if invalid_groups:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid security groups: {', '.join(invalid_groups)}"
        )
    
    # Validation: Verify all group memberships exist
    if payload.group_memberships:
        groups = db.query(Group).filter(
            Group.code.in_(payload.group_memberships),
            Group.tenant_id == tenant_id,
            Group.is_active == True
        ).all()
        
        found_codes = {g.code for g in groups}
        invalid_group_codes = [code for code in payload.group_memberships if code not in found_codes]
        
        if invalid_group_codes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid group membership codes: {', '.join(invalid_group_codes)}"
            )
    
    # Handle patient_access_level
    patient_access_level_db = payload.patient_access_level or "all"
    if patient_access_level_db == "all":
        patient_access_level_db = "all_offices"
    elif patient_access_level_db == "assigned":
        patient_access_level_db = "home_office"
    
    # Handle login_restrictions
    allowed_days = None
    allowed_from = None
    allowed_until = None
    if payload.login_restrictions:
        if payload.login_restrictions.use_24x7_access:
            # 24/7 access - set all to None
            allowed_days = None
            allowed_from = None
            allowed_until = None
        else:
            # Restricted access
            allowed_days = payload.login_restrictions.allowed_days
            if payload.login_restrictions.allowed_from:
                # Parse HH:MM string to time object
                time_parts = payload.login_restrictions.allowed_from.split(":")
                allowed_from = dt_time(int(time_parts[0]), int(time_parts[1]))
            if payload.login_restrictions.allowed_until:
                # Parse HH:MM string to time object
                time_parts = payload.login_restrictions.allowed_until.split(":")
                allowed_until = dt_time(int(time_parts[0]), int(time_parts[1]))
    
    # Update user basic fields
    user.username = payload.username
    if payload.password:
        user.password_hash = hash_password(payload.password)
    user.first_name = payload.first_name
    user.last_name = payload.last_name
    user.email = payload.email
    user.phone = payload.phone
    user.is_active = payload.is_active
    user.role = payload.roles[0] if payload.roles else user.role  # Legacy field
    user.updated_by = current_user.username if current_user else None
    user.patient_access_level = patient_access_level_db
    user.allowed_days = allowed_days
    user.allowed_from = allowed_from
    user.allowed_until = allowed_until
    
    # Update user offices (delete and recreate)
    db.query(UserOffice).filter(UserOffice.user_id == user_id).delete()
    for office_id in payload.assigned_offices:
        user_office = UserOffice(
            user_id=user.id,
            office_id=office_id,
            is_primary=(office_id == payload.home_office_id),
            is_active=True
        )
        db.add(user_office)
    
    # Update user roles (delete and recreate)
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    for role in roles:
        user_role = UserRole(
            user_id=user.id,
            role_id=role.id,
            tenant_id=tenant_id,
            assigned_by=current_user.id if current_user else None
        )
        db.add(user_role)
    
    # Update group memberships (delete and recreate)
    db.query(UserGroupMembership).filter(UserGroupMembership.user_id == user_id).delete()
    updated_group_memberships: list[str] = []
    if payload.group_memberships:
        groups = db.query(Group).filter(
            Group.code.in_(payload.group_memberships),
            Group.tenant_id == tenant_id
        ).all()
        
        for group in groups:
            user_group_membership = UserGroupMembership(
                user_id=user.id,
                group_id=group.id,
                tenant_id=tenant_id,
                assigned_by=current_user.id if current_user else None
            )
            db.add(user_group_membership)
            updated_group_memberships.append(group.code)
    
    # Update IP rules (delete and recreate)
    db.query(UserIPRule).filter(UserIPRule.user_id == user_id).delete()
    if payload.permitted_ips:
        for ip_address_str in payload.permitted_ips:
            # Check if IP address exists, create if not
            ip_address = db.query(IPAddress).filter(
                IPAddress.ip_address == ip_address_str
            ).first()
            
            if not ip_address:
                ip_address = IPAddress(
                    ip_address=ip_address_str,
                    name=f"IP for {user.username}",
                    is_active=True
                )
                db.add(ip_address)
                db.flush()
            
            # Create user IP rule
            user_ip_rule = UserIPRule(
                user_id=user.id,
                ip_id=ip_address.id,
                tenant_id=tenant_id,
                is_active=True
            )
            db.add(user_ip_rule)
    
    # Update time clock settings
    time_clock_settings = db.query(UserTimeClock).filter(
        UserTimeClock.user_id == user_id
    ).first()
    
    if payload.time_clock:
        if time_clock_settings:
            time_clock_settings.pay_rate = payload.time_clock.pay_rate
            time_clock_settings.overtime_method = payload.time_clock.overtime_method
            time_clock_settings.overtime_rate = payload.time_clock.overtime_rate
        else:
            time_clock = UserTimeClock(
                user_id=user.id,
                pay_rate=payload.time_clock.pay_rate,
                overtime_method=payload.time_clock.overtime_method,
                overtime_rate=payload.time_clock.overtime_rate
            )
            db.add(time_clock)
    else:
        # Delete time clock settings if not provided
        if time_clock_settings:
            db.delete(time_clock_settings)
    
    # Update preferences
    preferences_obj = db.query(UserPreference).filter(
        UserPreference.user_id == user_id
    ).first()
    
    if payload.preferences:
        prefs = payload.preferences
        # Convert string default_navigation_search to boolean
        # API sends string ("Patient", "Appointment", "Claim"), DB stores boolean
        # If string is provided, set to True, otherwise False
        default_nav_search = bool(prefs.default_navigation_search) if prefs.default_navigation_search else False
        
        if preferences_obj:
            preferences_obj.startup_screen = prefs.startup_screen
            preferences_obj.default_perio_screen = prefs.default_perio_screen
            preferences_obj.default_navigation_search = default_nav_search
            preferences_obj.default_search_by = prefs.default_search_by
            preferences_obj.referral_view = prefs.default_referral_view
            preferences_obj.show_production_colors = prefs.show_production_view
            preferences_obj.hide_provider_time = prefs.hide_provider_time
            preferences_obj.print_labels = prefs.print_labels
            preferences_obj.prompt_entry_date = prefs.prompt_entry_date
            preferences_obj.include_inactive_patients = prefs.include_inactive_patients
            if hasattr(preferences_obj, 'hipaa_compliant_scheduler'):
                preferences_obj.hipaa_compliant_scheduler = getattr(prefs, 'hipaa_compliant_scheduler', None)
            if hasattr(preferences_obj, 'is_ortho_assistant'):
                preferences_obj.is_ortho_assistant = getattr(prefs, 'is_ortho_assistant', None)
        else:
            user_pref = UserPreference(
                user_id=user.id,
                startup_screen=prefs.startup_screen,
                default_perio_screen=prefs.default_perio_screen,
                default_navigation_search=default_nav_search,
                default_search_by=prefs.default_search_by,
                referral_view=prefs.default_referral_view,
                show_production_colors=prefs.show_production_view,
                hide_provider_time=prefs.hide_provider_time,
                print_labels=prefs.print_labels,
                prompt_entry_date=prefs.prompt_entry_date,
                include_inactive_patients=prefs.include_inactive_patients,
                hipaa_compliant_scheduler=getattr(prefs, 'hipaa_compliant_scheduler', None),
                is_ortho_assistant=getattr(prefs, 'is_ortho_assistant', None)
            )
            db.add(user_pref)
    else:
        # Delete preferences if not provided
        if preferences_obj:
            db.delete(preferences_obj)
    
    db.commit()
    db.refresh(user)
    
    # Log audit
    log_audit(
        db,
        action="UPDATE_USER",
        success=True,
        tenant_id=tenant_id,
        actor_user_id=current_user.id if current_user else None,
        resource="users",
        resource_id=str(user.id),
        resource_pk=str(user.id),
        reason="User updated via Add/Edit User API",
    )
    
    # Build response (re-read roles to derive security_groups)
    updated_user_roles = (
        db.query(UserRole, Role)
        .join(Role, Role.id == UserRole.role_id)
        .filter(
            UserRole.user_id == user.id,
            UserRole.tenant_id == tenant_id,
        )
        .all()
    )
    updated_roles = [r.name for _, r in updated_user_roles]
    updated_security_groups = list({r.scope for _, r in updated_user_roles if r.scope})
    
    # Re-read group memberships from database
    updated_user_group_memberships = (
        db.query(UserGroupMembership, Group)
        .join(Group, Group.id == UserGroupMembership.group_id)
        .filter(
            UserGroupMembership.user_id == user.id,
            UserGroupMembership.tenant_id == tenant_id,
            Group.is_active == True
        )
        .all()
    )
    updated_group_memberships = [group.code for _, group in updated_user_group_memberships]

    updated_by_username = current_user.username if current_user else None
    
    return UserUpdateResponse(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        home_office_id=payload.home_office_id,
        assigned_offices=payload.assigned_offices,
        roles=updated_roles,
        security_groups=updated_security_groups,
        group_memberships=updated_group_memberships,
        permitted_ips=payload.permitted_ips or [],
        time_clock=payload.time_clock,
        preferences=payload.preferences,
        updated_at=user.updated_at or datetime.utcnow(),
        updated_by=updated_by_username,
    )
