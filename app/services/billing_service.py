"""Billing business logic that exceeds plain CRUD.

- Allocating a payment across procedures/claims with an over-allocation guard.
- Recalculating a claim's billed/estimate totals from its linked procedures.

Tables ``patient_payments`` / ``insurance_claims`` carry no ``tenant_id`` column;
tenancy is verified through the owning patient.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models import (
    InsuranceClaim,
    Patient,
    PatientPayment,
    PatientProcedure,
    PaymentAllocation,
)
from app.schemas.billing import AllocationLine


def _assert_patient_in_tenant(db: Session, patient_id: int, tenant_id: int) -> None:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.tenant_id != tenant_id:
        raise NotFoundError("Related patient not found in this tenant")


def allocate_payment(
    db: Session, payment_id: str, lines: list[AllocationLine], tenant_id: int
) -> list[PaymentAllocation]:
    payment = db.get(PatientPayment, payment_id)
    if payment is None:
        raise NotFoundError(f"PatientPayment '{payment_id}' was not found")
    _assert_patient_in_tenant(db, payment.patient_id, tenant_id)

    already = db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
            PaymentAllocation.payment_id == payment_id
        )
    ).scalar_one()
    requested = sum((line.amount for line in lines), Decimal("0"))
    if Decimal(already) + requested > payment.amount:
        raise ValidationError(
            "Allocations exceed the payment amount",
            details={
                "payment_amount": str(payment.amount),
                "already_allocated": str(already),
                "requested": str(requested),
            },
        )

    created: list[PaymentAllocation] = []
    for line in lines:
        alloc = PaymentAllocation(
            patient_id=payment.patient_id,
            payment_id=payment_id,
            procedure_id=line.procedure_id,
            claim_id=line.claim_id,
            ins_plan_id=line.ins_plan_id,
            provider_id=line.provider_id,
            amount=line.amount,
            alloc_type=line.alloc_type,
            alloc_date=line.alloc_date,
        )
        db.add(alloc)
        created.append(alloc)
    db.commit()
    for alloc in created:
        db.refresh(alloc)
    return created


def recalculate_claim(db: Session, claim_id: str, tenant_id: int) -> dict:
    claim = db.get(InsuranceClaim, claim_id)
    if claim is None:
        raise NotFoundError(f"InsuranceClaim '{claim_id}' was not found")
    _assert_patient_in_tenant(db, claim.patient_id, tenant_id)

    rows = db.execute(
        select(
            func.coalesce(func.sum(PatientProcedure.fee), 0),
            func.coalesce(func.sum(PatientProcedure.insurance_estimate), 0),
            func.count(),
        ).where(
            PatientProcedure.claim_id == claim_id,
            PatientProcedure.is_void.is_(False),
        )
    ).one()
    total_billed, est_insurance, count = rows

    claim.total_billed = Decimal(total_billed)
    claim.est_insurance = Decimal(est_insurance)
    db.commit()
    db.refresh(claim)
    return {
        "id": claim.id,
        "claim_number": claim.claim_number,
        "status": claim.status,
        "total_billed": claim.total_billed,
        "total_paid": claim.total_paid,
        "est_insurance": claim.est_insurance,
        "procedure_count": count,
    }
