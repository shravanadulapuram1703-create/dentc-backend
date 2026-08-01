"""Patient Overview aggregate response (PO-1)."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.billing import PatientBalance
from app.schemas.patient import PatientRead
from app.schemas.patient_intake import RosterPatientRead


class PatientOverviewResponse(BaseModel):
    """Everything the legacy Patient Overview screen needs, in one call. The most
    important blocks (patient, balance, account members) are fully typed; the
    remaining resources are passed through as their existing row shapes."""

    patient: PatientRead
    balance: PatientBalance
    visit: dict[str, Any] = Field(default_factory=dict)
    responsible_party: Optional[dict[str, Any]] = None
    account_members: list[RosterPatientRead] = Field(default_factory=list)
    appointments: list[dict[str, Any]] = Field(default_factory=list)
    recalls: list[dict[str, Any]] = Field(default_factory=list)
    insurance: list[dict[str, Any]] = Field(default_factory=list)
    referrals: list[dict[str, Any]] = Field(default_factory=list)
    contracts: dict[str, Any] = Field(default_factory=dict)
