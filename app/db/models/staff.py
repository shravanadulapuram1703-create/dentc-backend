"""Staff & operations domain models.

time_clock_entries · provider_insurance_ids · provider_route_slips
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin


class TimeClockEntry(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "time_clock_entries"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    clock_in: Mapped[datetime] = mapped_column()
    clock_out: Mapped[datetime | None]
    total_hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))


class ProviderInsuranceId(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "provider_insurance_ids"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    carrier_id: Mapped[int] = mapped_column(Integer, ForeignKey("insurance_carriers.id"), index=True)
    ins_id: Mapped[str | None] = mapped_column(String(100))
    in_network: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100))


class ProviderRouteSlip(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "provider_route_slips"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    procedure_code: Mapped[str | None] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    num_times: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str | None] = mapped_column(String(100))
