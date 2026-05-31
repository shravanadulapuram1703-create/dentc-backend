from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SetupFieldType = Literal[
    "text",
    "email",
    "tel",
    "phone",
    "number",
    "select",
    "checkbox",
    "password",
    "textarea",
    "date",
    "file_upload",
    "group",
    "rich_text",
    "badge",
    "actions",
    "list_selector",
    "readonly_block",
]


class SetupOption(BaseModel):
    value: str
    label: str


class SetupFieldValidation(BaseModel):
    required: Optional[bool] = None
    min: Optional[float] = None
    max: Optional[float] = None
    minLength: Optional[int] = None
    maxLength: Optional[int] = None
    pattern: Optional[str] = None
    message: Optional[str] = None


class SetupFieldUi(BaseModel):
    width: Literal["full", "half", "third"] = "full"
    group: Optional[str] = None
    order: int = 0


class SetupFieldDefinition(BaseModel):
    key: str
    label: str
    type: SetupFieldType
    placeholder: Optional[str] = None
    helpText: Optional[str] = None
    readOnly: Optional[bool] = None
    hidden: Optional[bool] = None
    options: Optional[List[SetupOption]] = None
    validation: Optional[SetupFieldValidation] = None
    ui: SetupFieldUi


class SetupSectionDefinition(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    layout: Optional[Literal["single", "two-column", "three-column"]] = None
    fields: List[SetupFieldDefinition]


class SetupTabDefinition(BaseModel):
    id: str
    label: str
    type: Literal["form", "table", "mixed"] = "form"
    sections: List[SetupSectionDefinition]
    features: Optional[Dict[str, Any]] = None
    columns: Optional[List[Dict[str, Any]]] = None
    actions: Optional[Dict[str, Any]] = None


class SetupMetadataItem(BaseModel):
    key: str
    label: str
    value: str


class SetupUiActions(BaseModel):
    edit: str
    save: str
    cancel: str


class AccountSetupConfigResponse(BaseModel):
    accountId: str
    title: str
    subtitle: Optional[str] = None
    actions: SetupUiActions
    metadata: List[SetupMetadataItem]
    tabs: List[SetupTabDefinition]
    values: Dict[str, Any]
    permissions: Dict[str, bool]
    api: Dict[str, Any]


class AccountSetupUpdateRequest(BaseModel):
    values: Dict[str, Any] = Field(default_factory=dict)


class AccountSetupUpdateResponse(BaseModel):
    accountId: str
    values: Dict[str, Any]
    metadata: List[SetupMetadataItem]


class AccountSetupMetadataResponse(BaseModel):
    metadata: List[SetupMetadataItem]


def as_ui_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")
