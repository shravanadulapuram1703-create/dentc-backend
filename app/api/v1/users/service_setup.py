"""
Service function for User Setup Metadata API endpoint.
Fetches all metadata and configuration options needed for Add/Edit User form.
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import List
from decimal import Decimal

from app.models.tenant import Tenant
from app.models.offices import Office
from app.models.role import Role

from app.api.v1.users.schemas import (
    UserSetupResponse,
    OrganizationInfo,
    OfficeSetupInfo,
    SecurityGroupInfo,
    RoleInfo,
    PatientAccessLevel,
    TimeClockConfig,
    OvertimeMethod,
    OvertimeRate,
    LoginRestrictions,
    UserPreferencesSchema,
    PreferenceOptions,
    PreferenceFlags,
)


def get_user_setup_metadata(
    db: Session,
    tenant_id: int
) -> UserSetupResponse:
    """
    Fetch all metadata and configuration options needed for Add/Edit User form.
    Returns data scoped to the specified tenant.
    """
    # Get organization/tenant information
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    organization = OrganizationInfo(
        pgid=f"P-{tenant.id}",
        pgid_name=tenant.name,
        tenant_id=str(tenant.id)
    )
    
    # Get offices for the tenant (active only)
    offices_query = db.query(Office).filter(
        Office.tenant_id == tenant_id,
        Office.is_active == True
    ).order_by(Office.office_name)
    
    offices = [
        OfficeSetupInfo(
            office_id=office.id,
            office_oid=office.office_code or f"O-{office.id}",
            office_name=office.office_name or "",
            is_active=office.is_active
        )
        for office in offices_query.all()
    ]
    
    # Get security groups (using Role.scope as security group code)
    # Get distinct scopes from roles, grouped by scope
    roles_by_scope = {}
    all_roles = db.query(Role).filter(Role.tenant_id == tenant_id).all()
    
    for role in all_roles:
        if role.scope:
            if role.scope not in roles_by_scope:
                roles_by_scope[role.scope] = []
            roles_by_scope[role.scope].append(role)
    
    # Build security groups from unique scopes
    security_groups = []
    for scope, roles_list in roles_by_scope.items():
        # Use the first role's name as the security group name
        # Or create a more descriptive name from scope
        role = roles_list[0]
        security_group_name = role.name if role.name else scope.replace("_", " ").title()
        
        security_groups.append(
            SecurityGroupInfo(
                code=scope,
                name=security_group_name,
                description=f"Security group: {scope}"
            )
        )
    
    # Sort security groups by name
    security_groups.sort(key=lambda x: x.name)
    
    # Get roles (using Role.name as code and label)
    roles_query = db.query(Role).filter(
        Role.tenant_id == tenant_id
    ).order_by(Role.name)
    
    roles = [
        RoleInfo(
            code=role.name,  # Use role name as code
            label=role.name  # Use role name as label
        )
        for role in roles_query.all()
    ]
    
    # Patient access levels (static)
    patient_access_levels = [
        PatientAccessLevel(
            code="all",
            label="Search patients in all offices"
        ),
        PatientAccessLevel(
            code="assigned",
            label="Search patients in assigned offices only"
        )
    ]
    
    # Time clock configuration
    time_clock = TimeClockConfig(
        enabled=True,  # Time clock is enabled by default
        overtime_methods=[
            OvertimeMethod(code="daily", label="Daily"),
            OvertimeMethod(code="weekly", label="Weekly"),
            OvertimeMethod(code="none", label="None")
        ],
        overtime_rates=[
            OvertimeRate(value=Decimal("1.0"), label="1.0x (Regular Rate)"),
            OvertimeRate(value=Decimal("1.5"), label="1.5x (Time and a Half)"),
            OvertimeRate(value=Decimal("2.0"), label="2.0x (Double Time)")
        ]
    )
    
    # Login restrictions defaults
    login_restrictions = LoginRestrictions(
        allow_24x7_default=True,
        allowed_days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        default_allowed_from="08:00",
        default_allowed_until="18:00"
    )
    
    # User preferences schema
    user_preferences_schema = UserPreferencesSchema(
        startup_screen=PreferenceOptions(
            options=["Dashboard", "Scheduler", "Patient"]
        ),
        default_perio_screen=PreferenceOptions(
            options=["Standard", "Advanced"]
        ),
        default_navigation_search=PreferenceOptions(
            options=["Patient", "Appointment", "Claim"]
        ),
        default_search_by=PreferenceOptions(
            options=["lastName", "firstName", "patientId", "chartNumber"]
        ),
        default_referral_view=PreferenceOptions(
            options=["All", "Active", "Pending"]
        ),
        flags=PreferenceFlags(
            show_production_view=True,
            hide_provider_time=False,
            print_labels=False,
            prompt_entry_date=False,
            include_inactive_patients=False,
            hipaa_compliant_scheduler=False,
            is_ortho_assistant=False
        )
    )
    
    return UserSetupResponse(
        organization=organization,
        offices=offices,
        security_groups=security_groups,
        roles=roles,
        patient_access_levels=patient_access_levels,
        time_clock=time_clock,
        login_restrictions=login_restrictions,
        user_preferences_schema=user_preferences_schema
    )
