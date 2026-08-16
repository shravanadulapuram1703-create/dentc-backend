"""Billing business logic that exceeds plain CRUD.

- Allocating a payment across procedures/claims with an over-allocation guard.
- Recalculating a claim's billed/estimate totals from its linked procedures.

Tables ``patient_payments`` / ``insurance_claims`` carry no ``tenant_id`` column;
tenancy is verified through the owning patient.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import uuid7
from app.db.models import (
    Appointment,
    AuditLog,
    ClaimSubmission,
    ExplosionCode,
    ExplosionCodeItem,
    InsuranceCarrier,
    InsuranceClaim,
    InsurancePlan,
    LedgerInsuranceDetail,
    Patient,
    PatientInsurance,
    PatientPayment,
    PatientProcedure,
    PaymentAllocation,
    ProcedureCode,
)
from app.integrations import redis_store
from app.schemas.billing import AllocationLine
from app.services.user_admin_service import resolve_user_names


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


def _get_claim(db: Session, claim_id: str, tenant_id: int) -> InsuranceClaim:
    claim = db.get(InsuranceClaim, claim_id)
    if claim is None:
        raise NotFoundError(f"InsuranceClaim '{claim_id}' was not found")
    _assert_patient_in_tenant(db, claim.patient_id, tenant_id)
    return claim


# ── INS-1: record an insurance payment with remittance identifiers ───────────
def record_insurance_payment(
    db: Session, tenant_id: int, payload: dict, *, actor_id: int | None = None
) -> LedgerInsuranceDetail:
    """Post a carrier insurance payment carrying the reconciliation identifiers
    (check / bank / EOB / EFT-trace) that a posted payment must keep so it can be
    matched back to the carrier's remittance."""
    _assert_patient_in_tenant(db, payload["patient_id"], tenant_id)
    if payload.get("claim_id"):
        _get_claim(db, payload["claim_id"], tenant_id)

    detail = LedgerInsuranceDetail(
        patient_id=payload["patient_id"],
        claim_id=payload.get("claim_id"),
        procedure_id=payload.get("procedure_id"),
        office_id=payload.get("office_id"),
        payment_date=payload.get("payment_date") or datetime.now(timezone.utc).date(),
        payment_method=payload.get("payment_method"),
        check_number=payload.get("check_number"),
        bank_number=payload.get("bank_number"),
        eob_number=payload.get("eob_number"),
        eft_trace_number=payload.get("eft_trace_number"),
        prim_ins_plan_id=payload.get("prim_ins_plan_id"),
        sec_ins_plan_id=payload.get("sec_ins_plan_id"),
        prim_estimated=payload.get("prim_estimated"),
        prim_ins_paid=payload.get("prim_ins_paid"),
        prim_ins_adjust=payload.get("prim_ins_adjust"),
        prim_deductible=payload.get("prim_deductible"),
        sec_estimated=payload.get("sec_estimated"),
        sec_ins_paid=payload.get("sec_ins_paid"),
        sec_ins_adjust=payload.get("sec_ins_adjust"),
        prim_posted=payload.get("prim_ins_paid") is not None,
        sec_posted=payload.get("sec_ins_paid") is not None,
        created_by=actor_id,
    )
    db.add(detail)
    # Roll the paid amount onto the claim so insurance A/R stays accurate.
    if payload.get("claim_id"):
        claim = db.get(InsuranceClaim, payload["claim_id"])
        paid = Decimal(payload.get("prim_ins_paid") or 0) + Decimal(payload.get("sec_ins_paid") or 0)
        claim.total_paid = Decimal(claim.total_paid or 0) + paid
        if claim.status in ("sent", "submitted", "pending"):
            claim.status = "paid" if paid > 0 else claim.status
            claim.paid_date = detail.payment_date
    db.commit()
    db.refresh(detail)
    redis_store.cache_delete(f"balance:{tenant_id}:{payload['patient_id']}")
    return detail


# ── SVC-1: submit a claim ─────────────────────────────────────────────────────
def submit_claim(
    db: Session, claim_id: str, tenant_id: int, payload: dict, *, actor_id: int | None = None
) -> dict:
    """Submit (send) a claim: stamp sent_date + status, and create the
    ``claim_submissions`` record that returns the ``batch_id`` / send method."""
    claim = _get_claim(db, claim_id, tenant_id)
    sent_date = payload.get("sent_date") or datetime.now(timezone.utc).date()
    batch_id = payload.get("batch_id") or f"BATCH-{uuid7()}"
    is_preauth = bool(payload.get("is_preauth"))

    submission = ClaimSubmission(
        claim_id=claim_id,
        batch_id=batch_id,
        is_preauth=is_preauth,
        total_charges=claim.total_billed,
        submission_status="sent",
        created_by=actor_id,
    )
    db.add(submission)

    claim.status = "preauth_sent" if is_preauth else "sent"
    claim.submitted_date = sent_date
    # Mark this claim's procedures billed so they stop showing as unbilled.
    for proc in db.execute(
        select(PatientProcedure).where(
            PatientProcedure.claim_id == claim_id, PatientProcedure.is_void.is_(False)
        )
    ).scalars():
        proc.billing_status = "billed"

    db.commit()
    db.refresh(submission)
    return {
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "status": claim.status,
        "batch_id": batch_id,
        "sent_date": sent_date,
        "send_method": payload.get("send_method", "electronic"),
        "submission_id": submission.id,
    }


# ── AUD-3: claim status-change history ───────────────────────────────────────
def claim_status_history(db: Session, claim_id: str, tenant_id: int) -> dict:
    """Auditable timeline of a claim's status transitions, composed from the audit
    log (the middleware records every status/submit POST) plus the claim's own
    lifecycle dates as synthesised events."""
    claim = _get_claim(db, claim_id, tenant_id)

    logs = db.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "insurance-claims",
            AuditLog.resource_id == str(claim_id),
        ).order_by(AuditLog.created_at.asc())
    ).scalars().all()

    actor_ids = {log.user_id for log in logs if log.user_id is not None}
    names = resolve_user_names(db, actor_ids)

    events: list[dict] = []
    for log in logs:
        path = log.path or ""
        if path.endswith("/status") or path.endswith("/submit") or path.endswith("/recalculate"):
            method = "submit" if path.endswith("/submit") else "status_change"
            events.append({
                "status": None,
                "changed_at": log.created_at.isoformat() if log.created_at else None,
                "changed_by": log.user_id,
                "changed_by_name": names.get(log.user_id),
                "method": method,
                "source": "audit_log",
            })

    # Synthesised lifecycle events from the claim's own date columns.
    for label, when in (
        ("submitted", claim.submitted_date), ("paid", claim.paid_date), ("closed", claim.close_date)
    ):
        if when is not None:
            events.append({
                "status": label, "changed_at": when.isoformat() if hasattr(when, "isoformat") else str(when),
                "changed_by": None, "changed_by_name": None, "method": None, "source": "claim_field",
            })

    events.sort(key=lambda e: e["changed_at"] or "")
    return {
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "current_status": claim.status,
        "events": events,
    }


# ── CHG-8: patient insurance summary (carrier names by rank) ─────────────────
_RANK_ORDER = ["primary", "secondary", "tertiary", "quaternary"]


def patient_insurance_summary(db: Session, patient_id: int, tenant_id: int) -> dict:
    _assert_patient_in_tenant(db, patient_id, tenant_id)
    slots = db.execute(
        select(PatientInsurance).where(
            PatientInsurance.patient_id == patient_id, PatientInsurance.is_active.is_(True)
        )
    ).scalars().all()

    plan_ids = {s.ins_plan_id for s in slots if s.ins_plan_id}
    plans = {p.id: p for p in db.execute(
        select(InsurancePlan).where(InsurancePlan.id.in_(plan_ids))
    ).scalars()} if plan_ids else {}
    carrier_ids = {p.carrier_id for p in plans.values() if p.carrier_id}
    carriers = {c.id: c.name for c in db.execute(
        select(InsuranceCarrier).where(InsuranceCarrier.id.in_(carrier_ids))
    ).scalars()} if carrier_ids else {}

    def _rank_of(slot: PatientInsurance) -> str:
        return (slot.insurance_type or "").lower() or "primary"

    ranked: list[dict] = []
    for slot in slots:
        plan = plans.get(slot.ins_plan_id)
        ranked.append({
            "rank": _rank_of(slot),
            "ins_plan_id": slot.ins_plan_id,
            "carrier_id": plan.carrier_id if plan else None,
            "carrier_name": carriers.get(plan.carrier_id) if plan else None,
            "group_number": plan.group_number if plan else None,
            "is_active": slot.is_active,
        })
    ranked.sort(key=lambda r: _RANK_ORDER.index(r["rank"]) if r["rank"] in _RANK_ORDER else 99)

    by_rank = {r["rank"]: r for r in ranked}
    return {
        "patient_id": patient_id,
        "primary": by_rank.get("primary"),
        "secondary": by_rank.get("secondary"),
        "plans": ranked,
    }


# ── CHG-9: today's appointment for the check-out flow ────────────────────────
def todays_appointment(db: Session, patient_id: int, tenant_id: int) -> dict:
    _assert_patient_in_tenant(db, patient_id, tenant_id)
    today = datetime.now(timezone.utc).date()
    appt = db.execute(
        select(Appointment).where(
            Appointment.patient_id == patient_id,
            Appointment.date == today,
            Appointment.is_archived.is_(False),
        ).order_by(Appointment.start_time.asc())
    ).scalars().first()
    if appt is None:
        return {"patient_id": patient_id, "has_appointment": False}
    return {
        "patient_id": patient_id,
        "appointment_id": appt.id,
        "appt_date": appt.date,
        "start_time": appt.start_time.isoformat() if appt.start_time else None,
        "status": appt.status,
        "provider_id": appt.provider_id,
        "operatory_id": appt.operatory_id,
        "has_appointment": True,
    }


# ── CHG-4: expand an explosion code into its procedures ──────────────────────
def expand_explosion_code(
    db: Session, code: str, tenant_id: int, *, office_id: int | None = None
) -> dict:
    stmt = select(ExplosionCode).where(
        ExplosionCode.tenant_id == tenant_id,
        ExplosionCode.code == code,
        ExplosionCode.is_active.is_(True),
    )
    rows = db.execute(stmt).scalars().all()
    # Prefer an office-specific definition, else a tenant-wide (office_id NULL) one.
    header = next((r for r in rows if r.office_id == office_id), None) or next(
        (r for r in rows if r.office_id is None), None
    ) or (rows[0] if rows else None)
    if header is None:
        raise NotFoundError(f"Explosion code '{code}' was not found")

    items = db.execute(
        select(ExplosionCodeItem).where(
            ExplosionCodeItem.explosion_code_id == header.id
        ).order_by(ExplosionCodeItem.display_order.asc(), ExplosionCodeItem.id.asc())
    ).scalars().all()

    proc_codes = {i.procedure_code for i in items}
    descs = {p.code: (p.description, p.default_fee) for p in db.execute(
        select(ProcedureCode).where(ProcedureCode.code.in_(proc_codes))
    ).scalars()} if proc_codes else {}

    procedures = []
    for item in items:
        desc, default_fee = descs.get(item.procedure_code, (None, None))
        procedures.append({
            "procedure_code": item.procedure_code,
            "description": desc,
            "default_fee": item.default_fee if item.default_fee is not None else default_fee,
            "tooth": item.tooth,
            "surface": item.surface,
            "display_order": item.display_order,
        })
    return {
        "explosion_code": header.code,
        "description": header.description,
        "procedures": procedures,
    }
