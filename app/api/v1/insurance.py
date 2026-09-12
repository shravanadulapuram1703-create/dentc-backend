"""Insurance supplemental routes (patient-insurance dev-report gaps).

Each router is registered **before** the generated CRUD for its prefix so the
literal sub-paths win over ``/{item_id}``:

* ``POST /insurance-subscribers/{id}/verify-eligibility`` — INS-PT-5, stamps the
  eligibility "Update Status" server-side.
* ``GET /insurance-plans/group-availability`` — INS-PT-20/21, "is this group
  number taken?" without paging the full list endpoint on every save.
* ``GET /insurance-carriers/name-availability`` and
  ``GET /employers/name-availability`` — INS-PT-13, the name-match probe the
  quick-add dialogs never had.
* ``GET /insurance-plans/metadata`` — PLAN-DTL-1/4, the wizard's catalogues
  (frequency ordinals, default coverage table, code groups, field vocabularies).
* ``GET/PUT /insurance-plans/{id}/coverage-rules`` — PLAN-DTL-8, the whole
  COVERAGE & LIMITATIONS + FREQ LIMITATION CODE GRP table in one call.
* ``POST /insurance-plans/{id}/copy-from/{source_id}`` — COPY FROM EXISTING,
  server-side.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.api.deps import (
    CurrentUser,
    DbSession,
    PageParams,
    TenantId,
    get_current_user,
    require_permission,
)
from app.core import concurrency
from app.db.models import Employer, InsuranceCarrier
from app.schemas.common import ErrorResponse
from app.schemas.insurance import (
    AffectedTreatmentPlansResponse,
    EligibilityVerifyRequest,
    EligibilityVerifyResult,
    GroupAvailabilityResult,
    InsurancePlanMetadata,
    NameAvailabilityResult,
    PlanCopyRequest,
    PlanCoverageReplaceRequest,
    PlanCoverageResponse,
    PlanHistoryResponse,
    PlanReEstimateRequest,
    PlanReEstimateResult,
    PlanUsage,
)
from app.services import (
    insurance_plan_edit_service,
    insurance_plan_service,
    insurance_service,
    permission_service,
)

_ERRORS = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
# EDIT-PLAN-5: the plan write paths share one permission dependency.
_plan_write = Depends(require_permission(
    *permission_service.INSURANCE_PLAN_WRITE, action="edit insurance plans",
))
_WRITE_ERRORS = {
    403: {"model": ErrorResponse}, 412: {"model": ErrorResponse},
    422: {"model": ErrorResponse}, 423: {"model": ErrorResponse},
}

router = APIRouter(
    prefix="/insurance-subscribers",
    tags=["Insurance"],
    dependencies=[Depends(get_current_user)],
    responses=_ERRORS,
)

plans_router = APIRouter(
    prefix="/insurance-plans",
    tags=["Insurance"],
    dependencies=[Depends(get_current_user)],
    responses=_ERRORS,
)

carriers_router = APIRouter(
    prefix="/insurance-carriers",
    tags=["Insurance"],
    dependencies=[Depends(get_current_user)],
    responses=_ERRORS,
)

employers_router = APIRouter(
    prefix="/employers",
    tags=["Insurance"],
    dependencies=[Depends(get_current_user)],
    responses=_ERRORS,
)


@router.post(
    "/{subscriber_id}/verify-eligibility",
    response_model=EligibilityVerifyResult,
    operation_id="verify_subscriber_eligibility",
    summary="Stamp a subscriber's eligibility verification (INS-PT-5)",
)
def verify_subscriber_eligibility(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    subscriber_id: Annotated[int, Path()],
    body: EligibilityVerifyRequest | None = None,
):
    req = body or EligibilityVerifyRequest()
    return insurance_service.verify_eligibility(
        db, subscriber_id, tenant_id, current,
        elig_status=req.elig_status, notes=req.notes,
    )


@plans_router.get(
    "/group-availability",
    response_model=GroupAvailabilityResult,
    operation_id="check_insurance_plan_group_availability",
    summary="Check whether a plan group number is already taken (INS-PT-20)",
)
def check_group_availability(
    db: DbSession,
    tenant_id: TenantId,
    group_number: Annotated[
        str, Query(description="Group number to test (trimmed, case-insensitive)")
    ],
    carrier_id: Annotated[int | None, Query(description="Scope the answer to one carrier")] = None,
    exclude_plan_id: Annotated[
        int | None, Query(description="Ignore this plan (the one being edited)")
    ] = None,
):
    """``taken`` is the answer the save path enforces: an **active** plan on the
    same carrier already holds this group number, so ``POST/PATCH
    /insurance-plans`` will 409 unless ``allow_duplicate_group`` is sent.

    Deactivated plans (``inactive_matches``, INS-PT-21) and plans under another
    carrier (``other_carrier_matches``) are reported but never block — the
    frontend was already treating both that way, and now the backend says so.
    """
    return insurance_service.group_availability(
        db, tenant_id, group_number,
        carrier_id=carrier_id, exclude_plan_id=exclude_plan_id,
    )


# ── PLAN-DTL-1/4: the wizard's catalogues ────────────────────────────────────
@plans_router.get(
    "/metadata",
    response_model=InsurancePlanMetadata,
    operation_id="get_insurance_plan_metadata",
    summary="Catalogues behind the INSURANCE DETAILS wizard (PLAN-DTL-1/4)",
)
def get_insurance_plan_metadata(db: DbSession, tenant_id: TenantId):
    """Frequency-limitation ordinals (what ``freq_limit`` stores), the default
    COVERAGE & LIMITATIONS table a new plan starts with, the FREQ-tab code
    groups and the PLAN-tab field vocabularies — from the tenant's
    ``definitions`` where it has them, else the built-in legacy lists
    (``catalog_sources`` says which)."""
    return insurance_plan_service.plan_metadata(db, tenant_id)


# ── PLAN-DTL-8: the coverage table as one document ───────────────────────────
@plans_router.get(
    "/{plan_id}/coverage-rules",
    response_model=PlanCoverageResponse,
    operation_id="get_insurance_plan_coverage",
    summary="A plan's coverage rules + frequency code groups in one call",
)
def get_insurance_plan_coverage(
    db: DbSession, tenant_id: TenantId, plan_id: Annotated[int, Path()],
):
    return insurance_plan_service.plan_coverage(db, plan_id, tenant_id)


@plans_router.put(
    "/{plan_id}/coverage-rules",
    response_model=PlanCoverageResponse,
    operation_id="replace_insurance_plan_coverage",
    summary="Replace a plan's coverage rules and/or frequency code groups atomically (PLAN-DTL-8)",
    dependencies=[_plan_write],
    responses=_WRITE_ERRORS,
)
def replace_insurance_plan_coverage(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    plan_id: Annotated[int, Path()],
    body: PlanCoverageReplaceRequest,
    request: Request,
):
    """One transaction for what used to be ~30 sequential POSTs.

    A section that is ``null`` is untouched. For a section that is sent: an
    item carrying the ``id`` of a row on this plan is updated in place (id and
    ``legacy_id`` survive), an item without one is inserted, and existing rows
    not mentioned are deleted. Any failure rolls the whole call back — no
    partial table.

    EDIT-PLAN-1: send ``expected_updated_at`` (the plan's ``updated_at`` you
    read) or ``If-Match`` / ``If-Unmodified-Since`` and the write is **412**
    if the plan changed since — the plan row is the version of the whole
    coverage document. EDIT-PLAN-5: **423 plan_locked** on a locked plan.
    """
    concurrency.from_headers(request.headers)
    rules = [r.model_dump(exclude_unset=True) for r in body.rules] if body.rules is not None else None
    groups = (
        [g.model_dump(exclude_unset=True) for g in body.frequency_groups]
        if body.frequency_groups is not None else None
    )
    kwargs = {}
    if "expected_updated_at" in body.model_fields_set:
        kwargs["expected_updated_at"] = body.expected_updated_at
    return insurance_plan_service.replace_plan_coverage(
        db, plan_id, tenant_id, rules=rules, frequency_groups=groups, actor_id=current.id,
        **kwargs,
    )


@plans_router.post(
    "/{plan_id}/copy-from/{source_plan_id}",
    response_model=PlanCoverageResponse,
    operation_id="copy_insurance_plan_from",
    summary="COPY FROM EXISTING — copy another plan's coverage table (and optionally its plan fields)",
    dependencies=[_plan_write],
    responses=_WRITE_ERRORS,
)
def copy_insurance_plan_from(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    plan_id: Annotated[int, Path()],
    source_plan_id: Annotated[int, Path()],
    request: Request,
    body: PlanCopyRequest | None = None,
):
    concurrency.from_headers(request.headers)
    req = body or PlanCopyRequest()
    return insurance_plan_service.copy_plan_coverage(
        db, plan_id, source_plan_id, tenant_id,
        include_rules=req.include_rules,
        include_frequency_groups=req.include_frequency_groups,
        include_plan_fields=req.include_plan_fields,
        actor_id=current.id,
    )


# ── EDIT-PLAN-2: usage / impact ──────────────────────────────────────────────
@plans_router.get(
    "/{plan_id}/usage",
    response_model=PlanUsage,
    operation_id="get_insurance_plan_usage",
    summary="Who is on this plan — distinct patients, subscribers, open claims, pending treatment plans (EDIT-PLAN-2)",
)
def get_insurance_plan_usage(db: DbSession, tenant_id: TenantId, plan_id: Annotated[int, Path()]):
    """The shared-plan banner in one call. ``patients`` is **distinct** (a
    patient holding the plan in two slots counts once; ``patient_links`` is
    the raw slot count), ``claims_open`` excludes closed / paid / denied /
    voided claims, ``treatment_plans`` / ``treatment_plan_items_pending`` are
    what ``POST …/re-estimate`` would touch. Every count is index-backed."""
    return insurance_plan_edit_service.plan_usage(db, plan_id, tenant_id)


# ── EDIT-PLAN-6: per-plan change history ─────────────────────────────────────
@plans_router.get(
    "/{plan_id}/history",
    response_model=PlanHistoryResponse,
    operation_id="get_insurance_plan_history",
    summary="Change log for one plan — plan fields, coverage rules and frequency groups, with user names (EDIT-PLAN-6)",
)
def get_insurance_plan_history(
    db: DbSession, tenant_id: TenantId, page: PageParams, plan_id: Annotated[int, Path()],
):
    """Aggregates ``audit_logs`` rows for the plan itself, for every coverage
    rule / frequency group written under it (``details.scope.ins_plan_id``,
    plus older rows matched on the plan's current rule ids), and the bulk
    coverage PUT / copy (``changes[]`` lists each row-level change). Newest
    first; the response also carries the "Modified by / on" strip."""
    return insurance_plan_edit_service.plan_history(
        db, plan_id, tenant_id, page=page.page, size=page.size,
    )


# ── EDIT-PLAN-3: the re-estimate cascade ─────────────────────────────────────
@plans_router.get(
    "/{plan_id}/affected-treatment-plans",
    response_model=AffectedTreatmentPlansResponse,
    operation_id="list_insurance_plan_affected_treatment_plans",
    summary="Treatment plans with open items a change to this plan's coverage re-prices (EDIT-PLAN-3)",
)
def list_affected_treatment_plans(
    db: DbSession, tenant_id: TenantId, page: PageParams, plan_id: Annotated[int, Path()],
):
    """Same set as ``GET /treatment-plans?ins_plan_id=`` restricted to plans
    that still have an open (not completed, not archived) item, with the
    patient name, the open-item count and whether the patient's *active* slot
    is still this plan (``coverage_source``)."""
    items, total = insurance_plan_edit_service.affected_treatment_plans(
        db, plan_id, tenant_id, page=page.page, size=page.size,
    )
    pages = (total + page.size - 1) // page.size if page.size else 0
    return {
        "plan_id": plan_id, "items": items,
        "meta": {"page": page.page, "size": page.size, "total": total, "pages": pages},
    }


@plans_router.post(
    "/{plan_id}/re-estimate",
    response_model=PlanReEstimateResult,
    operation_id="re_estimate_insurance_plan",
    summary="Re-estimate every affected treatment plan (and re-sum open claims) after a coverage change (EDIT-PLAN-3)",
    dependencies=[_plan_write],
    responses=_WRITE_ERRORS,
)
def re_estimate_insurance_plan(
    db: DbSession,
    tenant_id: TenantId,
    current: CurrentUser,
    plan_id: Annotated[int, Path()],
    body: PlanReEstimateRequest | None = None,
):
    """Runs ``POST /treatment-plans/{id}/re-estimate`` for each affected plan
    inline, under ``max_plans``; one plan's failure is recorded on its line
    and the sweep continues. ``dry_run`` returns the same shape without
    writing — the "re-estimate N pending treatment plans?" prompt. Open claims
    on the plan are re-summed from their lines (``recalculate_claims``)."""
    req = body or PlanReEstimateRequest()
    return insurance_plan_edit_service.re_estimate_cascade(
        db, plan_id, tenant_id, actor_id=current.id,
        dry_run=req.dry_run, use_new_fees=req.use_new_fees,
        treatment_plan_ids=req.treatment_plan_ids, max_plans=req.max_plans,
        recalculate_claims=req.recalculate_claims,
    )


@carriers_router.get(
    "/name-availability",
    response_model=NameAvailabilityResult,
    operation_id="check_insurance_carrier_name_availability",
    summary="Check whether a carrier name is already used (INS-PT-13)",
)
def check_carrier_name_availability(
    db: DbSession,
    tenant_id: TenantId,
    name: Annotated[str, Query(description="Carrier name to test (trimmed, case-insensitive)")],
    exclude_id: Annotated[int | None, Query(description="Ignore this carrier")] = None,
):
    return insurance_service.name_availability(
        db, InsuranceCarrier, tenant_id, name, exclude_id=exclude_id
    )


@employers_router.get(
    "/name-availability",
    response_model=NameAvailabilityResult,
    operation_id="check_employer_name_availability",
    summary="Check whether an employer name is already used (INS-PT-13)",
)
def check_employer_name_availability(
    db: DbSession,
    tenant_id: TenantId,
    name: Annotated[str, Query(description="Employer name to test (trimmed, case-insensitive)")],
    exclude_id: Annotated[int | None, Query(description="Ignore this employer")] = None,
):
    return insurance_service.name_availability(
        db, Employer, tenant_id, name, exclude_id=exclude_id
    )
