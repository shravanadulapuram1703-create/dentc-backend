"""Treatment-plan service endpoints that supplement generated CRUD."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.enriched import PatientProcedureRead
from app.schemas.treatment import (
    BookFromPlanRequest,
    BookFromPlanResult,
    PostPlanItemRequest,
    ReEstimateResult,
    TreatmentPlanItemRead,
    TreatmentPlanReport,
    TreatmentPlanSummary,
)
from app.services import procedure_rules_service, treatment_service
from app.services.enrich_service import enrich_patient_procedure

router = APIRouter(
    tags=["Treatment Plans"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)

# Published vocabulary/enforcement contract (PROC-INT-6/8). Separate router so it
# lands under the Metadata tag with the other /metadata/* rule tables.
metadata_router = APIRouter(
    tags=["Metadata"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}},
)


@router.get(
    "/treatment-plans/{plan_id}/summary",
    response_model=TreatmentPlanSummary,
    operation_id="get_treatment_plan_summary",
    summary="Roll up a treatment plan's item fees into a summary",
)
def treatment_plan_summary(
    db: DbSession,
    tenant_id: TenantId,
    plan_id: Annotated[str, Path()],
):
    return treatment_service.plan_summary(db, plan_id, tenant_id)


@router.post(
    "/treatment-plans/{plan_id}/re-estimate",
    response_model=ReEstimateResult,
    operation_id="re_estimate_treatment_plan",
    summary="Compute per-item insurance estimates from the patient's coverage (PLAN-3)",
)
def re_estimate_plan(
    db: DbSession,
    tenant_id: TenantId,
    plan_id: Annotated[str, Path()],
    phase: Annotated[int | None, Query(description="Limit to one Phase ID")] = None,
    use_new_fees: Annotated[bool, Query(
        description=(
            "Legacy 'Use New Fees': re-price every line through the server fee "
            "resolver (assignment -> plan -> office default -> code default) and "
            "record the schedule that priced it (PLAN-29) before re-estimating."
        ),
    )] = False,
):
    """PLAN-3. Reads the patient's active primary coverage, matches each line's
    code against the plan's coverage bands with the **ranked, coverage-category-
    aware** matcher the charge estimate uses (FEE-1 — the lexical matcher priced
    every migrated plan at 0 %), applies the deductible in priority order, caps at
    the annual maximum, and writes both `treatment_plan_items.insurance_estimate`
    **and** the per-item `treatment-plan-insurance-details` row (estimated_ins /
    estimated_pat / deductible / coverage_pct / annual_max_rem), which the Edit
    Treatment ADVANCED panel reads."""
    return treatment_service.re_estimate(
        db, plan_id, tenant_id, phase_id=phase, use_new_fees=use_new_fees,
    )


@router.post(
    "/treatment-plans/{plan_id}/book",
    response_model=BookFromPlanResult,
    status_code=201,
    operation_id="book_treatment_plan_items",
    summary="New Appt from the plan: one transaction books the selected items (PLAN-APPT-5)",
    description=(
        "Creates the appointment, one `appointment_procedures` line per item (linked by "
        "`treatment_plan_item_id`, PLAN-APPT-2) and flips every item to `scheduled` "
        "(PLAN-APPT-1) — all or nothing. Provider defaults to the first item's provider "
        "(PLAN-APPT-3), operatory to the provider's default chair or the office chair whose "
        "column provider matches (PLAN-APPT-4), duration to the sum of the items' chair time. "
        "409 `item_already_scheduled` if an item is already on a live appointment; 422 "
        "`item_completed` / `item_archived` / `provider_required` / `office_required`."
    ),
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def book_treatment_plan_items(
    db: DbSession,
    tenant_id: TenantId,
    plan_id: Annotated[str, Path()],
    body: BookFromPlanRequest,
    current=Depends(get_current_user),
):
    return treatment_service.book_from_plan(
        db, plan_id, tenant_id, body.model_dump(exclude_unset=True), created_by=current.id
    )


@router.get(
    "/treatment-plans/{plan_id}/report",
    response_model=TreatmentPlanReport,
    operation_id="get_treatment_plan_report",
    summary="Server-side treatment-plan report payload (PLAN-6)",
)
def treatment_plan_report(
    db: DbSession,
    tenant_id: TenantId,
    plan_id: Annotated[str, Path()],
):
    return treatment_service.plan_report(db, plan_id, tenant_id)


@router.get(
    "/patients/{patient_id}/treatment-plan-items",
    response_model=PaginatedResponse[TreatmentPlanItemRead],
    operation_id="list_patient_treatment_plan_items",
    summary="All of a patient's plan items in one call, paged (PLAN-12, PROC-INT-4)",
    description=(
        "Every item across every plan of the patient, tenant-scoped through the plan. "
        "**Breaking (PROC-INT-4):** returns the standard `{items, meta}` envelope — the "
        "previous bare array ignored `size`. Each item carries `procedure_id`, the live "
        "charge that fulfilled it (PROC-INT-1). `size` defaults to 200 so the "
        "reconciliation call keeps seeing the whole plan set in one page."
    ),
)
def patient_treatment_plan_items(
    db: DbSession,
    tenant_id: TenantId,
    patient_id: Annotated[int, Path()],
    include_archived: Annotated[bool, Query()] = False,
    include_completed: Annotated[
        bool, Query(description="false = only open items (status != completed)")
    ] = True,
    plan_id: Annotated[str | None, Query(description="Limit to one plan")] = None,
    status: Annotated[str | None, Query(description="Exact item status")] = None,
    procedure_code: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=500)] = 200,
):
    items, total = treatment_service.list_patient_items(
        db, patient_id, tenant_id,
        include_archived=include_archived, include_completed=include_completed,
        plan_id=plan_id, status=status, procedure_code=procedure_code,
        page=page, size=size,
    )
    treatment_service.enrich_treatment_plan_item(db, items, tenant_id)
    return PaginatedResponse.build(items, total, page, size)


@router.post(
    "/treatment-plan-items/{item_id}/post",
    response_model=PatientProcedureRead,
    status_code=201,
    operation_id="post_treatment_plan_item",
    summary="Post to Ledger: create the charge that fulfils this item and close it (PROC-INT-1/2)",
    description=(
        "One transaction: a `patient_procedures` row is created with "
        "`treatment_plan_item_id` = this item (inheriting code, tooth, surface, quadrant, "
        "material, fee, estimate and provider unless overridden in the body) and the item "
        "flips to `status='completed'` with `end_date` = the service date. "
        "409 `item_already_posted` if a live charge already fulfils the item; 422 "
        "`provider_required` / `office_required` when neither the body nor the item/plan "
        "supplies one. Voiding the charge later reopens the item."
    ),
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def post_treatment_plan_item(
    db: DbSession,
    tenant_id: TenantId,
    item_id: Annotated[str, Path()],
    body: PostPlanItemRequest | None = None,
    current=Depends(get_current_user),
):
    payload = body.model_dump(exclude_unset=True) if body is not None else {}
    charge = treatment_service.post_item_to_ledger(
        db, item_id, tenant_id, payload, created_by=current.id
    )
    enrich_patient_procedure(db, [charge], tenant_id)
    return charge


@router.put(
    "/treatment-plan-items/{item_id}/icd-codes",
    response_model=TreatmentPlanItemRead,
    operation_id="set_treatment_plan_item_icd_codes",
    summary="Replace the item's ICD-10 diagnosis set (PLAN-26); [] clears all",
)
def set_treatment_plan_item_icd_codes(
    db: DbSession,
    tenant_id: TenantId,
    item_id: Annotated[str, Path()],
    icd_code_ids: Annotated[list[int], Body(embed=True)],
):
    """The same reconciliation `PATCH /treatment-plan-items/{id}` runs when the
    body carries `icd_code_ids` — an item with `id` keeps its row, order is the
    list order (`ordinal`), anything unmentioned is removed. 422
    `icd_code_not_found` names the unknown ids."""
    item = treatment_service.set_item_icd_codes(db, item_id, tenant_id, icd_code_ids)
    treatment_service.enrich_treatment_plan_item(db, [item], tenant_id)
    return item


@metadata_router.get(
    "/metadata/treatment-plan-rules",
    operation_id="get_treatment_plan_rules",
    summary="Item status / referral-type / pre-auth vocabularies and the server-owned transitions",
)
def treatment_plan_rules() -> dict:
    """Published so the Edit Treatment window drives its STATUS / PRE AUTH STATUS /
    Referral Type controls from the same table the API validates against."""
    from app.schemas.treatment import ItemStatus, PreauthStatus, ReferralType
    from typing import get_args

    return {
        "item_statuses": list(get_args(ItemStatus)),
        "server_owned_statuses": {
            "completed": "set when a charge is posted against the item; released on void",
            "scheduled": "set when an appointment line books the item; reverted to "
                         "status_before_scheduled when the appointment is cancelled/deleted",
        },
        "released_status": treatment_service.RELEASED_STATUS,
        "referral_types": list(get_args(ReferralType)),
        "preauth_statuses": list(get_args(PreauthStatus)),
        "posting_flags": ["update_end_date_at_posting", "re_estimate_at_posting"],
        "default_item_duration_minutes": treatment_service.DEFAULT_ITEM_DURATION_MINUTES,
        "eligibility": {
            "empty_assignment_means": "unrestricted",
            "endpoint": "/procedure-codes/eligibility?codes=",
        },
    }


@metadata_router.get(
    "/metadata/procedure-entry-rules",
    operation_id="get_procedure_entry_rules",
    summary="Surface / quadrant / tooth vocabulary and the enforcement contract (PROC-INT-6/8)",
    description=(
        "The canonical surface codes (M O I D B F L, Class V as B5/F5/L5), their storage "
        "order, the quadrant codes, Universal tooth numbering incl. supernumerary, which "
        "`procedure_codes` flags the server enforces with a 422 (and which are advisory), "
        "and the error codes a client can expect. Drive the ADD PROCEDURE DETAILS pop-up "
        "from this so every client renders what the API validates."
    ),
)
def procedure_entry_rules() -> dict:
    return procedure_rules_service.rules_metadata()
