"""Patient ledger feed endpoint (Phase 3 / C-3, optional aggregate)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.billing import LedgerResponse
from app.services import ledger_service

router = APIRouter(prefix="/patients", tags=["Billing"], dependencies=[Depends(get_current_user)])


@router.get(
    "/{patient_id}/ledger",
    response_model=LedgerResponse,
    operation_id="get_patient_ledger",
    summary="Get a patient's ledger feed with running balance",
)
def get_ledger(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
):
    return ledger_service.get_patient_ledger(
        db, patient_id, tenant_id, date_from=date_from, date_to=date_to, page=page, size=size
    )
