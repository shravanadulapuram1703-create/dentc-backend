"""Letters module DTOs (render / batch / letter-context / consent signing)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.core.datetimes import UtcDatetime
from app.db.models import (
    Appointment,
    LetterBatchItem,
    LetterBatchRun,
    Office,
    Provider,
    Referral,
    ResponsibleParty,
    TreatmentPlan,
)
from app.schemas.common import ORMModel
from app.schemas.factory import build_schemas
from app.schemas.patient import PatientRead

# Distinctly-named sub-shapes so they don't clash with the CRUD components.
_LetterOfficeRead = build_schemas(Office, "LetterContextOffice")[2]
_LetterProviderRead = build_schemas(Provider, "LetterContextProvider")[2]
_LetterRpRead = build_schemas(ResponsibleParty, "LetterContextResponsibleParty")[2]
_LetterReferralRead = build_schemas(Referral, "LetterContextReferral")[2]
_LetterAppointmentRead = build_schemas(Appointment, "LetterContextAppointment")[2]
_LetterPlanRead = build_schemas(TreatmentPlan, "LetterContextTreatmentPlan")[2]

LetterBatchRunRead = build_schemas(LetterBatchRun, "LetterBatchRun")[2]
LetterBatchItemRead = build_schemas(LetterBatchItem, "LetterBatchItem")[2]


class MergeFieldRead(BaseModel):
    """One entry of the authoritative 56-token merge catalog (LTR-5)."""

    token: str = Field(..., examples=["PAT_FIRST_NAME"])
    placeholder: str = Field(..., examples=["#PAT_FIRST_NAME#"])
    group: str = Field(..., examples=["patient"])
    label: str = Field(..., examples=["First name"])
    requires_balance: bool = Field(
        False, description="Resolving this token runs the (slow) balance aggregate"
    )
    requires_treatment_plan: bool = Field(
        False, description="Only resolves when the letter is launched from a treatment plan"
    )


class MergeFieldCatalog(BaseModel):
    fields: list[MergeFieldRead]


class LetterRenderRequest(BaseModel):
    template_id: int
    patient_id: int
    office_id: int | None = Field(
        None, description="Printing office. Defaults to the patient's home office."
    )
    treatment_plan_id: str | None = Field(
        None,
        description="Binds #TX_PLAN_TH_NUMBER# (LTR-4). Without it the token prints blank.",
    )


class LetterRenderResponse(BaseModel):
    template_id: int
    patient_id: int
    title: str
    letter_type: str | None = None
    rendered_html: str
    unresolved_tokens: list[str] = Field(
        default_factory=list,
        description="Catalog tokens the template used that resolved to nothing (printed blank)",
    )
    merge_fields: dict[str, str] = Field(
        default_factory=dict, description="Resolved value of every token this template uses"
    )
    unknown_tokens: list[str] = Field(
        default_factory=list,
        description="#TOKEN#s in the body that are not in the merge catalog at all",
    )


class LetterBatchRequest(BaseModel):
    template_id: int
    patient_ids: list[int] = Field(..., min_length=1)
    office_id: int | None = None
    store_html: bool = Field(
        False,
        description="Retain each rendered body on the run (off by default — a batch "
                    "is normally consumed as one print stream)",
    )


class LetterBatchResponse(BaseModel):
    batch: LetterBatchRunRead  # type: ignore[valid-type]
    items: list[LetterBatchItemRead]  # type: ignore[valid-type]


class LetterContextResponse(ORMModel):
    """LTR-6: the whole merge context in one call (was 2–6 round trips)."""

    patient: PatientRead
    office: _LetterOfficeRead | None = None  # type: ignore[valid-type]
    provider: _LetterProviderRead | None = None  # type: ignore[valid-type]
    responsible_party: _LetterRpRead | None = None  # type: ignore[valid-type]
    referred_by: _LetterReferralRead | None = None  # type: ignore[valid-type]
    next_appointment: _LetterAppointmentRead | None = None  # type: ignore[valid-type]
    next_appointment_provider: _LetterProviderRead | None = None  # type: ignore[valid-type]
    last_appointment: _LetterAppointmentRead | None = None  # type: ignore[valid-type]
    treatment_plan: _LetterPlanRead | None = None  # type: ignore[valid-type]
    treatment_plan_teeth: list[str] = Field(default_factory=list)
    balance: dict[str, Any] | None = Field(
        None, description="Only present when include_balance=true (the slow aggregate)"
    )
    today: date
    merge_fields: dict[str, str] = Field(
        default_factory=dict, description="Every catalog token resolved for this patient"
    )
    unresolved_tokens: list[str] = Field(
        default_factory=list, description="Catalog tokens with no value in this context"
    )


class ConsentSignRequest(BaseModel):
    """LTR-10: capture a signature against an existing consent row."""

    signature_data: str | None = Field(
        None, description="Base64 / data-URL image of a drawn signature"
    )
    document_id: int | None = Field(
        None, description="An uploaded patient-document holding the scanned wet-signed copy"
    )
    status: str = Field("signed", examples=["signed", "declined", "voided"])
    signature_method: str | None = Field(None, examples=["drawn", "scanned", "verbal"])
    signer_name: str | None = None
    signer_relationship: str | None = Field(None, examples=["self", "guardian"])
    declined_reason: str | None = None


class ConsentFormMaster(BaseModel):
    """A blank consent master already sitting in the storage bucket (LTR-1 #4)."""

    name: str
    storage_bucket: str
    storage_path: str
    content_type: str | None = None
    size: int | None = None
    updated_at: UtcDatetime | None = None
    url: str | None = Field(None, description="Signed URL, when signing is available")


class ConsentFormList(BaseModel):
    items: list[ConsentFormMaster]
    storage_bucket: str | None = None
    storage_prefix: str | None = None
    is_configured: bool = Field(
        ..., description="False when no document bucket is configured (dev): items is empty"
    )
