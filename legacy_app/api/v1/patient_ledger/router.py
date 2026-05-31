"""
Patient Ledger API routes (contract-driven).
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth.dependencies import get_current_user
from app.models.user import User

from app.api.v1.patient_ledger import service
from app.api.v1.patient_ledger.schemas import (
    LedgerEntriesResponse,
    BalancesResponse,
    ProcedureCreateRequest,
    ProcedureCreateResponse,
    ProcedureDetailsResponse,
    ProcedureUpdateRequest,
    ClaimCreateRequest,
    ClaimCreateResponse,
    ClaimDetailsResponse,
    ClaimUpdateRequest,
    ClaimSendRequest,
    ClaimSendResponse,
    ClaimsListResponse,
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentDetailsResponse,
    AdjustmentCreateRequest,
    AdjustmentCreateResponse,
    AdjustmentDetailsResponse,
)

router = APIRouter(prefix="/patients", tags=["Patient Ledger"])

import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)

# ==================================================
# Ledger Entries
# ==================================================

@router.get("/{patientId}/ledger", response_model=LedgerEntriesResponse)
def get_patient_ledger(
    patientId: str = Path(..., description="Patient numeric ID"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    transaction_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("date"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    logger.info(f"Patient ID: {patientId}")
    return service.get_ledger_entries(
        db=db,
        patient_id=patientId,
        date_from=date_from,
        date_to=date_to,
        transaction_type=transaction_type,
        status_filter=status,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# ==================================================
# Balances
# ==================================================

@router.get("/{patientId}/balances", response_model=BalancesResponse)
def get_patient_balances(
    patientId: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.get_balances(db=db, patient_id=patientId)


# ==================================================
# Procedures
# ==================================================

@router.post("/{patientId}/procedures", response_model=ProcedureCreateResponse, status_code=status.HTTP_201_CREATED)
def add_patient_procedure(
    patientId: str = Path(...),
    payload: ProcedureCreateRequest = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.add_procedure(db=db, patient_id=patientId, payload=payload, current_user=current_user)


@router.get("/{patientId}/procedures/{procedureId}", response_model=ProcedureDetailsResponse)
def get_patient_procedure(
    patientId: str = Path(...),
    procedureId: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.get_procedure(db=db, patient_id=patientId, procedure_id=procedureId)


@router.put("/{patientId}/procedures/{procedureId}", response_model=ProcedureDetailsResponse)
def update_patient_procedure(
    patientId: str = Path(...),
    procedureId: str = Path(...),
    payload: ProcedureUpdateRequest = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.update_procedure(db=db, patient_id=patientId, procedure_id=procedureId, payload=payload, current_user=current_user)


@router.delete("/{patientId}/procedures/{procedureId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient_procedure(
    patientId: str = Path(...),
    procedureId: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service.delete_procedure(db=db, patient_id=patientId, procedure_id=procedureId)
    return None


# ==================================================
# Claims
# ==================================================

@router.post("/{patientId}/claims", response_model=ClaimCreateResponse, status_code=status.HTTP_201_CREATED)
def create_claim(
    patientId: str = Path(...),
    payload: ClaimCreateRequest = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.create_claim(db=db, patient_id=patientId, payload=payload, current_user=current_user)


@router.get("/{patientId}/claims", response_model=ClaimsListResponse)
def list_claims(
    patientId: str = Path(...),
    status: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.list_claims(db=db, patient_id=patientId, status_filter=status, limit=limit, offset=offset)


@router.get("/{patientId}/claims/{claimId}", response_model=ClaimDetailsResponse)
def get_claim(
    patientId: str = Path(...),
    claimId: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.get_claim_details(db=db, patient_id=patientId, claim_id=claimId)


@router.put("/{patientId}/claims/{claimId}", response_model=ClaimDetailsResponse)
def update_claim(
    patientId: str = Path(...),
    claimId: str = Path(...),
    payload: ClaimUpdateRequest = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.update_claim(db=db, patient_id=patientId, claim_id=claimId, payload=payload, current_user=current_user)


@router.post("/{patientId}/claims/{claimId}/send", response_model=ClaimSendResponse)
def send_claim(
    patientId: str = Path(...),
    claimId: str = Path(...),
    payload: ClaimSendRequest = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.send_claim(db=db, patient_id=patientId, claim_id=claimId, payload=payload, current_user=current_user)


# ==================================================
# Payments
# ==================================================

@router.post("/{patientId}/payments", response_model=PaymentCreateResponse, status_code=status.HTTP_201_CREATED)
def add_payment(
    patientId: str = Path(...),
    payload: PaymentCreateRequest = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.add_payment(db=db, patient_id=patientId, payload=payload, current_user=current_user)


@router.get("/{patientId}/payments/{paymentId}", response_model=PaymentDetailsResponse)
def get_payment(
    patientId: str = Path(...),
    paymentId: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.get_payment(db=db, patient_id=patientId, payment_id=paymentId)


# ==================================================
# Adjustments
# ==================================================

@router.post("/{patientId}/adjustments", response_model=AdjustmentCreateResponse, status_code=status.HTTP_201_CREATED)
def add_adjustment(
    patientId: str = Path(...),
    payload: AdjustmentCreateRequest = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.add_adjustment(db=db, patient_id=patientId, payload=payload, current_user=current_user)


@router.get("/{patientId}/adjustments/{adjustmentId}", response_model=AdjustmentDetailsResponse)
def get_adjustment(
    patientId: str = Path(...),
    adjustmentId: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.get_adjustment(db=db, patient_id=patientId, adjustment_id=adjustmentId)

