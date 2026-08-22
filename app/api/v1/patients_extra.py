"""Patients-module supplemental routes (documents, claim detail/lifecycle/attachments,
progress-note sign, duplicate check). Mounted before the generic CRUD routers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, PageParams, TenantId, get_current_user
from app.core import filestore
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.letters import ConsentSignRequest
from app.schemas.patient_extra import (
    ClaimAttachmentRead,
    ClaimDetailResponse,
    ClaimStatusUpdate,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    PatientConsentSignedRead,
    PatientDocumentRead,
    UploadLimits,
)
from app.services import patient_extra_service as svc

_auth = [Depends(get_current_user)]
_errs = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

# ── Patient documents ────────────────────────────────────────────────────────
documents_router = APIRouter(prefix="/patient-documents", tags=["Patients"], dependencies=_auth, responses=_errs)


@documents_router.get(
    "",
    response_model=PaginatedResponse[PatientDocumentRead],
    operation_id="list_patient_documents",
    summary="Patient documents, filtered and paged (LTR-12)",
)
def list_documents(
    db: DbSession,
    tenant_id: TenantId,
    page: PageParams,
    patient_id: Annotated[int | None, Query(description="Scope to one patient")] = None,
    document_type: Annotated[str | None, Query(description="e.g. consent-form")] = None,
    office_id: Annotated[int | None, Query()] = None,
):
    items, total = svc.list_documents(
        db, tenant_id, patient_id,
        document_type=document_type, office_id=office_id,
        search=page.search, page=page.page, size=page.size,
    )
    return PaginatedResponse.build(items, total, page.page, page.size)


@documents_router.post("", response_model=PatientDocumentRead, status_code=status.HTTP_201_CREATED,
                       operation_id="upload_patient_document")
async def upload_document(
    db: DbSession, tenant_id: TenantId, current: CurrentUser,
    file: Annotated[UploadFile, File()],
    patient_id: Annotated[int, Form()],
    office_id: Annotated[int | None, Form()] = None,
    document_type: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
):
    data = await file.read()
    return svc.create_document(
        db, tenant_id, patient_id, office_id=office_id, document_type=document_type,
        description=description, file_name=file.filename or "document",
        content_type=file.content_type, data=data, user_id=current.id,
    )


@documents_router.get(
    "/limits",
    response_model=UploadLimits,
    operation_id="get_patient_document_limits",
    summary="The upload size cap and content-type allow-list the API enforces (NOTE-DOC-5)",
)
def get_document_limits():
    """Published so the file picker states exactly the limits the API enforces.

    Declared before ``/{document_id}`` so the literal path wins over the int
    parameter.
    """
    return filestore.upload_limits()


@documents_router.get("/{document_id}", response_model=PatientDocumentRead, operation_id="get_patient_document")
def get_document(db: DbSession, tenant_id: TenantId, document_id: Annotated[int, Path()]):
    return svc.get_document(db, tenant_id, document_id)


@documents_router.get(
    "/{document_id}/content",
    operation_id="get_patient_document_content",
    summary="Stream a document's bytes with the caller's tenant checks applied (LTR-1)",
    response_class=StreamingResponse,
)
def get_document_content(db: DbSession, tenant_id: TenantId, document_id: Annotated[int, Path()]):
    """The browser-facing read path for documents held in object storage.

    The frontend must never hold bucket credentials and cannot address ``gs://``,
    so either it gets a short-lived signed URL (``file_url``) or it comes here and
    we stream the object after re-checking tenancy.
    """
    doc, body, content_type, size = svc.open_document(db, tenant_id, document_id)
    headers = {"Content-Disposition": f'inline; filename="{doc.file_name}"'}
    if size is not None:
        headers["Content-Length"] = str(size)
    return StreamingResponse(
        body, media_type=content_type or "application/octet-stream", headers=headers
    )


@documents_router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="delete_patient_document")
def delete_document(db: DbSession, tenant_id: TenantId, document_id: Annotated[int, Path()]):
    svc.delete_document(db, tenant_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Claim detail / lifecycle / attachments ───────────────────────────────────
claims_router = APIRouter(prefix="/insurance-claims", tags=["Billing"], dependencies=_auth, responses=_errs)


@claims_router.get("/{claim_id}/detail", response_model=ClaimDetailResponse, operation_id="get_claim_detail")
def get_claim_detail(db: DbSession, tenant_id: TenantId, claim_id: Annotated[str, Path()]):
    return svc.get_claim_detail(db, tenant_id, claim_id)


@claims_router.post("/{claim_id}/status", operation_id="set_claim_status")
def set_claim_status(db: DbSession, tenant_id: TenantId, claim_id: Annotated[str, Path()], body: ClaimStatusUpdate):
    claim = svc.set_claim_status(db, tenant_id, claim_id, body.status)
    return {"id": claim.id, "status": claim.status}


@claims_router.get("/{claim_id}/attachments", response_model=list[ClaimAttachmentRead], operation_id="list_claim_attachments")
def list_claim_attachments(db: DbSession, tenant_id: TenantId, claim_id: Annotated[str, Path()]):
    return svc.list_claim_attachments(db, tenant_id, claim_id)


@claims_router.post("/{claim_id}/attachments", response_model=ClaimAttachmentRead,
                    status_code=status.HTTP_201_CREATED, operation_id="upload_claim_attachment")
async def upload_claim_attachment(
    db: DbSession, tenant_id: TenantId, current: CurrentUser, claim_id: Annotated[str, Path()],
    file: Annotated[UploadFile, File()],
    attachment_type: Annotated[str | None, Form()] = None,
):
    data = await file.read()
    return svc.create_claim_attachment(
        db, tenant_id, claim_id, attachment_type=attachment_type,
        file_name=file.filename or "attachment", content_type=file.content_type,
        data=data, user_id=current.id,
    )


@claims_router.get(
    "/{claim_id}/attachments/{attachment_id}/content",
    operation_id="get_claim_attachment_content",
    summary="Stream a claim attachment with the caller's tenant checks applied (NOTE-DOC-3)",
    response_class=StreamingResponse,
)
def get_claim_attachment_content(
    db: DbSession, tenant_id: TenantId,
    claim_id: Annotated[str, Path()], attachment_id: Annotated[int, Path()],
):
    """Claim attachments used to be handed back as a public ``/uploads/...`` URL,
    readable with no token and no tenant check. That mount is gone; this is the
    read path."""
    att, body, content_type, size = svc.open_claim_attachment(db, tenant_id, claim_id, attachment_id)
    headers = {"Content-Disposition": f'inline; filename="{att.file_name}"'}
    if size is not None:
        headers["Content-Length"] = str(size)
    return StreamingResponse(
        body, media_type=content_type or "application/octet-stream", headers=headers
    )


@claims_router.delete("/{claim_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT,
                      operation_id="delete_claim_attachment")
def delete_claim_attachment(db: DbSession, tenant_id: TenantId, claim_id: Annotated[str, Path()],
                            attachment_id: Annotated[int, Path()]):
    svc.delete_claim_attachment(db, tenant_id, attachment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Progress-note sign + per-note attachments moved to app/api/v1/progress_notes.py
# (PN-2 over-the-shoulder signing + PN-3 attachments).


# ── Consent signing (LTR-10) ─────────────────────────────────────────────────
# The generic CRUD router owns /patient-consents; this adds the one operation the
# resource had no way to express — capturing a signature, from a drawn canvas or
# from an uploaded scan of the wet-signed paper copy.
consents_router = APIRouter(prefix="/patient-consents", tags=["Patients"], dependencies=_auth, responses=_errs)


@consents_router.get(
    "/statuses",
    operation_id="list_patient_consent_statuses",
    summary="The published patient_consents.status vocabulary",
)
def list_consent_statuses():
    return {
        "statuses": list(svc.CONSENT_STATUSES),
        "signature_methods": list(svc.SIGNATURE_METHODS),
    }


@consents_router.post(
    "/{consent_id}/sign",
    response_model=PatientConsentSignedRead,
    operation_id="sign_patient_consent",
    summary="Attach a signature (drawn capture or scanned copy) to a consent record",
)
def sign_consent(
    db: DbSession, tenant_id: TenantId, current: CurrentUser,
    consent_id: Annotated[int, Path()], body: ConsentSignRequest,
):
    return svc.sign_consent(db, tenant_id, consent_id, body.model_dump(exclude_unset=True), current.id)


# ── Duplicate check ──────────────────────────────────────────────────────────
dup_router = APIRouter(prefix="/patients", tags=["Patients"], dependencies=_auth, responses=_errs)


@dup_router.post("/check-duplicate", response_model=DuplicateCheckResponse, operation_id="check_patient_duplicate")
def check_duplicate(db: DbSession, tenant_id: TenantId, body: DuplicateCheckRequest):
    return {"candidates": svc.check_duplicate(db, tenant_id, body.model_dump())}
