"""Patients-module supplemental services."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import filestore
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.db.models import (
    User,
    ConsentSignature,
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
from app.services import signature_service as sig_svc

# NOTE-DOC-5: the size cap and the type allow-list live in ``filestore`` so every
# upload route enforces one rule set and ``GET /patient-documents/limits`` can
# publish it. (Was a bare 10 MB check here with no type validation at all.)

# Duplicate check: scan a wider window than we return, so scoring (not the SQL
# LIMIT) decides which candidates the user sees.
_SCAN_LIMIT = 200
_MAX_CANDIDATES = 25


def _validate_document_links(
    db: Session, patient_id: int, procedure_id: str | None, claim_id: str | None,
) -> tuple[str | None, str | None]:
    """PROC-7c: a document tied to a procedure/claim renders inside *that*
    patient's chart and counts toward *that* charge's ``requires_attachment``,
    so a mis-pointed id is both a PHI disclosure and a false "attached" — 422,
    never a silent write. Blank strings (a multipart form's way of saying
    "none") are treated as absent."""
    procedure_id = (procedure_id or "").strip() or None
    claim_id = (claim_id or "").strip() or None
    if procedure_id is not None:
        proc = db.get(PatientProcedure, procedure_id)
        if proc is None or proc.patient_id != patient_id:
            raise ValidationError(
                "procedure_id does not belong to this patient",
                details={"code": "document_procedure_mismatch", "field": "procedure_id",
                         "procedure_id": procedure_id, "patient_id": patient_id},
            )
        if claim_id is None and proc.claim_id:
            claim_id = proc.claim_id  # a document on a claimed charge is on its claim too
    if claim_id is not None:
        claim = db.get(InsuranceClaim, claim_id)
        if claim is None or claim.patient_id != patient_id:
            raise ValidationError(
                "claim_id does not belong to this patient",
                details={"code": "document_claim_mismatch", "field": "claim_id",
                         "claim_id": claim_id, "patient_id": patient_id},
            )
    return procedure_id, claim_id


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
    procedure_id: str | None = None, claim_id: str | None = None,
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
    if procedure_id:
        clauses.append(PatientDocument.procedure_id == procedure_id)
    if claim_id:
        clauses.append(PatientDocument.claim_id == claim_id)
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
    context: str | None = None, procedure_id: str | None = None, claim_id: str | None = None,
) -> PatientDocument:
    _require_patient(db, patient_id, tenant_id)
    procedure_id, claim_id = _validate_document_links(db, patient_id, procedure_id, claim_id)
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
        procedure_id=procedure_id, claim_id=claim_id,
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
# SIG-5: the vocabulary lives once in signature_service (``topaz`` added).
SIGNATURE_METHODS = sig_svc.SIGNATURE_METHODS

# A drawn signature arrives as a data-URL PNG from a canvas. Cap it: the column is
# TEXT, and an uncapped base64 blob is an easy way to bloat the row.
_MAX_SIGNATURE_CHARS = sig_svc.MAX_SIGNATURE_CHARS


def _require_consent(db: Session, tenant_id: int, consent_id: int) -> PatientConsent:
    row = db.execute(
        select(PatientConsent).where(
            PatientConsent.id == consent_id, PatientConsent.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if row is None or row.is_deleted:
        raise NotFoundError(f"Consent '{consent_id}' was not found")
    return row


def _resolve_countersigner(db: Session, tenant_id: int, item: dict) -> tuple[int | None, str | None]:
    user_id = item.get("signer_user_id")
    provider_id = item.get("signer_provider_id")
    if user_id is not None:
        user = db.get(User, int(user_id))
        if user is None or user.tenant_id != tenant_id:
            raise ValidationError("signer_user_id does not name a user in this practice",
                                  code="countersigner_not_found", details={"field": "signer_user_id"})
    if provider_id is not None:
        provider = db.get(Provider, str(provider_id))
        if provider is None or provider.tenant_id != tenant_id:
            raise ValidationError("signer_provider_id does not name a provider in this practice",
                                  code="countersigner_not_found", details={"field": "signer_provider_id"})
    return (int(user_id) if user_id is not None else None,
            str(provider_id) if provider_id is not None else None)


def _add_countersign(db: Session, tenant_id: int, consent: PatientConsent, item: dict,
                     user_id: int | None) -> ConsentSignature:
    """CS-2: one countersignature line (dentist / hygienist / …) on a consent."""
    role = (item.get("role") or "").strip().lower().replace(" ", "_")
    if role not in sig_svc.CONSENT_COUNTERSIGN_ROLES:
        raise ValidationError(
            f"role must be one of {', '.join(sig_svc.CONSENT_COUNTERSIGN_ROLES)}",
            code="invalid_countersign_role", details={"field": "role", "value": role},
        )
    if not (item.get("signature_data") or "").strip():
        raise ValidationError("A countersignature needs signature_data", code="signature_required",
                              details={"field": "signature_data", "role": role})
    signer_user_id, signer_provider_id = _resolve_countersigner(db, tenant_id, item)
    capture = sig_svc.normalise_capture(item)
    signed_at, _source = sig_svc.resolve_signed_at(item.get("signed_at"))
    row = ConsentSignature(
        tenant_id=tenant_id, consent_id=consent.id, role=role,
        signer_user_id=signer_user_id, signer_provider_id=signer_provider_id,
        signer_name=(item.get("signer_name") or "").strip()[:120] or None,
        captured_at=capture.get("signed_at") if item.get("signed_at") is not None else None,
        content_hash=sig_svc.consent_content_hash(consent.rendered_html),
        is_active=True, created_by=user_id,
    )
    sig_svc.apply_capture(row, capture)
    row.signed_at = signed_at
    db.add(row)
    db.flush()
    sig_svc.record_event(
        db, tenant_id=tenant_id, entity_type=sig_svc.ENTITY_CONSENT_SIGNATURE, entity_id=row.id,
        event=sig_svc.EVENT_CAPTURED, actor_id=user_id, patient_id=consent.patient_id, source=row,
        signature_type=f"consent_{role}", content_hash=row.content_hash,
        occurred_at=row.signed_at, reason=f"consent {consent.id}",
    )
    return row


def add_countersign(db: Session, tenant_id: int, consent_id: int, payload: dict,
                    user_id: int | None) -> ConsentSignature:
    """``POST /patient-consents/{id}/countersign`` — a line signed after the
    patient's (the stored flow), on any consent that is not declined / voided."""
    consent = _require_consent(db, tenant_id, consent_id)
    if consent.status in ("declined", "voided"):
        raise ConflictError(f"Consent '{consent_id}' is {consent.status}; it cannot be countersigned",
                            code="consent_not_signable")
    row = _add_countersign(db, tenant_id, consent, payload, user_id)
    db.commit()
    db.refresh(row)
    return row


def list_consent_signatures(db: Session, tenant_id: int, consent_id: int) -> list[ConsentSignature]:
    _require_consent(db, tenant_id, consent_id)
    return list(db.execute(
        select(ConsentSignature).where(ConsentSignature.consent_id == consent_id)
        .order_by(ConsentSignature.id)
    ).scalars().all())


def void_countersign(db: Session, tenant_id: int, consent_id: int, signature_id: int,
                     user_id: int | None, reason: str | None) -> ConsentSignature:
    _require_consent(db, tenant_id, consent_id)
    row = db.get(ConsentSignature, signature_id)
    if row is None or row.consent_id != consent_id or row.tenant_id != tenant_id:
        raise NotFoundError(f"Consent signature '{signature_id}' was not found")
    if not row.is_active:
        raise ValidationError("This countersignature has already been voided",
                              code="signature_already_inactive")
    row.is_active = False
    row.voided_at = datetime.now(timezone.utc)
    row.voided_by = user_id
    sig_svc.record_event(
        db, tenant_id=tenant_id, entity_type=sig_svc.ENTITY_CONSENT_SIGNATURE, entity_id=row.id,
        event=sig_svc.EVENT_VOIDED, actor_id=user_id, patient_id=None, source=row,
        signature_type=f"consent_{row.role}", content_hash=row.content_hash, reason=reason,
    )
    db.commit()
    db.refresh(row)
    return row


def sign_consent(
    db: Session, tenant_id: int, consent_id: int, payload: dict, user_id: int | None,
) -> PatientConsent:
    """Capture a signature against an existing consent row.

    Routes into the same record, mirroring how a practice actually works:

    * ``signature_data`` — the pad / canvas capture (+ the Topaz block).
    * ``document_id``    — an already-uploaded scan of the wet-signed paper copy.
    * ``signed_document_id`` (CS-1) — the PDF rebuilt with the signature stamped
      on the lines, kept *beside* ``document_id``; sent together with
      ``signature_data`` in both viewer flows.
    * ``countersigns[]`` (CS-2) — the dentist / hygienist / … lines.

    Every document must belong to the same tenant *and* patient as the consent.
    One of signature / document is required unless the caller records a
    ``declined`` outcome. Re-signing an already signed consent is a conflict,
    because the earlier signature is the record. **CS-7**: the signer is any user
    of the practice — never required to be the consent's ``created_by``; a
    hygienist signs what the front desk printed.
    """
    consent = _require_consent(db, tenant_id, consent_id)

    status = (payload.get("status") or "signed").strip().lower()
    if status not in CONSENT_STATUSES:
        raise ValidationError(
            f"status must be one of {', '.join(CONSENT_STATUSES)}", code="invalid_status"
        )

    signature = payload.get("signature_data")
    document_id = payload.get("document_id")
    signed_document_id = payload.get("signed_document_id")
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
        if not signature and document_id is None and signed_document_id is None:
            raise ValidationError(
                "Signing requires signature_data, document_id or signed_document_id",
                code="signature_required",
            )
        if signature and len(signature) > _MAX_SIGNATURE_CHARS:
            raise ValidationError("Signature payload is too large", code="signature_too_large")

    # SIG-1/2/3/8: validate + default the Topaz block (encrypts the SigString,
    # refuses an empty pad, stamps the workstation) before anything is written.
    capture = sig_svc.normalise_capture(payload)
    is_topaz = bool(capture.get("sig_string")) or capture.get("device_source") == sig_svc.DEVICE_SOURCE_TOPAZ

    def _same_patient_document(doc_id, field: str):  # noqa: ANN001, ANN202
        doc = get_document(db, tenant_id, int(doc_id))
        if doc.patient_id != consent.patient_id:
            raise ValidationError(
                f"{field} belongs to a different patient", code="document_patient_mismatch",
                details={"field": field},
            )
        return doc

    if document_id is not None:
        consent.document_id = _same_patient_document(document_id, "document_id").id
    if signed_document_id is not None:
        consent.signed_document_id = _same_patient_document(signed_document_id, "signed_document_id").id
    # The method follows the capture, not the presence of a scan: a pad
    # signature that also hands over its signed PDF is still ``topaz``.
    if signature:
        method = method or ("topaz" if is_topaz else "drawn")
    elif document_id is not None:
        method = method or "scanned"

    if signature:
        consent.signature_data = signature
        capture.pop("signature_data", None)
    # CS-3: the client's capture time is honoured within tolerance; the raw
    # value is kept either way.
    client_signed_at = payload.get("signed_at")
    signed_at, signed_at_source = sig_svc.resolve_signed_at(client_signed_at)
    capture.pop("signed_at", None)
    sig_svc.apply_capture(consent, capture)
    consent.status = status
    consent.signature_method = method
    consent.signer_name = payload.get("signer_name") or consent.signer_name
    consent.signer_relationship = payload.get("signer_relationship") or consent.signer_relationship
    consent.declined_reason = payload.get("declined_reason") or consent.declined_reason
    if status in ("signed", "declined"):
        consent.signed_by = user_id
        consent.signed_at = signed_at
        consent.signed_at_source = signed_at_source
        consent.captured_at = (
            sig_svc.resolve_signed_at(client_signed_at, tolerance_minutes=10 ** 9)[0]
            if client_signed_at is not None else None
        )
    if status == "signed":
        # SIG-7: freeze what was signed. An edit to rendered_html afterwards
        # reads as ``signature_status="stale"`` instead of silently re-attesting.
        # CS-4: and keep the as-signed HTML itself, immutable.
        consent.content_hash = sig_svc.consent_content_hash(consent.rendered_html)
        consent.signed_rendered_html = consent.rendered_html
    event = {"signed": sig_svc.EVENT_CAPTURED, "declined": sig_svc.EVENT_DECLINED,
             "voided": sig_svc.EVENT_VOIDED}.get(status)
    if event is not None:
        sig_svc.record_event(
            db, tenant_id=tenant_id, entity_type=sig_svc.ENTITY_PATIENT_CONSENT,
            entity_id=consent.id, event=event, actor_id=user_id, patient_id=consent.patient_id,
            source=consent, signature_type="consent", content_hash=consent.content_hash,
            reason=consent.declined_reason if status == "declined" else None,
            occurred_at=consent.signed_at,
        )
    # CS-2: the countersign lines captured in the same sitting.
    for item in payload.get("countersigns") or []:
        _add_countersign(db, tenant_id, consent, dict(item), user_id)
    db.commit()
    db.refresh(consent)
    sig_svc.enrich_patient_consents(db, [consent], tenant_id)
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


# GAP-AP-21: identifiers that are placeholders, not identities. The dev/UAT
# data holds SSN ``123456789`` on nine patients and chart ``123456`` on more;
# any single one of them used to block *every* later registration with a 409,
# because a lone SSN/chart match counted as a certain duplicate. A value that
# cannot identify anyone is never matched on at all — not in the SQL, not in
# the score — so ``check_duplicate`` never reports it and the 409 never fires.
_SYNTHETIC_DIGIT_RUNS = frozenset({
    "123456789", "987654321", "12345678", "1234567", "123456", "12345", "1234",
    "0123456789", "1234567890",
    "078051120",  # the 1938 Woolworth wallet-card SSN, the most-used SSN ever
    "219099999",  # the SSA's advertised never-issued number
})


def is_synthetic_identifier(value: str | None) -> bool:
    """True when ``value`` is an obvious placeholder (all one digit, a keyboard
    run, the famous never-issued SSNs) or too short to identify anyone."""
    text = (value or "").strip()
    if not text:
        return True
    if any(ch.isalpha() for ch in text):
        # ``CH-DUP1``, ``A1``: an alphanumeric chart number is a real identifier
        # however few digits it carries; the digit heuristics below are for
        # purely numeric values, where "1234" really is a placeholder.
        return False
    digits = _digits(text)
    if not digits:
        return True  # punctuation only
    if len(digits) < 4:
        return True
    if len(set(digits)) == 1:  # 000000000, 111111111, 999999999 …
        return True
    if digits in _SYNTHETIC_DIGIT_RUNS:
        return True
    # SSA rules: area 000/666/9xx and a 00 group or 0000 serial are never issued.
    if len(digits) == 9:
        area, group, serial = digits[:3], digits[3:5], digits[5:]
        if area in ("000", "666") or area.startswith("9") or group == "00" or serial == "0000":
            return True
    return False


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
    # GAP-AP-21: a placeholder identifier matches nothing.
    if is_synthetic_identifier(ssn):
        ssn = None
    if is_synthetic_identifier(chart_no):
        chart_no = None
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

    GAP-AP-21: an SSN or chart-number match needs *one* corroborating field
    (last name or DOB). Placeholders are already filtered out before matching,
    so what reaches here is a real-looking value — but ``chart_no`` is not
    unique in the migrated data (10,045 duplicated groups) and a mistyped SSN
    is far more common than two records for one person under different names
    and birthdays. Such a hit is still *reported* (``match_on``/score), so the
    user sees it; it just does not refuse the registration on its own.
    """
    got = set(match_on)
    corroborated = bool(got & {"last_name", "dob"})
    if ("ssn" in got or "chart_no" in got) and corroborated:
        return True
    full_name = {"first_name", "last_name"} <= got
    return full_name and bool(got & {"dob", "phone", "email"})


def raise_if_duplicate(db: Session, tenant_id: int, payload: dict, *, force_create: bool) -> None:
    """The one 409 both create paths raise (GAP-AP-21).

    ``POST /patients`` and ``POST /patients/register`` used to disagree: the
    composite refused a strong match and the plain create accepted the identical
    body, so the guard was bypassed by the very endpoint the frontend fell back
    to. The body shape (``error.details.candidates[]``) is what the UI's
    "Identical Patients Found" modal consumes — keep it stable.
    """
    if force_create:
        return
    dupes = find_strong_duplicates(db, tenant_id, payload)
    if dupes:
        raise ConflictError(
            "A patient matching these details already exists.",
            code="duplicate_patient",
            details={"candidates": dupes, "override_field": "force_create"},
        )


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
