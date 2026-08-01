"""Add-Patient intake extras: opening-balance seed (GAP-AP-12) and the atomic
composite register endpoint (GAP-AP-13/15/18).

Mounted before the generic CRUD ``/patients`` router so the literal sub-paths
(``/patients/register``, ``/patients/{id}/opening-balance``) win over the
generic ``/patients/{item_id}`` route.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.patient_intake import (
    AccountPlanRead,
    OpeningBalanceIn,
    OpeningBalanceRead,
    RegisterRequest,
    RegisterResponse,
    RosterPatientRead,
)
from app.schemas.patient_overview import PatientOverviewResponse
from app.services import patient_intake_service as svc
from app.services import patient_overview_service as overview_svc

_errs = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
router = APIRouter(prefix="/patients", tags=["Patients"], dependencies=[Depends(get_current_user)], responses=_errs)
# LEG-14: the guarantor's account roster, nested under /responsible-parties.
rp_router = APIRouter(prefix="/responsible-parties", tags=["Patients"],
                      dependencies=[Depends(get_current_user)], responses=_errs)
# PO-4: family/account-scoped appointment query, under /appointments.
appt_router = APIRouter(prefix="/appointments", tags=["Appointments"],
                        dependencies=[Depends(get_current_user)], responses=_errs)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="register_patient",
    summary="Register a patient with responsible party, alerts, questionnaire, recalls and opening balance in one transaction (GAP-AP-13/15/18)",
)
def register_patient(db: DbSession, tenant_id: TenantId, current: CurrentUser, body: RegisterRequest):
    return svc.register_patient(db, tenant_id, body, user_id=current.id)


@router.get(
    "/{patient_id}/opening-balance",
    response_model=OpeningBalanceRead,
    operation_id="get_patient_opening_balance",
    summary="Get a patient's opening A/R aging buckets (GAP-AP-12)",
)
def get_opening_balance(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    return svc.get_opening_balance(db, patient_id, tenant_id)


@router.put(
    "/{patient_id}/opening-balance",
    response_model=OpeningBalanceRead,
    operation_id="set_patient_opening_balance",
    summary="Seed/replace a patient's opening A/R aging buckets (GAP-AP-12)",
)
def set_opening_balance(
    db: DbSession, tenant_id: TenantId, current: CurrentUser,
    patient_id: Annotated[int, Path()], body: OpeningBalanceIn,
):
    return svc.upsert_opening_balance(db, patient_id, tenant_id, body.model_dump(), user_id=current.id)


@router.get(
    "/{patient_id}/overview",
    response_model=PatientOverviewResponse,
    operation_id="get_patient_overview",
    summary="Aggregate Patient Overview: patient+balance+RP+members+appts+recalls+insurance+referrals+contracts (PO-1)",
)
def get_overview(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    return overview_svc.get_patient_overview(db, patient_id, tenant_id)


@router.get(
    "/{patient_id}/insurance-plans",
    response_model=list[AccountPlanRead],
    operation_id="list_patient_insurance_plans",
    summary="Insurance plans already on this patient's account (PO-12: canonical name for account-plans)",
)
def list_insurance_plans(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    return svc.get_account_plans(db, patient_id, tenant_id)


@router.get(
    "/{patient_id}/account-plans",
    response_model=list[AccountPlanRead],
    operation_id="list_patient_account_plans",
    summary="Alias of /insurance-plans (legacy Account Plans scope, LEG-5) — kept for back-compat",
)
def list_account_plans(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    return svc.get_account_plans(db, patient_id, tenant_id)


@rp_router.get(
    "/{rp_id}/patients",
    response_model=list[RosterPatientRead],
    operation_id="list_responsible_party_patients",
    summary="Patients a responsible party is billing-responsible for, with balance/aging/visits (LEG-14/PO-3)",
)
def list_rp_patients(db: DbSession, tenant_id: TenantId, rp_id: Annotated[str, Path()]):
    # PO-3: raw string id, so migrated legacy-guarantor accounts resolve too.
    return svc.get_responsible_party_roster(db, rp_id, tenant_id)


@appt_router.get(
    "/family",
    operation_id="list_family_appointments",
    summary="Appointments across every patient on an account (legacy VIEW FUTURE FAMILY APPT, PO-4)",
)
def list_family_appointments(
    db: DbSession, tenant_id: TenantId,
    responsible_party_id: Annotated[str, Query(description="Account guarantor id (raw string)")],
    upcoming_only: Annotated[bool, Query()] = False,
):
    return overview_svc.get_family_appointments(
        db, tenant_id, responsible_party_id, upcoming_only=upcoming_only
    )
