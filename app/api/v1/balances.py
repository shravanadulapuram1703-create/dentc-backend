"""Patient balance endpoint (Phase 3) — computed, Redis-cached aggregate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.billing import AccountBalance, PatientBalance
from app.services import balance_service

router = APIRouter(prefix="/patients", tags=["Billing"], dependencies=[Depends(get_current_user)])


@router.get(
    "/{patient_id}/balance",
    response_model=PatientBalance,
    operation_id="get_patient_balance",
    summary="Get a patient's computed account balance",
)
def get_balance(db: DbSession, tenant_id: TenantId, patient_id: int = Path(...)):
    return balance_service.get_patient_balance(db, patient_id, tenant_id)


@router.get(
    "/{patient_id}/account-balance",
    response_model=AccountBalance,
    operation_id="get_patient_account_balance",
    summary="AL-11: the legacy BALANCES table — account aggregate + one row per member",
)
def get_account_balance(db: DbSession, tenant_id: TenantId, patient_id: int = Path(...)):
    """One call for the whole account. The per-member entries are exactly what
    ``GET /patients/{id}/balance`` returns, so the ledger's BALANCES panel no longer
    needs one request per family member."""
    return balance_service.get_account_balance(db, patient_id, tenant_id)
