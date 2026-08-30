"""Patient Medical History wire schemas (MH-2/3/4/5/6/7/8/12/16).

The document is deliberately one component: the screen owns four legacy tabs
whose rows are meaningless apart (a signature without the answers it signed is
the MH-6 bug), so read and write both address the whole thing.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

AlertResponse = Literal["yes", "no", "unknown"]
Scope = Literal["all", "alerts", "dental", "medical"]
QuestionnaireType = Literal["dental", "medical"]
CompletionScope = Literal["alerts", "dental", "medical"]


# ── reads ────────────────────────────────────────────────────────────────────
class MedicalHistoryCatalogItem(BaseModel):
    code: str
    label: Optional[str] = None
    section: Optional[str] = None
    #: ``key2`` — ``text``/``textarea``/``date``/``number``; null means Yes/No.
    input_kind: Optional[str] = None
    input_type: Optional[str] = None
    sort_order: Optional[int] = None
    # MH-14: the Setup flags, so an answered row can drive a flash alert / charge gate.
    is_flash_alert: bool = False
    blocks_charges: bool = False
    definition_id: Optional[int] = None
    group_code: Optional[str] = None


class MedicalAlertAnswer(BaseModel):
    id: int
    patient_id: int
    alert_code: str
    alert_label: Optional[str] = None
    section: Optional[str] = None
    response: Optional[str] = None
    comments: Optional[str] = None
    answered_at: Optional[datetime] = None
    is_active: bool = True
    is_flash_alert: bool = False
    blocks_charges: bool = False
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class QuestionnaireAnswer(BaseModel):
    id: int
    patient_id: int
    questionnaire_type: str
    question_code: str
    question_text: Optional[str] = None
    answer: Optional[str] = None
    answered_at: Optional[datetime] = None
    is_active: bool = True
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MedicalHistorySignature(BaseModel):
    id: int
    patient_id: int
    signature_type: Optional[str] = None
    signature_data: Optional[str] = None
    signature_len: Optional[int] = None
    device_source: Optional[str] = None
    is_user_sig: bool = False
    signed_at: Optional[datetime] = None
    signed_by_user_id: Optional[int] = None
    signed_by_name: Optional[str] = None
    #: MH-6: SHA-256 of the answers as signed. Null on migrated rows, which is
    #: why ``signature_status`` can be ``unverifiable``.
    content_hash: Optional[str] = None
    is_active: bool = True
    superseded_by_id: Optional[int] = None
    voided_at: Optional[datetime] = None
    voided_by: Optional[int] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MedicalHistoryVersion(BaseModel):
    id: int
    patient_id: int
    scope: Optional[str] = None
    content_hash: Optional[str] = None
    item_count: Optional[int] = None
    comments: Optional[str] = None
    signature_id: Optional[int] = None
    completed_at: Optional[datetime] = None
    completed_by: Optional[int] = None
    completed_by_name: Optional[str] = None
    source_patient_id: Optional[int] = None
    copied_at: Optional[datetime] = None
    is_archived: bool = False
    created_at: Optional[datetime] = None


class MedicalHistoryVersionAnswer(BaseModel):
    answer_type: Optional[str] = None
    question_code: str
    question_text: Optional[str] = None
    answer_code: Optional[str] = None
    answer_text: Optional[str] = None
    notes: Optional[str] = None
    section: Optional[str] = None


class MedicalHistoryVersionDetail(MedicalHistoryVersion):
    answers: list[MedicalHistoryVersionAnswer] = Field(default_factory=list)
    signature: Optional[MedicalHistorySignature] = None


class MedicalHistoryEmergencyContact(BaseModel):
    id: int
    patient_id: int
    name: str
    relationship: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_primary: bool = False
    is_active: bool = True


class MedicalHistoryPatient(BaseModel):
    id: int
    chart_no: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[date] = None
    gender: Optional[str] = None
    home_office_id: Optional[int] = None


class MedicalHistoryCompletion(BaseModel):
    last_completed_at: Optional[datetime] = None
    last_completed_by: Optional[int] = None
    last_completed_by_name: Optional[str] = None


class MedicalHistoryDocument(BaseModel):
    """MH-2: everything the screen needs, in one call."""

    patient_id: int
    patient: MedicalHistoryPatient
    #: MH-13: first-class Additional Comments (was an alert row keyed
    #: ``ADDITIONAL_COMMENTS``).
    comments: Optional[str] = None
    alerts: list[MedicalAlertAnswer] = Field(default_factory=list)
    dental_responses: list[QuestionnaireAnswer] = Field(default_factory=list)
    medical_responses: list[QuestionnaireAnswer] = Field(default_factory=list)
    #: MH-11: ``patient_emergency_contacts`` is authoritative; the questionnaire
    #: catalog no longer carries the block.
    emergency_contacts: list[MedicalHistoryEmergencyContact] = Field(default_factory=list)
    signatures: list[MedicalHistorySignature] = Field(default_factory=list)
    current_signature: Optional[MedicalHistorySignature] = None
    #: MH-6: ``signed`` (hash matches), ``stale`` (answers moved under the
    #: signature), ``unverifiable`` (a migrated signature with no hash) or
    #: ``unsigned``.
    signature_status: str = "unsigned"
    content_hash: Optional[str] = None
    versions: list[MedicalHistoryVersion] = Field(default_factory=list)
    #: MH-1: the resolved catalogs. ``catalog_sources`` says ``tenant`` when the
    #: tenant has a seeded catalog and ``builtin`` when the server is serving the
    #: legacy list because the tenant's is missing or below the size guard.
    catalogs: dict[str, list[MedicalHistoryCatalogItem]] = Field(default_factory=dict)
    catalog_sources: dict[str, str] = Field(default_factory=dict)
    completion: dict[str, MedicalHistoryCompletion] = Field(default_factory=dict)
    copied_from_patient_id: Optional[int] = None
    copied_at: Optional[datetime] = None
    copied_by_name: Optional[str] = None
    #: Set on writes: the codes this request actually changed, per section.
    changed: Optional[dict[str, list[str]]] = None
    #: MH-12: contradictions stored because ``allow_contradictions`` was set.
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    version_id: Optional[int] = None
    signature_id: Optional[int] = None


class MedicalHistoryChange(BaseModel):
    """MH-8: one entry of the append-only change log."""

    id: int
    patient_id: int
    entity_type: str
    entity_id: Optional[int] = None
    code: Optional[str] = None
    label: Optional[str] = None
    action: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    source_patient_id: Optional[int] = None
    changed_by: Optional[int] = None
    changed_by_name: Optional[str] = None
    changed_at: Optional[datetime] = None


# ── writes ───────────────────────────────────────────────────────────────────
class MedicalAlertIn(BaseModel):
    alert_code: str
    alert_label: Optional[str] = None
    #: Null/omitted with no comment resets the row to **Not Answered** (deleted).
    response: Optional[AlertResponse] = None
    comments: Optional[str] = None


class QuestionnaireAnswerIn(BaseModel):
    question_code: str
    question_text: Optional[str] = None
    #: Null/empty resets the row to Not Answered (deleted).
    answer: Optional[str] = None


class EmergencyContactIn(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    relationship: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_primary: Optional[bool] = None
    is_active: Optional[bool] = None


class MedicalHistorySaveRequest(BaseModel):
    """MH-3: the whole document in one transaction.

    Only the codes present are touched, so a partial save is safe. ``replace_*``
    opts into a true full-section replace, where every stored code the payload
    omits is reset to Not Answered — that is what legacy's **NO TO ALL ALERTS**
    followed by Save means, and it is now one request instead of ~90.
    """

    comments: Optional[str] = None
    alerts: Optional[list[MedicalAlertIn]] = None
    dental_responses: Optional[list[QuestionnaireAnswerIn]] = None
    medical_responses: Optional[list[QuestionnaireAnswerIn]] = None
    emergency_contacts: Optional[list[EmergencyContactIn]] = None
    replace_alerts: bool = False
    replace_dental: bool = False
    replace_medical: bool = False
    #: MH-16: assert that the patient reviewed and confirmed these tabs now.
    mark_completed: list[CompletionScope] = Field(default_factory=list)
    #: MH-12: store a contradiction instead of 422ing on it. Recorded in the log.
    allow_contradictions: bool = False


class MedicalHistoryCopyRequest(BaseModel):
    scope: Scope = "all"
    allow_contradictions: bool = False


class MedicalHistorySignRequest(BaseModel):
    signature_data: str
    device_source: Optional[str] = None
    is_user_sig: bool = False
    #: MH-6: who is attesting, if not the authenticated operator of the pad.
    signed_by_user_id: Optional[int] = None
    signature_type: str = "medical_history"
    scope: Scope = "all"


class SignatureVoidRequest(BaseModel):
    reason: Optional[str] = None


class MedicalHistoryRules(BaseModel):
    """MH-5/MH-12: the published answer vocabulary and contradiction rules."""

    response_values: list[str]
    not_answered_is: str
    response_semantics: dict[str, str]
    reset_to_not_answered: str
    exclusions: list[dict[str, Any]]
    override: dict[str, Any]
    code_convention: dict[str, Any]
    emergency_contact_authority: str
