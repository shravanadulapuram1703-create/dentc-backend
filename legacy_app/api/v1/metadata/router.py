"""
Metadata APIs required by Patient Ledger contract.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth.dependencies import get_current_user
from app.models.user import User

from app.api.v1.patient_ledger import service as ledger_service
from app.api.v1.patient_ledger.schemas import (
    ProcedureCodesMetaResponse,
    PaymentCodesResponse,
    AdjustmentCodesResponse,
    ClaimStatusesResponse,
    TransactionTypesResponse,
)

router = APIRouter(prefix="/metadata", tags=["Metadata"])


@router.get("/procedure-codes", response_model=ProcedureCodesMetaResponse)
def get_procedure_codes(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ledger_service.get_metadata_procedure_codes(db=db, category=category, search=search, limit=limit)


@router.get("/payment-codes", response_model=PaymentCodesResponse)
def get_payment_codes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ledger_service.get_payment_codes(db=db)


@router.get("/adjustment-codes", response_model=AdjustmentCodesResponse)
def get_adjustment_codes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ledger_service.get_adjustment_codes(db=db)


@router.get("/claim-statuses", response_model=ClaimStatusesResponse)
def get_claim_statuses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ledger_service.get_claim_statuses(db=db)


@router.get("/transaction-types", response_model=TransactionTypesResponse)
def get_transaction_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ledger_service.get_transaction_types(db=db)

