"""Identity & Organisation domain models.

tenants · users · refresh_tokens · offices · providers · operatories ·
user_offices · office_groups
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, LegacyIdMixin, TimestampMixin


class Tenant(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "tenants"

    legacy_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(80), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "users"
    # short_id is the legacy 6-char user code; unique within a tenant (NULLs allowed).
    __table_args__ = (
        UniqueConstraint("tenant_id", "short_id", name="uq_users_tenant_short_id"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(50), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(50), default="staff")
    # Security tab (Users module gap #4): scalar patient-data access level.
    patient_access_level: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None]
    # Authentication module (login dev-report §3): legacy onboarding gates.
    is_legacy_user: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_activation_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    password_created_at: Mapped[datetime | None]
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # Audit Information panel (users dev-report gap #8): who last edited this user.
    # ``updated_at`` is already provided by TimestampMixin.
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # ── Security -> Users (users_missing_fields dev-report): structural gaps ──
    short_id: Mapped[str | None] = mapped_column(String(6), index=True)  # gap #1
    report_access_provider_id: Mapped[str | None] = mapped_column(  # gap #2
        String(50), ForeignKey("providers.id")
    )
    custom_1: Mapped[str | None] = mapped_column(String(255))  # gap #3
    custom_2: Mapped[str | None] = mapped_column(String(255))  # gap #3
    signature_data: Mapped[str | None] = mapped_column(Text)  # gap #4 (base64 Topaz capture)
    # PN-1: per-user signature metadata so "Load My Signature" can round-trip
    # independent of any patient. ``signature_updated_at`` is when the signature
    # itself last changed (distinct from the row's ``updated_at``).
    signature_len: Mapped[int | None]
    signature_device_source: Mapped[str | None] = mapped_column(String(20))
    signature_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    image_url: Mapped[str | None] = mapped_column(String(500))  # gap #5 (avatar)
    # PDP-3: server-side persistent default patient (last opened). ON DELETE SET
    # NULL so a hard-deleted patient can't strand the user on a 404; soft-deleted
    # patients are filtered to null at read time (PDP-4).
    last_patient_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("patients.id", ondelete="SET NULL")
    )


class RefreshToken(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime]
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AuthActionToken(Base, IntPKMixin, CreatedAtMixin):
    """Single-use, TTL-bounded token for password-reset & legacy activation.

    Authentication module (login dev-report §2.1–2.5 / §4). DB-backed (not Redis)
    so the flows work reliably regardless of cache availability. Only the SHA-256
    of the raw token is stored; the raw value is delivered to the user (emailed
    for reset, returned by the legacy-verify endpoint for activation).
    """

    __tablename__ = "auth_action_tokens"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(30))  # password_reset | legacy_activation
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None]


class Office(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "offices"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    office_code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    short_id: Mapped[str | None] = mapped_column(String(20))
    # LTR-3: the corporate / DBA name printed by the #OFFICE_CNAME# merge field.
    # 17 letter templates use it; without it they printed ``name`` twice.
    corporate_name: Mapped[str | None] = mapped_column(String(255))
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    fax: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")
    slot_interval_minutes: Mapped[int] = mapped_column(Integer, default=10)
    schedule_start_hour: Mapped[int] = mapped_column(Integer, default=8)
    schedule_end_hour: Mapped[int] = mapped_column(Integer, default=17)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # ── Billing configuration (Office Setup -> Info tab, gap #11) ─────────────
    phone_2: Mapped[str | None] = mapped_column(String(20))
    phone_ext: Mapped[str | None] = mapped_column(String(10))
    tax_id: Mapped[str | None] = mapped_column(String(50))
    billing_provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    use_billing_license: Mapped[bool] = mapped_column(Boolean, default=False)
    office_group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("office_groups.id"))
    opening_date: Mapped[date | None]
    default_fee_schedule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("fee_schedules.id"))
    default_ucr_fee_schedule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("fee_schedules.id"))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class Provider(Base, CreatedAtMixin):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(20))
    short_id: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(50), default="dentist")
    npi: Mapped[str | None] = mapped_column(String(50))
    license: Mapped[str | None] = mapped_column(String(100))
    tax_id: Mapped[str | None] = mapped_column(String(50))
    dea_id: Mapped[str | None] = mapped_column(String(50))
    specialty: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Office Assignment -> Providers grid (gap #28): legacy split-name + audit columns.
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # Provider Setup -> User & Permissions (provider dev-report gap #6): linked user account.
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    # Provider Setup -> Info "Provider/Advanced Settings" (provider dev-report gap #7).
    scheduler_color: Mapped[str | None] = mapped_column(String(20))  # hex
    is_ortho_provider: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_in_appointnow: Mapped[bool] = mapped_column(Boolean, default=True)
    # LTR-3: provider letterhead. 10 letter templates print the *provider's* own
    # address/phone block (#PAT_PREF_PROV_Address# …); with no columns they fell
    # back to the office block, i.e. the wrong address on a patient-facing letter.
    # Still nullable — the merge falls back to the office when unset.
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    default_provider_time: Mapped[int | None] = mapped_column(Integer)  # minutes
    is_billing_provider: Mapped[bool] = mapped_column(Boolean, default=False)
    dosespot_user_id: Mapped[str | None] = mapped_column(String(100))
    updox_direct_address: Mapped[str | None] = mapped_column(String(255))
    denticon_user_id: Mapped[str | None] = mapped_column(String(100))
    print_separate_claim_form: Mapped[bool] = mapped_column(Boolean, default=False)
    ortho_questionnaire_template: Mapped[str | None] = mapped_column(String(100))
    custom_1: Mapped[str | None] = mapped_column(String(255))
    custom_2: Mapped[str | None] = mapped_column(String(255))


class Operatory(Base, CreatedAtMixin):
    __tablename__ = "operatories"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(100))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    # Scheduler gap #1: default provider shown in the operatory column header.
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserOffice(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "user_offices"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class OfficeGroup(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "office_groups"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    address2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(100))
