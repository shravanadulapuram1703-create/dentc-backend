"""Insurance domain models.

employers · insurance_carriers · insurance_plans · insurance_subscribers ·
insurance_coverage_rules
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class Employer(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "employers"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    # Insurance dev-report INS-5: legacy Employer screen fields.
    salesrep: Mapped[str | None] = mapped_column(String(255))
    contact_person: Mapped[str | None] = mapped_column(String(255))
    # INS-5/INS-6: server-maintained audit actors (``updated_at`` via TimestampMixin).
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class InsuranceCarrier(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "insurance_carriers"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    carrier_type: Mapped[str | None] = mapped_column(String(20))
    payer_id: Mapped[str | None] = mapped_column(String(50))
    national_id: Mapped[str | None] = mapped_column(String(50))
    claim_type: Mapped[str | None] = mapped_column(String(10))
    fee_id: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    phone2: Mapped[str | None] = mapped_column(String(20))
    # INS-4: Fax & Email modeled discretely (no longer crammed into notes).
    fax: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    address2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    website: Mapped[str | None] = mapped_column(String(255))
    contact: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    ref_num: Mapped[str | None] = mapped_column(String(50))
    vbs_id: Mapped[str | None] = mapped_column(String(50))
    vbs_pgid: Mapped[str | None] = mapped_column(String(50))
    cda_carrier_transaction_counter: Mapped[str | None] = mapped_column(String(50))
    # INS-3: medical-carrier capability flags (nullable = unknown) + sub-type.
    supports_realtime_eligibility: Mapped[bool | None] = mapped_column(Boolean)
    supports_claim_status: Mapped[bool | None] = mapped_column(Boolean)
    supports_dxc_attachment: Mapped[bool | None] = mapped_column(Boolean)
    insurance_type: Mapped[str | None] = mapped_column(String(50))
    # Legacy free-text audit (migrated source); kept for display.
    created_on: Mapped[datetime | None]
    created_by: Mapped[str | None] = mapped_column(String(100))
    modified_on: Mapped[datetime | None]
    modified_by: Mapped[str | None] = mapped_column(String(100))
    # INS-6: server-maintained modified actor (``updated_at`` via TimestampMixin).
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InsurancePlan(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "insurance_plans"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    carrier_id: Mapped[int] = mapped_column(Integer, ForeignKey("insurance_carriers.id"), index=True)
    employer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employers.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    group_number: Mapped[str | None] = mapped_column(String(100))
    plan_type: Mapped[str | None] = mapped_column(String(50))
    is_prepaid: Mapped[bool] = mapped_column(Boolean, default=False)
    individual_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    individual_deductible: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ortho_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    family_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    family_deductible: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    anniversary_date: Mapped[date | None]
    coverage_type: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InsuranceSubscriber(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "insurance_subscribers"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    ins_plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("insurance_plans.id"), index=True)
    subscriber_patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"))
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    sub_first_name: Mapped[str | None] = mapped_column(String(100))
    sub_last_name: Mapped[str | None] = mapped_column(String(100))
    sub_mi: Mapped[str | None] = mapped_column(String(10))
    sub_address: Mapped[str | None] = mapped_column(String(255))
    sub_city: Mapped[str | None] = mapped_column(String(100))
    sub_state: Mapped[str | None] = mapped_column(String(50))
    sub_zip: Mapped[str | None] = mapped_column(String(20))
    sub_dob: Mapped[date | None]
    sub_gender: Mapped[str | None] = mapped_column(String(10))
    sub_ssn: Mapped[str | None] = mapped_column(String(20))
    sub_member_id: Mapped[str | None] = mapped_column(String(100))
    group_number: Mapped[str | None] = mapped_column(String(100))
    effective_date: Mapped[date | None]
    term_date: Mapped[date | None]
    family_max_remaining: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    family_ded_remaining: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ortho_remaining: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    anniversary_date: Mapped[date | None]
    elig_status: Mapped[str | None] = mapped_column(String(20))
    elig_verified_on: Mapped[datetime | None]
    elig_verified_by: Mapped[str | None] = mapped_column(String(100))
    elig_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InsuranceCoverageRule(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "insurance_coverage_rules"

    ins_plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("insurance_plans.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    start_code: Mapped[str] = mapped_column(String(20))
    end_code: Mapped[str] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255))
    coverage_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ded_waived: Mapped[bool] = mapped_column(Boolean, default=False)
    freq_limit: Mapped[str | None] = mapped_column(String(50))
    age_limit: Mapped[str | None] = mapped_column(String(50))
    wait_period: Mapped[str | None] = mapped_column(String(50))


class InsCustomCoverage(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "ins_custom_coverage"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    start_code: Mapped[str] = mapped_column(String(20))
    end_code: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(String(255))
    coverage_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ded_waived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100))


class FeeScheduleAssignment(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "fee_schedule_assignments"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"), index=True)
    carrier_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_carriers.id"))
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    # FEE-3: legacy "Office Group" target — assign a fee schedule at the group level.
    office_group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("office_groups.id"))
    fee_schedule_id: Mapped[int] = mapped_column(Integer, ForeignKey("fee_schedules.id"), index=True)
    specialty_id: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(100))
