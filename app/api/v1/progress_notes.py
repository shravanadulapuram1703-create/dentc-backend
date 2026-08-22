"""Progress-notes supplemental routes (progress-notes dev-report gaps).

Generic CRUD over ``/progress-notes`` covers list/create/read/update/delete (the
update path now enforces lock + strike-off audit via ``ProgressNoteCRUD``). This
module adds what the engine can't express:

- **PN-2** ``POST /progress-notes/{note_id}/sign`` — sign as the caller, or as a
  verified provider (optional ``{username, password}`` body).
- **PN-3** ``GET|POST /progress-notes/{note_id}/attachments`` +
  ``DELETE …/{attachment_id}`` — per-note files.
- **PN-6** ``GET /note-macros/categories`` — distinct macro categories.

Registered before the generic routers so literal sub-paths win over ``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, File, Form, Path, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.progress_notes import (
    NoteMacroCategory,
    ProgressNoteAttachmentRead,
    ProgressNoteSignRequest,
    ProgressNoteSignResult,
)
from app.services import progress_notes_service as svc
from app.services.user_admin_service import resolve_user_names

_auth = [Depends(get_current_user)]
_errs = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}

router = APIRouter(prefix="/progress-notes", tags=["Clinical"], dependencies=_auth, responses=_errs)


@router.post("/{note_id}/sign", response_model=ProgressNoteSignResult, operation_id="sign_progress_note",
             summary="Sign a note as the caller, or as a verified provider (PN-2)")
def sign_progress_note(
    db: DbSession, tenant_id: TenantId, current: CurrentUser,
    note_id: Annotated[int, Path()],
    body: Annotated[Optional[ProgressNoteSignRequest], Body()] = None,
):
    creds = body or ProgressNoteSignRequest()
    note = svc.sign_progress_note(
        db, tenant_id, note_id, current.id,
        username=creds.username, password=creds.password,
    )
    name = None
    if note.signed_by is not None:
        name = resolve_user_names(db, {note.signed_by}).get(note.signed_by)
    return ProgressNoteSignResult(
        id=note.id, signed_by=note.signed_by, signed_by_name=name, signed_at=note.signed_at
    )


@router.get("/{note_id}/attachments", response_model=list[ProgressNoteAttachmentRead],
            operation_id="list_progress_note_attachments", summary="List a note's attachments (PN-3)")
def list_attachments(db: DbSession, tenant_id: TenantId, note_id: Annotated[int, Path()]):
    return svc.list_attachments(db, tenant_id, note_id)


@router.post("/{note_id}/attachments", response_model=ProgressNoteAttachmentRead,
             status_code=status.HTTP_201_CREATED, operation_id="upload_progress_note_attachment",
             summary="Attach a file to a note (PN-3)")
async def upload_attachment(
    db: DbSession, tenant_id: TenantId, current: CurrentUser,
    note_id: Annotated[int, Path()],
    file: Annotated[UploadFile, File()],
    attachment_type: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
):
    data = await file.read()
    return svc.create_attachment(
        db, tenant_id, note_id, attachment_type=attachment_type, description=description,
        file_name=file.filename or "attachment", content_type=file.content_type,
        data=data, user_id=current.id,
    )


@router.get(
    "/{note_id}/attachments/{attachment_id}/content",
    operation_id="get_progress_note_attachment_content",
    summary="Stream a note attachment with the caller's tenant checks applied (NOTE-DOC-3)",
    response_class=StreamingResponse,
)
def get_attachment_content(
    db: DbSession, tenant_id: TenantId,
    note_id: Annotated[int, Path()], attachment_id: Annotated[int, Path()],
):
    """Note attachments used to be handed back as a public ``/uploads/...`` URL,
    readable with no token and no tenant check. That mount is gone; this is the
    read path — and it is what ``file_url`` now points at."""
    att, body, content_type, size = svc.open_attachment(db, tenant_id, note_id, attachment_id)
    headers = {"Content-Disposition": f'inline; filename="{att.file_name}"'}
    if size is not None:
        headers["Content-Length"] = str(size)
    return StreamingResponse(
        body, media_type=content_type or "application/octet-stream", headers=headers
    )


@router.delete("/{note_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT,
               operation_id="delete_progress_note_attachment", summary="Remove a note attachment (PN-3)")
def delete_attachment(db: DbSession, tenant_id: TenantId, note_id: Annotated[int, Path()],
                      attachment_id: Annotated[int, Path()]):
    svc.delete_attachment(db, tenant_id, note_id, attachment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── PN-6: macro categories (tagged Procedures to match note-macros CRUD) ──────
macro_router = APIRouter(prefix="/note-macros", tags=["Procedures"], dependencies=_auth, responses=_errs)


@macro_router.get("/categories", response_model=list[NoteMacroCategory],
                  operation_id="list_note_macro_categories",
                  summary="Distinct macro categories for the Category dropdown (PN-6)")
def list_note_macro_categories(db: DbSession, tenant_id: TenantId):
    return svc.note_macro_categories(db, tenant_id)
