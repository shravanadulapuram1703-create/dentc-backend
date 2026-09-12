"""Prescription (patient Rx) wire schemas — MA-5.

Generated from the model like every other CRUD entity, with the
acknowledgement block typed by hand: the frontend compares
``acknowledged_alert_ids`` against the Medical History row ids it displays.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import Field, create_model

from app.core.datetimes import UtcDatetime
from app.db.models import Prescription
from app.schemas.factory import build_schemas
from app.schemas.medical_alerts import ActiveMedicalAlert, PrescriptionAlertWarning

_SERVER_OWNED = (
    "acknowledged_alerts", "alert_warnings", "alerts_acknowledged_at", "alerts_acknowledged_by",
)

_Create, _Update, _ReadBase = build_schemas(
    Prescription, "PrescriptionBase",
    create_exclude=_SERVER_OWNED,
    update_exclude=_SERVER_OWNED + ("alerts_acknowledged", "acknowledged_alert_ids"),
)


class PrescriptionCreate(_Create):  # type: ignore[valid-type, misc]
    """``alerts_acknowledged`` says the prescriber saw the patient's active
    medical alerts before saving. Without it, a drug that matches an active
    allergy is a **409** ``prescription_alert_conflict`` (never stored). With
    it, ``acknowledged_alert_ids`` (Medical History row ids; defaults to every
    active one) and a full ``acknowledged_alerts`` snapshot are persisted."""

    alerts_acknowledged: bool = False
    acknowledged_alert_ids: Optional[list[int]] = None


class PrescriptionUpdate(_Update):  # type: ignore[valid-type, misc]
    pass


PrescriptionRead = create_model(
    "PrescriptionRead", __base__=_ReadBase,
    alerts_acknowledged=(bool, False),
    acknowledged_alert_ids=(Optional[list[int]], None),
    acknowledged_alerts=(Optional[list[ActiveMedicalAlert]], None),
    alert_warnings=(Optional[list[PrescriptionAlertWarning]], None),
    alerts_acknowledged_at=(Optional[UtcDatetime], None),
    alerts_acknowledged_by=(Optional[int], None),
    #: Transient (not stored): the warnings the *write* raised, echoed on the
    #: 201 so the client can show the server's words instead of a generic confirm.
    warnings=(list[PrescriptionAlertWarning], Field(default_factory=list)),
)

__all__ = ["PrescriptionCreate", "PrescriptionRead", "PrescriptionUpdate"]

_ = Any  # keep the import for type checkers reading the generated fields
