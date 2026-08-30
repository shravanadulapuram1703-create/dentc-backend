"""Patient Medical History routes (MH-2/3/4/6/7/8/15).

Mounted before the generic CRUD ``/patients`` and ``/patient-signatures``
routers so the literal sub-paths win over ``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.medical_history import (
    MedicalHistoryChange,
    MedicalHistoryCopyRequest,
    MedicalHistoryDocument,
    MedicalHistoryRules,
    MedicalHistorySaveRequest,
    MedicalHistorySignRequest,
    MedicalHistorySignature,
    MedicalHistoryVersion,
    MedicalHistoryVersionDetail,
    SignatureVoidRequest,
)
from app.services import medical_history_rules as rules_svc
from app.services import medical_history_service as svc

_errs = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}

router = APIRouter(
    prefix="/patients", tags=["Patients"],
    dependencies=[Depends(get_current_user)], responses=_errs,
)
signature_router = APIRouter(
    prefix="/patient-signatures", tags=["Patients"],
    dependencies=[Depends(get_current_user)], responses=_errs,
)
metadata_router = APIRouter(
    tags=["Patients"], dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}},
)

PatientPath = Annotated[int, Path(description="patient identifier")]


@router.get(
    "/{patient_id}/medical-history",
    response_model=MedicalHistoryDocument,
    operation_id="get_patient_medical_history",
    summary="Medical alerts, both questionnaires, emergency contacts, signatures and the resolved catalogs in one call (MH-2)",
)
def get_medical_history(db: DbSession, tenant_id: TenantId, patient_id: PatientPath):
    """Replaces the nine-plus request open (four row listings, the overview, three
    ``/definition-groups`` reads and one ``/definitions`` per group).

    ``catalog_sources`` says whether each catalog came from the tenant's seeded
    ``definitions`` or from the server's built-in legacy list, so a client never
    has to carry its own copy or guess whether a stray test group is real (MH-1).
    """
    return svc.get_document(db, tenant_id, patient_id)


@router.put(
    "/{patient_id}/medical-history",
    response_model=MedicalHistoryDocument,
    operation_id="save_patient_medical_history",
    summary="Save the whole medical-history document in one transaction (MH-3)",
    responses={
        422: {
            "model": ErrorResponse,
            "description": (
                "`contradictory_medical_alerts` — the merged answers break a rule "
                "published at `GET /metadata/medical-history-rules`. `error.details."
                "contradictions` names the rule and the conflicting codes; resubmit "
                "with `allow_contradictions: true` to store it anyway."
            ),
        },
    },
)
def save_medical_history(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    patient_id: PatientPath,
    body: MedicalHistorySaveRequest,
):
    """One transaction for the whole document — legacy's **NO TO ALL ALERTS**
    stops being ~90 sequential POSTs through a six-connection browser pool, and a
    tab closed mid-save can no longer leave a half-written medical history."""
    return svc.save_document(
        db, tenant_id, patient_id, body.model_dump(exclude_unset=True), user_id=current.id
    )


@router.post(
    "/{patient_id}/medical-history/copy-from/{source_patient_id}",
    response_model=MedicalHistoryDocument,
    operation_id="copy_patient_medical_history",
    summary="Copy another chart's medical history onto this patient (MH-4)",
)
def copy_medical_history(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    patient_id: PatientPath,
    source_patient_id: Annotated[int, Path(description="chart to copy from")],
    body: MedicalHistoryCopyRequest | None = None,
):
    """Atomic and attributable. The client-side implementation was ~90 reads then
    ~90 writes with nothing recording where the answers came from; every copied
    row now lands in the change log naming the source chart, and the version row
    carries ``source_patient_id``/``copied_at``."""
    payload = body or MedicalHistoryCopyRequest()
    return svc.copy_from(
        db, tenant_id, patient_id, source_patient_id,
        scope=payload.scope, user_id=current.id,
        allow_contradictions=payload.allow_contradictions,
    )


@router.post(
    "/{patient_id}/medical-history/sign",
    response_model=MedicalHistoryDocument,
    status_code=status.HTTP_201_CREATED,
    operation_id="sign_patient_medical_history",
    summary="Capture a signature over a frozen version of this medical history (MH-6)",
)
def sign_medical_history(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    patient_id: PatientPath,
    body: MedicalHistorySignRequest,
):
    """Freezes the answers into a version (``medical_history_records`` +
    ``medical_history_details``) and stamps the same ``content_hash`` on the
    signature, so a later edit flips ``signature_status`` to ``stale`` instead of
    leaving a signature that silently no longer matches what it attests to."""
    return svc.sign(db, tenant_id, patient_id, body.model_dump(exclude_unset=True),
                    user_id=current.id)


@router.get(
    "/{patient_id}/medical-history/versions",
    response_model=list[MedicalHistoryVersion],
    operation_id="list_patient_medical_history_versions",
    summary="Signed / completed versions of this medical history (MH-6/16)",
)
def list_versions(db: DbSession, tenant_id: TenantId, patient_id: PatientPath):
    return svc.list_versions(db, tenant_id, patient_id)


@router.get(
    "/{patient_id}/medical-history/versions/{version_id}",
    response_model=MedicalHistoryVersionDetail,
    operation_id="get_patient_medical_history_version",
    summary="One frozen version with the answers as they stood when signed (MH-6)",
)
def get_version(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: PatientPath,
    version_id: Annotated[int, Path(description="medical-history version identifier")],
):
    return svc.get_version(db, tenant_id, patient_id, version_id)


@router.get(
    "/{patient_id}/medical-history/changes",
    response_model=list[MedicalHistoryChange],
    operation_id="list_patient_medical_history_changes",
    summary="Append-only, field-level change log for this patient's answers (MH-8)",
)
def list_changes(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: PatientPath,
    entity_type: Annotated[
        str | None,
        Query(description="alert | dental | medical | comments | signature | copy"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    """``audit_logs`` records one row per request, which for the composite write
    is a single entry for a whole document. A medical record has to be able to
    answer "who changed *this answer* and when"."""
    return svc.list_changes(db, tenant_id, patient_id, entity_type=entity_type, limit=limit)


@router.get(
    "/{patient_id}/medical-history/pdf",
    operation_id="get_patient_medical_history_pdf",
    summary="Server-rendered medical-history form (MH-15)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Medical history PDF"}},
)
def medical_history_pdf(db: DbSession, tenant_id: TenantId, patient_id: PatientPath):
    pdf = svc.render_pdf(db, tenant_id, patient_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="medical-history-{patient_id}.pdf"'
        },
    )


@signature_router.post(
    "/{signature_id}/void",
    response_model=MedicalHistorySignature,
    operation_id="void_patient_signature",
    summary="Void / clear a captured signature (MH-7)",
)
def void_signature(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    signature_id: Annotated[int, Path(description="signature identifier")],
    body: SignatureVoidRequest | None = None,
):
    """Signatures were append-only with no supersede, so a *cleared* signature
    could not be represented at all. Voiding keeps the row and its audit trail."""
    return svc.void_signature(
        db, tenant_id, signature_id, user_id=current.id,
        reason=(body.reason if body else None),
    )


@metadata_router.get(
    "/metadata/medical-history-rules",
    response_model=MedicalHistoryRules,
    operation_id="get_medical_history_rules",
    summary="Answer vocabulary (MH-5) and contradiction rules (MH-12) the API enforces",
)
def medical_history_rules():
    """Published so the form can grey out the boxes from the same table the
    server validates against — a rule added in ``medical_history_rules`` reaches
    the UI without a frontend release."""
    return rules_svc.published_rules()
