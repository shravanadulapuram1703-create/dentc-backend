"""Patients-module supplemental services."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import filestore
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.db.models import (
    ClaimAttachment,
    InsuranceClaim,
    LedgerInsuranceDetail,
    Office,
    Patient,
    PatientConsent,
    PatientDocument,
    PatientProcedure,
    PaymentAllocation,
    Provider,
)
from app.schemas.patient_extra import DuplicateCandidate
from app.services import document_store

# NOTE-DOC-5: the size cap and the type allow-list live in ``filestore`` so every
# upload route enforces one rule set and ``GET /patient-documents/limits`` can
# publish it. (Was a bare 10 MB check here with no type validation at all.)

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
def list_documents(
    db: Session, tenant_id: int, patient_id: int | None = None, *,
    document_type: str | None = None, office_id: int | None = None,
    search: str | None = None, page: int = 1, size: int = 20,
) -> tuple[list[PatientDocument], int]:
    """LTR-12: filtered + paged, matching the rest of the API.

    The Letters history only wants ``document_type=consent-form``; before this it
    had to fetch every document a patient had ever had and filter client-side.
    ``patient_id`` stays optional so an office-wide document search is possible,
    but tenancy is always enforced.
    """
    clauses = [
        PatientDocument.tenant_id == tenant_id,
        PatientDocument.is_deleted.is_(False),
    ]
    if patient_id is not None:
        clauses.append(PatientDocument.patient_id == patient_id)
    if document_type:
        clauses.append(PatientDocument.document_type == document_type)
    if office_id is not None:
        clauses.append(PatientDocument.office_id == office_id)
    if search:
        term = f"%{search.strip()}%"
        clauses.append(or_(
            PatientDocument.file_name.ilike(term),
            PatientDocument.description.ilike(term),
        ))

    total = db.execute(
        select(func.count()).select_from(PatientDocument).where(*clauses)
    ).scalar_one()
    rows = list(db.execute(
        select(PatientDocument).where(*clauses)
        .order_by(PatientDocument.created_at.desc(), PatientDocument.id.desc())
        .offset((max(page, 1) - 1) * size).limit(size)
    ).scalars().all())
    for row in rows:
        _stamp_url(row)
    return rows, total


def _stamp_url(doc: PatientDocument) -> PatientDocument:
    """LTR-1 ask #2: hand back a URL the browser can actually fetch.

    Set on the in-memory row only — a signed URL is short-lived, so persisting it
    would serve an expired link on the next read.
    """
    doc.file_url = document_store.public_url(doc)
    return doc


def get_document(db: Session, tenant_id: int, doc_id: int) -> PatientDocument:
    doc = db.execute(
        select(PatientDocument).where(
            PatientDocument.id == doc_id, PatientDocument.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if doc is None or doc.is_deleted:
        raise NotFoundError(f"Document '{doc_id}' was not found")
    return _stamp_url(doc)


def create_document(
    db: Session, tenant_id: int, patient_id: int, *, office_id: int | None,
    document_type: str | None, description: str | None,
    file_name: str, content_type: str | None, data: bytes, user_id: int | None,
    context: str | None = None,
) -> PatientDocument:
    _require_patient(db, patient_id, tenant_id)
    filestore.validate_upload(file_name, content_type, data)
    # LTR-1 / NOTE-DOC-2: everything lands under the bucket's ``documents/`` root
    # — ``documents/notes/`` when the caller declares ``context=note``, else
    # ``documents/consent-forms/`` for a consent type, else ``documents/general/``.
    # Local disk (same layout) when no bucket is configured.
    stored = document_store.store(
        tenant_id=tenant_id, patient_id=patient_id, document_type=document_type,
        file_name=file_name, content_type=content_type, data=data, context=context,
    )
    doc = PatientDocument(
        tenant_id=tenant_id, patient_id=patient_id, office_id=office_id,
        document_type=document_type, description=description, file_name=file_name,
        content_type=content_type, file_size=len(data),
        file_path=stored.path, file_url=stored.url,
        storage_backend=stored.backend, storage_bucket=stored.bucket,
        storage_path=stored.path,
        created_by=user_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _stamp_url(doc)


def open_document(db: Session, tenant_id: int, doc_id: int):  # noqa: ANN201
    """Streaming body + headers for ``GET /patient-documents/{id}/content``."""
    doc = get_document(db, tenant_id, doc_id)
    try:
        body, content_type, size = document_store.open_stream(doc)
    except FileNotFoundError as exc:  # blob gone / storage unavailable
        raise NotFoundError(f"Document '{doc_id}' content is not available") from exc
    return doc, body, content_type or doc.content_type, size


def delete_document(db: Session, tenant_id: int, doc_id: int) -> None:
    doc = get_document(db, tenant_id, doc_id)
    doc.is_deleted = True
    document_store.delete(doc)
    db.commit()


# ── Consent signing (LTR-10) ─────────────────────────────────────────────────
# The published ``patient_consents.status`` vocabulary. Also seeded as the
# ``consent_status`` definitions group so the FE renders labels from the backend.
CONSENT_STATUSES = ("pending", "printed", "signed", "declined", "voided")
SIGNATURE_METHODS = ("drawn", "scanned", "verbal")

# A drawn signature arrives as a data-URL PNG from a canvas. Cap it: the column is
# TEXT, and an uncapped base64 blob is an easy way to bloat the row.
_MAX_SIGNATURE_CHARS = 512 * 1024


def _require_consent(db: Session, tenant_id: int, consent_id: int) -> PatientConsent:
    row = db.execute(
        select(PatientConsent).where(
            PatientConsent.id == consent_id, PatientConsent.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if row is None or row.is_deleted:
        raise NotFoundError(f"Consent '{consent_id}' was not found")
    return row


def sign_consent(
    db: Session, tenant_id: int, consent_id: int, payload: dict, user_id: int | None,
) -> PatientConsent:
    """Capture a signature against an existing consent row.

    Two routes into the same record, mirroring how a practice actually works:

    * ``signature_data`` — a base64 canvas capture signed on-screen.
    * ``document_id``    — an already-uploaded scan of the wet-signed paper copy,
      which must belong to the same tenant *and* the same patient as the consent.

    One of the two is required unless the caller is recording a ``declined``
    outcome. Signing is idempotent-ish but not silent: re-signing an already
    signed consent is a conflict, because the earlier signature is the record.
    """
    consent = _require_consent(db, tenant_id, consent_id)

    status = (payload.get("status") or "signed").strip().lower()
    if status not in CONSENT_STATUSES:
        raise ValidationError(
            f"status must be one of {', '.join(CONSENT_STATUSES)}", code="invalid_status"
        )

    signature = payload.get("signature_data")
    document_id = payload.get("document_id")
    method = (payload.get("signature_method") or "").strip().lower() or None
    if method and method not in SIGNATURE_METHODS:
        raise ValidationError(
            f"signature_method must be one of {', '.join(SIGNATURE_METHODS)}",
            code="invalid_signature_method",
        )

    if status == "signed":
        if consent.status == "signed":
            raise ConflictError(
                f"Consent '{consent_id}' is already signed", code="already_signed"
            )
        if not signature and document_id is None:
            raise ValidationError(
                "Signing requires either signature_data or document_id",
                code="signature_required",
            )
        if signature and len(signature) > _MAX_SIGNATURE_CHARS:
            raise ValidationError("Signature payload is too large", code="signature_too_large")

    if document_id is not None:
        doc = get_document(db, tenant_id, int(document_id))
        if doc.patient_id != consent.patient_id:
            raise ValidationError(
                "document_id belongs to a different patient", code="document_patient_mismatch"
            )
        consent.document_id = doc.id
        method = method or "scanned"
    elif signature:
        method = method or "drawn"

    if signature:
        consent.signature_data = signature
    consent.status = status
    consent.signature_method = method
    consent.signer_name = payload.get("signer_name") or consent.signer_name
    consent.signer_relationship = payload.get("signer_relationship") or consent.signer_relationship
    consent.declined_reason = payload.get("declined_reason") or consent.declined_reason
    if status in ("signed", "declined"):
        consent.signed_by = user_id
        consent.signed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(consent)
    return consent


# ── Claim attachments ────────────────────────────────────────────────────────
def _require_claim(db: Session, claim_id: str, tenant_id: int) -> InsuranceClaim:
    claim = db.get(InsuranceClaim, claim_id)
    if claim is None:
        raise NotFoundError(f"Claim '{claim_id}' was not found")
    _require_patient(db, claim.patient_id, tenant_id)  # tenancy via the claim's patient
    return claim


def list_claim_attachments(db: Session, tenant_id: int, claim_id: str) -> list[ClaimAttachment]:
    _require_claim(db, claim_id, tenant_id)
    rows = list(db.execute(
        select(ClaimAttachment).where(
            ClaimAttachment.claim_id == claim_id, ClaimAttachment.is_deleted.is_(False)
        ).order_by(ClaimAttachment.created_at.desc())
    ).scalars().all())
    return stamp_claim_attachment_urls(claim_id, rows)


#: INS-PAY-8: the claim attachment-type vocabulary. ``attachment_type`` was free
#: text, so the EOB the Insurance Payment window uploads went up as the literal
#: string ``"EOB"`` with nothing documenting or enforcing that spelling — a
#: second client sending ``"eob"`` or ``"Explanation of Benefits"`` would file it
#: somewhere the EOB lookup never finds. ``scripts/seed_account_definitions.py``
#: seeds these as the ``attachment_type`` definitions group so the picker is
#: driven from the same list.
#:
#: An unrecognised value is stored **as written**, not rejected: the codes below
#: are the ones a dental claim actually carries, but a carrier can ask for
#: something none of them names, and a 422 mid-upload would leave the user with a
#: claim they cannot attach to. Recognised spellings are normalised to the code.
CLAIM_ATTACHMENT_TYPES: dict[str, str] = {
    "EOB": "Explanation of Benefits",
    "XRAY": "Radiograph / X-Ray",
    "PHOTO": "Intraoral Photograph",
    "PERIO": "Periodontal Chart",
    "NARRATIVE": "Narrative / Letter",
    "REFERRAL": "Referral",
    "TXPLAN": "Treatment Plan",
    "PREAUTH": "Pre-authorisation Response",
    "OTHER": "Other",
}

#: Spellings seen in the wild that mean one of the codes above.
_ATTACHMENT_TYPE_ALIASES = {
    "explanation of benefits": "EOB",
    "x-ray": "XRAY", "xray": "XRAY", "radiograph": "XRAY",
    "photograph": "PHOTO", "intraoral photograph": "PHOTO", "image": "PHOTO",
    "perio chart": "PERIO", "periodontal chart": "PERIO", "perio": "PERIO",
    "letter": "NARRATIVE", "narrative": "NARRATIVE",
    "treatment plan": "TXPLAN", "tx plan": "TXPLAN",
    "pre-auth": "PREAUTH", "preauth": "PREAUTH", "pre-authorization": "PREAUTH",
}


def canonical_attachment_type(value: str | None) -> str | None:
    """Normalise a written attachment type to its catalog code (INS-PAY-8)."""
    if value is None:
        return None
    token = value.strip()
    if not token:
        return None
    upper = token.upper()
    if upper in CLAIM_ATTACHMENT_TYPES:
        return upper
    return _ATTACHMENT_TYPE_ALIASES.get(token.lower(), token)


def create_claim_attachment(
    db: Session, tenant_id: int, claim_id: str, *, attachment_type: str | None,
    file_name: str, content_type: str | None, data: bytes, user_id: int | None,
) -> ClaimAttachment:
    _require_claim(db, claim_id, tenant_id)
    filestore.validate_upload(file_name, content_type, data)
    rel, _public = filestore.save_file(f"claim_attachments/{claim_id}", file_name, data)
    att = ClaimAttachment(
        tenant_id=tenant_id, claim_id=claim_id,
        attachment_type=canonical_attachment_type(attachment_type),
        file_name=file_name, content_type=content_type, file_size=len(data),
        # NOTE-DOC-3: file_url is the authenticated /content route, stamped once
        # the row has an id. Never the public /uploads path — this is PHI.
        file_path=rel, file_url="", created_by=user_id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    att.file_url = _claim_attachment_url(claim_id, att.id)
    return att


def _claim_attachment_url(claim_id: str, att_id: int) -> str:
    """The authenticated streaming URL for a claim attachment (NOTE-DOC-3).

    Claim attachments used to be handed back as ``/uploads/...``, served by a
    public static mount with no token and no tenant check. That mount is gone.
    """
    return document_store.absolute_url(
        f"{settings.API_V1_PREFIX}/insurance-claims/{claim_id}/attachments/{att_id}/content"
    )


def stamp_claim_attachment_urls(
    claim_id: str, rows: list[ClaimAttachment],
) -> list[ClaimAttachment]:
    for row in rows:
        row.file_url = _claim_attachment_url(claim_id, row.id)
    return rows


def open_claim_attachment(db: Session, tenant_id: int, claim_id: str, att_id: int):  # noqa: ANN201
    """Body + headers for ``GET /insurance-claims/{id}/attachments/{id}/content``."""
    _require_claim(db, claim_id, tenant_id)
    att = db.execute(
        select(ClaimAttachment).where(
            ClaimAttachment.id == att_id,
            ClaimAttachment.claim_id == claim_id,
            ClaimAttachment.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if att is None or att.is_deleted:
        raise NotFoundError(f"Attachment '{att_id}' was not found")
    try:
        body, size = filestore.open_stream(att.file_path)
    except FileNotFoundError as exc:
        raise NotFoundError(f"Attachment '{att_id}' content is not available") from exc
    return att, body, att.content_type, size


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
