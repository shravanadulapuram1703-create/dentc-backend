"""
Service layer for Patient Ledger APIs (contract-driven).
All business logic lives here (no controller logic).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple, Dict
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.offices import Office
from app.api.v1.scheduler.models import ProcedureCode, SchedulerProvider
from app.models.offices import OfficeProvider

from app.models.patient_ledger import (
    PatientLedgerEntry,
    PatientProcedure,
    PatientClaim,
    PatientClaimProcedure,
    PatientClaimEvent,
    PatientClaimAttachment,
    PatientPayment,
    PatientPaymentApplication,
    PatientAdjustment,
    PatientAdjustmentApplication,
    PaymentCode,
    AdjustmentCode,
    ClaimStatus,
    TransactionType,
)

from app.api.v1.patient_ledger.schemas import (
    LedgerEntriesResponse,
    LedgerEntry,
    Pagination,
    BalancesResponse,
    Aging,
    RecentActivity,
    LastPayment,
    ProcedureCreateRequest,
    ProcedureCreateResponse,
    ProcedureDetailsResponse,
    ProcedureUpdateRequest,
    ClaimCreateRequest,
    ClaimCreateResponse,
    ClaimProcedureSummary,
    ClaimDetailsResponse,
    ClaimSendRequest,
    ClaimSendResponse,
    ClaimsListResponse,
    ClaimsListItem,
    ClaimUpdateRequest,
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentDetailsResponse,
    AdjustmentCreateRequest,
    AdjustmentCreateResponse,
    AdjustmentDetailsResponse,
    ProcedureCodesMetaResponse,
    ProcedureCodeMeta,
    ProcedureCodeRequirement,
    PaymentCodesResponse,
    PaymentCodeMeta,
    AdjustmentCodesResponse,
    AdjustmentCodeMeta,
    ClaimStatusesResponse,
    ClaimStatusMeta,
    TransactionTypesResponse,
    TransactionTypeMeta,
    OfficeProvidersResponse,
    OfficeProviderMeta,
)


import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)

def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _now_utc() -> datetime:
    return datetime.utcnow()


def _get_patient_or_404(db: Session, patient_id: str) -> Patient:
    try:
        pid = int(patient_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid patientId")
    patient = db.query(Patient).filter(Patient.id == pid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


def _get_office_or_404(db: Session, office_id: str) -> Office:
    try:
        oid = int(office_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Office not found")
    office = db.query(Office).filter(Office.id == oid).first()
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")
    return office


def _get_provider_or_404(db: Session, provider_id: str) -> OfficeProvider:
    provider = db.query(OfficeProvider).filter(OfficeProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


def _get_procedure_code_or_422(db: Session, code: str) -> ProcedureCode:
    proc_code = db.query(ProcedureCode).filter(ProcedureCode.code == code).first()
    if not proc_code:
        raise HTTPException(
            status_code=422, 
            detail=f"Procedure code '{code}' not found. Please ensure the procedure code exists in the system."
        )
    return proc_code


def _validate_procedure_requirements(proc_code: ProcedureCode, payload: ProcedureCreateRequest | ProcedureUpdateRequest):
    # Contract rules: if code requires tooth/surface/quadrant/materials, must be provided.
    # Handle None values for requirements (default to False if None)
    requires_tooth = proc_code.requires_tooth if proc_code.requires_tooth is not None else False
    requires_surface = proc_code.requires_surface if proc_code.requires_surface is not None else False
    requires_quadrant = proc_code.requires_quadrant if proc_code.requires_quadrant is not None else False
    requires_materials = proc_code.requires_materials if proc_code.requires_materials is not None else False
    
    if requires_tooth and not getattr(payload, "tooth", None):
        raise HTTPException(
            status_code=422, 
            detail=f"Procedure code '{proc_code.code}' requires a tooth number to be specified."
        )
    if requires_surface and not getattr(payload, "surface", None):
        raise HTTPException(
            status_code=422, 
            detail=f"Procedure code '{proc_code.code}' requires surface codes to be specified."
        )
    if requires_quadrant and not getattr(payload, "quadrant", None):
        raise HTTPException(
            status_code=422, 
            detail=f"Procedure code '{proc_code.code}' requires a quadrant to be specified."
        )
    if requires_materials and not getattr(payload, "materials", None):
        raise HTTPException(
            status_code=422, 
            detail=f"Procedure code '{proc_code.code}' requires materials to be specified."
        )


def _get_last_running_balance(db: Session, patient_id_int: int) -> Decimal:
    last = (
        db.query(PatientLedgerEntry.running_balance)
        .filter(PatientLedgerEntry.patient_id == patient_id_int)
        .order_by(PatientLedgerEntry.posted_date.desc(), PatientLedgerEntry.id.desc())
        .limit(1)
        .scalar()
    )
    return Decimal(last or 0)


def get_ledger_entries(
    db: Session,
    patient_id: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    transaction_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> LedgerEntriesResponse:
    patient = _get_patient_or_404(db, patient_id)

    q = db.query(PatientLedgerEntry).filter(PatientLedgerEntry.patient_id == patient.id)

    if date_from:
        q = q.filter(PatientLedgerEntry.posted_date >= date_from)
    if date_to:
        q = q.filter(PatientLedgerEntry.posted_date <= date_to)
    if transaction_type:
        q = q.filter(PatientLedgerEntry.transaction_type == transaction_type)
    if status_filter:
        q = q.filter(PatientLedgerEntry.status == status_filter)

    total = q.count()

    # Sorting
    sort_col = PatientLedgerEntry.posted_date
    if sort_by == "amount":
        sort_col = PatientLedgerEntry.posted_amount
    elif sort_by == "provider":
        sort_col = PatientLedgerEntry.provider_name
    elif sort_by == "code":
        sort_col = PatientLedgerEntry.code

    if sort_order == "asc":
        q = q.order_by(sort_col.asc(), PatientLedgerEntry.id.asc())
    else:
        q = q.order_by(sort_col.desc(), PatientLedgerEntry.id.desc())

    rows = q.limit(limit).offset(offset).all()

    entries: List[LedgerEntry] = []
    for r in rows:
        entries.append(
            LedgerEntry(
                id=r.id,
                transaction_id=r.transaction_id,
                posted_date=r.posted_date,
                patient_id=str(r.patient_id),
                patient_name=r.patient_name,
                office_id=str(r.office_id),
                office_name=r.office_name,
                apply_to=r.apply_to,
                code=r.code,
                tooth=r.tooth or "",
                surface=r.surface or "",
                type=r.type,
                has_notes=r.has_notes,
                has_eob=r.has_eob,
                has_attachments=r.has_attachments,
                description=r.description,
                billing_order=r.billing_order or "",
                duration_minutes=r.duration_minutes,
                provider_id=r.provider_id or "",
                provider_name=r.provider_name or "",
                est_patient=float(r.est_patient or 0),
                est_insurance=float(r.est_insurance or 0),
                posted_amount=float(r.posted_amount),
                running_balance=float(r.running_balance),
                created_by=r.created_by,
                created_at=r.created_at,
                transaction_type=r.transaction_type,
                status=r.status or "",
                procedure_id=r.procedure_id,
                claim_id=r.claim_id,
                payment_id=r.payment_id,
                adjustment_id=r.adjustment_id,
            )
        )

    return LedgerEntriesResponse(
        ledger_entries=entries,
        pagination=Pagination(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


def _compute_aging_fifo(entries: List[PatientLedgerEntry]) -> Aging:
    """
    FIFO aging approximation:
    - Apply negative posted_amount (payments/adjustments) to oldest positive charges.
    - Bucket remaining charges by age in days.
    """
    today = date.today()
    charges: List[Tuple[date, Decimal]] = []
    credits_total = Decimal("0.00")

    for e in sorted(entries, key=lambda x: (x.posted_date, x.id)):
        amt = Decimal(e.posted_amount)
        if amt > 0:
            charges.append((e.posted_date, amt))
        elif amt < 0:
            credits_total += (-amt)

    remaining: List[Tuple[date, Decimal]] = []
    for dos, amt in charges:
        if credits_total <= 0:
            remaining.append((dos, amt))
            continue
        applied = min(amt, credits_total)
        left = amt - applied
        credits_total -= applied
        if left > 0:
            remaining.append((dos, left))

    buckets = {
        "current": Decimal("0.00"),
        "age_30": Decimal("0.00"),
        "age_60": Decimal("0.00"),
        "age_90": Decimal("0.00"),
        "age_120": Decimal("0.00"),
    }
    for dos, amt in remaining:
        age_days = (today - dos).days
        if age_days <= 30:
            buckets["current"] += amt
        elif age_days <= 60:
            buckets["age_30"] += amt
        elif age_days <= 90:
            buckets["age_60"] += amt
        elif age_days <= 120:
            buckets["age_90"] += amt
        else:
            buckets["age_120"] += amt

    return Aging(
        current=float(buckets["current"]),
        age_30=float(buckets["age_30"]),
        age_60=float(buckets["age_60"]),
        age_90=float(buckets["age_90"]),
        age_120=float(buckets["age_120"]),
    )


def get_balances(db: Session, patient_id: str) -> BalancesResponse:
    patient = _get_patient_or_404(db, patient_id)

    entries = (
        db.query(PatientLedgerEntry)
        .filter(PatientLedgerEntry.patient_id == patient.id)
        .order_by(PatientLedgerEntry.posted_date.asc(), PatientLedgerEntry.id.asc())
        .all()
    )

    account_balance = float(sum((Decimal(e.posted_amount) for e in entries), Decimal("0.00")))

    # Contract gap: split patient vs insurance balance requires allocation rules not specified.
    # Minimal safe implementation:
    # - patient_balance = account_balance
    # - insurance_balance = 0 until insurance-payment workflow defined
    patient_balance = account_balance
    insurance_balance = 0.0

    # Estimated totals from procedures still not fully reconciled
    proc_rows = db.query(PatientProcedure).filter(PatientProcedure.patient_id == patient.id).all()
    est_ins = float(sum((Decimal(p.est_insurance or 0) for p in proc_rows), Decimal("0.00")))
    est_pat = float(sum((Decimal(p.est_patient or 0) for p in proc_rows), Decimal("0.00")))

    aging = _compute_aging_fifo(entries)

    today = date.today()
    today_charges = float(
        sum(
            (Decimal(e.posted_amount) for e in entries if e.posted_date == today and Decimal(e.posted_amount) > 0),
            Decimal("0.00"),
        )
    )

    last_ins_payment = (
        db.query(PatientPayment)
        .filter(PatientPayment.patient_id == patient.id, PatientPayment.payment_type == "insurance")
        .order_by(PatientPayment.payment_date.desc(), PatientPayment.created_at.desc())
        .first()
    )
    last_pat_payment = (
        db.query(PatientPayment)
        .filter(PatientPayment.patient_id == patient.id, PatientPayment.payment_type == "patient")
        .order_by(PatientPayment.payment_date.desc(), PatientPayment.created_at.desc())
        .first()
    )

    return BalancesResponse(
        account_balance=account_balance,
        patient_balance=patient_balance,
        insurance_balance=insurance_balance,
        estimated_insurance=est_ins,
        estimated_patient=est_pat,
        aging=aging,
        recent_activity=RecentActivity(
            today_charges=today_charges,
            last_insurance_payment=(
                LastPayment(amount=float(last_ins_payment.payment_amount), date=last_ins_payment.payment_date)
                if last_ins_payment
                else None
            ),
            last_patient_payment=(
                LastPayment(amount=float(last_pat_payment.payment_amount), date=last_pat_payment.payment_date)
                if last_pat_payment
                else None
            ),
        ),
    )


def add_procedure(db: Session, patient_id: str, payload: ProcedureCreateRequest, current_user) -> ProcedureCreateResponse:
    patient = _get_patient_or_404(db, patient_id)

    if payload.date_of_service > date.today():
        raise HTTPException(status_code=422, detail="Date of service cannot be in the future")
    if payload.fee <= 0:
        raise HTTPException(status_code=422, detail="Fee must be positive")

    proc_code = _get_procedure_code_or_422(db, payload.procedure_code)
    _validate_procedure_requirements(proc_code, payload)

    provider = _get_provider_or_404(db, payload.provider_id)
    office = _get_office_or_404(db, payload.office_id)

    transaction_id = _id("TXN")
    ledger_id = _id("LED")
    procedure_id = _id("PRC")

    last_balance = _get_last_running_balance(db, patient.id)
    posted_amount = Decimal(str(payload.fee))
    running_balance = last_balance + posted_amount

    entry = PatientLedgerEntry(
        id=ledger_id,
        transaction_id=transaction_id,
        posted_date=payload.date_of_service,
        patient_id=patient.id,
        patient_name=f"{patient.last_name or ''}, {patient.first_name or ''}".strip(", "),
        office_id=office.id,
        office_name=office.office_name,
        apply_to=payload.apply_to or "P",
        code=payload.procedure_code,
        tooth=payload.tooth,
        surface=payload.surface,
        type="P",
        has_notes=bool(payload.notes),
        description=proc_code.description,
        billing_order=payload.billing_order,
        duration_minutes=payload.duration_minutes,
        provider_id=provider.id,
        provider_name=provider.name,
        est_patient=Decimal(str(payload.est_patient)),
        est_insurance=Decimal(str(payload.est_insurance)),
        posted_amount=posted_amount,
        running_balance=running_balance,
        created_by=getattr(current_user, "username", "system"),
        transaction_type="procedure",
        status="not_sent",
        procedure_id=procedure_id,
    )

    proc = PatientProcedure(
        id=procedure_id,
        patient_id=patient.id,
        procedure_code=payload.procedure_code,
        date_of_service=payload.date_of_service,
        provider_id=provider.id,
        provider_name=provider.name,
        office_id=office.id,
        office_name=office.office_name,
        tooth=payload.tooth,
        surface=payload.surface,
        quadrant=payload.quadrant,
        materials=payload.materials,
        duration_minutes=payload.duration_minutes,
        fee=Decimal(str(payload.fee)),
        est_patient=Decimal(str(payload.est_patient)),
        est_insurance=Decimal(str(payload.est_insurance)),
        billing_order=payload.billing_order,
        notes=payload.notes,
        apply_to=payload.apply_to or "P",
        status="not_sent",
        claim_id=None,
        ledger_entry_id=ledger_id,
        created_by=getattr(current_user, "username", "system"),
        updated_by=getattr(current_user, "username", "system"),
    )

    try:
        db.add(entry)
        db.add(proc)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {e}")

    return ProcedureCreateResponse(
        procedure_id=procedure_id,
        ledger_entry_id=ledger_id,
        transaction_id=transaction_id,
        posted_date=payload.date_of_service,
        running_balance=float(running_balance),
        status="not_sent",
        created_at=entry.created_at,
    )


def get_procedure(db: Session, patient_id: str, procedure_id: str) -> ProcedureDetailsResponse:
    patient = _get_patient_or_404(db, patient_id)
    proc = db.query(PatientProcedure).filter(PatientProcedure.id == procedure_id, PatientProcedure.patient_id == patient.id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procedure not found")

    return ProcedureDetailsResponse(
        procedure_id=proc.id,
        procedure_code=proc.procedure_code,
        date_of_service=proc.date_of_service,
        provider_id=proc.provider_id,
        provider_name=proc.provider_name,
        office_id=str(proc.office_id),
        office_name=proc.office_name,
        tooth=proc.tooth,
        surface=proc.surface,
        quadrant=proc.quadrant,
        materials=proc.materials,
        duration_minutes=proc.duration_minutes,
        fee=float(proc.fee),
        est_patient=float(proc.est_patient),
        est_insurance=float(proc.est_insurance),
        billing_order=proc.billing_order or "",
        notes=proc.notes,
        status=proc.status,
        claim_id=proc.claim_id,
        ledger_entry_id=proc.ledger_entry_id,
        created_by=proc.created_by,
        created_at=proc.created_at,
        updated_at=proc.updated_at,
    )


def update_procedure(db: Session, patient_id: str, procedure_id: str, payload: ProcedureUpdateRequest, current_user) -> ProcedureDetailsResponse:
    patient = _get_patient_or_404(db, patient_id)
    proc = db.query(PatientProcedure).filter(PatientProcedure.id == procedure_id, PatientProcedure.patient_id == patient.id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procedure not found")

    if proc.status != "not_sent" or proc.claim_id:
        raise HTTPException(status_code=403, detail="Procedure already sent to insurance, cannot be modified")

    # Determine procedure_code for requirements validation
    code_to_validate = payload.procedure_code or proc.procedure_code
    proc_code = _get_procedure_code_or_422(db, code_to_validate)
    _validate_procedure_requirements(proc_code, payload)

    if payload.date_of_service and payload.date_of_service > date.today():
        raise HTTPException(status_code=422, detail="Date of service cannot be in the future")
    if payload.fee is not None and payload.fee <= 0:
        raise HTTPException(status_code=422, detail="Fee must be positive")

    # Update procedure fields
    for field in [
        "procedure_code",
        "date_of_service",
        "tooth",
        "surface",
        "quadrant",
        "materials",
        "duration_minutes",
        "billing_order",
        "notes",
        "apply_to",
    ]:
        val = getattr(payload, field)
        if val is not None:
            setattr(proc, field, val)

    if payload.provider_id is not None:
        provider = _get_provider_or_404(db, payload.provider_id)
        proc.provider_id = provider.id
        proc.provider_name = provider.name

    if payload.office_id is not None:
        office = _get_office_or_404(db, payload.office_id)
        proc.office_id = office.id
        proc.office_name = office.office_name

    if payload.fee is not None:
        proc.fee = Decimal(str(payload.fee))
    if payload.est_patient is not None:
        proc.est_patient = Decimal(str(payload.est_patient))
    if payload.est_insurance is not None:
        proc.est_insurance = Decimal(str(payload.est_insurance))

    proc.updated_by = getattr(current_user, "username", "system")

    # Update corresponding ledger entry (same transaction) as well
    entry = db.query(PatientLedgerEntry).filter(PatientLedgerEntry.id == proc.ledger_entry_id).first()
    if entry:
        entry.posted_date = proc.date_of_service
        entry.code = proc.procedure_code
        entry.tooth = proc.tooth
        entry.surface = proc.surface
        entry.description = proc_code.description
        entry.billing_order = proc.billing_order
        entry.duration_minutes = proc.duration_minutes
        entry.provider_id = proc.provider_id
        entry.provider_name = proc.provider_name
        entry.has_notes = bool(proc.notes)
        entry.est_patient = proc.est_patient
        entry.est_insurance = proc.est_insurance

        # NOTE: adjusting posted_amount and running_balance retroactively is ambiguous.
        # Minimal safe behavior: disallow fee change after posting to ledger
        if payload.fee is not None:
            raise HTTPException(status_code=422, detail="Updating fee after posting is not supported")

    db.commit()
    db.refresh(proc)
    return get_procedure(db, patient_id, procedure_id)


def delete_procedure(db: Session, patient_id: str, procedure_id: str):
    patient = _get_patient_or_404(db, patient_id)
    proc = db.query(PatientProcedure).filter(PatientProcedure.id == procedure_id, PatientProcedure.patient_id == patient.id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procedure not found")
    if proc.status != "not_sent" or proc.claim_id:
        raise HTTPException(status_code=403, detail="Procedure already sent to insurance, cannot be deleted")

    # Delete procedure + ledger entry atomically
    entry = db.query(PatientLedgerEntry).filter(PatientLedgerEntry.id == proc.ledger_entry_id).first()
    try:
        if entry:
            db.delete(entry)
        db.delete(proc)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {e}")


def _generate_claim_number(db: Session) -> str:
    # stable, human-friendly claim number; contract doesn't define format
    # Use sequential count for tenant_1 for now.
    count = db.query(func.count(PatientClaim.id)).scalar() or 0
    return f"CLM-{count + 1:06d}"


def create_claim(db: Session, patient_id: str, payload: ClaimCreateRequest, current_user) -> ClaimCreateResponse:
    patient = _get_patient_or_404(db, patient_id)
    if not payload.procedure_ids:
        raise HTTPException(status_code=400, detail="No procedures selected")

    procs = (
        db.query(PatientProcedure)
        .filter(PatientProcedure.patient_id == patient.id, PatientProcedure.id.in_(payload.procedure_ids))
        .all()
    )
    if len(procs) != len(set(payload.procedure_ids)):
        raise HTTPException(status_code=404, detail="One or more procedures not found")

    # Prevent duplicate claims
    # for p in procs:
    #     if p.claim_id:
    #         raise HTTPException(status_code=400, detail="One or more procedures already in a claim")

    dos_from = payload.date_of_service_from or min(p.date_of_service for p in procs)
    dos_to = payload.date_of_service_to or max(p.date_of_service for p in procs)

    claim_id = _id("CLM")
    claim_number = _generate_claim_number(db)

    total_fee = sum((Decimal(p.fee) for p in procs), Decimal("0.00"))
    total_est_ins = sum((Decimal(p.est_insurance) for p in procs), Decimal("0.00"))

    claim = PatientClaim(
        id=claim_id,
        claim_number=claim_number,
        patient_id=patient.id,
        status="created",
        claim_type=payload.claim_type,
        billing_order=payload.billing_order,
        date_of_service_from=dos_from,
        date_of_service_to=dos_to,
        total_submitted_fees=total_fee,
        total_fee=total_fee,
        total_est_insurance=total_est_ins,
        notes=payload.notes,
        created_by=getattr(current_user, "username", "system"),
        last_status_update_date=date.today(),
    )

    try:
        db.add(claim)
        for p in procs:
            db.add(PatientClaimProcedure(id=_id("CPR"), claim_id=claim_id, procedure_id=p.id))
            p.claim_id = claim_id
            # Keep procedure status as not_sent until claim is sent (contract gap; safest)
        db.add(PatientClaimEvent(id=_id("CEV"), claim_id=claim_id, event_type="created", event_by=getattr(current_user, "username", "system"), details=None))

        # Ledger claim_event (posted_amount 0)
        last_balance = _get_last_running_balance(db, patient.id)
        led = PatientLedgerEntry(
            id=_id("LED"),
            transaction_id=_id("TXN"),
            posted_date=date.today(),
            patient_id=patient.id,
            patient_name=f"{patient.last_name or ''}, {patient.first_name or ''}".strip(", "),
            office_id=int(procs[0].office_id),
            office_name=procs[0].office_name,
            apply_to="P",
            code="CLM",
            description=f"Claim created {claim_number}",
            posted_amount=Decimal("0.00"),
            running_balance=last_balance,
            created_by=getattr(current_user, "username", "system"),
            transaction_type="claim_event",
            status="created",
            claim_id=claim_id,
        )
        db.add(led)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {e}")

    return ClaimCreateResponse(
        claim_id=claim_id,
        claim_number=claim_number,
        status="created",
        claim_type=payload.claim_type,
        billing_order=payload.billing_order,
        date_of_service_from=dos_from,
        date_of_service_to=dos_to,
        total_submitted_fees=float(total_fee),
        total_fee=float(total_fee),
        total_est_insurance=float(total_est_ins),
        procedures=[
            ClaimProcedureSummary(
                procedure_id=p.id,
                procedure_code=p.procedure_code,
                date_of_service=p.date_of_service,
                fee=float(p.fee),
                est_insurance=float(p.est_insurance),
            )
            for p in procs
        ],
        created_by=getattr(current_user, "username", "system"),
        created_at=claim.created_at,
    )


def list_claims(db: Session, patient_id: str, status_filter: Optional[str], limit: int, offset: int) -> ClaimsListResponse:
    patient = _get_patient_or_404(db, patient_id)
    q = db.query(PatientClaim).filter(PatientClaim.patient_id == patient.id)
    if status_filter:
        q = q.filter(PatientClaim.status == status_filter)
    total = q.count()
    claims = q.order_by(PatientClaim.created_at.desc()).limit(limit).offset(offset).all()
    return ClaimsListResponse(
        claims=[
            ClaimsListItem(
                claim_id=c.id,
                claim_number=c.claim_number,
                status=c.status,
                claim_type=c.claim_type,
                date_of_service_from=c.date_of_service_from,
                date_of_service_to=c.date_of_service_to,
                total_fee=float(c.total_fee),
                total_est_insurance=float(c.total_est_insurance),
                created_date=c.created_date,
                created_by=c.created_by,
            )
            for c in claims
        ],
        pagination=Pagination(total=total, limit=limit, offset=offset, has_more=(offset + limit) < total),
    )


def get_claim_details(db: Session, patient_id: str, claim_id: str) -> ClaimDetailsResponse:
    patient = _get_patient_or_404(db, patient_id)
    claim = db.query(PatientClaim).filter(PatientClaim.id == claim_id, PatientClaim.patient_id == patient.id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    # Contract contains large nested objects; current backend lacks subscriber coverage mapping.
    # Minimal safe approach: populate from patient + patient_insurance if available, otherwise empty strings.
    # (Contract gap flagged in deliverables.)

    # Procedures in claim
    cps = db.query(PatientClaimProcedure).filter(PatientClaimProcedure.claim_id == claim.id).all()
    proc_rows = [cp.procedure for cp in cps]

    # Attachments
    att_rows = db.query(PatientClaimAttachment).filter(PatientClaimAttachment.claim_id == claim.id).all()
    attachment_required = any(a.required and not a.provided for a in att_rows)

    # Amounts: insurance paid not implemented yet
    total_ins_paid = 0.0
    variance = float(Decimal(claim.total_fee) - Decimal(str(total_ins_paid)))

    return ClaimDetailsResponse(
        claim_id=claim.id,
        claim_number=claim.claim_number,
        status=claim.status,
        claim_type=claim.claim_type,
        billing_order=claim.billing_order,
        date_of_service_from=claim.date_of_service_from,
        date_of_service_to=claim.date_of_service_to,
        created_date=claim.created_date,
        created_time=str(claim.created_time),
        created_by=claim.created_by,
        last_status_update_date=claim.last_status_update_date,
        claim_sent_date=claim.claim_sent_date,
        claim_sent_status=claim.claim_sent_status,
        claim_close_date=claim.claim_close_date,
        claim_closed_by=claim.claim_closed_by,
        dxc_attachment_id=claim.dxc_attachment_id,
        icd10_codes=claim.icd10_codes,
        patient_info={
            "patient_id": str(patient.id),
            "patient_name": f"{patient.last_name or ''}, {patient.first_name or ''}".strip(", "),
            "patient_dob": patient.dob if patient.dob else None,
            "subscriber_name": "",
            "subscriber_id": "",
            "subscriber_dob": None,
            "responsible_party_name": "",
            "responsible_party_id": "",
            "responsible_party_dob": None,
        },
        coverage_info={
            "insurance_carrier": "",
            "carrier_phone": None,
            "group_plan": None,
            "benefits_used": None,
            "employer_name": None,
            "deductibles_used": None,
        },
        billing_dentist={"provider_id": proc_rows[0].provider_id if proc_rows else "", "provider_name": proc_rows[0].provider_name if proc_rows else ""},
        treating_dentist={"provider_id": proc_rows[0].provider_id if proc_rows else "", "provider_name": proc_rows[0].provider_name if proc_rows else ""},
        amounts={
            "total_submitted_fees": float(claim.total_submitted_fees),
            "total_fee": float(claim.total_fee),
            "total_est_insurance": float(claim.total_est_insurance),
            "total_insurance_paid": total_ins_paid,
            "variance": variance,
        },
        payment_info={"check_number": None, "bank_number": None, "eob_number": None},
        notes=claim.notes,
        attachment_required=attachment_required,
        procedures=[
            {
                "procedure_id": p.id,
                "dos": p.date_of_service,
                "code": p.procedure_code,
                "tooth": p.tooth,
                "surface": p.surface,
                "description": p.procedure_code,
                "bref": "",
                "submitted": float(p.fee),
                "fee": float(p.fee),
                "est_ins": float(p.est_insurance),
                "ins_paid": 0.0,
                "ins_overpayment": 0.0,
                "ins_allocated": 0.0,
                "overpayment_disbursement": 0.0,
                "write_off_1": 0.0,
                "write_off_2": 0.0,
                "write_off_3": 0.0,
                "other_insurance": 0.0,
                "reason_code": None,
            }
            for p in proc_rows
        ],
        attachments=[
            {
                "attachment_id": a.id,
                "attachment_type": a.attachment_type,
                "required": a.required,
                "provided": a.provided,
                "file_name": a.file_name,
                "uploaded_at": a.uploaded_at,
            }
            for a in att_rows
        ],
    )


def update_claim(db: Session, patient_id: str, claim_id: str, payload: ClaimUpdateRequest, current_user) -> ClaimDetailsResponse:
    patient = _get_patient_or_404(db, patient_id)
    claim = db.query(PatientClaim).filter(PatientClaim.id == claim_id, PatientClaim.patient_id == patient.id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status != "created":
        raise HTTPException(status_code=403, detail="Claim already sent, cannot be modified")

    if payload.notes is not None:
        claim.notes = payload.notes
    if payload.icd10_codes is not None:
        claim.icd10_codes = payload.icd10_codes
    # payment_info fields exist in contract; current DB doesn't persist them yet (gap).

    claim.last_status_update_date = date.today()
    db.add(PatientClaimEvent(id=_id("CEV"), claim_id=claim.id, event_type="note_update", event_by=getattr(current_user, "username", "system"), details=None))
    db.commit()
    return get_claim_details(db, patient_id, claim_id)


def send_claim(db: Session, patient_id: str, claim_id: str, payload: ClaimSendRequest, current_user) -> ClaimSendResponse:
    patient = _get_patient_or_404(db, patient_id)
    claim = db.query(PatientClaim).filter(PatientClaim.id == claim_id, PatientClaim.patient_id == patient.id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status != "created":
        raise HTTPException(status_code=403, detail="Claim already sent or cannot be modified")

    if payload.send_method not in {"electronic", "paper", "fax"}:
        raise HTTPException(status_code=400, detail="Invalid send_method")

    # Validate attachments if any are required
    att_rows = db.query(PatientClaimAttachment).filter(PatientClaimAttachment.claim_id == claim.id).all()
    if any(a.required and not a.provided for a in att_rows):
        raise HTTPException(status_code=422, detail="Missing required attachments")

    batch_id = payload.batch_id or _id("BATCH")
    sent_dt = datetime.utcnow()

    # Claim state transition
    claim.status = "sent"
    claim.batch_id = batch_id
    claim.send_method = payload.send_method
    claim.claim_sent_date = sent_dt.date()
    claim.claim_sent_status = "sent"
    claim.last_status_update_date = sent_dt.date()

    # Mark procedures as sent
    cps = db.query(PatientClaimProcedure).filter(PatientClaimProcedure.claim_id == claim.id).all()
    proc_ids = [cp.procedure_id for cp in cps]
    if proc_ids:
        db.query(PatientProcedure).filter(PatientProcedure.id.in_(proc_ids)).update({"status": "sent"}, synchronize_session=False)

    # Event + ledger claim_event (0 amount)
    db.add(PatientClaimEvent(id=_id("CEV"), claim_id=claim.id, event_type="sent", event_by=getattr(current_user, "username", "system"), details={"batch_id": batch_id, "send_method": payload.send_method}))

    last_balance = _get_last_running_balance(db, patient.id)
    db.add(
        PatientLedgerEntry(
            id=_id("LED"),
            transaction_id=_id("TXN"),
            posted_date=sent_dt.date(),
            patient_id=patient.id,
            patient_name=f"{patient.last_name or ''}, {patient.first_name or ''}".strip(", "),
            office_id=int(cps[0].procedure.office_id) if cps else 0,
            office_name=cps[0].procedure.office_name if cps else "",
            apply_to="P",
            code="CLM-S",
            description=f"Claim sent {claim.claim_number}",
            posted_amount=Decimal("0.00"),
            running_balance=last_balance,
            created_by=getattr(current_user, "username", "system"),
            transaction_type="claim_event",
            status="sent",
            claim_id=claim.id,
        )
    )

    db.commit()

    return ClaimSendResponse(
        claim_id=claim.id,
        batch_id=batch_id,
        status="sent",
        sent_date=sent_dt.date(),
        sent_time=sent_dt.time().strftime("%H:%M:%S"),
        sent_by=getattr(current_user, "username", "system"),
        send_method=payload.send_method,
    )


def add_payment(db: Session, patient_id: str, payload: PaymentCreateRequest, current_user) -> PaymentCreateResponse:
    patient = _get_patient_or_404(db, patient_id)
    if payload.payment_amount <= 0:
        raise HTTPException(status_code=422, detail="payment_amount must be positive")

    # Validate procedures if provided
    proc_ids: List[str] = payload.procedure_ids or []
    if proc_ids:
        rows = db.query(PatientProcedure).filter(PatientProcedure.patient_id == patient.id, PatientProcedure.id.in_(proc_ids)).all()
        if len(rows) != len(set(proc_ids)):
            raise HTTPException(status_code=404, detail="One or more procedures not found")

    transaction_id = _id("TXN")
    ledger_id = _id("LED")
    payment_id = _id("PMT")

    last_balance = _get_last_running_balance(db, patient.id)
    posted_amount = -Decimal(str(payload.payment_amount))
    running_balance = last_balance + posted_amount

    # Provider optional
    provider_name = None
    if payload.provider_id:
        provider = _get_provider_or_404(db, payload.provider_id)
        provider_name = provider.name

    entry = PatientLedgerEntry(
        id=ledger_id,
        transaction_id=transaction_id,
        posted_date=payload.payment_date,
        patient_id=patient.id,
        patient_name=f"{patient.last_name or ''}, {patient.first_name or ''}".strip(", "),
        office_id=patient.home_office_id or 0,
        office_name=db.query(Office.office_name).filter(Office.id == patient.home_office_id).scalar() if patient.home_office_id else "",
        apply_to=payload.apply_to,
        code="PMT",
        description=f"{payload.payment_type} payment",
        posted_amount=posted_amount,
        running_balance=running_balance,
        created_by=getattr(current_user, "username", "system"),
        transaction_type="insurance_payment" if payload.payment_type == "insurance" else "patient_payment",
        status="posted",
        payment_id=payment_id,
        provider_id=payload.provider_id,
        provider_name=provider_name,
        has_notes=bool(payload.notes),
    )

    payment = PatientPayment(
        id=payment_id,
        patient_id=patient.id,
        payment_date=payload.payment_date,
        payment_amount=Decimal(str(payload.payment_amount)),
        payment_type=payload.payment_type,
        payment_method=payload.payment_method,
        apply_to=payload.apply_to,
        provider_id=payload.provider_id,
        provider_name=provider_name,
        check_number=payload.check_number,
        bank_number=payload.bank_number,
        notes=payload.notes,
        ledger_entry_id=ledger_id,
        created_by=getattr(current_user, "username", "system"),
    )

    try:
        db.add(entry)
        db.add(payment)
        for pid in proc_ids:
            db.add(PatientPaymentApplication(id=_id("PMA"), payment_id=payment_id, procedure_id=pid, amount=Decimal("0.00")))
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {e}")

    return PaymentCreateResponse(
        payment_id=payment_id,
        ledger_entry_id=ledger_id,
        transaction_id=transaction_id,
        posted_date=payload.payment_date,
        running_balance=float(running_balance),
        status="posted",
        created_at=entry.created_at,
    )


def get_payment(db: Session, patient_id: str, payment_id: str) -> PaymentDetailsResponse:
    patient = _get_patient_or_404(db, patient_id)
    p = db.query(PatientPayment).filter(PatientPayment.id == payment_id, PatientPayment.patient_id == patient.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    apps = db.query(PatientPaymentApplication).filter(PatientPaymentApplication.payment_id == p.id).all()
    return PaymentDetailsResponse(
        payment_id=p.id,
        payment_date=p.payment_date,
        payment_amount=float(p.payment_amount),
        payment_type=p.payment_type,
        payment_method=p.payment_method,
        apply_to=p.apply_to,
        provider_id=p.provider_id,
        provider_name=p.provider_name,
        procedure_ids=[a.procedure_id for a in apps],
        check_number=p.check_number,
        bank_number=p.bank_number,
        notes=p.notes,
        ledger_entry_id=p.ledger_entry_id,
        created_by=p.created_by,
        created_at=p.created_at,
    )


def add_adjustment(db: Session, patient_id: str, payload: AdjustmentCreateRequest, current_user) -> AdjustmentCreateResponse:
    patient = _get_patient_or_404(db, patient_id)
    if payload.adjustment_amount >= 0:
        raise HTTPException(status_code=422, detail="adjustment_amount must be negative")

    proc_ids: List[str] = payload.procedure_ids or []
    if proc_ids:
        rows = db.query(PatientProcedure).filter(PatientProcedure.patient_id == patient.id, PatientProcedure.id.in_(proc_ids)).all()
        if len(rows) != len(set(proc_ids)):
            raise HTTPException(status_code=404, detail="One or more procedures not found")

    transaction_id = _id("TXN")
    ledger_id = _id("LED")
    adj_id = _id("ADJ")

    last_balance = _get_last_running_balance(db, patient.id)
    posted_amount = Decimal(str(payload.adjustment_amount))  # already negative
    running_balance = last_balance + posted_amount

    entry = PatientLedgerEntry(
        id=ledger_id,
        transaction_id=transaction_id,
        posted_date=payload.adjustment_date,
        patient_id=patient.id,
        patient_name=f"{patient.last_name or ''}, {patient.first_name or ''}".strip(", "),
        office_id=patient.home_office_id or 0,
        office_name=db.query(Office.office_name).filter(Office.id == patient.home_office_id).scalar() if patient.home_office_id else "",
        apply_to=payload.apply_to,
        code="ADJ",
        description=payload.adjustment_reason,
        posted_amount=posted_amount,
        running_balance=running_balance,
        created_by=getattr(current_user, "username", "system"),
        transaction_type="adjustment",
        status="posted",
        adjustment_id=adj_id,
        has_notes=bool(payload.notes),
    )

    adj = PatientAdjustment(
        id=adj_id,
        patient_id=patient.id,
        adjustment_date=payload.adjustment_date,
        adjustment_amount=posted_amount,
        adjustment_code=payload.adjustment_code,
        adjustment_reason=payload.adjustment_reason,
        apply_to=payload.apply_to,
        notes=payload.notes,
        ledger_entry_id=ledger_id,
        created_by=getattr(current_user, "username", "system"),
    )

    try:
        db.add(entry)
        db.add(adj)
        for pid in proc_ids:
            db.add(PatientAdjustmentApplication(id=_id("ADA"), adjustment_id=adj_id, procedure_id=pid, amount=Decimal("0.00")))
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {e}")

    return AdjustmentCreateResponse(
        adjustment_id=adj_id,
        ledger_entry_id=ledger_id,
        transaction_id=transaction_id,
        posted_date=payload.adjustment_date,
        running_balance=float(running_balance),
        status="posted",
        created_at=entry.created_at,
    )


def get_adjustment(db: Session, patient_id: str, adjustment_id: str) -> AdjustmentDetailsResponse:
    patient = _get_patient_or_404(db, patient_id)
    a = db.query(PatientAdjustment).filter(PatientAdjustment.id == adjustment_id, PatientAdjustment.patient_id == patient.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    apps = db.query(PatientAdjustmentApplication).filter(PatientAdjustmentApplication.adjustment_id == a.id).all()
    return AdjustmentDetailsResponse(
        adjustment_id=a.id,
        adjustment_date=a.adjustment_date,
        adjustment_amount=float(a.adjustment_amount),
        adjustment_code=a.adjustment_code,
        adjustment_reason=a.adjustment_reason,
        apply_to=a.apply_to,
        procedure_ids=[x.procedure_id for x in apps],
        notes=a.notes,
        ledger_entry_id=a.ledger_entry_id,
        created_by=a.created_by,
        created_at=a.created_at,
    )


# ==================================================
# Metadata (contract routes)
# ==================================================

def get_metadata_procedure_codes(db: Session, category: Optional[str], search: Optional[str], limit: int) -> ProcedureCodesMetaResponse:
    # q = db.query(ProcedureCode)#.filter(ProcedureCode.is_active == True)
    if category:
        logger.info(f"Category Check: {category} and category type: {type(category)}")
        category = category.replace("+", "").capitalize()
        q = db.query(ProcedureCode).filter(ProcedureCode.category.ilike(category))#== category)
        logger.info(f"Category Check qqqqqqqqqqqqqq: {q}")
    if search:
        term = f"%{search}%"
        logger.info(f"Search Check: {search} and search type: {type(search)}")
        q =db.query(ProcedureCode).filter(
            (ProcedureCode.code.ilike(term))
            | (ProcedureCode.user_code.ilike(term))
            | (ProcedureCode.description.ilike(term))
        )
    logger.info(f"Check: 222222222222222222")
    rows = q.order_by(ProcedureCode.code).limit(limit).all()
    logger.info(f"Rows: {rows}")
    categories = [r[0] for r in db.query(ProcedureCode.category).distinct().order_by(ProcedureCode.category).all()]
    return ProcedureCodesMetaResponse(
        procedure_codes=[
            ProcedureCodeMeta(
                code=r.code,
                user_code=r.user_code,
                description=r.description,
                category=r.category,
                default_fee = r.default_fee,
                default_duration = r.default_duration,
                requirements=ProcedureCodeRequirement(
                    tooth=r.requires_tooth,
                    surface=r.requires_surface,
                    quadrant=r.requires_quadrant,
                    materials=r.requires_materials,
                ),
                is_active=True,
            )
            for r in rows
        ],
        categories=categories,
    )


def get_payment_codes(db: Session) -> PaymentCodesResponse:
    codes = db.query(PaymentCode).filter(PaymentCode.is_active == True).order_by(PaymentCode.code).all()
    return PaymentCodesResponse(
        payment_codes=[PaymentCodeMeta(code=c.code, description=c.description, type=c.type, is_active=c.is_active) for c in codes]
    )


def get_adjustment_codes(db: Session) -> AdjustmentCodesResponse:
    codes = db.query(AdjustmentCode).filter(AdjustmentCode.is_active == True).order_by(AdjustmentCode.code).all()
    return AdjustmentCodesResponse(
        adjustment_codes=[AdjustmentCodeMeta(code=c.code, description=c.description, is_active=c.is_active) for c in codes]
    )


def get_claim_statuses(db: Session) -> ClaimStatusesResponse:
    rows = db.query(ClaimStatus).order_by(ClaimStatus.code).all()
    return ClaimStatusesResponse(
        claim_statuses=[ClaimStatusMeta(code=r.code, display_name=r.display_name, description=r.description) for r in rows]
    )


def get_transaction_types(db: Session) -> TransactionTypesResponse:
    rows = db.query(TransactionType).order_by(TransactionType.code).all()
    return TransactionTypesResponse(
        transaction_types=[TransactionTypeMeta(code=r.code, display_name=r.display_name, description=r.description) for r in rows]
    )


def get_office_providers(db: Session, office_id: str) -> OfficeProvidersResponse:
    try:
        oid = int(office_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid officeId")
    providers = (
        db.query(SchedulerProvider)
        .filter(and_(SchedulerProvider.office_id == oid, SchedulerProvider.is_active == True))
        .order_by(SchedulerProvider.name)
        .all()
    )
    return OfficeProvidersResponse(
        providers=[
            OfficeProviderMeta(provider_id=p.id, provider_name=p.name, npi=None, is_active=p.is_active)
            for p in providers
        ]
    )

