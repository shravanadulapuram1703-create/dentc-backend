"""Supporting-records readiness DTOs (PROC-7c / PROC-7d).

The checklist every procedure-entry screen and the claim fill-out renders from
one source: which records a code requires, which are on file, and the evidence
behind each answer.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class SupportingRecordRule(BaseModel):
    label: str
    stage: str = Field(
        description="post = judgeable before the charge exists; claim = only once posted")
    satisfied_when: str
    error_code: str


class ProcedureReadiness(BaseModel):
    patient_id: int
    procedure_code: str
    tooth: str | None = None
    date_of_service: date | None = None
    procedure_id: str | None = Field(None, description="Set when judging a posted charge")
    claim_id: str | None = None
    requires: list[str] = Field(
        default_factory=list,
        description="attachment | perio_chart | photo | xray | missing_tooth_info")
    satisfied: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    deferred: list[str] = Field(
        default_factory=list,
        description="Required but not judgeable yet (an attachment before the charge is posted)",
    )
    ready: bool = Field(description="True when nothing is missing (deferred does not count)")
    evidence: dict[str, Any] = Field(
        default_factory=dict, description="Per record key: what was found")
    rules: dict[str, SupportingRecordRule] = Field(default_factory=dict)


class ClaimMissingRecord(BaseModel):
    procedure_id: str
    procedure_code: str
    tooth: str | None = None
    date_of_service: date | None = None
    record: str
    code: str = Field(description="attachment_required | perio_chart_required | …")


class ClaimEnclosures(BaseModel):
    """PROC-7d: the ADA claim-form Enclosures box, derived from what is attached."""

    radiographs: int = 0
    oral_images: int = 0
    models: int = 0
    narratives: int = 0
    perio_charts: int = 0
    other: int = 0
    attachments_enclosed: bool = False
    required_attachment_types: list[str] = Field(
        default_factory=list, description="XRAY | PHOTO | PERIO | NARRATIVE")
    missing_attachment_types: list[str] = Field(default_factory=list)


class ClaimReadiness(BaseModel):
    claim_id: str
    claim_number: str
    patient_id: int
    status: str
    ready: bool
    enforced_on_submit: bool = Field(description="Whether POST …/submit 422s on missing records")
    procedures: list[ProcedureReadiness] = Field(default_factory=list)
    missing: list[ClaimMissingRecord] = Field(default_factory=list)
    enclosures: ClaimEnclosures
