"""Supporting-records readiness (PROC-7c / PROC-7d).

Three reads over one service (``supporting_records_service``) so every client
shows the same checklist: the pre-post check for the Add Procedure pop-up, the
per-charge check for the ledger / treatment plan, and the whole-claim check the
claim fill-out and submit path use. Registered before the generic CRUD routers
so ``/patient-procedures/{id}/readiness`` and ``/insurance-claims/{id}/readiness``
resolve ahead of ``/{item_id}``.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.supporting_records import ClaimReadiness, ProcedureReadiness
from app.services import supporting_records_service as svc

router = APIRouter(
    tags=["Procedures"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)

_PerioAge = Annotated[int | None, Query(
    ge=0, description="A perio exam older than this many months (before the date of service) "
                      "does not satisfy requires_perio_chart; default = server setting",
)]
_StrictTooth = Annotated[bool, Query(
    description="requires_xray is satisfied only by a DICOM instance tagged with the tooth",
)]


@router.get(
    "/patients/{patient_id}/procedure-readiness",
    response_model=ProcedureReadiness,
    operation_id="get_procedure_readiness",
    summary="Which supporting records a code requires and which are already on file (PROC-7c)",
    description=(
        "The pre-post checklist for the Add Procedure pop-up / treatment-plan post: "
        "``requires`` lists the code's supporting-record flags, ``satisfied`` / ``missing`` "
        "what the patient's chart already holds, ``deferred`` what can only be judged once "
        "the charge exists (an attachment). Posting is never blocked by this; claim "
        "submission is (422 supporting_records_missing)."
    ),
)
def procedure_readiness(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    procedure_code: Annotated[str, Query(description="The code about to be posted")],
    tooth: Annotated[str | None, Query(
        description="Universal tooth id, for the x-ray tooth match")] = None,
    date_of_service: Annotated[date | None, Query(description="Defaults to any date")] = None,
    perio_max_age_months: _PerioAge = None,
    strict_tooth: _StrictTooth = False,
):
    return svc.procedure_readiness(
        db, tenant_id, patient_id, procedure_code=procedure_code, tooth=tooth,
        date_of_service=date_of_service, perio_max_age_months=perio_max_age_months,
        strict_tooth=strict_tooth,
    )


@router.get(
    "/patient-procedures/{procedure_id}/readiness",
    response_model=ProcedureReadiness,
    operation_id="get_patient_procedure_readiness",
    summary="Supporting-records readiness of one posted charge (PROC-7c)",
)
def posted_procedure_readiness(
    db: DbSession,
    tenant_id: TenantId,
    procedure_id: Annotated[str, Path()],
    perio_max_age_months: _PerioAge = None,
    strict_tooth: _StrictTooth = False,
):
    return svc.posted_procedure_readiness(
        db, tenant_id, procedure_id, perio_max_age_months=perio_max_age_months,
        strict_tooth=strict_tooth,
    )


@router.get(
    "/insurance-claims/{claim_id}/readiness",
    response_model=ClaimReadiness,
    operation_id="get_claim_readiness",
    summary="Every procedure on a claim judged against its supporting-record flags, plus "
            "the derived Enclosures box (PROC-7c/7d)",
    description=(
        "``missing`` is exactly what ``POST /insurance-claims/{id}/submit`` will refuse on "
        "(422 supporting_records_missing) unless ``allow_missing_records`` is sent. "
        "``enclosures`` pre-populates the ADA claim form's Enclosures box from the claim's "
        "attachments and says which attachment types the claim's codes still ask for."
    ),
)
def claim_readiness(
    db: DbSession,
    tenant_id: TenantId,
    claim_id: Annotated[str, Path()],
    perio_max_age_months: _PerioAge = None,
    strict_tooth: _StrictTooth = False,
):
    return svc.claim_readiness(
        db, tenant_id, claim_id, perio_max_age_months=perio_max_age_months,
        strict_tooth=strict_tooth,
    )
