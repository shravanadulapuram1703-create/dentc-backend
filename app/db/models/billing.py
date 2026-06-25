"""Billing & claims domain models.

patient_payments · insurance_claims · claim_submissions ·
ledger_insurance_details · payment_allocations · patient_payment_plans ·
patient_ins_payment_plans · patient_sec_ins_payment_plans · patient_reg_plans ·
ortho_plans
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class PatientPayment(Base, CreatedAtMixin):
    __tablename__ = "patient_payments"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20), index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_date: Mapped[date] = mapped_column()
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payment_type: Mapped[str] = mapped_column(String(20))
    payment_method: Mapped[str | None] = mapped_column(String(50))
    check_number: Mapped[str | None] = mapped_column(String(100))
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    is_void: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class InsuranceClaim(Base, CreatedAtMixin):
    __tablename__ = "insurance_claims"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    claim_number: Mapped[str] = mapped_column(String(50), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    claim_type: Mapped[str] = mapped_column(String(20), default="primary")
    billing_order: Mapped[str | None] = mapped_column(String(10))
    date_of_service_from: Mapped[date | None]
    date_of_service_to: Mapped[date | None]
    total_billed: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    est_insurance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    submitted_date: Mapped[date | None]
    paid_date: Mapped[date | None]
    close_date: Mapped[date | None]
    billing_provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    treating_provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    carrier_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_carriers.id"))
    ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    is_preauth: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ClaimSubmission(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "claim_submissions"

    claim_id: Mapped[str] = mapped_column(String(50), ForeignKey("insurance_claims.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    batch_id: Mapped[str | None] = mapped_column(String(50))
    is_preauth: Mapped[bool] = mapped_column(Boolean, default=False)
    total_charges: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    num_lines: Mapped[int | None]
    submission_status: Mapped[str | None] = mapped_column(String(10))
    claim_text: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class LedgerInsuranceDetail(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "ledger_insurance_details"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    procedure_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("patient_procedures.id"))
    legacy_ledger_id: Mapped[str | None] = mapped_column(String(20), index=True)
    claim_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("insurance_claims.id"))
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    prim_estimated: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    prim_ind_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    prim_deductible: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    prim_ins_paid: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    prim_ins_adjust: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sec_estimated: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sec_ins_paid: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sec_ins_adjust: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    ter_ins_paid: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    prim_ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    sec_ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    ter_ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    prim_posted: Mapped[bool] = mapped_column(Boolean, default=False)
    sec_posted: Mapped[bool] = mapped_column(Boolean, default=False)


class PaymentAllocation(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "payment_allocations"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    procedure_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("patient_procedures.id"))
    payment_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("patient_payments.id"), index=True)
    claim_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("insurance_claims.id"))
    ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    alloc_date: Mapped[date | None]
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    alloc_type: Mapped[str | None] = mapped_column(String(5))


class PatientPaymentPlan(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "patient_payment_plans"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    plan_bal_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    tx_plan_number: Mapped[str | None] = mapped_column(String(50))
    setup_date: Mapped[date | None]
    amt_financed: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    down_payment: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    apr: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    fin_charge: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    interval_type: Mapped[str | None] = mapped_column(String(20))
    num_payments: Mapped[int | None]
    periodic_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    first_due_date: Mapped[date | None]
    rem_payments: Mapped[int | None]
    rem_total_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # AL-3: discriminate Regular-Patient vs Ortho-Patient contract panels.
    plan_type: Mapped[str] = mapped_column(String(20), default="regular")  # regular | ortho
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(100))


class PatientInsPaymentPlan(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "patient_ins_payment_plans"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    legacy_plan_id: Mapped[str | None] = mapped_column(String(20))
    periodic_order: Mapped[int | None]
    periodic_date: Mapped[date | None]
    periodic_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # AL-3: financial summary so the Ortho-/Regular-Insurance panels can show
    # Plan Amount / Down Pay / Rem-Total / Rem-#-of-Pay (not just Next Per. Amt/Date).
    plan_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    down_payment: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rem_total_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rem_payments: Mapped[int | None]
    is_billed: Mapped[bool] = mapped_column(Boolean, default=False)
    billing_code: Mapped[str | None] = mapped_column(String(50))
    ledger_id: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(100))


class PatientSecInsPaymentPlan(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "patient_sec_ins_payment_plans"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    legacy_plan_id: Mapped[str | None] = mapped_column(String(20))
    periodic_order: Mapped[int | None]
    periodic_date: Mapped[date | None]
    periodic_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # AL-3: financial summary (see PatientInsPaymentPlan).
    plan_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    down_payment: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rem_total_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rem_payments: Mapped[int | None]
    is_billed: Mapped[bool] = mapped_column(Boolean, default=False)
    billing_code: Mapped[str | None] = mapped_column(String(50))
    ledger_id: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(100))


class PatientRegPlan(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "patient_reg_plans"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    setup_date: Mapped[date | None]
    amt_financed: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    down_payment: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    apr: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    fin_charge: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    interval_type: Mapped[str | None] = mapped_column(String(20))
    num_payments: Mapped[int | None]
    periodic_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    first_due_date: Mapped[date | None]
    rem_payments: Mapped[int | None]
    rem_total_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(100))


class OrthoPlan(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "ortho_plans"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    procedure_code: Mapped[str | None] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    description: Mapped[str | None] = mapped_column(String(255))
    total_ortho_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    ins_share_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pat_share_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    treat_start_date: Mapped[date | None]
    treat_end_date: Mapped[date | None]
    banding_date: Mapped[date | None]
    ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    ins_setup_date: Mapped[date | None]
    ins_plan_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    ins_down_pay: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    ins_interval: Mapped[str | None] = mapped_column(String(20))
    ins_num_payments: Mapped[int | None]
    ins_periodic_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    ins_rem_payments: Mapped[int | None]
    ins_rem_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    ins_first_due_date: Mapped[date | None]
    ins_months_remaining: Mapped[int | None]
    ins_notes: Mapped[str | None] = mapped_column(Text)
    pat_amt_financed: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pat_down_pay: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pat_apr: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    pat_fin_charge: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pat_interval: Mapped[str | None] = mapped_column(String(20))
    pat_num_payments: Mapped[int | None]
    pat_periodic_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pat_rem_payments: Mapped[int | None]
    pat_rem_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pat_first_due_date: Mapped[date | None]
    sec_ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    sec_ins_plan_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sec_ins_periodic_amt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sec_ins_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(100))
