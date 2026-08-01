"""Custom schemas for per-patient catalog answers.

`PatientMedicalAlert` needs its ``response`` constrained to the legacy tri-state
(LEG-2): ``yes|no|unknown``. A *missing row* still means "not asked"; an explicit
``unknown`` is available when the row exists but the answer is genuinely unknown.
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


class PatientMedicalAlertUpdate(BaseModel):
    alert_code: Optional[str] = None
    alert_label: Optional[str] = None
    response: Optional[AlertResponse] = None
    comments: Optional[str] = None
    is_active: Optional[bool] = None


class PatientMedicalAlertRead(ORMModel):
    id: int
    tenant_id: int
    patient_id: int
    alert_code: str
    alert_label: Optional[str] = None
    response: Optional[str] = None
    comments: Optional[str] = None
    is_active: bool
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
