"""Letters module routes (LTR-1 #4, LTR-5, LTR-6).

* ``/letters/merge-fields``      — the authoritative 56-token merge catalog.
* ``/letters/render``            — server-side merge for one patient.
* ``/letters/render-batch``      — the same across a patient list, as a job.
* ``/letters/batches[/{id}]``    — the durable run records.
* ``/patients/{id}/letter-context`` — the whole merge context in one call.
* ``/consent-forms``             — blank consent masters in the storage bucket.

Mounted before the generic CRUD router so ``/letters/...`` and the literal
``/patients/{id}/letter-context`` sub-path win over ``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentUser, DbSession, PageParams, TenantId, get_current_user
from app.core.config import settings
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.letters import (
    ConsentFormList,
    LetterBatchRequest,
    LetterBatchResponse,
    LetterBatchRunRead,
    LetterContextResponse,
    LetterRenderRequest,
    LetterRenderResponse,
    MergeFieldCatalog,
)
from app.services import document_store
from app.services import letter_service as svc

_auth = [Depends(get_current_user)]
_errs = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

router = APIRouter(prefix="/letters", tags=["Communications"], dependencies=_auth, responses=_errs)
patient_router = APIRouter(prefix="/patients", tags=["Communications"], dependencies=_auth, responses=_errs)
consent_forms_router = APIRouter(tags=["Communications"], dependencies=_auth, responses=_errs)


# ── LTR-5: merge catalog + render ────────────────────────────────────────────
@router.get(
    "/merge-fields",
    response_model=MergeFieldCatalog,
    operation_id="list_letter_merge_fields",
    summary="The authoritative merge-field catalog every letter template can use",
)
def list_merge_fields():
    return {"fields": svc.merge_field_catalog()}


@router.post(
    "/render",
    response_model=LetterRenderResponse,
    operation_id="render_letter",
    summary="Merge one letter template for one patient (server-side)",
)
def render_letter(db: DbSession, tenant_id: TenantId, body: LetterRenderRequest):
    return svc.render_template(
        db, tenant_id,
        template_id=body.template_id, patient_id=body.patient_id,
        office_id=body.office_id, treatment_plan_id=body.treatment_plan_id,
    )


@router.post(
    "/render-batch",
    response_model=LetterBatchResponse,
    operation_id="render_letter_batch",
    summary="Run one template across a patient list (the CS001..CS009 collection sweeps)",
)
def render_letter_batch(
    db: DbSession, tenant_id: TenantId, current: CurrentUser, body: LetterBatchRequest,
):
    run = svc.run_batch(
        db, tenant_id,
        template_id=body.template_id, patient_ids=body.patient_ids,
        office_id=body.office_id, store_html=body.store_html, user_id=current.id,
    )
    _run, items = svc.get_batch(db, tenant_id, run.id)
    return {"batch": run, "items": items}


@router.get(
    "/batches",
    response_model=PaginatedResponse[LetterBatchRunRead],
    operation_id="list_letter_batches",
)
def list_letter_batches(
    db: DbSession, tenant_id: TenantId, page: PageParams,
    template_id: Annotated[int | None, Query()] = None,
    office_id: Annotated[int | None, Query()] = None,
):
    items, total = svc.list_batches(
        db, tenant_id, template_id=template_id, office_id=office_id,
        page=page.page, size=page.size,
    )
    return PaginatedResponse.build(items, total, page.page, page.size)


@router.get(
    "/batches/{batch_id}",
    response_model=LetterBatchResponse,
    operation_id="get_letter_batch",
)
def get_letter_batch(db: DbSession, tenant_id: TenantId, batch_id: Annotated[int, Path()]):
    run, items = svc.get_batch(db, tenant_id, batch_id)
    return {"batch": run, "items": items}


# ── LTR-6: aggregate merge context ───────────────────────────────────────────
@patient_router.get(
    "/{patient_id}/letter-context",
    response_model=LetterContextResponse,
    operation_id="get_patient_letter_context",
    summary="Everything a letter merge needs for this patient, in one round trip",
)
def get_letter_context(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    office_id: Annotated[int | None, Query(description="Printing office (default: home office)")] = None,
    treatment_plan_id: Annotated[str | None, Query(description="Binds #TX_PLAN_TH_NUMBER# (LTR-4)")] = None,
    include_balance: Annotated[bool, Query(
        description="Run the account-balance aggregate (needed only by #RP_TOTAL_BAL# templates)"
    )] = False,
):
    ctx = svc.build_context(
        db, tenant_id, patient_id,
        office_id=office_id, treatment_plan_id=treatment_plan_id,
        include_balance=include_balance,
    )
    values = svc.resolve_merge_fields(ctx)
    return {
        **ctx,
        "merge_fields": values,
        "unresolved_tokens": sorted(k for k, v in values.items() if not v),
    }


# ── LTR-1 #4: blank consent masters living in the bucket ─────────────────────
@consent_forms_router.get(
    "/consent-forms",
    response_model=ConsentFormList,
    operation_id="list_consent_forms",
    summary="Blank consent-form masters stored in the documents bucket",
)
def list_consent_forms(
    prefix: Annotated[str | None, Query(description="Object-key prefix (default: consent-forms/)")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
):
    return {
        "items": document_store.list_consent_masters(prefix, limit),
        "storage_bucket": settings.GCS_BUCKET_DOCUMENTS,
        "storage_prefix": prefix or settings.GCS_CONSENT_FORMS_PREFIX,
        "is_configured": document_store.gcs_enabled(),
    }
