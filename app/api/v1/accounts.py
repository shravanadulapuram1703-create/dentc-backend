"""Family accounts & guarantor routes (RP-3/5/6/8/9/13/15/16).

Logic lives in :mod:`app.services.family_account_service`. Mounted before the generic
``/patients`` CRUD router so ``/patients/{id}/account`` etc. win.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user, require_permission
from app.schemas.accounts import (
    AccountChangeEventRead,
    AccountInsurancePlan,
    AccountPage,
    AccountPartyCreate,
    AccountPartyRead,
    AccountPartyUpdate,
    AccountPaymentCreate,
    AccountPaymentResponse,
    AccountRead,
    AccountRules,
    AccountStatementCreate,
    AccountUpdate,
    ChangeGuarantorRequest,
    ChangeGuarantorResponse,
    MergeAccountsRequest,
    MergeAccountsResponse,
)
from app.schemas.common import ErrorResponse
from app.schemas.transactions import StatementRead
from app.services import family_account_service as svc
from app.services import statement_service

_errs = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
         404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
         422: {"model": ErrorResponse}}
router = APIRouter(prefix="/accounts", tags=["Patients"],
                   dependencies=[Depends(get_current_user)], responses=_errs)
patient_router = APIRouter(prefix="/patients", tags=["Patients"],
                           dependencies=[Depends(get_current_user)], responses=_errs)
metadata_router = APIRouter(tags=["Patients"], dependencies=[Depends(get_current_user)],
                            responses={401: {"model": ErrorResponse}})

AccountId = Annotated[int, Path()]


# ── RP-3 ──────────────────────────────────────────────────────────────────────
@router.get("", response_model=AccountPage, operation_id="list_accounts",
            summary="Accounts, searchable by account number / legacy RPID / member or guarantor name (RP-3/RP-12)")
def list_accounts(
    db: DbSession, tenant_id: TenantId,
    search: Annotated[str | None, Query()] = None,
    account_no: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = True,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return svc.list_accounts(db, tenant_id, search=search, account_no=account_no,
                             is_active=is_active, page=page, size=size)


@router.get("/{account_id}", response_model=AccountRead, operation_id="get_account",
            summary="Account + primary guarantor + additional parties + members with balance/visits/recall (RP-3)")
def get_account(db: DbSession, tenant_id: TenantId, account_id: AccountId):
    return svc.get_account(db, tenant_id, account_id)


@router.patch("/{account_id}", response_model=AccountRead, operation_id="update_account",
              summary="Account-level billing flags / account number / notes (RP-3)")
def update_account(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                   account_id: AccountId, body: AccountUpdate):
    return svc.update_account(db, tenant_id, account_id, body.model_dump(exclude_unset=True),
                              user_id=current.id)


@patient_router.get("/{patient_id}/account", response_model=AccountRead,
                    operation_id="get_patient_account",
                    summary="The patient's account, with the patient's own guarantor (RP-3)")
def get_patient_account(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    return svc.get_patient_account(db, tenant_id, patient_id)


# ── RP-6 ──────────────────────────────────────────────────────────────────────
@patient_router.post(
    "/{patient_id}/change-guarantor", response_model=ChangeGuarantorResponse,
    operation_id="change_patient_guarantor",
    summary="Change guarantor / move the patient between accounts, optionally with dependents and the open balance (RP-6)",
)
def change_guarantor(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                     patient_id: Annotated[int, Path()], body: ChangeGuarantorRequest):
    payload = body.model_dump(exclude_unset=True)
    if body.person is not None:
        payload["person"] = body.person.model_dump(exclude_unset=True)
    payload.setdefault("move_open_balance", True)
    return svc.change_guarantor(db, tenant_id, patient_id, payload, user_id=current.id)


@router.post("/{account_id}/merge", response_model=MergeAccountsResponse,
             operation_id="merge_accounts",
             summary="Merge a duplicate account into this one (members + parties move; source closed) (RP-6)")
def merge_accounts(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                   account_id: AccountId, body: MergeAccountsRequest):
    return svc.merge_accounts(db, tenant_id, account_id, body.source_account_id, user_id=current.id)


# ── RP-8 ──────────────────────────────────────────────────────────────────────
@router.get("/{account_id}/parties", response_model=list[AccountPartyRead],
            operation_id="list_account_parties",
            summary="Primary guarantor (role=primary, id null) + up to two additional parties (RP-8)")
def list_parties(db: DbSession, tenant_id: TenantId, account_id: AccountId):
    return svc.list_parties(db, tenant_id, account_id)


@router.post("/{account_id}/parties", response_model=AccountPartyRead,
             status_code=status.HTTP_201_CREATED, operation_id="add_account_party",
             summary="Add a secondary / billing-contact party (patient, existing RP or inline person) (RP-8)")
def add_party(db: DbSession, tenant_id: TenantId, current: CurrentUser,
              account_id: AccountId, body: AccountPartyCreate):
    data = body.model_dump(exclude_unset=True)
    if body.person is not None:
        data["person"] = body.person.model_dump(exclude_unset=True)
    return svc.add_party(db, tenant_id, account_id, data, user_id=current.id)


@router.patch("/{account_id}/parties/{party_id}", response_model=AccountPartyRead,
              operation_id="update_account_party", summary="Update an additional party (RP-8)")
def update_party(db: DbSession, tenant_id: TenantId, current: CurrentUser, account_id: AccountId,
                 party_id: Annotated[int, Path()], body: AccountPartyUpdate):
    return svc.update_party(db, tenant_id, account_id, party_id,
                            body.model_dump(exclude_unset=True), user_id=current.id)


@router.delete("/{account_id}/parties/{party_id}", status_code=status.HTTP_204_NO_CONTENT,
               operation_id="remove_account_party", summary="Remove an additional party (RP-8)")
def remove_party(db: DbSession, tenant_id: TenantId, current: CurrentUser, account_id: AccountId,
                 party_id: Annotated[int, Path()]):
    svc.remove_party(db, tenant_id, account_id, party_id, user_id=current.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{account_id}/parties/{party_id}/make-primary", response_model=AccountRead,
             operation_id="make_account_party_primary",
             summary="Swap an additional party with the primary guarantor (RP-8)")
def make_primary(db: DbSession, tenant_id: TenantId, current: CurrentUser, account_id: AccountId,
                 party_id: Annotated[int, Path()]):
    return svc.make_primary(db, tenant_id, account_id, party_id, user_id=current.id)


# ── RP-9 ──────────────────────────────────────────────────────────────────────
@router.post(
    "/{account_id}/payments", response_model=AccountPaymentResponse,
    status_code=status.HTTP_201_CREATED, operation_id="post_account_payment",
    summary="One guarantor payment split across members server-side (oldest_first | by_member) (RP-9)",
    dependencies=[Depends(require_permission("transactions_add_post_patient_payments"))],
)
def post_account_payment(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                         account_id: AccountId, body: AccountPaymentCreate):
    data = body.model_dump(exclude_unset=True)
    if body.allocations is not None:
        data["allocations"] = [a.model_dump() for a in body.allocations]
    return svc.post_account_payment(db, tenant_id, account_id, data, user_id=current.id)


@router.post("/{account_id}/statements", response_model=StatementRead,
             status_code=status.HTTP_201_CREATED, operation_id="generate_account_statement",
             summary="One statement for the whole account, addressed to the guarantor, member sections (RP-9)")
def generate_account_statement(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                               account_id: AccountId, body: AccountStatementCreate | None = None):
    payload = (body or AccountStatementCreate()).model_dump(exclude_unset=True)
    stmt = svc.generate_account_statement(db, tenant_id, account_id, payload, actor_id=current.id)
    return statement_service._statement_out(stmt)


# ── RP-13 ─────────────────────────────────────────────────────────────────────
@router.get("/{account_id}/insurance", response_model=list[AccountInsurancePlan],
            operation_id="list_account_insurance",
            summary="Distinct plans/subscribers used by account members (Add New Member → attach family plan) (RP-13)")
def account_insurance(db: DbSession, tenant_id: TenantId, account_id: AccountId):
    return svc.account_insurance(db, tenant_id, account_id)


# ── RP-16 ─────────────────────────────────────────────────────────────────────
@router.get("/{account_id}/change-log", response_model=list[AccountChangeEventRead],
            operation_id="list_account_change_log", summary="Guarantor/account changes touching this account (RP-16)")
def account_change_log(db: DbSession, tenant_id: TenantId, account_id: AccountId):
    return svc.change_log(db, tenant_id, account_id=account_id)


@patient_router.get("/{patient_id}/change-log", response_model=list[AccountChangeEventRead],
                    operation_id="list_patient_change_log",
                    summary="Guarantor/account changes for this patient (RP-16)")
def patient_change_log(db: DbSession, tenant_id: TenantId, patient_id: Annotated[int, Path()]):
    return svc.change_log(db, tenant_id, patient_id=patient_id)


# ── RP-15 ─────────────────────────────────────────────────────────────────────
@metadata_router.get("/metadata/account-rules", response_model=AccountRules,
                     operation_id="get_account_rules",
                     summary="Guarantor kinds, link precedence, relationship codes, party limits (RP-15)")
def account_rules():
    return svc.rules_metadata()
