"""Imaging (DICOM archive) API — per-patient viewer for the X-ray/Images tab.

Three routers:
  * ``router``          /patients/{id}/imaging(+/summary)  — authed (bearer)
  * ``instances_router``/dicom-instances/{sop}             — authed (bearer)
  * ``assets_router``   /dicom-instances/{sop}/{thumbnail|web|original}
        — token-authorised (NO bearer), so the URLs work directly in <img>/<a>.
        Redirects to a GCS signed URL in prod, or streams bytes in proxy/dev.

Mounted before the generic CRUD router so these literal paths win. See
docs/imaging/DICOM_IMAGING_API_CONTRACT.md for the frontend wiring contract.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, Request, Response, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import DbSession, TenantId, get_current_user
from app.core.config import settings
from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.logging import get_logger
from app.integrations import object_storage as obj
from app.schemas.common import ErrorResponse
from app.schemas.imaging import (
    DicomInstanceOut,
    PatientImagingResponse,
    PatientImagingSummary,
)
from app.services import audit_service
from app.services import dicom_capture_service as capture_svc
from app.services import imaging_service as svc

logger = get_logger(__name__)

_errs = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

router = APIRouter(prefix="/patients", tags=["Imaging"],
                   dependencies=[Depends(get_current_user)], responses=_errs)
instances_router = APIRouter(prefix="/dicom-instances", tags=["Imaging"],
                             dependencies=[Depends(get_current_user)], responses=_errs)
# NO bearer dependency here — these are authorised by the ?token= query param.
assets_router = APIRouter(prefix="/dicom-instances", tags=["Imaging"], responses=_errs)


@router.get(
    "/{patient_id}/imaging",
    response_model=PatientImagingResponse,
    operation_id="get_patient_imaging",
    summary="Patient imaging tree (studies → series → instances) with ready-to-use image URLs",
)
def get_patient_imaging(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    modality: Annotated[str | None, Query(description="Filter by modality, e.g. IO/PX/XC")] = None,
    tooth: Annotated[int | None, Query(description="Filter to instances tagged with this tooth number")] = None,
    date_from: Annotated[str | None, Query(description="Study date >= YYYY-MM-DD")] = None,
    date_to: Annotated[str | None, Query(description="Study date <= YYYY-MM-DD")] = None,
):
    return svc.get_patient_imaging(
        db, patient_id, tenant_id,
        modality=modality, tooth=tooth, date_from=date_from, date_to=date_to,
    )


@router.post(
    "/{patient_id}/imaging/captures",
    response_model=DicomInstanceOut,
    operation_id="create_patient_imaging_capture",
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a freshly captured image/DICOM file (GCS + Postgres, matched to this patient's imaging history)",
)
async def create_capture(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    file: Annotated[UploadFile, File()],
    modality: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
):
    data = await file.read()
    instance = capture_svc.ingest_capture(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        data=data,
        content_type=file.content_type or "application/octet-stream",
        modality_hint=modality,
        description=description,
    )
    return svc.get_instance_detail(db, instance.sop_instance_uid, tenant_id)


@router.get(
    "/{patient_id}/imaging/summary",
    response_model=PatientImagingSummary,
    operation_id="get_patient_imaging_summary",
    summary="Imaging counts for the tab badge / patient overview",
)
def get_patient_imaging_summary(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    return svc.get_patient_imaging_summary(db, patient_id, tenant_id)


@instances_router.get(
    "/{sop_instance_uid}",
    response_model=DicomInstanceOut,
    operation_id="get_dicom_instance",
    summary="Single image instance metadata + asset URLs",
)
def get_dicom_instance(db: DbSession, tenant_id: TenantId, sop_instance_uid: Annotated[str, Path()]):
    return svc.get_instance_detail(db, sop_instance_uid, tenant_id)


def _serve_asset(db: Session, request: Request, sop_instance_uid: str, kind: str, token: str) -> Response:
    """Shared handler for the three binary endpoints."""
    claim = obj.verify_asset_token(token)
    if claim is None:
        raise UnauthorizedError("Invalid or expired image token", code="invalid_image_token")
    tok_sop, tok_kind, tenant_id = claim
    if tok_sop != sop_instance_uid or tok_kind != kind:
        raise UnauthorizedError("Image token does not match the requested asset",
                                code="image_token_mismatch")

    resolved = svc.resolve_asset(db, sop_instance_uid, kind, tenant_id)
    if resolved is None:
        raise NotFoundError("Image asset is not available yet", code="asset_not_ready")
    stored, _inst = resolved

    if settings.IMAGING_AUDIT_READS:
        try:
            audit_service.write_audit(
                tenant_id=tenant_id, user_id=None, method="GET", path=str(request.url.path),
                status_code=200, ip_address=(request.client.host if request.client else None),
                request_id=getattr(request.state, "request_id", None),
                resource_type="dicom_instance", resource_id=sop_instance_uid,
            )
        except Exception as exc:  # noqa: BLE001 - never break serving on audit
            logger.debug("imaging read audit failed for %s: %s", sop_instance_uid, exc)

    download_name = f"{sop_instance_uid}.dcm" if kind == "original" else None
    # Prod: redirect the browser straight to a short-lived GCS signed URL.
    url = obj.signed_url(stored.bucket, stored.object_key, download_name=download_name)
    if url:
        return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # Proxy/dev: stream the bytes through the API.
    try:
        gen, content_type, size = obj.stream(stored.bucket, stored.object_key)
    except FileNotFoundError as exc:
        raise NotFoundError("Image asset is not available yet", code="asset_not_ready") from exc
    headers = {"Cache-Control": "private, max-age=3600"}
    if download_name:
        headers["Content-Disposition"] = f'inline; filename="{download_name}"'
    if size:
        headers["Content-Length"] = str(size)
    return StreamingResponse(
        gen, media_type=content_type or stored.content_type or "application/octet-stream",
        headers=headers,
    )


@assets_router.get("/{sop_instance_uid}/thumbnail", operation_id="get_dicom_thumbnail",
                   summary="Thumbnail JPEG (token-authorised; use directly in <img src>)")
def get_thumbnail(db: DbSession, request: Request, sop_instance_uid: Annotated[str, Path()],
                  token: Annotated[str, Query()]):
    return _serve_asset(db, request, sop_instance_uid, "thumb", token)


@assets_router.get("/{sop_instance_uid}/web", operation_id="get_dicom_web_image",
                   summary="Full-resolution web JPEG (token-authorised)")
def get_web_image(db: DbSession, request: Request, sop_instance_uid: Annotated[str, Path()],
                  token: Annotated[str, Query()]):
    return _serve_asset(db, request, sop_instance_uid, "web", token)


@assets_router.get("/{sop_instance_uid}/original", operation_id="download_dicom_original",
                   summary="Original .dcm download (token-authorised, audited)")
def download_original(db: DbSession, request: Request, sop_instance_uid: Annotated[str, Path()],
                      token: Annotated[str, Query()]):
    return _serve_asset(db, request, sop_instance_uid, "original", token)
