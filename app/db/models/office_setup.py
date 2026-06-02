"""Office Setup module models (Setup -> Offices, per-office configuration).

Backs the tabs that had no persistence: Statement (#12), Integration (#13),
Schedule (#14), Advanced (#16), SmartAssist (#17). All office-scoped and reached
only after verifying the office belongs to the authenticated tenant.

- office_statement_settings  1:1 office — Statement tab (messages + settings + logo)
- office_integrations        1:1 office — Integration tab
- office_schedule_days       7 per office — Schedule tab weekly grid
- office_advanced_settings   1:1 office — Advanced tab
- office_smart_assist        1:1 office — SmartAssist master toggle
- office_smart_assist_items  N per office — SmartAssist item grid
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class OfficeStatementSettings(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "office_statement_settings"
    __table_args__ = (UniqueConstraint("office_id", name="uq_office_statement_settings_office"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    # Monthly statement messages (<=100 chars each)
    message_general: Mapped[str | None] = mapped_column(String(100))
    message_current: Mapped[str | None] = mapped_column(String(100))
    message_30: Mapped[str | None] = mapped_column(String(100))
    message_60: Mapped[str | None] = mapped_column(String(100))
    message_90: Mapped[str | None] = mapped_column(String(100))
    message_120: Mapped[str | None] = mapped_column(String(100))
    # Settings
    correspondence_name: Mapped[str | None] = mapped_column(String(255))
    logo_option: Mapped[str] = mapped_column(String(20), default="office")  # office | custom | none
    logo_url: Mapped[str | None] = mapped_column(String(500))
    address_source: Mapped[str] = mapped_column(String(20), default="office")  # office | custom
    statement_address_1: Mapped[str | None] = mapped_column(String(255))
    statement_address_2: Mapped[str | None] = mapped_column(String(255))
    statement_city: Mapped[str | None] = mapped_column(String(100))
    statement_state: Mapped[str | None] = mapped_column(String(50))
    statement_zip: Mapped[str | None] = mapped_column(String(20))
    statement_phone: Mapped[str | None] = mapped_column(String(20))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class OfficeIntegrations(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "office_integrations"
    __table_args__ = (UniqueConstraint("office_id", name="uq_office_integrations_office"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    service_email: Mapped[str | None] = mapped_column(String(255))
    service_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_assist_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    patient_comm_url: Mapped[str | None] = mapped_column(String(500))
    patient_portal_url: Mapped[str | None] = mapped_column(String(500))
    dentiray_storage_format: Mapped[str | None] = mapped_column(String(50))
    transfirst_device: Mapped[str | None] = mapped_column(String(100))
    dosespot_clinic_id: Mapped[str | None] = mapped_column(String(100))
    dosespot_key_enc: Mapped[str | None] = mapped_column(Text)  # encrypted; returned masked
    accepted_cards: Mapped[str | None] = mapped_column(String(255))  # CSV e.g. "visa,mc,amex"
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class OfficeScheduleDay(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "office_schedule_days"
    __table_args__ = (UniqueConstraint("office_id", "day_of_week", name="uq_office_schedule_day"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Mon … 6=Sun
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    lunch_start: Mapped[time | None] = mapped_column(Time)
    lunch_end: Mapped[time | None] = mapped_column(Time)


class OfficeAdvancedSettings(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "office_advanced_settings"
    __table_args__ = (UniqueConstraint("office_id", name="uq_office_advanced_settings_office"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    # Financial
    finance_charge_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    min_balance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    min_charge: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    days_before_charge: Mapped[int | None]
    sales_tax_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Insurance / scheduler defaults
    default_appt_duration: Mapped[int | None]
    scheduler_end_date: Mapped[date | None]
    place_of_service: Mapped[str | None] = mapped_column(String(50))
    area_code: Mapped[str | None] = mapped_column(String(10))
    default_city: Mapped[str | None] = mapped_column(String(100))
    default_state: Mapped[str | None] = mapped_column(String(50))
    default_zip: Mapped[str | None] = mapped_column(String(20))
    preferred_provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    is_ortho: Mapped[bool] = mapped_column(Boolean, default=False)
    # Patient check-in
    hipaa_notice: Mapped[str | None] = mapped_column(Text)
    consent_forms: Mapped[str | None] = mapped_column(Text)
    # Automation
    send_ecard: Mapped[bool] = mapped_column(Boolean, default=False)
    effective_date: Mapped[date | None]
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class OfficeSmartAssist(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "office_smart_assist"
    __table_args__ = (UniqueConstraint("office_id", name="uq_office_smart_assist_office"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class OfficeSmartAssistItem(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "office_smart_assist_items"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    item_code: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(500))
    frequency: Mapped[str | None] = mapped_column(String(30))  # EVERY_VISIT | EVERY_YEAR | …
    sms_template_id: Mapped[str | None] = mapped_column(String(50))
    include_unpaid_balance: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
