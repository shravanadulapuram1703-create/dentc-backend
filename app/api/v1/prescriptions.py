"""Prescription supplements (MA-5).

Mounted before the generic ``/prescriptions`` CRUD router so the literal
``/prescriptions/alert-check`` wins over ``/{item_id}``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.medical_alerts import PrescriptionAlertCheckRequest, PrescriptionAlertCheckResult
from app.services import prescription_service as svc

router = APIRouter(
    prefix="/prescriptions",
    tags=["Clinical"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.post(
    "/alert-check",
    response_model=PrescriptionAlertCheckResult,
    operation_id="check_prescription_alerts",
    summary="Drug <-> medical-alert check: what POST /prescriptions will warn or refuse on (MA-5)",
)
def check_prescription_alerts(
    db: DbSession, tenant_id: TenantId, body: PrescriptionAlertCheckRequest
):
    """Read-only preview of the save-time check, so the Add screen can show the
    server's warnings before the prescriber presses Save. ``blocking`` is exactly
    the condition ``POST /prescriptions`` 409s on without ``alerts_acknowledged``."""
    return svc.check_alerts(
        db, tenant_id, body.patient_id, drug_name=body.drug_name, library_rx_id=body.library_rx_id
    )
