"""Identity & Organisation domain models.

tenants · users · refresh_tokens · offices · providers · operatories ·
user_offices · office_groups
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
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
