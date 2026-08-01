"""Payment-plan service endpoints (Ortho + Regular contracts).

Supplements the generated CRUD for ``/ortho-plans`` and ``/patient-payment-plans``
with the behaviour a contract needs and a table alone cannot express:

* **PP-2** — post a due instalment to the patient ledger (per row, or a sweep).
* **OPP-9 / RPP-5** — the patient-side instalment schedule: read, replace, or
  generate it from the contract's own terms by server-side amortisation.
* **PP-3** — the server-rendered contract and coupon documents.

Mounted before the generic CRUD routers so the literal sub-paths win over
``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from app.api.deps import DbSession, TenantId, get_current_user
from app.schemas.payment_plan import (
    ContractResponse,
    GenerateScheduleRequest,
    PlanKind,
    PostDueRequest,
    PostDueResult,
    PostedInstallment,
    PostInstallmentRequest,
    ReplaceInstallmentsRequest,
    ScheduleResponse,
)
from app.services import payment_plan_service as svc

router = APIRouter(tags=["Billing"], dependencies=[Depends(get_current_user)])

InstallmentId = Annotated[int, Path(description="Instalment row id")]
PlanId = Annotated[int, Path(description="Contract id")]
PlanKindPath = Annotated[PlanKind, Path(description="ortho | regular")]


def _post(db, tenant_id, side: str, installment_id: int, body, current):  # noqa: ANN001, ANN202
    return svc.post_installment(
        db, side, installment_id, tenant_id,
        actor_id=current.id,
        override=body.model_dump(exclude_unset=True) if body else {},
    )


# ── PP-2: post a periodic billing instalment ─────────────────────────────────
@router.post(
    "/patient-ins-payment-plans/{installment_id}/post",
    response_model=PostedInstallment,
    status_code=status.HTTP_201_CREATED,
    operation_id="post_ins_payment_plan_installment",
    summary="Post a primary-insurance instalment to the patient ledger (PP-2)",
)
def post_ins_installment(
    db: DbSession,
    tenant_id: TenantId,
    installment_id: InstallmentId,
    body: PostInstallmentRequest | None = None,
    current=Depends(get_current_user),
):
    return _post(db, tenant_id, "ins", installment_id, body, current)


@router.post(
    "/patient-sec-ins-payment-plans/{installment_id}/post",
    response_model=PostedInstallment,
    status_code=status.HTTP_201_CREATED,
    operation_id="post_sec_ins_payment_plan_installment",
    summary="Post a secondary-insurance instalment to the patient ledger (PP-2)",
)
def post_sec_ins_installment(
    db: DbSession,
    tenant_id: TenantId,
    installment_id: InstallmentId,
    body: PostInstallmentRequest | None = None,
    current=Depends(get_current_user),
):
    return _post(db, tenant_id, "sec_ins", installment_id, body, current)


@router.post(
    "/patient-plan-installments/{installment_id}/post",
    response_model=PostedInstallment,
    status_code=status.HTTP_201_CREATED,
    operation_id="post_patient_plan_installment",
    summary="Post a patient-side instalment to the patient ledger (PP-2)",
)
def post_patient_installment(
    db: DbSession,
    tenant_id: TenantId,
    installment_id: InstallmentId,
    body: PostInstallmentRequest | None = None,
    current=Depends(get_current_user),
):
    return _post(db, tenant_id, "patient", installment_id, body, current)


@router.post(
    "/payment-plans/post-due",
    response_model=PostDueResult,
    operation_id="post_due_payment_plan_installments",
    summary="Post every instalment due on/before a date (nightly batch, PP-2)",
)
def post_due(
    db: DbSession,
    tenant_id: TenantId,
    body: PostDueRequest | None = None,
    current=Depends(get_current_user),
):
    payload = body or PostDueRequest()
    return svc.post_due(
        db, tenant_id,
        actor_id=current.id,
        patient_id=payload.patient_id,
        ortho_plan_id=payload.ortho_plan_id,
        payment_plan_id=payload.payment_plan_id,
        through_date=payload.through_date,
        sides=payload.sides,
        dry_run=payload.dry_run,
    )


# ── OPP-9 / RPP-5: the patient-side instalment schedule ──────────────────────
@router.get(
    "/payment-plans/{plan_kind}/{plan_id}/installments",
    response_model=ScheduleResponse,
    operation_id="get_payment_plan_schedule",
    summary="Patient-side instalment schedule with posted/unposted state (OPP-9/RPP-5)",
)
def get_schedule(db: DbSession, tenant_id: TenantId, plan_kind: PlanKindPath, plan_id: PlanId):
    plan = svc.get_plan(db, plan_kind, plan_id, tenant_id)
    return svc.schedule_response(db, plan, plan_kind, tenant_id, persisted=True)


@router.put(
    "/payment-plans/{plan_kind}/{plan_id}/installments",
    response_model=ScheduleResponse,
    operation_id="replace_payment_plan_schedule",
    summary="Replace the unposted instalments of a contract (OPP-9/RPP-5)",
)
def replace_schedule(
    db: DbSession,
    tenant_id: TenantId,
    plan_kind: PlanKindPath,
    plan_id: PlanId,
    body: ReplaceInstallmentsRequest,
    current=Depends(get_current_user),
):
    return svc.replace_installments(
        db, plan_kind, plan_id, tenant_id,
        [i.model_dump() for i in body.installments],
        actor_id=current.id,
    )


@router.post(
    "/payment-plans/{plan_kind}/{plan_id}/installments/generate",
    response_model=ScheduleResponse,
    operation_id="generate_payment_plan_schedule",
    summary="Amortise the contract terms into an instalment schedule (OPP-9/RPP-5)",
)
def generate_schedule(
    db: DbSession,
    tenant_id: TenantId,
    plan_kind: PlanKindPath,
    plan_id: PlanId,
    body: GenerateScheduleRequest | None = None,
    current=Depends(get_current_user),
):
    payload = (body or GenerateScheduleRequest()).model_dump(exclude_unset=True)
    payload.setdefault("persist", True)
    return svc.generate_schedule(
        db, plan_kind, plan_id, tenant_id, payload, actor_id=current.id
    )


# ── PP-3: server-rendered contract / coupons ─────────────────────────────────
@router.get(
    "/payment-plans/{plan_kind}/{plan_id}/contract",
    response_model=ContractResponse,
    operation_id="get_payment_plan_contract",
    summary="Server-computed contract payload (Truth-in-Lending box + schedule, PP-3)",
)
def get_contract(db: DbSession, tenant_id: TenantId, plan_kind: PlanKindPath, plan_id: PlanId):
    return svc.build_contract(db, plan_kind, plan_id, tenant_id)


@router.get(
    "/payment-plans/{plan_kind}/{plan_id}/contract.pdf",
    operation_id="get_payment_plan_contract_pdf",
    summary="Server-rendered contract PDF (PP-3)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Contract PDF"}},
)
def get_contract_pdf(db: DbSession, tenant_id: TenantId, plan_kind: PlanKindPath, plan_id: PlanId):
    contract = svc.build_contract(db, plan_kind, plan_id, tenant_id)
    return Response(
        content=svc.render_contract_pdf(contract),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="contract-{plan_kind}-{plan_id}.pdf"'
        },
    )


@router.get(
    "/payment-plans/{plan_kind}/{plan_id}/coupons.pdf",
    operation_id="get_payment_plan_coupons_pdf",
    summary="Server-rendered payment-coupon strip PDF (PP-3)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Coupons PDF"}},
)
def get_coupons_pdf(db: DbSession, tenant_id: TenantId, plan_kind: PlanKindPath, plan_id: PlanId):
    contract = svc.build_contract(db, plan_kind, plan_id, tenant_id)
    return Response(
        content=svc.render_coupons_pdf(contract),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="coupons-{plan_kind}-{plan_id}.pdf"'
        },
    )
