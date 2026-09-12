"""Patient Medical History routes (MH-2/3/4/6/7/8/15).

Mounted before the generic CRUD ``/patients`` and ``/patient-signatures``
routers so the literal sub-paths win over ``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.medical_alerts import MedicalAlertSummary, MedicalAlertSummaryBatch
from app.schemas.patient_catalog import (
    MedicalAlertBulkRequest,
    MedicalAlertBulkResponse,
    QuestionnaireResponseBulkRequest,
    QuestionnaireResponseBulkResponse,
)
from app.schemas.medical_history import (
    MedicalHistoryAudit,
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
from app.services import medical_alert_summary_service as summary_svc
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
# GAP-AP-22: bulk upserts on the two answer resources. Mounted before the
# generic CRUD routers so ``/bulk`` is never read as an ``{item_id}``.
alerts_bulk_router = APIRouter(
    prefix="/patient-medical-alerts", tags=["Patients"],
    dependencies=[Depends(get_current_user)], responses=_errs,
)
responses_bulk_router = APIRouter(
    prefix="/patient-questionnaire-responses", tags=["Patients"],
    dependencies=[Depends(get_current_user)], responses=_errs,
)

PatientPath = Annotated[int, Path(description="patient identifier")]


@alerts_bulk_router.post(
    "/bulk",
    response_model=MedicalAlertBulkResponse,
    operation_id="bulk_upsert_patient_medical_alerts",
    summary="Create/update many medical-alert answers for one patient in one transaction (GAP-AP-22)",
)
def bulk_upsert_medical_alerts(
    db: DbSession, tenant_id: TenantId, current: CurrentUser, body: MedicalAlertBulkRequest,
):
    """Replaces one ``POST /patient-medical-alerts`` per row (~1.2 s each on a
    remote database; ~105 s for a full legacy catalog). Keyed by ``alert_code``:
    an active row for the code is updated in place, otherwise inserted; a null
    ``response`` **and** ``comments`` resets the code to Not Answered. Runs the
    same MH-12 contradiction rules, MA-3 catalog fill, MH-8 change log and MH-14
    flash-alert propagation as the single-row resource. All-or-nothing.
    """
    return svc.bulk_upsert_alerts(
        db, tenant_id, body.patient_id, [i.model_dump(exclude_unset=True) for i in body.items],
        user_id=current.id, allow_contradictions=body.allow_contradictions, replace=body.replace,
    )


@responses_bulk_router.post(
    "/bulk",
    response_model=QuestionnaireResponseBulkResponse,
    operation_id="bulk_upsert_patient_questionnaire_responses",
    summary="Create/update many questionnaire answers for one patient in one transaction (GAP-AP-22)",
)
def bulk_upsert_questionnaire_responses(
    db: DbSession, tenant_id: TenantId, current: CurrentUser,
    body: QuestionnaireResponseBulkRequest,
):
    """Keyed by ``(questionnaire_type, question_code)``; a null ``answer`` resets
    the code to Not Answered. ``replace`` clears the stored codes of every
    questionnaire type *present in the payload* that the payload omits.
    All-or-nothing."""
    return svc.bulk_upsert_responses(
        db, tenant_id, body.patient_id, [i.model_dump(exclude_unset=True) for i in body.items],
        user_id=current.id, replace=body.replace,
    )


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
    "/{patient_id}/medical-history/audit",
    response_model=MedicalHistoryAudit,
    operation_id="get_patient_medical_history_audit",
    summary="Created / Modified stamps (overall + per section) and last-reviewed, server-computed (MH-18)",
)
def medical_history_audit(db: DbSession, tenant_id: TenantId, patient_id: PatientPath):
    """Replaces the five list calls (two of them over soft-deleted rows, capped
    at one page) the header strip was issuing to derive ``min(created_at)`` /
    ``max(updated_at)``. Cleared answers and the field-level change log both
    count, so a removal reads as a modification."""
    svc._patient(db, tenant_id, patient_id)
    return svc.get_audit(db, tenant_id, patient_id)


@router.get(
    "/{patient_id}/medical-alerts/summary",
    response_model=MedicalAlertSummary,
    operation_id="get_patient_medical_alert_summary",
    summary="Active medical alerts (Medical History YES answers + free-text patient alerts) in one call (MA-2)",
)
def medical_alert_summary(db: DbSession, tenant_id: TenantId, patient_id: PatientPath):
    """The shape the Prescriptions banner, the scheduler popover and the
    appointment Details pop-out all read. ``history_on_file`` separates *no
    history* from *no active alerts*; ``comments`` is the Additional Comments
    text (MA-7), so no consumer has to special-case a magic alert row."""
    svc._patient(db, tenant_id, patient_id)
    return summary_svc.summarize_one(db, tenant_id, patient_id)


@metadata_router.get(
    "/medical-alerts/summary",
    response_model=MedicalAlertSummaryBatch,
    operation_id="list_medical_alert_summaries",
    summary="Bulk per-patient alert summaries, ``?patient_ids=1,2,3`` (<= 200) (MA-2)",
)
def medical_alert_summaries(
    db: DbSession,
    tenant_id: TenantId,
    patient_ids: Annotated[str, Query(description="Comma-separated patient ids, at most 200")],
):
    """One request for a whole scheduler day/week instead of two per patient.
    Patients outside the tenant are silently absent from ``items``."""
    ids = svc.parse_patient_ids(patient_ids) or []
    if not ids:
        return {"items": []}
    from sqlalchemy import select  # noqa: PLC0415
    from app.db.models import Patient  # noqa: PLC0415

    valid = [
        pid for (pid,) in db.execute(
            select(Patient.id).where(Patient.id.in_(ids), Patient.tenant_id == tenant_id)
        ).all()
    ]
    summaries = summary_svc.summarize(db, tenant_id, valid)
    return {"items": [summaries[pid] for pid in ids if pid in summaries]}


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
