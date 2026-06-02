"""Account Information module models (Setup -> Account Information).

Per-account (tenant) configuration that has nowhere to live on the lean migrated
``tenants`` table. All tables are ``tenant_id``-scoped so multi-account scales
automatically (Tenant == Account).

- account_settings        1:1 tenant — Basic + Advanced configuration
- account_communications  1:1 tenant — Communications tab (TCR/Twilio business info)
- office_phone_assignments N per tenant — Communications phone-number assignments
- account_holidays         N per tenant — Holidays tab
- account_consents         versioned per tenant — Online Registration consent
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class AccountSettings(Base, IntPKMixin, TimestampMixin):
    """1:1 with tenant. Basic + Advanced tabs. Created on first access (upsert)."""

    __tablename__ = "account_settings"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_account_settings_tenant"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)

    # ── Basic: contact / corporate address ──────────────────────────────────
    contact_first_name: Mapped[str | None] = mapped_column(String(100))
    contact_last_name: Mapped[str | None] = mapped_column(String(100))
    corporate_address_1: Mapped[str | None] = mapped_column(String(255))
    corporate_address_2: Mapped[str | None] = mapped_column(String(255))
    corporate_city: Mapped[str | None] = mapped_column(String(100))
    corporate_state: Mapped[str | None] = mapped_column(String(50))
    corporate_zip: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    phone_2: Mapped[str | None] = mapped_column(String(20))
    culture_code: Mapped[str] = mapped_column(String(20), default="en-US")
    custom_1: Mapped[str | None] = mapped_column(String(255))
    custom_2: Mapped[str | None] = mapped_column(String(255))
    pgid: Mapped[str | None] = mapped_column(String(50))
    oid: Mapped[str | None] = mapped_column(String(50))
    logo_url: Mapped[str | None] = mapped_column(String(500))

    # ── Basic: statement address ────────────────────────────────────────────
    statement_use_corporate: Mapped[bool] = mapped_column(Boolean, default=True)
    statement_address_1: Mapped[str | None] = mapped_column(String(255))
    statement_address_2: Mapped[str | None] = mapped_column(String(255))
    statement_city: Mapped[str | None] = mapped_column(String(100))
    statement_state: Mapped[str | None] = mapped_column(String(50))
    statement_zip: Mapped[str | None] = mapped_column(String(20))
    statement_phone: Mapped[str | None] = mapped_column(String(20))

    # ── Advanced: options ─────────────────────────────────────────────────
    theme: Mapped[str | None] = mapped_column(String(50))
    enable_full_screen: Mapped[bool] = mapped_column(Boolean, default=False)
    ortho_claim_fee_mode: Mapped[str | None] = mapped_column(String(50))
    ortho_visit_code: Mapped[str | None] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    max_treatment_plan_discount: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    treatment_plan_discount_code: Mapped[str | None] = mapped_column(String(50))
    per_visit_copay_code: Mapped[str | None] = mapped_column(String(50))
    only_show_office_items: Mapped[bool] = mapped_column(Boolean, default=False)
    statement_close_out_individual: Mapped[bool] = mapped_column(Boolean, default=False)
    statement_close_out_all: Mapped[bool] = mapped_column(Boolean, default=False)
    show_booked_production: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_post_periodic_charges: Mapped[bool] = mapped_column(Boolean, default=False)
    show_flash_alerts_insurance: Mapped[bool] = mapped_column(Boolean, default=False)
    pronoun_field_visible: Mapped[str | None] = mapped_column(String(10))  # YES | NO

    # ── Advanced: ledger colors (values ref chart-colors) ───────────────────
    procedure_color: Mapped[str | None] = mapped_column(String(50))
    insurance_payment_color: Mapped[str | None] = mapped_column(String(50))
    claim_lines_color: Mapped[str | None] = mapped_column(String(50))
    patient_payment_color: Mapped[str | None] = mapped_column(String(50))
    adjustment_color: Mapped[str | None] = mapped_column(String(50))
    statement_lines_color: Mapped[str | None] = mapped_column(String(50))
    notes_lines_color: Mapped[str | None] = mapped_column(String(50))

    # ── Advanced: default settings ──────────────────────────────────────────
    charting_option: Mapped[str | None] = mapped_column(String(50))
    default_charting_tab: Mapped[str | None] = mapped_column(String(50))
    show_production_colors: Mapped[bool] = mapped_column(Boolean, default=False)
    model_office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    default_treatment_plan_filter: Mapped[str | None] = mapped_column(String(50))
    credit_ins_overpayment_to_patient: Mapped[bool] = mapped_column(Boolean, default=False)
    password_expiration_days: Mapped[int] = mapped_column(Integer, default=365)
    scheduler_show_non_working_days: Mapped[bool] = mapped_column(Boolean, default=False)
    email_receipts_to_patients: Mapped[bool] = mapped_column(Boolean, default=False)
    default_fee_increase_code: Mapped[str | None] = mapped_column(String(50))
    default_fee_decrease_code: Mapped[str | None] = mapped_column(String(50))
    default_transfer_code: Mapped[str | None] = mapped_column(String(50))
    default_write_off_code: Mapped[str | None] = mapped_column(String(50))

    # ── Advanced: required-field modes (enums, not bool) ─────────────────────
    phone_required_mode: Mapped[str | None] = mapped_column(String(20))
    dob_required_mode: Mapped[str | None] = mapped_column(String(20))
    ssn_required_mode: Mapped[str | None] = mapped_column(String(20))
    email_required: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Advanced: third party ─────────────────────────────────────────────
    edi_vendor: Mapped[str | None] = mapped_column(String(50))
    transfirst_auto_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    transworld_all_offices: Mapped[bool] = mapped_column(Boolean, default=False)
    transworld_office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    transworld_portal_url: Mapped[str | None] = mapped_column(String(500))
    xvweb_url: Mapped[str | None] = mapped_column(String(500))
    cloud9_url: Mapped[str | None] = mapped_column(String(500))
    auto_eligibility: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Advanced: payment portal / Planet DDS Pay ────────────────────────────
    payment_portal_posting_office: Mapped[str | None] = mapped_column(String(50))  # office id or sentinel
    payment_portal_post_to_rp: Mapped[bool] = mapped_column(Boolean, default=False)
    use_planet_dds_pay: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Advanced: AI Assist (secret encrypted at rest, never returned) ───────
    ai_assist_org_id: Mapped[str | None] = mapped_column(String(100))
    ai_assist_client_id: Mapped[str | None] = mapped_column(String(255))
    ai_assist_client_secret_enc: Mapped[str | None] = mapped_column(Text)

    # ── Audit (per-record, since tenants has none) ───────────────────────────
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class AccountCommunications(Base, IntPKMixin, TimestampMixin):
    """1:1 with tenant. Communications tab — TCR/Twilio toll-free business profile."""

    __tablename__ = "account_communications"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_account_communications_tenant"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    comm_number_type: Mapped[str | None] = mapped_column(String(20))  # toll_free | local_text
    business_name: Mapped[str | None] = mapped_column(String(255))
    region_of_operations: Mapped[str | None] = mapped_column(String(255))
    comm_country: Mapped[str] = mapped_column(String(2), default="US")
    comm_address_1: Mapped[str | None] = mapped_column(String(255))
    comm_address_2: Mapped[str | None] = mapped_column(String(255))
    comm_city: Mapped[str | None] = mapped_column(String(100))
    comm_state: Mapped[str | None] = mapped_column(String(50))
    comm_zip: Mapped[str | None] = mapped_column(String(20))
    ein_enc: Mapped[str | None] = mapped_column(Text)  # encrypted; returned masked
    website: Mapped[str | None] = mapped_column(String(500))
    comm_contact_first_name: Mapped[str | None] = mapped_column(String(100))
    comm_contact_last_name: Mapped[str | None] = mapped_column(String(100))
    business_title: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(100))
    comm_contact_email: Mapped[str | None] = mapped_column(String(255))
    comm_contact_phone: Mapped[str | None] = mapped_column(String(20))
    business_type: Mapped[str | None] = mapped_column(String(50))
    company_status: Mapped[str | None] = mapped_column(String(50))
    stock_symbol: Mapped[str | None] = mapped_column(String(20))
    stock_exchange: Mapped[str | None] = mapped_column(String(50))
    business_identity: Mapped[str | None] = mapped_column(String(255))
    business_industry: Mapped[str | None] = mapped_column(String(100))
    telecom_status: Mapped[str | None] = mapped_column(String(30))
    telecom_verified_at: Mapped[datetime | None]
    telecom_verified_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class OfficePhoneAssignment(Base, IntPKMixin, CreatedAtMixin):
    """N per tenant. Communications -> phone-number assignment to offices."""

    __tablename__ = "office_phone_assignments"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    assignment_type: Mapped[str] = mapped_column(String(30), default="office_specific")  # office_specific | multi_office_shared
    phone_number: Mapped[str | None] = mapped_column(String(20))
    is_model_office: Mapped[bool] = mapped_column(Boolean, default=False)


class AccountHoliday(Base, IntPKMixin, TimestampMixin):
    """N per tenant. Holidays tab."""

    __tablename__ = "account_holidays"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    # NULL = account-level holiday; set = office-scoped (Office Setup -> Holidays, gap #15).
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    holiday_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(20))  # CLOSED | OPEN | HALF_DAY
    holiday_type: Mapped[str | None] = mapped_column(String(20))  # FEDERAL | CUSTOM
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class AccountConsent(Base, IntPKMixin, CreatedAtMixin):
    """Versioned per tenant. Online Registration -> Patient Consent Info."""

    __tablename__ = "account_consents"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    header: Mapped[str] = mapped_column(String(500))
    body_html: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    effective_date: Mapped[date | None]
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    archived_at: Mapped[datetime | None]
