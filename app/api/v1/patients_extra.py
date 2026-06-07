"""Patients-module supplemental routes (documents, claim detail/lifecycle/attachments,
progress-note sign, duplicate check). Mounted before the generic CRUD routers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.patient_extra import (
    ClaimAttachmentRead,
    ClaimDetailResponse,
    ClaimStatusUpdate,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    PatientDocumentRead,
)
from app.services import patient_extra_service as svc

_auth = [Depends(get_current_user)]
_errs = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

# ── Patient documents ────────────────────────────────────────────────────────
documents_router = APIRouter(prefix="/patient-documents", tags=["Patients"], dependencies=_auth, responses=_errs)


@documents_router.get("", response_model=list[PatientDocumentRead], operation_id="list_patient_documents")
def list_documents(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Query()]):
    return svc.list_documents(db, tenant_id, patient_id)


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


@documents_router.get("/{document_id}", response_model=PatientDocumentRead, operation_id="get_patient_document")
def get_document(db: DbSession, tenant_id: TenantId, document_id: Annotated[int, Path()]):
    return svc.get_document(db, tenant_id, document_id)


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


@claims_router.delete("/{claim_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT,
                      operation_id="delete_claim_attachment")
def delete_claim_attachment(db: DbSession, tenant_id: TenantId, claim_id: Annotated[str, Path()],
                            attachment_id: Annotated[int, Path()]):
    svc.delete_claim_attachment(db, tenant_id, attachment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Progress-note sign ───────────────────────────────────────────────────────
progress_router = APIRouter(prefix="/progress-notes", tags=["Clinical"], dependencies=_auth, responses=_errs)


@progress_router.post("/{note_id}/sign", operation_id="sign_progress_note")
def sign_progress_note(db: DbSession, tenant_id: TenantId, current: CurrentUser, note_id: Annotated[int, Path()]):
    note = svc.sign_progress_note(db, tenant_id, note_id, current.id)
    return {"id": note.id, "signed_by": note.signed_by,
            "signed_at": note.signed_at.isoformat() if note.signed_at else None}


# ── Duplicate check ──────────────────────────────────────────────────────────
dup_router = APIRouter(prefix="/patients", tags=["Patients"], dependencies=_auth, responses=_errs)


@dup_router.post("/check-duplicate", response_model=DuplicateCheckResponse, operation_id="check_patient_duplicate")
def check_duplicate(db: DbSession, tenant_id: TenantId, body: DuplicateCheckRequest):
    return {"candidates": svc.check_duplicate(db, tenant_id, body.model_dump())}
