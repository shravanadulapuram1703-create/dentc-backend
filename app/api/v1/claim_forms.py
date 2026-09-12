"""ADA Dental Claim Form (2024) routes (ADA-BE-1 / 6 / 11 / 14).

``GET /insurance-claims/{id}/ada-claim-form`` is the assembled form as JSON
(one request instead of the ~18 the browser renderer issued);
``GET …/reports/ada-claim-form`` is the same data as ``application/pdf``
(``mode=form`` on plain paper, ``mode=overlay`` for pre-printed stock, with
printer-calibration offsets) and ``POST /insurance-claims/reports/ada-claim-form``
renders a batch of claims into one document ("print all unsent paper
claims"). Every PDF writes a PRINT audit row (``resource_type='claim_report'``)
recording user, timestamp, mode and form version.

Mounted before the generic CRUD routers so the literal sub-paths win over
``/insurance-claims/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.claim_form import (
    AdaClaimForm,
    ClaimFormBatchRequest,
    PatientToothStatus,
    ProviderTaxonomyCode,
)
from app.schemas.common import ErrorResponse
from app.services import ada_claim_pdf, claim_form_service, print_service, provider_taxonomy_service
from app.services.account_scope import load_patient

router = APIRouter(
    prefix="/insurance-claims",
    tags=["Billing"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
patient_router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
metadata_router = APIRouter(tags=["Metadata"], dependencies=[Depends(get_current_user)])

ClaimPath = Annotated[str, Path(description="Claim id")]
Mode = Annotated[Literal["form", "overlay"], Query(
    description="form = full form on plain paper; overlay = data only for pre-printed ADA stock")]
Offset = Annotated[float, Query(ge=-72, le=72, description="printer calibration, points")]
_PDF = {200: {"content": {"application/pdf": {}}, "description": "Rendered claim form"}}


def _pdf_response(pdf: bytes, filename: str) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def _audit(db, request: Request, tenant_id: int, user, form: dict, **params) -> None:  # noqa: ANN001
    print_service.record_print(
        db, tenant_id=tenant_id, user_id=getattr(user, "id", None), patient_id=form["patient_id"],
        report=form["claim_id"], path=str(request.url.path),
        params={"claim_number": form.get("claim_number"), "form_version": form["form_version"],
                "pages": form["pages"], **params},
        resource_type="claim_report",
    )


@router.get(
    "/{claim_id}/ada-claim-form",
    response_model=AdaClaimForm,
    operation_id="get_ada_claim_form",
    summary="The assembled ADA Dental Claim Form (2024) for one claim, as JSON (ADA-BE-1)",
)
def ada_claim_form(
    db: DbSession, tenant_id: TenantId, claim_id: ClaimPath,
    include_signature_images: Annotated[bool, Query(
        description="SIG-16: embed the captured signature images (data URLs) under authorizations.signatures"
    )] = False,
):
    return claim_form_service.assemble(db, claim_id, tenant_id,
                                       include_signature_images=include_signature_images)


@router.get(
    "/{claim_id}/reports/ada-claim-form",
    operation_id="get_ada_claim_form_report",
    summary="ADA Dental Claim Form (2024) as a printable PDF (ADA-BE-1)",
    response_class=Response,
    responses=_PDF,
)
def ada_claim_form_report(
    request: Request, db: DbSession, tenant_id: TenantId, current: CurrentUser, claim_id: ClaimPath,
    mode: Mode = "form", offset_x: Offset = 0.0, offset_y: Offset = 0.0,
):
    form = claim_form_service.assemble(db, claim_id, tenant_id, include_signature_images=True)
    pdf = ada_claim_pdf.render([form], mode=mode, offset_x=offset_x, offset_y=offset_y)
    _audit(db, request, tenant_id, current, form, mode=mode, offset_x=offset_x, offset_y=offset_y)
    return _pdf_response(pdf, f"ada-claim-{form.get('claim_number') or claim_id}.pdf")


@router.post(
    "/reports/ada-claim-form",
    operation_id="render_ada_claim_form_batch",
    summary="Many claims' ADA forms in one PDF, e.g. every unsent paper claim (ADA-BE-1)",
    response_class=Response,
    responses=_PDF,
)
def ada_claim_form_batch(
    request: Request, db: DbSession, tenant_id: TenantId, current: CurrentUser, body: ClaimFormBatchRequest,
):
    forms = [claim_form_service.assemble(db, cid, tenant_id, include_signature_images=True)
             for cid in dict.fromkeys(body.claim_ids)]
    pdf = ada_claim_pdf.render(forms, mode=body.mode, offset_x=body.offset_x, offset_y=body.offset_y)
    for form in forms:
        _audit(db, request, tenant_id, current, form, mode=body.mode, batch=len(forms))
    return _pdf_response(pdf, f"ada-claims-batch-{len(forms)}.pdf")


@patient_router.get(
    "/{patient_id}/tooth-status",
    response_model=PatientToothStatus,
    operation_id="get_patient_tooth_status",
    summary="Per-tooth present / missing / extracted / implant from the chart, uncapped (ADA-BE-6)",
)
def patient_tooth_status(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    patient = load_patient(db, patient_id, tenant_id)
    teeth = claim_form_service.tooth_status(db, patient.id)
    return {"patient_id": patient.id, "teeth": teeth,
            "missing_teeth": [t["tooth"] for t in teeth if t["status"] != "present"]}


@metadata_router.get(
    "/metadata/ada-claim-form-rules",
    operation_id="get_ada_claim_form_rules",
    summary="Vocabularies, derivation rules and error codes behind the ADA claim form",
)
def ada_claim_form_rules() -> dict:
    return claim_form_service.rules_metadata()


@metadata_router.get(
    "/metadata/provider-taxonomy-codes",
    response_model=list[ProviderTaxonomyCode],
    operation_id="list_provider_taxonomy_codes",
    summary="Dental Healthcare Provider Taxonomy codes + the specialty keywords that map to them (ADA-BE-14)",
)
def provider_taxonomy_codes():
    return provider_taxonomy_service.catalog()
