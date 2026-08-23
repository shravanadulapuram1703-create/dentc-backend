"""Patients-module supplemental DTOs (documents, claim detail, duplicate check)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.db.models import (
    ClaimAttachment,
    InsuranceClaim,
    LedgerInsuranceDetail,
    PatientConsent,
    PatientDocument,
    PatientProcedure,
    PaymentAllocation,
)
from app.schemas.factory import build_schemas

PatientDocumentRead = build_schemas(PatientDocument, "PatientDocument", read_exclude=("file_path",))[2]
ClaimAttachmentRead = build_schemas(ClaimAttachment, "ClaimAttachment", read_exclude=("file_path",))[2]
# LTR-10: the sign response. Named distinctly so it does not collide with the
# generic CRUD ``PatientConsentRead`` component.
PatientConsentSignedRead = build_schemas(PatientConsent, "PatientConsentSigned")[2]

# Composed claim-detail sub-shapes (distinct names to avoid CRUD component clashes).
_ClaimDetailClaimRead = build_schemas(InsuranceClaim, "ClaimDetailClaim")[2]
_ClaimDetailProcedureRead = build_schemas(PatientProcedure, "ClaimDetailProcedure")[2]
_ClaimDetailPaymentRead = build_schemas(PaymentAllocation, "ClaimDetailPayment")[2]
_ClaimDetailCoverageRead = build_schemas(LedgerInsuranceDetail, "ClaimDetailCoverage")[2]


class ClaimDetailResponse(BaseModel):
    claim: _ClaimDetailClaimRead  # type: ignore[valid-type]
    procedures: list[_ClaimDetailProcedureRead]  # type: ignore[valid-type]
    payments: list[_ClaimDetailPaymentRead]  # type: ignore[valid-type]
    coverage: list[_ClaimDetailCoverageRead]  # type: ignore[valid-type]


class ClaimStatusUpdate(BaseModel):
    status: str = Field(..., examples=["submitted", "paid", "denied", "closed"])


class DuplicateCheckRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    dob: date | None = None
    ssn: str | None = None
    chart_no: str | None = None
    # KAN-108: Quick Save collects contact details, so they have to be matchable.
    phone: str | None = None
    email: str | None = None


class DuplicateCandidate(BaseModel):
    id: int
    chart_no: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    dob: date | None = None
    is_active: bool
    match_score: int = Field(..., description="0-100 heuristic confidence")
    # BUG-1: the columns a user needs to tell candidates apart (were blank in the UI).
    email: str | None = None
    phone: str | None = None
    home_office_short_id: str | None = None
    preferred_provider_name: str | None = None
    # KAN-108: which fields actually lined up, and whether that is confident
    # enough that POST /patients/register will refuse without force_create.
    match_on: list[str] = Field(default_factory=list)
    is_strong: bool = False


class DuplicateCheckResponse(BaseModel):
    candidates: list[DuplicateCandidate]


class DocumentResult(BaseModel):
    id: int
    file_url: str


class UploadLimits(BaseModel):
    """NOTE-DOC-5: the server-enforced upload rules, published so the UI states
    the same numbers it is validated against instead of hardcoding its own."""

    max_bytes: int
    max_megabytes: float
    allowed_content_types: list[str]
    allowed_extensions: list[str]
    # The accepted ``context`` values on POST /patient-documents. Each maps to a
    # folder in the storage bucket, so an unlisted value is rejected rather than
    # silently filed under the default.
    allowed_contexts: list[str]
