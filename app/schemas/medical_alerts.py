"""Medical-alert surfacing wire schemas (MA-2/MA-5).

The one shape every consumer of "what are this patient's active alerts" reads —
the Prescriptions banner, the scheduler block badge/popover and the appointment
Details pop-out. It mirrors the summary the frontend was already building
client-side from two list calls per patient, so it drops in without a change of
shape.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.core.datetimes import UtcDatetime

AlertSource = Literal["medical_history", "patient_alert"]


class ActiveMedicalAlert(BaseModel):
    id: int
    #: ``medical_history`` — a Medical History answer of YES; ``patient_alert`` —
    #: a free-text banner alert from ``/patient-alerts``.
    source: AlertSource
    #: ``alert_code`` for a Medical History row; ``""`` for a free-text alert.
    code: str = ""
    label: str
    #: Catalog group ("Allergic To", "Check, if applicable", …); free-text alerts
    #: report ``Account Alert``; a row whose group is unknown reports ``Other``.
    section: str
    comments: str = ""
    is_flash_alert: bool = False
    blocks_charges: bool = False
    answered_at: Optional[UtcDatetime] = None


class MedicalAlertSummary(BaseModel):
    """MA-2: the per-patient alert summary."""

    patient_id: int
    #: Sorted for display: allergies first, then catalog order, then label.
    alerts: list[ActiveMedicalAlert] = Field(default_factory=list)
    alert_count: int = 0
    allergy_count: int = 0
    #: MA-7: the Medical History "Additional Comments" text (first-class on the
    #: history header; a legacy ``ADDITIONAL_COMMENTS`` row is still read).
    comments: str = ""
    #: True when at least one Medical History alert row exists (YES *or* NO) —
    #: "no history on file" and "no active alerts" are different states.
    history_on_file: bool = False
    #: One line per section — ``"Allergic To: Aspirin; Check, if applicable:
    #: Cardiac Pacemaker"`` — for tooltips and confirms. Null when no alerts.
    summary_text: Optional[str] = None


class MedicalAlertSummaryBatch(BaseModel):
    """``GET /medical-alerts/summary?patient_ids=`` — one summary per requested
    patient (a patient with no rows still appears, with an empty summary)."""

    items: list[MedicalAlertSummary] = Field(default_factory=list)


# ── MA-5: prescriptions ──────────────────────────────────────────────────────
class PrescriptionAlertWarning(BaseModel):
    """One drug<->alert match found when a prescription is written / checked."""

    alert_id: int
    source: AlertSource
    code: str = ""
    label: str
    section: str
    #: ``allergy_key`` — a ``prescription_library.allergy_keys`` entry matched the
    #: alert; ``drug_name`` — the alert's label appears in the drug name itself.
    matched_on: Literal["allergy_key", "drug_name"]
    key: str


class PrescriptionAlertCheckRequest(BaseModel):
    patient_id: int
    drug_name: str
    library_rx_id: Optional[int] = None


class PrescriptionAlertCheckResult(BaseModel):
    """What ``POST /prescriptions`` will do with this drug for this patient: the
    warnings it will raise, and whether it will refuse without
    ``alerts_acknowledged``."""

    patient_id: int
    drug_name: str
    library_rx_id: Optional[int] = None
    warnings: list[PrescriptionAlertWarning] = Field(default_factory=list)
    alerts: list[ActiveMedicalAlert] = Field(default_factory=list)
    history_on_file: bool = False
    #: True when ``POST /prescriptions`` without ``alerts_acknowledged`` would 409.
    blocking: bool = False
    override_field: str = "alerts_acknowledged"
