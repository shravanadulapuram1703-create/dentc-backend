"""Insurance domain models.

employers · insurance_carriers · insurance_plans · insurance_subscribers ·
insurance_coverage_rules · insurance_plan_frequency_groups
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class Employer(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "employers"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    # INS-PT-11: the legacy EMPLOYER DETAILS dialog has two address lines. They
    # were being joined on a newline into ``address`` client-side, which made the
    # second line unaddressable (and unsearchable) — ``insurance_carriers`` has
    # carried ``address2`` since INS-4, so this is the same shape.
    address2: Mapped[str | None] = mapped_column(String(255))
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


class InsurancePlan(Base, IntPKMixin, TimestampMixin):
    """A plan row is shared by every patient linked to it, which is why the patient
    screen renders it read-only and edits belong in Setup -> Insurance -> Plans.

    INS-PT-8: the Setup grid shows **Created** and **Modified** as *date + user*.
    ``TimestampMixin`` supplies ``updated_at``; ``updated_by`` is the server-stamped
    actor (``CRUDBase.update``); the four legacy free-text columns mirror
    ``insurance_carriers`` so a migrated row can still name who touched it in
    Denticon, where no ``users`` row exists to point at.
    """

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
    # PLAN-DTL-3: the legacy dialog captures the anniversary as Month/Day only —
    # a plan year "starts on 1 Jan", not "on 1 Jan 2022". The full-date column
    # stays (migrated rows carry one); these two are the canonical *typed*
    # answer, kept in sync by ``InsurancePlanCRUD`` whichever shape is written.
    anniversary_month: Mapped[int | None] = mapped_column(Integer)
    anniversary_day: Mapped[int | None] = mapped_column(Integer)
    # LEG-7: legacy plan header "Anni. Date Exp" alongside the anniversary date.
    anniversary_expiry_date: Mapped[date | None]
    coverage_type: Mapped[str | None] = mapped_column(String(10))
    # PLAN-DTL-1: the nine PLAN/BENEFITS-tab fields that had no column, so the
    # wizard was parking them in browser localStorage per plan id. Codes are
    # stored as written (``insurance_plan_service.PLAN_FIELD_OPTIONS`` publishes
    # the vocabularies) — the PROV-3 call: an unfamiliar string beats a 422 on a
    # form the user cannot otherwise submit.
    # EDIT-PLAN-9: the four coded fields default to the legacy dialog's values
    # (``insurance_plan_service.PLAN_FIELD_DEFAULTS``) so a new row never
    # holds NULL and the first edit of a plan no longer audits four "changes"
    # the user did not make; Alembic ``7f483f6833a7`` backfilled the migrated
    # rows the same way. ``lifetime_ortho_benefits`` defaults **true** — the
    # legacy dialog's default (an ortho maximum is a lifetime figure on almost
    # every plan); migrated rows keep the false the first migration wrote.
    fees_to_print: Mapped[str | None] = mapped_column(String(20), default="office_ucr")
    claim_option: Mapped[str | None] = mapped_column(String(20), default="submit")
    form_to_print: Mapped[str | None] = mapped_column(String(20), default="ADA2024")
    reporting_subtype: Mapped[str | None] = mapped_column(String(50))
    network_type: Mapped[str | None] = mapped_column(String(20), default="unknown")
    noa_only: Mapped[bool] = mapped_column(Boolean, default=False)
    per_visit_copay: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    lifetime_ortho_benefits: Mapped[bool] = mapped_column(Boolean, default=True)
    plan_notes: Mapped[str | None] = mapped_column(Text)
    # EDIT-PLAN-5: a locked plan can only be edited (or unlocked) by a caller
    # holding ``setup_insurance_plans_screen_edit_locked_plan`` — the right
    # existed in the catalog with nothing to honour it. ``locked_at``/
    # ``locked_by`` are stamped server-side when the flag flips on.
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_at: Mapped[datetime | None]
    locked_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # INS-PT-8: legacy free-text audit (migrated source), same shape as the carrier.
    created_on: Mapped[datetime | None]
    created_by: Mapped[str | None] = mapped_column(String(100))
    modified_on: Mapped[datetime | None]
    modified_by: Mapped[str | None] = mapped_column(String(100))
    # INS-PT-8: server-maintained modified actor (``updated_at`` via TimestampMixin).
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
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
    # ADA-BE-10: subscriber name suffix (Items 5 / 12, 837D NM107). ``sub_``
    # prefixed like every other subscriber demographic column on this table.
    sub_suffix: Mapped[str | None] = mapped_column(String(10))
    sub_address: Mapped[str | None] = mapped_column(String(255))
    # INS-PT-4: legacy screen has two subscriber address lines.
    sub_address2: Mapped[str | None] = mapped_column(String(255))
    sub_city: Mapped[str | None] = mapped_column(String(100))
    sub_state: Mapped[str | None] = mapped_column(String(50))
    sub_zip: Mapped[str | None] = mapped_column(String(20))
    sub_dob: Mapped[date | None]
    sub_gender: Mapped[str | None] = mapped_column(String(10))
    # INS-PT-1 / INS-PT-2: legacy subscriber Marital Status + Phone.
    marital_status: Mapped[str | None] = mapped_column(String(20))
    sub_phone: Mapped[str | None] = mapped_column(String(20))
    sub_ssn: Mapped[str | None] = mapped_column(String(20))
    sub_member_id: Mapped[str | None] = mapped_column(String(100))
    group_number: Mapped[str | None] = mapped_column(String(100))
    effective_date: Mapped[date | None]
    term_date: Mapped[date | None]
    # INS-PT-6: legacy Eligibility grid distinguishes Plan Date from Sub Date
    # (effective_date/term_date above are the subscriber dates).
    plan_effective_date: Mapped[date | None]
    plan_term_date: Mapped[date | None]
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


class InsuranceCoverageRule(Base, IntPKMixin, TimestampMixin):
    """One row of a plan's COVERAGE & LIMITATIONS table.

    Two row shapes share the table and the estimate engine honours both
    (``estimate_service._match_rule``): a **category** row (``start_code`` =
    ``end_code`` = a Denticon coverage-category code such as ``03A``,
    ``category="0"``) and an **exception** row (``start_code`` = ``end_code`` =
    an ADA code, ``category`` = the parent category code). Migrated plans also
    band on real ADA ranges (``D0100``–``D0999``).

    PLAN-DTL-5: the three limit columns were free-text strings. ``freq_limit`` is
    now an **integer ordinal** into the frequency catalogue (PLAN-DTL-4,
    ``insurance_plan_service.FREQUENCY_LIMITATIONS``; ``0``/NULL = no limitation)
    and ``age_min``/``age_max``/``wait_months`` are the typed limits. The legacy
    ``age_limit``/``wait_period`` strings are kept as **derived mirrors** —
    written by the server from the typed columns on every save, parsed *into*
    them when an older client still sends only the string — so no reader breaks
    during the cutover and there is exactly one source of truth.

    The table has no ``tenant_id``; ``InsuranceCoverageRuleCRUD`` scopes every
    access through the owning plan.
    """

    __tablename__ = "insurance_coverage_rules"

    ins_plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("insurance_plans.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    start_code: Mapped[str] = mapped_column(String(20))
    end_code: Mapped[str] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255))
    coverage_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ded_waived: Mapped[bool] = mapped_column(Boolean, default=False)
    # PLAN-DTL-4/5: 1-based ordinal into FREQUENCY_LIMITATIONS; 0 / NULL = none.
    freq_limit: Mapped[int | None] = mapped_column(Integer)
    # PLAN-DTL-5: typed limits (canonical).
    age_min: Mapped[int | None] = mapped_column(Integer)
    age_max: Mapped[int | None] = mapped_column(Integer)
    wait_months: Mapped[int | None] = mapped_column(Integer)
    # Legacy string mirrors — derived from the typed columns on every write.
    age_limit: Mapped[str | None] = mapped_column(String(50))
    wait_period: Mapped[str | None] = mapped_column(String(50))
    # PLAN-DTL-9: "Modified On/By" (``updated_at`` via TimestampMixin).
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class InsurancePlanFrequencyGroup(Base, IntPKMixin, TimestampMixin):
    """PLAN-DTL-2: one row of the legacy FREQ LIMITATION CODE GRP tab.

    A code group (a ``definitions`` ``INSLIMITATIONS`` code such as ``01`` =
    "Diagnostic: Periodic Exam (D0120)") limited to a frequency, optionally
    whole-mouth, optionally capped per day. The frontend had been storing these
    as reserved-shape ``insurance_coverage_rules`` rows (``category="FREQGRP"``,
    ``start_code="FQ01"``, whole-mouth encoded as ``age_limit="WM"``) that every
    coverage consumer had to know to skip; Alembic ``c8d9e0f1a2b3`` moves those
    rows here and the coverage-rule write path refuses the shape from now on.
    """

    __tablename__ = "insurance_plan_frequency_groups"
    __table_args__ = (
        # A plan lists each code group once — the legacy grid is keyed by it.
        UniqueConstraint("ins_plan_id", "code_group", name="uq_plan_frequency_groups_plan_code"),
        Index("ix_plan_frequency_groups_tenant_plan", "tenant_id", "ins_plan_id"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    ins_plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("insurance_plans.id"), index=True)
    #: ``definitions.key1`` of the INSLIMITATIONS row (``01``, ``02A``, …).
    code_group: Mapped[str] = mapped_column(String(20))
    #: The code-group label at the time it was chosen (denormalised for the grid).
    description: Mapped[str | None] = mapped_column(String(255))
    #: Same ordinal vocabulary as ``insurance_coverage_rules.freq_limit``.
    freq_limit: Mapped[int | None] = mapped_column(Integer)
    whole_mouth: Mapped[bool] = mapped_column(Boolean, default=False)
    per_day_quantity: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


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
