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
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.db.models import Employer, InsuranceCarrier
from app.schemas.common import ErrorResponse
from app.schemas.insurance import (
    EligibilityVerifyRequest,
    EligibilityVerifyResult,
    GroupAvailabilityResult,
    NameAvailabilityResult,
)
from app.services import insurance_service

_ERRORS = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

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
