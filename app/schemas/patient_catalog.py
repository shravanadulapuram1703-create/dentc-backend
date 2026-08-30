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

from pydantic import BaseModel

from app.schemas.common import ORMModel

AlertResponse = Literal["yes", "no", "unknown"]


class PatientMedicalAlertCreate(BaseModel):
    patient_id: int
    alert_code: str
    alert_label: Optional[str] = None
    response: Optional[AlertResponse] = None
    comments: Optional[str] = None
    is_active: Optional[bool] = None
    #: MH-12: store a contradiction deliberately instead of 422ing on it.
    allow_contradictions: bool = False


class PatientMedicalAlertUpdate(BaseModel):
    alert_code: Optional[str] = None
    alert_label: Optional[str] = None
    response: Optional[AlertResponse] = None
    comments: Optional[str] = None
    is_active: Optional[bool] = None
    allow_contradictions: bool = False


class PatientMedicalAlertRead(ORMModel):
    id: int
    tenant_id: int
    patient_id: int
    alert_code: str
    alert_label: Optional[str] = None
    response: Optional[str] = None
    comments: Optional[str] = None
    answered_at: Optional[datetime] = None
    is_active: bool
    # Denormalised from the catalog by ``enrich_medical_alerts`` (MH-14).
    section: Optional[str] = None
    is_flash_alert: bool = False
    blocks_charges: bool = False
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class PatientQuestionnaireResponseCreate(BaseModel):
    patient_id: int
    questionnaire_type: str
    question_code: str
    question_text: Optional[str] = None
    answer: Optional[str] = None
    is_active: Optional[bool] = None


class PatientQuestionnaireResponseUpdate(BaseModel):
    questionnaire_type: Optional[str] = None
    question_code: Optional[str] = None
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
    answered_at: Optional[datetime] = None
    is_active: bool
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
