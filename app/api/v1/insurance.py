"""Insurance supplemental routes (patient-insurance dev-report gaps).

INS-PT-5 — ``POST /insurance-subscribers/{subscriber_id}/verify-eligibility``
stamps the eligibility "Update Status" server-side. Registered before the generic
``insurance-subscribers`` CRUD so the literal sub-path wins over ``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.insurance import EligibilityVerifyRequest, EligibilityVerifyResult
from app.services import insurance_service

router = APIRouter(
    prefix="/insurance-subscribers",
    tags=["Insurance"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.post(
    "/{subscriber_id}/verify-eligibility",
    response_model=EligibilityVerifyResult,
    operation_id="verify_subscriber_eligibility",
    summary="Stamp a subscriber's eligibility verification (INS-PT-5)",
)
def verify_subscriber_eligibility(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    subscriber_id: Annotated[int, Path()],
    body: EligibilityVerifyRequest | None = None,
):
    req = body or EligibilityVerifyRequest()
    return insurance_service.verify_eligibility(
        db, subscriber_id, tenant_id, current,
        elig_status=req.elig_status, notes=req.notes,
    )
