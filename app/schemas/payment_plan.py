"""Payment-plan schemas — Ortho + Regular contracts.

Covers the gaps in ``docs/payment-plans/payment_plans_backend_devreport.md``:

* enriched read models (OPP-11 / PP-7 — resolvable actor + office names),
* a constrained ``plan_type`` on the write models (PP-8),
* the request/response contracts for the periodic-billing posting endpoints
  (PP-2), the server-side amortisation/schedule endpoints (OPP-9 / RPP-5) and
  the server-rendered contract document (PP-3).

Read models keep the generated component names; the factory output is subclassed
under a private ``…Full`` name so each public component is defined exactly once
(same pattern as :mod:`app.schemas.enriched`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, BeforeValidator, Field, create_model

from app.db import models as m
from app.schemas.factory import build_schemas

PlanKind = Literal["ortho", "regular"]
PlanSide = Literal["patient", "ins", "sec_ins"]


def _norm_plan_type(value):  # noqa: ANN001, ANN202
    """PP-8: accept the FE's casing variants, store the canonical vocabulary."""
    return value.strip().lower() if isinstance(value, str) else value


# PP-8: `plan_type` was unconstrained free text; the vocabulary is now enforced
# on writes. Reads stay a plain ``str`` so migrated legacy values still serialise.
PlanType = Annotated[Literal["regular", "ortho"], BeforeValidator(_norm_plan_type)]


# ── ortho_plans ──────────────────────────────────────────────────────────────
OrthoPlanCreate, OrthoPlanUpdate, _ortho_base = build_schemas(m.OrthoPlan, "OrthoPlanFull")

OrthoPlanRead = create_model(
    "OrthoPlanRead",
    __base__=_ortho_base,
    # OPP-11 / PP-7 — resolved by ``enrich_ortho_plan``.
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
    pref_provider_name=(Optional[str], None),
    created_office_name=(Optional[str], None),
    created_office_code=(Optional[str], None),
)


# ── patient_payment_plans ────────────────────────────────────────────────────
_ppl_create, _ppl_update, _ppl_base = build_schemas(
    m.PatientPaymentPlan, "PatientPaymentPlanFull"
)

PatientPaymentPlanCreate = create_model(
    "PatientPaymentPlanCreate", __base__=_ppl_create, plan_type=(PlanType, "regular")
)
PatientPaymentPlanUpdate = create_model(
    "PatientPaymentPlanUpdate", __base__=_ppl_update, plan_type=(Optional[PlanType], None)
)
PatientPaymentPlanRead = create_model(
    "PatientPaymentPlanRead",
    __base__=_ppl_base,
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
)


# ── PP-2: post a due instalment to the patient ledger ────────────────────────
class PostInstallmentRequest(BaseModel):
    """Overrides for a single posting. Everything is optional — the service
    resolves each value from the contract, then the patient, before failing."""

    post_date: date | None = Field(
        None, description="Ledger date of service (defaults to the instalment's periodic_date)"
    )
    procedure_code: str | None = Field(
        None, description="Billing code to charge (defaults to the instalment/contract code)"
    )
    fee: Decimal | None = Field(None, description="Charge amount (defaults to periodic_amt)")
    provider_id: str | None = Field(
        None,
        description="Defaults to the plan's pref_provider_id, then the patient's preferred"
                    " provider",
    )
    office_id: int | None = Field(
        None, description="Defaults to the plan's office, then the patient's home office"
    )
    notes: str | None = None


class PostedInstallment(BaseModel):
    installment_id: int
    source: str = Field(..., description="ins | sec_ins | patient — which instalment table")
    patient_id: int
    periodic_order: int | None = None
    periodic_date: date | None = None
    ledger_id: str = Field(..., description="patient_procedures.id of the posted charge")
    procedure_code: str
    amount: Decimal
    post_date: date
    provider_id: str
    office_id: int


class SkippedInstallment(BaseModel):
    installment_id: int
    source: str
    reason: str


class PostDueRequest(BaseModel):
    """PP-2 batch: post every instalment due on/before ``through_date``."""

    patient_id: int | None = Field(None, description="Limit to one patient (omit = whole tenant)")
    ortho_plan_id: int | None = None
    payment_plan_id: int | None = None
    through_date: date | None = Field(None, description="Defaults to today (UTC)")
    sides: list[PlanSide] | None = Field(
        None, description="Which instalment tables to sweep (default: all three)"
    )
    dry_run: bool = Field(False, description="Report what would post without writing")


class PostDueResult(BaseModel):
    posted: list[PostedInstallment] = []
    skipped: list[SkippedInstallment] = []
    total_posted_amount: Decimal = Decimal("0")
    through_date: date
    dry_run: bool = False


# ── OPP-9 / RPP-5: patient-side instalment schedule ──────────────────────────
class InstallmentIn(BaseModel):
    periodic_order: int | None = None
    periodic_date: date | None = None
    periodic_amt: Decimal | None = None
    plan_amount: Decimal | None = None
    down_payment: Decimal | None = None
    rem_total_amt: Decimal | None = None
    rem_payments: int | None = None
    billing_code: str | None = None


class ReplaceInstallmentsRequest(BaseModel):
    installments: list[InstallmentIn] = Field(default_factory=list)


class GenerateScheduleRequest(BaseModel):
    """Server-side amortisation from the contract's own terms (OPP-10/RPP-1).

    Anything left ``None`` is read off the contract row, so the usual call is an
    empty body: the server is then the single source of truth for the schedule.
    """

    amount_financed: Decimal | None = None
    down_payment: Decimal | None = None
    apr: Decimal | None = Field(None, description="Annual percentage rate, e.g. 12.5")
    num_payments: int | None = None
    first_due_date: date | None = None
    interval_type: str | None = Field(
        None, description="monthly | semi_monthly | weekly | bi_weekly | quarterly | annually"
    )
    billing_code: str | None = None
    persist: bool = Field(True, description="Write the rows (False = preview only)")


class ScheduleTerms(BaseModel):
    """The Truth-in-Lending style box, computed server-side."""

    amount_financed: Decimal = Decimal("0")
    down_payment: Decimal = Decimal("0")
    apr: Decimal = Decimal("0")
    finance_charge: Decimal = Decimal("0")
    total_of_payments: Decimal = Decimal("0")
    periodic_amt: Decimal = Decimal("0")
    num_payments: int = 0
    interval_type: str = "monthly"
    first_due_date: date | None = None
    final_due_date: date | None = None


class ScheduleRow(BaseModel):
    installment_id: int | None = None
    periodic_order: int
    periodic_date: date | None = None
    periodic_amt: Decimal = Decimal("0")
    rem_payments: int = 0
    rem_total_amt: Decimal = Decimal("0")
    is_billed: bool = False
    ledger_id: str | None = None
    billing_code: str | None = None


class ScheduleResponse(BaseModel):
    plan_kind: PlanKind
    plan_id: int
    patient_id: int
    plan_side: PlanSide = "patient"
    terms: ScheduleTerms
    rows: list[ScheduleRow] = []
    persisted: bool = False


# ── PP-3: server-rendered contract / coupons ─────────────────────────────────
class ContractParty(BaseModel):
    patient_id: int
    patient_name: str | None = None
    chart_no: str | None = None
    address: str | None = None
    phone: str | None = None
    responsible_party_name: str | None = None


class ContractResponse(BaseModel):
    """Everything the printed contract shows, computed server-side so the paper
    output and any reconciliation report agree (PP-3)."""

    plan_kind: PlanKind
    plan_id: int
    party: ContractParty
    office_name: str | None = None
    provider_name: str | None = None
    setup_date: date | None = None
    billing_code: str | None = None
    initial_billing_code: str | None = None
    financial_disclosure: str | None = None
    disclosure_text: str | None = None
    terms: ScheduleTerms
    rows: list[ScheduleRow] = []
    notes: str | None = None
    created_by_name: str | None = None
    generated_at: str
