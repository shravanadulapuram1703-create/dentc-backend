"""Provider Setup module models (Setup -> Providers, per-provider configuration).

Backs the Provider Setup tabs that had no persistence (provider setup backend
dev-report gaps #1–#5). Every table is ``tenant_id``-scoped and reached only after
verifying the provider belongs to the authenticated tenant.

- provider_schedule_days   N per provider — Schedules tab (gap #1, per-day/office hours)
- provider_holidays        N per provider — Holidays tab (gap #2, time off)
- provider_watermarks      1:1 provider  — Watermarks tab (gap #3, document images)
- provider_referral_offices N per provider — Referrals tab (gap #4, receive-at allow-list)
- provider_carrier_logins  N per provider — Carrier Login tab (gap #5, encrypted creds)
"""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class ProviderScheduleDay(Base, IntPKMixin, CreatedAtMixin):
    """Per-provider working hours by day/office with an effective-from date (gap #1)."""

    __tablename__ = "provider_schedule_days"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    # NULL = applies to every office the provider works at; set = office-specific hours.
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Mon … 6=Sun
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    lunch_start: Mapped[time | None] = mapped_column(Time)
    lunch_end: Mapped[time | None] = mapped_column(Time)
    effective_from: Mapped[date | None] = mapped_column(Date)


class ProviderHoliday(Base, IntPKMixin, TimestampMixin):
    """Provider-specific time off (gap #2)."""

    __tablename__ = "provider_holidays"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    holiday_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(20))  # CLOSED | OPEN | HALF_DAY
    holiday_type: Mapped[str | None] = mapped_column(String(20))  # FEDERAL | CUSTOM
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ProviderWatermark(Base, IntPKMixin, TimestampMixin):
    """1:1 with provider. Per-provider document watermark/signature images (gap #3)."""

    __tablename__ = "provider_watermarks"
    __table_args__ = (UniqueConstraint("provider_id", name="uq_provider_watermarks_provider"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    watermark_image_url: Mapped[str | None] = mapped_column(String(500))
    signature_image_url: Mapped[str | None] = mapped_column(String(500))
    opacity: Mapped[int | None] = mapped_column(Integer)  # 0–100
    position: Mapped[str | None] = mapped_column(String(30))  # center | top_left | …
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ProviderReferralOffice(Base, IntPKMixin, CreatedAtMixin):
    """M:N provider↔office allow-list — offices where a provider receives referrals (gap #4)."""

    __tablename__ = "provider_referral_offices"
    __table_args__ = (
        UniqueConstraint("provider_id", "office_id", name="uq_provider_referral_office"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)


class ProviderCarrierLogin(Base, IntPKMixin, TimestampMixin):
    """Per-provider carrier portal credentials (gap #5). Password encrypted at rest."""

    __tablename__ = "provider_carrier_logins"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    carrier_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_carriers.id"), index=True)
    portal_name: Mapped[str | None] = mapped_column(String(255))
    portal_url: Mapped[str | None] = mapped_column(String(500))
    username: Mapped[str | None] = mapped_column(String(255))
    password_enc: Mapped[str | None] = mapped_column(Text)  # encrypted; returned masked
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
