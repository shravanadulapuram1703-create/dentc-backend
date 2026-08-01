"""Patients-module supplemental DTOs (documents, claim detail, duplicate check)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.db.models import (
    ClaimAttachment,
    InsuranceClaim,
    LedgerInsuranceDetail,
    PatientDocument,
    PatientProcedure,
    PaymentAllocation,
)
from app.schemas.factory import build_schemas

PatientDocumentRead = build_schemas(PatientDocument, "PatientDocument", read_exclude=("file_path",))[2]
ClaimAttachmentRead = build_schemas(ClaimAttachment, "ClaimAttachment", read_exclude=("file_path",))[2]

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
    home_office_short_id: str | None = None
    preferred_provider_name: str | None = None


class DuplicateCheckResponse(BaseModel):
    candidates: list[DuplicateCandidate]


class DocumentResult(BaseModel):
    id: int
    file_url: str
