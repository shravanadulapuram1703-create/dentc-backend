"""Patients-module supplemental services."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select
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
from app.schemas.patient_extra import DuplicateCandidate

_MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB

# Duplicate check: scan a wider window than we return, so scoring (not the SQL
# LIMIT) decides which candidates the user sees.
_SCAN_LIMIT = 200
_MAX_CANDIDATES = 25


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
def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


# Normalised phone comparison. Patient.phone is free-form ("(555) 123-4567",
# "555-123-4567", …) so a literal compare misses; strip the separators in SQL the
# same way appointnow_service does.
def _phone_expr():
    return func.replace(func.replace(func.replace(func.replace(
        Patient.phone, "-", ""), " ", ""), "(", ""), ")", "")


def check_duplicate(db: Session, tenant_id: int, req: dict) -> list[dict]:
    """Candidate existing patients for an about-to-be-created record.

    KAN-108: Quick Save collects name + DOB + *contact details*, so phone/email
    have to be matchable — a repeat patient whose name is spelled differently is
    otherwise invisible. Candidates are scored, sorted and *then* truncated: the
    clauses are OR-ed, so truncating first let a bulk first-name-only match crowd
    out the exact same-person row.
    """
    first, last = (req.get("first_name") or "").strip(), (req.get("last_name") or "").strip()
    dob, ssn, chart_no = req.get("dob"), req.get("ssn"), req.get("chart_no")
    phone, email = (req.get("phone") or "").strip(), (req.get("email") or "").strip()
    phone_digits = _digits(phone)
    if not any([first, last, ssn, chart_no, phone_digits, email]):
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
    if dob:
        conds.append(Patient.dob == dob)
    if phone_digits:
        conds.append(_phone_expr().ilike(f"%{phone_digits}%"))
    if email:
        conds.append(func.lower(Patient.email) == email.lower())
    rows = db.execute(
        select(Patient).where(Patient.tenant_id == tenant_id, or_(*conds)).limit(_SCAN_LIMIT)
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
        match_on: list[str] = []
        if last and (p.last_name or "").lower() == last.lower():
            score += 30
            match_on.append("last_name")
        if first and (p.first_name or "").lower() == first.lower():
            score += 30
            match_on.append("first_name")
        if dob and p.dob == dob:
            score += 25
            match_on.append("dob")
        if ssn and p.ssn == ssn:
            score += 40
            match_on.append("ssn")
        if chart_no and p.chart_no == chart_no:
            score += 40
            match_on.append("chart_no")
        if phone_digits and _digits(p.phone) and phone_digits in _digits(p.phone):
            score += 25
            match_on.append("phone")
        if email and (p.email or "").strip().lower() == email.lower():
            score += 25
            match_on.append("email")
        if not match_on:
            # Matched the OR-clause but nothing survived the exact re-check
            # (e.g. an ``ilike`` wildcard hit) — not a candidate.
            continue
        out.append({
            "id": p.id, "chart_no": p.chart_no, "first_name": p.first_name,
            "last_name": p.last_name, "dob": p.dob, "is_active": p.is_active,
            "match_score": min(score, 100),
            "email": p.email,
            "phone": p.phone,
            "match_on": match_on,
            "is_strong": _is_strong(match_on),
            "home_office_short_id": offices.get(p.home_office_id),
            "preferred_provider_name": providers.get(p.preferred_provider_id),
        })
    out.sort(key=lambda c: (c["is_strong"], c["match_score"]), reverse=True)
    return out[:_MAX_CANDIDATES]


def _is_strong(match_on: list[str]) -> bool:
    """Whether a candidate is near-certainly the same person.

    Deliberately narrower than ``match_score``: this gates the hard 409 on
    registration, so a false positive blocks legitimate work. A shared surname,
    or a household phone shared by a parent and child, must not qualify on its
    own — the full name has to line up as well.
    """
    got = set(match_on)
    if "ssn" in got or "chart_no" in got:
        return True
    full_name = {"first_name", "last_name"} <= got
    return full_name and bool(got & {"dob", "phone", "email"})


def find_strong_duplicates(db: Session, tenant_id: int, req: dict) -> list[dict]:
    """The subset of :func:`check_duplicate` confident enough to block a create.

    Returned JSON-safe: these go into an ``AppError.details`` payload, which the
    exception handler serialises directly rather than through a response model,
    so a raw ``date`` would blow up as a 500. Round-tripping through
    ``DuplicateCandidate`` also keeps the 409 body identical in shape to
    ``POST /patients/check-duplicate``.
    """
    return [
        DuplicateCandidate(**c).model_dump(mode="json")
        for c in check_duplicate(db, tenant_id, req)
        if c["is_strong"]
    ]
