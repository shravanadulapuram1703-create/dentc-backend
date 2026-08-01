"""Patients-module supplemental services."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import filestore
from app.core.config import settings as cfg
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.db.models import (
    ClaimAttachment,
    InsuranceClaim,
    LedgerInsuranceDetail,
    Office,
    Patient,
    PatientDocument,
    PatientProcedure,
    PaymentAllocation,
    Provider,
)

_MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB


def _require_patient(db: Session, patient_id: int, tenant_id: int) -> Patient:
    p = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if p is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return p


# ── Patient documents ────────────────────────────────────────────────────────
def list_documents(db: Session, tenant_id: int, patient_id: int) -> list[PatientDocument]:
    return list(db.execute(
        select(PatientDocument).where(
            PatientDocument.tenant_id == tenant_id,
            PatientDocument.patient_id == patient_id,
            PatientDocument.is_deleted.is_(False),
        ).order_by(PatientDocument.created_at.desc())
    ).scalars().all())


def get_document(db: Session, tenant_id: int, doc_id: int) -> PatientDocument:
    doc = db.execute(
        select(PatientDocument).where(
            PatientDocument.id == doc_id, PatientDocument.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if doc is None or doc.is_deleted:
        raise NotFoundError(f"Document '{doc_id}' was not found")
    return doc


def create_document(
    db: Session, tenant_id: int, patient_id: int, *, office_id: int | None,
    document_type: str | None, description: str | None,
    file_name: str, content_type: str | None, data: bytes, user_id: int | None,
) -> PatientDocument:
    _require_patient(db, patient_id, tenant_id)
    if len(data) > _MAX_UPLOAD:
        raise ValidationError("File exceeds 10 MB limit", code="file_too_large")
    rel, url = filestore.save_file(f"patient_documents/{patient_id}", file_name, data)
    doc = PatientDocument(
        tenant_id=tenant_id, patient_id=patient_id, office_id=office_id,
        document_type=document_type, description=description, file_name=file_name,
        content_type=content_type, file_size=len(data), file_path=rel, file_url=url,
        created_by=user_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def delete_document(db: Session, tenant_id: int, doc_id: int) -> None:
    doc = get_document(db, tenant_id, doc_id)
    doc.is_deleted = True
    filestore.delete_file(doc.file_path)
    db.commit()


# ── Claim attachments ────────────────────────────────────────────────────────
def _require_claim(db: Session, claim_id: str, tenant_id: int) -> InsuranceClaim:
    claim = db.get(InsuranceClaim, claim_id)
    if claim is None:
        raise NotFoundError(f"Claim '{claim_id}' was not found")
    _require_patient(db, claim.patient_id, tenant_id)  # tenancy via the claim's patient
    return claim


def list_claim_attachments(db: Session, tenant_id: int, claim_id: str) -> list[ClaimAttachment]:
    _require_claim(db, claim_id, tenant_id)
    return list(db.execute(
        select(ClaimAttachment).where(
            ClaimAttachment.claim_id == claim_id, ClaimAttachment.is_deleted.is_(False)
        ).order_by(ClaimAttachment.created_at.desc())
    ).scalars().all())


def create_claim_attachment(
    db: Session, tenant_id: int, claim_id: str, *, attachment_type: str | None,
    file_name: str, content_type: str | None, data: bytes, user_id: int | None,
) -> ClaimAttachment:
    _require_claim(db, claim_id, tenant_id)
    if len(data) > _MAX_UPLOAD:
        raise ValidationError("File exceeds 10 MB limit", code="file_too_large")
    rel, url = filestore.save_file(f"claim_attachments/{claim_id}", file_name, data)
    att = ClaimAttachment(
        tenant_id=tenant_id, claim_id=claim_id, attachment_type=attachment_type,
        file_name=file_name, content_type=content_type, file_size=len(data),
        file_path=rel, file_url=url, created_by=user_id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


def delete_claim_attachment(db: Session, tenant_id: int, att_id: int) -> None:
    att = db.execute(
        select(ClaimAttachment).where(
            ClaimAttachment.id == att_id, ClaimAttachment.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if att is None or att.is_deleted:
        raise NotFoundError(f"Attachment '{att_id}' was not found")
    att.is_deleted = True
    filestore.delete_file(att.file_path)
    db.commit()


# ── Composed claim detail + lifecycle ────────────────────────────────────────
def get_claim_detail(db: Session, tenant_id: int, claim_id: str) -> dict:
    claim = _require_claim(db, claim_id, tenant_id)
    procedures = list(db.execute(
        select(PatientProcedure).where(PatientProcedure.claim_id == claim_id)
    ).scalars().all())
    payments = list(db.execute(
        select(PaymentAllocation).where(PaymentAllocation.claim_id == claim_id)
    ).scalars().all())
    coverage = list(db.execute(
        select(LedgerInsuranceDetail).where(LedgerInsuranceDetail.claim_id == claim_id)
    ).scalars().all())
    return {"claim": claim, "procedures": procedures, "payments": payments, "coverage": coverage}


def set_claim_status(db: Session, tenant_id: int, claim_id: str, status: str) -> InsuranceClaim:
    claim = _require_claim(db, claim_id, tenant_id)
    claim.status = status
    today = datetime.now(timezone.utc).date()
    if status == "submitted" and not claim.submitted_date:
        claim.submitted_date = today
    elif status == "paid":
        claim.paid_date = today
    elif status == "closed":
        claim.close_date = today
        claim.is_active = False
    db.commit()
    db.refresh(claim)
    return claim


# Progress-note signing moved to app/services/progress_notes_service.py (PN-2).


# ── Duplicate check ──────────────────────────────────────────────────────────
def check_duplicate(db: Session, tenant_id: int, req: dict) -> list[dict]:
    first, last = (req.get("first_name") or "").strip(), (req.get("last_name") or "").strip()
    dob, ssn, chart_no = req.get("dob"), req.get("ssn"), req.get("chart_no")
    if not any([first, last, ssn, chart_no]):
        return []

    conds = []
    if last:
        conds.append(Patient.last_name.ilike(last))
    if first:
        conds.append(Patient.first_name.ilike(first))
    if ssn:
        conds.append(Patient.ssn == ssn)
    if chart_no:
        conds.append(Patient.chart_no == chart_no)
    rows = db.execute(
        select(Patient).where(Patient.tenant_id == tenant_id, or_(*conds)).limit(25)
    ).scalars().all()

    # BUG-1: batch-resolve the office short-id + provider name so the candidate grid
    # can show enough to tell people apart (was blank client-side).
    office_ids = {p.home_office_id for p in rows if p.home_office_id is not None}
    provider_ids = {p.preferred_provider_id for p in rows if p.preferred_provider_id}
    offices = {o.id: (o.short_id or o.office_code) for o in db.execute(
        select(Office).where(Office.id.in_(office_ids))).scalars()} if office_ids else {}
    providers = {pr.id: pr.name for pr in db.execute(
        select(Provider).where(Provider.id.in_(provider_ids))).scalars()} if provider_ids else {}

    out = []
    for p in rows:
        score = 0
        if last and (p.last_name or "").lower() == last.lower():
            score += 30
        if first and (p.first_name or "").lower() == first.lower():
            score += 30
        if dob and p.dob == dob:
            score += 25
        if ssn and p.ssn == ssn:
            score += 40
        if chart_no and p.chart_no == chart_no:
            score += 40
        out.append({
            "id": p.id, "chart_no": p.chart_no, "first_name": p.first_name,
            "last_name": p.last_name, "dob": p.dob, "is_active": p.is_active,
            "match_score": min(score, 100),
            "email": p.email,
            "home_office_short_id": offices.get(p.home_office_id),
            "preferred_provider_name": providers.get(p.preferred_provider_id),
        })
    out.sort(key=lambda c: c["match_score"], reverse=True)
    return out
