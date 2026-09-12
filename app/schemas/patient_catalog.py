"""Custom schemas for per-patient catalog answers.

`PatientMedicalAlert` needs its ``response`` constrained to the legacy tri-state
(LEG-2): ``yes|no|unknown``. A *missing row* still means "not asked"; an explicit
``unknown`` is available when the row exists but the answer is genuinely unknown.
MH-5 publishes that distinction at ``GET /metadata/medical-history-rules`` and
the API never collapses one into the other.

MH-8: both reads carry ``updated_by`` (+ the resolved name) so the legacy
screen's "Modified By" stops rendering blank, and ``answered_at`` — when the
answer was actually given, which a row's ``updated_at`` is not.

MH-14: the alert read denormalises the Setup catalog's ``is_flash_alert`` /
``blocks_charges`` onto the patient's answered row, so a scheduler popover or a
charge gate can act on a Yes answer without re-reading ``/definitions`` per row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.core.datetimes import UtcDatetime

AlertResponse = Literal["yes", "no", "unknown"]

#: GAP-AP-20: the column widths, carried onto every write schema so an
#: over-long derived code is a 422 that names the field, never a 500 that rolls
#: back the whole registration. Published at ``/metadata/medical-history-rules``
#: so the frontend's ``CATALOG_CODE_MAX_LENGTH`` is one number read from here.
CATALOG_CODE_MAX_LENGTH = 100
ALERT_LABEL_MAX_LENGTH = 255
SECTION_MAX_LENGTH = 100
QUESTIONNAIRE_TYPE_MAX_LENGTH = 20


class PatientMedicalAlertCreate(BaseModel):
    patient_id: int
    alert_code: str = Field(..., max_length=CATALOG_CODE_MAX_LENGTH)
    #: MA-3: optional overrides — filled from the MEDALERT catalog when omitted.
    alert_label: Optional[str] = Field(None, max_length=ALERT_LABEL_MAX_LENGTH)
    section: Optional[str] = Field(None, max_length=SECTION_MAX_LENGTH)
    response: Optional[AlertResponse] = None
    comments: Optional[str] = None
    #: MA-4: per-answer overrides of the Setup catalog's flags (omit to derive).
    is_flash_alert: Optional[bool] = None
    blocks_charges: Optional[bool] = None
    is_active: Optional[bool] = None
    #: MH-12: store a contradiction deliberately instead of 422ing on it.
    allow_contradictions: bool = False


class PatientMedicalAlertUpdate(BaseModel):
    alert_code: Optional[str] = Field(None, max_length=CATALOG_CODE_MAX_LENGTH)
    alert_label: Optional[str] = Field(None, max_length=ALERT_LABEL_MAX_LENGTH)
    section: Optional[str] = Field(None, max_length=SECTION_MAX_LENGTH)
    response: Optional[AlertResponse] = None
    comments: Optional[str] = None
    is_flash_alert: Optional[bool] = None
    blocks_charges: Optional[bool] = None
    is_active: Optional[bool] = None
    allow_contradictions: bool = False


# ── GAP-AP-22: bulk upsert (one transaction, one patient) ────────────────────
class MedicalAlertBulkItem(BaseModel):
    """One alert answer in a bulk write. Keyed by ``alert_code``: an active row
    for the code is updated in place, otherwise one is inserted."""

    alert_code: str = Field(..., max_length=CATALOG_CODE_MAX_LENGTH)
    alert_label: Optional[str] = Field(None, max_length=ALERT_LABEL_MAX_LENGTH)
    section: Optional[str] = Field(None, max_length=SECTION_MAX_LENGTH)
    response: Optional[AlertResponse] = None
    comments: Optional[str] = None
    is_flash_alert: Optional[bool] = None
    blocks_charges: Optional[bool] = None


class MedicalAlertBulkRequest(BaseModel):
    patient_id: int
    items: list[MedicalAlertBulkItem] = Field(default_factory=list, max_length=500)
    #: MH-12: store a contradiction deliberately instead of 422ing on it.
    allow_contradictions: bool = False
    #: True = every stored code the payload omits is cleared (legacy "No to
    #: all" / a full re-save); False (default) = only the sent codes are touched.
    replace: bool = False


class QuestionnaireResponseBulkItem(BaseModel):
    questionnaire_type: str = Field(..., max_length=QUESTIONNAIRE_TYPE_MAX_LENGTH)
    question_code: str = Field(..., max_length=CATALOG_CODE_MAX_LENGTH)
    question_text: Optional[str] = None
    answer: Optional[str] = None


class QuestionnaireResponseBulkRequest(BaseModel):
    patient_id: int
    items: list[QuestionnaireResponseBulkItem] = Field(default_factory=list, max_length=500)
    #: True = every stored code of a questionnaire type *present in the payload*
    #: that the payload omits is cleared; a type absent from ``items`` is never touched.
    replace: bool = False


class BulkWriteSummary(BaseModel):
    patient_id: int
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0
    #: MH-12 contradictions that were stored because ``allow_contradictions`` was set.
    contradictions: list[dict] = Field(default_factory=list)


class PatientMedicalAlertRead(ORMModel):
    id: int
    tenant_id: int
    patient_id: int
    alert_code: str
    alert_label: Optional[str] = None
    response: Optional[str] = None
    comments: Optional[str] = None
    answered_at: Optional[UtcDatetime] = None
    is_active: bool
    # MA-3/MA-4: the *effective* values — the row's own override when set, else
    # the MEDALERT catalog's (resolved by ``enrich_medical_alerts``).
    section: Optional[str] = None
    is_flash_alert: bool = False
    blocks_charges: bool = False
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None
    created_at: UtcDatetime
    updated_at: Optional[UtcDatetime] = None


class PatientQuestionnaireResponseCreate(BaseModel):
    patient_id: int
    questionnaire_type: str = Field(..., max_length=QUESTIONNAIRE_TYPE_MAX_LENGTH)
    question_code: str = Field(..., max_length=CATALOG_CODE_MAX_LENGTH)
    question_text: Optional[str] = None
    answer: Optional[str] = None
    is_active: Optional[bool] = None


class PatientQuestionnaireResponseUpdate(BaseModel):
    questionnaire_type: Optional[str] = Field(None, max_length=QUESTIONNAIRE_TYPE_MAX_LENGTH)
    question_code: Optional[str] = Field(None, max_length=CATALOG_CODE_MAX_LENGTH)
    question_text: Optional[str] = None
    answer: Optional[str] = None
    is_active: Optional[bool] = None


class PatientQuestionnaireResponseRead(ORMModel):
    id: int
    tenant_id: int
    patient_id: int
    questionnaire_type: str
    question_code: str
    question_text: Optional[str] = None
    answer: Optional[str] = None
    answered_at: Optional[UtcDatetime] = None
    is_active: bool
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None
    created_at: UtcDatetime
    updated_at: Optional[UtcDatetime] = None


# GAP-AP-22: "array in, array out" — the written rows in payload order, plus counts.
class MedicalAlertBulkResponse(BulkWriteSummary):
    items: list[PatientMedicalAlertRead] = Field(default_factory=list)


class QuestionnaireResponseBulkResponse(BulkWriteSummary):
    items: list[PatientQuestionnaireResponseRead] = Field(default_factory=list)
