import re
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.setup.schemas import (
    AccountSetupConfigResponse,
    AccountSetupMetadataResponse,
    AccountSetupUpdateResponse,
    SetupFieldDefinition,
    SetupFieldUi,
    SetupMetadataItem,
    SetupSectionDefinition,
    SetupTabDefinition,
    SetupUiActions,
    as_ui_datetime,
)
from app.models.account_setup import AccountSetup
from app.models.offices import Office
from app.models.tenant import Tenant
from app.models.user import User
from app.services.rbac_service import user_has_permission

EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
VALID_CULTURES = [
    {"value": "en-US", "label": "English - United States"},
    {"value": "es-US", "label": "Spanish - United States"},
]
LEDGER_COLORS = [
    {"value": "green", "label": "Green - Healthy"},
    {"value": "yellow", "label": "Yellow - Attention"},
    {"value": "red", "label": "Red - Delinquent"},
    {"value": "blue", "label": "Blue - Information"},
]

ACCOUNT_SETUP_READ_PERMISSIONS: Set[str] = {"USER_MANAGE", "BILLING_VIEW", "BASIC"}
ACCOUNT_SETUP_EDIT_PERMISSIONS: Set[str] = {"USER_MANAGE"}


def ensure_can_read_setup(current_user: User) -> None:
    if current_user.is_platform_user or current_user.role == "super_admin":
        return
    if any(user_has_permission(current_user, perm) for perm in ACCOUNT_SETUP_READ_PERMISSIONS):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User lacks permission to read account setup",
    )


def ensure_can_edit_setup(current_user: User) -> None:
    if current_user.is_platform_user or current_user.role == "super_admin":
        return
    if any(user_has_permission(current_user, perm) for perm in ACCOUNT_SETUP_EDIT_PERMISSIONS):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User lacks permission to update account setup",
    )


def _build_tabs() -> List[SetupTabDefinition]:
    def field(
        *,
        key: str,
        label: str,
        type_value: str,
        order: int,
        width: str = "half",
        group: Optional[str] = None,
        placeholder: Optional[str] = None,
        help_text: Optional[str] = None,
        read_only: bool = False,
        hidden: bool = False,
        options: Optional[List[Dict[str, str]]] = None,
        validation: Optional[Dict[str, Any]] = None,
    ) -> SetupFieldDefinition:
        return SetupFieldDefinition(
            key=key,
            label=label,
            type=type_value,  # type: ignore[arg-type]
            placeholder=placeholder,
            helpText=help_text,
            readOnly=read_only,
            hidden=hidden,
            options=options,
            validation=validation,
            ui=SetupFieldUi(width=width, group=group, order=order),
        )

    return [
        SetupTabDefinition(
            id="basic",
            label="BASIC",
            type="form",
            sections=[
                SetupSectionDefinition(
                    id="account_information",
                    title="Account Information",
                    description="Core account profile details",
                    layout="two-column",
                    fields=[
                        field(
                            key="accountNumber",
                            label="Dental Account #",
                            type_value="text",
                            validation={"required": True},
                            read_only=True,
                            order=1,
                        ),
                        field(
                            key="accountName",
                            label="Account Name",
                            type_value="text",
                            placeholder="Enter account name",
                            validation={"required": True, "maxLength": 150},
                            order=2,
                        ),
                        field(
                            key="email",
                            label="Email",
                            type_value="email",
                            validation={
                                "required": True,
                                "pattern": EMAIL_PATTERN,
                                "message": "Please provide a valid email address.",
                            },
                            order=3,
                        ),
                        field(
                            key="phone",
                            label="Phone",
                            type_value="phone",
                            placeholder="(000) 000-0000",
                            validation={"required": False},
                            order=4,
                        ),
                        field(
                            key="cultureCode",
                            label="Current Culture",
                            type_value="select",
                            options=VALID_CULTURES,
                            order=5,
                        ),
                    ],
                ),
                SetupSectionDefinition(
                    id="corporate_logo_upload",
                    title="Corporate Logo Upload",
                    layout="single",
                    fields=[
                        field(
                            key="logoUrl",
                            label="Corporate Logo",
                            type_value="file_upload",
                            help_text="Allowed formats: PNG/JPG. Recommended max size: 2MB.",
                            width="full",
                            order=1,
                        ),
                    ],
                ),
                SetupSectionDefinition(
                    id="corporate_address",
                    title="Corporate Address",
                    layout="two-column",
                    fields=[
                        field(key="address.line1", label="Address Line 1", type_value="text", order=1),
                        field(key="address.line2", label="Address Line 2", type_value="text", order=2),
                        field(
                            key="address.cityStateZip",
                            label="City / State / ZIP",
                            type_value="group",
                            width="full",
                            group="city_state_zip",
                            order=3,
                            help_text="Grouped fields rendered as one row in the UI.",
                        ),
                    ],
                ),
                SetupSectionDefinition(
                    id="statement_address",
                    title="Statement Address",
                    layout="two-column",
                    fields=[
                        field(key="statementAddress.line1", label="Address Line 1", type_value="text", order=1),
                        field(key="statementAddress.line2", label="Address Line 2", type_value="text", order=2),
                        field(
                            key="statementAddress.cityStateZip",
                            label="City / State / ZIP",
                            type_value="group",
                            width="full",
                            group="statement_city_state_zip",
                            order=3,
                        ),
                    ],
                ),
                SetupSectionDefinition(
                    id="contact_details",
                    title="Contact Details",
                    layout="two-column",
                    fields=[
                        field(key="contact.primaryPhone", label="Primary Phone", type_value="phone", order=1),
                        field(key="contact.secondaryPhone", label="Secondary Phone", type_value="phone", order=2),
                        field(key="contact.website", label="Website", type_value="text", order=3),
                        field(key="contact.supportEmail", label="Support Email", type_value="email", order=4),
                    ],
                ),
                SetupSectionDefinition(
                    id="custom_fields",
                    title="Custom Fields",
                    layout="single",
                    fields=[
                        field(
                            key="customFields.notes",
                            label="Notes",
                            type_value="textarea",
                            width="full",
                            placeholder="Internal notes",
                            order=1,
                        ),
                    ],
                )
            ],
        ),
        SetupTabDefinition(
            id="advanced",
            label="ADVANCED",
            type="form",
            sections=[
                SetupSectionDefinition(
                    id="ledger_colors",
                    title="Ledger Colors",
                    layout="two-column",
                    fields=[
                        field(
                            key="advancedSettings.ledgerColors.current",
                            label="Current",
                            type_value="select",
                            options=LEDGER_COLORS,
                            order=1,
                        ),
                        field(
                            key="advancedSettings.ledgerColors.overdue30",
                            label="30+ Days Overdue",
                            type_value="select",
                            options=LEDGER_COLORS,
                            order=2,
                        ),
                    ],
                ),
                SetupSectionDefinition(
                    id="options",
                    title="Options",
                    layout="two-column",
                    fields=[
                        field(key="enableFullScreen", label="Enable Full Screen", type_value="checkbox", order=1),
                        field(key="advancedSettings.autoApplyFinanceCharges", label="Auto Apply Finance Charges", type_value="checkbox", order=2),
                        field(key="advancedSettings.showLedgerAlerts", label="Show Ledger Alerts", type_value="checkbox", order=3),
                        field(
                            key="maxTreatmentPlanDiscount",
                            label="Maximum Treatment Plan Discount (%)",
                            type_value="number",
                            validation={"min": 0, "max": 100},
                            order=4,
                        ),
                    ],
                ),
                SetupSectionDefinition(
                    id="default_settings",
                    title="Default Settings",
                    layout="two-column",
                    fields=[
                        field(key="advancedSettings.chartingStyle", label="Charting Style", type_value="select", options=[{"value": "ada", "label": "ADA"}, {"value": "universal", "label": "Universal"}], order=1),
                        field(key="advancedSettings.defaultFinanceCode", label="Default Finance Code", type_value="select", options=[{"value": "FIN001", "label": "FIN001"}, {"value": "FIN002", "label": "FIN002"}], order=2),
                    ],
                ),
                SetupSectionDefinition(
                    id="required_fields",
                    title="Required Fields",
                    layout="two-column",
                    fields=[
                        field(key="advancedSettings.requiredFields.insuranceId", label="Insurance ID", type_value="checkbox", order=1),
                        field(key="advancedSettings.requiredFields.ssn", label="SSN", type_value="checkbox", order=2),
                        field(key="advancedSettings.requiredFields.dob", label="Date of Birth", type_value="checkbox", order=3),
                    ],
                ),
                SetupSectionDefinition(
                    id="third_party_settings",
                    title="Third Party Settings",
                    layout="two-column",
                    fields=[
                        field(key="advancedSettings.thirdParty.vendor", label="Vendor", type_value="select", options=[{"value": "none", "label": "None"}, {"value": "stripe", "label": "Stripe"}, {"value": "waystar", "label": "Waystar"}], order=1),
                        field(key="advancedSettings.thirdParty.enabled", label="Enabled", type_value="checkbox", order=2),
                    ],
                ),
                SetupSectionDefinition(
                    id="payment_portal",
                    title="Payment Portal",
                    layout="two-column",
                    fields=[
                        field(key="advancedSettings.paymentPortal.provider", label="Provider", type_value="select", options=[{"value": "stripe", "label": "Stripe"}, {"value": "square", "label": "Square"}], order=1),
                        field(key="advancedSettings.paymentPortal.enableGuestCheckout", label="Enable Guest Checkout", type_value="checkbox", order=2),
                    ],
                ),
                SetupSectionDefinition(
                    id="api_client_credentials",
                    title="API / Client Credentials",
                    layout="two-column",
                    fields=[
                        field(key="advancedSettings.apiCredentials.clientId", label="Client ID", type_value="text", order=1),
                        field(key="advancedSettings.apiCredentials.clientSecret", label="Client Secret", type_value="password", help_text="Masked in UI", order=2),
                    ],
                ),
            ],
        ),
        SetupTabDefinition(
            id="holidays",
            label="HOLIDAYS",
            type="table",
            sections=[],
            features={"selectable": True, "bulkDelete": True, "dateFilter": True},
            columns=[
                {"key": "date", "label": "Date", "type": "date"},
                {"key": "holidayName", "label": "Holiday Name", "type": "text"},
                {"key": "status", "label": "Status", "type": "badge"},
                {"key": "type", "label": "Type", "type": "text"},
                {"key": "actions", "label": "Actions", "type": "actions"},
            ],
            actions={"addHoliday": True, "addFederalHoliday": True, "deleteSelected": True},
        ),
        SetupTabDefinition(
            id="communications",
            label="COMMUNICATIONS",
            type="form",
            sections=[
                SetupSectionDefinition(
                    id="business_information",
                    title="Business Information",
                    layout="two-column",
                    fields=[
                        field(key="communications.businessInformation.country", label="Country", type_value="select", options=[{"value": "US", "label": "United States"}, {"value": "CA", "label": "Canada"}], order=1),
                        field(key="communications.businessInformation.entityType", label="Entity Type", type_value="select", options=[{"value": "llc", "label": "LLC"}, {"value": "corp", "label": "Corporation"}, {"value": "sole_prop", "label": "Sole Proprietorship"}], order=2),
                        field(key="communications.businessInformation.description", label="Description", type_value="textarea", width="full", order=3),
                    ],
                ),
                SetupSectionDefinition(
                    id="business_contact",
                    title="Business Contact",
                    layout="two-column",
                    fields=[
                        field(key="communications.businessContact.phone", label="Business Phone", type_value="phone", order=1),
                        field(key="communications.businessContact.supportEmail", label="Support Email", type_value="email", order=2),
                    ],
                ),
                SetupSectionDefinition(
                    id="phone_number_assignment",
                    title="Phone Number Assignment",
                    layout="single",
                    fields=[
                        field(key="communications.phoneNumberAssignment.officeIds", label="Assigned Offices", type_value="list_selector", width="full", order=1),
                    ],
                ),
                SetupSectionDefinition(
                    id="business_type",
                    title="Business Type",
                    layout="two-column",
                    fields=[
                        field(key="communications.businessType.primary", label="Primary Type", type_value="select", options=[{"value": "general", "label": "General Dentistry"}, {"value": "ortho", "label": "Orthodontics"}], order=1),
                    ],
                ),
            ],
        ),
        SetupTabDefinition(
            id="online_registration",
            label="ONLINE_REGISTRATION",
            type="mixed",
            actions={"preview": True, "exportPdf": True},
            sections=[
                SetupSectionDefinition(
                    id="consent_header",
                    title="Consent Header",
                    layout="single",
                    fields=[field(key="consent.header", label="Header", type_value="text", width="full", order=1)],
                ),
                SetupSectionDefinition(
                    id="consent_body",
                    title="Consent Body",
                    layout="single",
                    fields=[field(key="consent.body", label="Body", type_value="rich_text", width="full", order=1)],
                ),
                SetupSectionDefinition(
                    id="compliance_notes",
                    title="Compliance Notes",
                    layout="single",
                    fields=[field(key="consent.complianceNotes", label="Compliance Notes", type_value="readonly_block", width="full", read_only=True, order=1)],
                ),
            ],
        ),
    ]


def _editable_field_keys() -> Set[str]:
    return {
        "accountName",
        "email",
        "phone",
        "cultureCode",
        "enableFullScreen",
        "maxTreatmentPlanDiscount",
    }


def _valid_field_keys() -> Set[str]:
    return _editable_field_keys() | {"accountNumber"}


def _readonly_field_keys() -> Set[str]:
    return {"accountNumber"}


def _build_values(record: AccountSetup) -> Dict[str, Any]:
    return {
        "accountNumber": record.account_number,
        "accountName": record.account_name,
        "email": record.email,
        "phone": "",
        "logoUrl": "",
        "cultureCode": record.culture_code,
        "enableFullScreen": record.enable_full_screen,
        "maxTreatmentPlanDiscount": record.max_treatment_plan_discount,
        "address": {
            "line1": "",
            "line2": "",
            "city": "",
            "state": "",
            "zip": "",
            "statementLine1": "",
            "statementLine2": "",
            "statementCity": "",
            "statementState": "",
            "statementZip": "",
        },
        "holidays": [],
        "advancedSettings": {
            "ledgerColors": {"current": "green", "overdue30": "yellow"},
            "autoApplyFinanceCharges": False,
            "showLedgerAlerts": True,
            "chartingStyle": "ada",
            "defaultFinanceCode": "FIN001",
            "requiredFields": {"insuranceId": True, "ssn": False, "dob": True},
            "thirdParty": {"vendor": "none", "enabled": False},
            "paymentPortal": {"provider": "stripe", "enableGuestCheckout": True},
            "apiCredentials": {"clientId": "", "clientSecret": ""},
        },
        "communications": {
            "businessInformation": {"country": "US", "entityType": "llc", "description": ""},
            "businessContact": {"phone": "", "supportEmail": record.email},
            "phoneNumberAssignment": {"officeIds": []},
            "businessType": {"primary": "general"},
        },
        "consent": {
            "header": "Patient Consent Form",
            "body": "I hereby authorize treatment and acknowledge privacy practices.",
            "complianceNotes": "This block is compliance-controlled and read only.",
        },
    }


def _build_permissions(current_user: User) -> Dict[str, bool]:
    can_edit = current_user.is_platform_user or current_user.role == "super_admin" or any(
        user_has_permission(current_user, perm) for perm in ACCOUNT_SETUP_EDIT_PERMISSIONS
    )
    return {
        "canEdit": bool(can_edit),
        "canDelete": bool(can_edit),
        "canUpload": bool(can_edit),
    }


def _build_api_mapping(record: AccountSetup) -> Dict[str, Any]:
    return {
        "get": f"/account/{record.account_id}",
        "update": f"/account/{record.account_id}",
        "uploadLogo": "/account/logo/upload",
        "holidays": {
            "add": "/holidays",
            "delete": "/holidays/{id}",
            "list": "/holidays",
        },
    }


def _extract_updatable_values(payload_values: Dict[str, Any]) -> Dict[str, Any]:
    # Supports both flat payloads and nested values from dynamic forms.
    if any(k in _valid_field_keys() for k in payload_values.keys()):
        return payload_values

    extracted: Dict[str, Any] = {}
    for key in ("accountName", "email", "phone", "cultureCode", "enableFullScreen", "maxTreatmentPlanDiscount"):
        if key in payload_values:
            extracted[key] = payload_values[key]
    return extracted


def _validate_update_values(payload_values: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload_values, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed payload: values must be an object")

    candidate_values = _extract_updatable_values(payload_values)
    keys = set(candidate_values.keys())
    unknown = sorted(keys - _valid_field_keys())
    if unknown:
        _raise_422("Unknown field keys", {"unknownFields": unknown})

    sanitized: Dict[str, Any] = {}
    for key, value in candidate_values.items():
        if key in _readonly_field_keys():
            continue
        if key not in _editable_field_keys():
            continue

        if key == "accountName":
            if not isinstance(value, str):
                _raise_422("Type mismatch", {"field": key, "expected": "string"})
            stripped = value.strip()
            if not stripped:
                _raise_422("Validation failed", {"field": key, "message": "Account name is required"})
            if len(stripped) > 150:
                _raise_422("Validation failed", {"field": key, "message": "Maximum length is 150"})
            sanitized[key] = stripped
            continue

        if key == "email":
            if not isinstance(value, str):
                _raise_422("Type mismatch", {"field": key, "expected": "string"})
            stripped = value.strip()
            if not stripped or not re.match(EMAIL_PATTERN, stripped):
                _raise_422("Validation failed", {"field": key, "message": "Please provide a valid email address."})
            sanitized[key] = stripped
            continue

        if key == "phone":
            if not isinstance(value, str):
                _raise_422("Type mismatch", {"field": key, "expected": "string"})
            sanitized[key] = value.strip()
            continue

        if key == "cultureCode":
            if not isinstance(value, str):
                _raise_422("Type mismatch", {"field": key, "expected": "string"})
            valid_values = {item["value"] for item in VALID_CULTURES}
            if value not in valid_values:
                _raise_422("Validation failed", {"field": key, "allowedValues": sorted(valid_values)})
            sanitized[key] = value
            continue

        if key == "enableFullScreen":
            if not isinstance(value, bool):
                _raise_422("Type mismatch", {"field": key, "expected": "boolean"})
            sanitized[key] = value
            continue

        if key == "maxTreatmentPlanDiscount":
            if isinstance(value, bool) or not isinstance(value, int):
                _raise_422("Type mismatch", {"field": key, "expected": "integer"})
            if value < 0 or value > 100:
                _raise_422("Validation failed", {"field": key, "message": "Value must be between 0 and 100"})
            sanitized[key] = value

    return sanitized
    #                     ),
    #                 ],
    #             )
    #         ],
    #     ),
    # ]


def _build_metadata(record: AccountSetup) -> List[SetupMetadataItem]:
    return [
        SetupMetadataItem(key="pgid", label="PGID", value=record.pgid or ""),
        SetupMetadataItem(key="oid", label="OID", value=record.oid or ""),
        SetupMetadataItem(key="updatedAt", label="Modified On", value=as_ui_datetime(record.updated_at)),
        SetupMetadataItem(key="updatedBy", label="Modified By", value=record.updated_by_email or ""),
    ]


def _default_account_id(tenant_id: int) -> str:
    return f"acc-{tenant_id:03d}"


def _default_account_number(tenant_id: int) -> str:
    return f"{100000 + tenant_id}"


def _resolve_tenant_and_oid(db: Session, tenant_id: int) -> tuple[Tenant, Optional[str]]:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    office = (
        db.query(Office)
        .filter(Office.tenant_id == tenant_id, Office.is_active.is_(True))
        .order_by(Office.id.asc())
        .first()
    )
    return tenant, (office.office_code if office else None)


def get_or_create_account_setup_record(db: Session, tenant_id: int, current_user: User) -> AccountSetup:
    record = db.query(AccountSetup).filter(AccountSetup.tenant_id == tenant_id).first()
    if record:
        return record

    tenant, oid = _resolve_tenant_and_oid(db, tenant_id)
    record = AccountSetup(
        tenant_id=tenant_id,
        account_id=_default_account_id(tenant_id),
        account_number=_default_account_number(tenant_id),
        account_name=tenant.name,
        email=current_user.email,
        culture_code="en-US",
        enable_full_screen=False,
        max_treatment_plan_discount=0,
        pgid=tenant.code,
        oid=oid,
        updated_by_user_id=current_user.id,
        updated_by_email=current_user.email,
        lock_version=1,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_account_setup_config(
    db: Session,
    current_user: User,
    account_id: Optional[str] = None,
) -> AccountSetupConfigResponse:
    ensure_can_read_setup(current_user)
    record = get_or_create_account_setup_record(db, current_user.tenant_id, current_user)
    if account_id and record.account_id != account_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    return AccountSetupConfigResponse(
        accountId=record.account_id,
        title="Account Setup",
        subtitle="Manage account configuration and settings",
        actions=SetupUiActions(edit="Edit", save="Save", cancel="Cancel"),
        metadata=_build_metadata(record),
        tabs=_build_tabs(),
        values=_build_values(record),
        permissions=_build_permissions(current_user),
        api=_build_api_mapping(record),
    )


def get_account_setup_metadata(
    db: Session,
    current_user: User,
    account_id: Optional[str] = None,
) -> AccountSetupMetadataResponse:
    ensure_can_read_setup(current_user)
    record = get_or_create_account_setup_record(db, current_user.tenant_id, current_user)
    if account_id and record.account_id != account_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return AccountSetupMetadataResponse(metadata=_build_metadata(record))


def _raise_422(message: str, details: Dict[str, Any]) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error": {"code": "BUSINESS_RULE_VIOLATION", "message": message, "details": details}},
    )


def _validate_update_values(payload_values: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload_values, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed payload: values must be an object")

    keys = set(payload_values.keys())
    unknown = sorted(keys - _valid_field_keys())
    if unknown:
        _raise_422("Unknown field keys", {"unknownFields": unknown})

    sanitized: Dict[str, Any] = {}
    for key, value in payload_values.items():
        if key in _readonly_field_keys():
            continue

        if key == "accountName":
            if not isinstance(value, str):
                _raise_422("Type mismatch", {"field": key, "expected": "string"})
            stripped = value.strip()
            if not stripped:
                _raise_422("Validation failed", {"field": key, "message": "Account name is required"})
            if len(stripped) > 150:
                _raise_422("Validation failed", {"field": key, "message": "Maximum length is 150"})
            sanitized[key] = stripped
            continue

        if key == "email":
            if not isinstance(value, str):
                _raise_422("Type mismatch", {"field": key, "expected": "string"})
            stripped = value.strip()
            if not stripped or not re.match(EMAIL_PATTERN, stripped):
                _raise_422("Validation failed", {"field": key, "message": "Please provide a valid email address."})
            sanitized[key] = stripped
            continue

        if key == "cultureCode":
            if not isinstance(value, str):
                _raise_422("Type mismatch", {"field": key, "expected": "string"})
            valid_values = {item["value"] for item in VALID_CULTURES}
            if value not in valid_values:
                _raise_422("Validation failed", {"field": key, "allowedValues": sorted(valid_values)})
            sanitized[key] = value
            continue

        if key == "enableFullScreen":
            if not isinstance(value, bool):
                _raise_422("Type mismatch", {"field": key, "expected": "boolean"})
            sanitized[key] = value
            continue

        if key == "maxTreatmentPlanDiscount":
            if isinstance(value, bool) or not isinstance(value, int):
                _raise_422("Type mismatch", {"field": key, "expected": "integer"})
            if value < 0 or value > 100:
                _raise_422("Validation failed", {"field": key, "message": "Value must be between 0 and 100"})
            sanitized[key] = value

    return sanitized


def update_account_setup(
    db: Session,
    current_user: User,
    payload_values: Dict[str, Any],
) -> AccountSetupUpdateResponse:
    ensure_can_edit_setup(current_user)
    record = get_or_create_account_setup_record(db, current_user.tenant_id, current_user)
    sanitized = _validate_update_values(payload_values)

    if "accountName" in sanitized:
        record.account_name = sanitized["accountName"]
    if "email" in sanitized:
        record.email = sanitized["email"]
    if "cultureCode" in sanitized:
        record.culture_code = sanitized["cultureCode"]
    if "enableFullScreen" in sanitized:
        record.enable_full_screen = sanitized["enableFullScreen"]
    if "maxTreatmentPlanDiscount" in sanitized:
        record.max_treatment_plan_discount = sanitized["maxTreatmentPlanDiscount"]

    record.updated_by_user_id = current_user.id
    record.updated_by_email = current_user.email
    record.lock_version = int(record.lock_version or 0) + 1

    db.add(record)
    db.commit()
    db.refresh(record)

    updated_values = _build_values(record)
    # Return only writable keys in update response values, contract-style.
    response_values = {k: v for k, v in updated_values.items() if k != "accountNumber"}

    return AccountSetupUpdateResponse(
        accountId=record.account_id,
        values=response_values,
        metadata=[
            SetupMetadataItem(key="updatedAt", label="Modified On", value=as_ui_datetime(record.updated_at)),
            SetupMetadataItem(key="updatedBy", label="Modified By", value=record.updated_by_email or ""),
        ],
    )
