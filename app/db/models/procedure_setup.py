"""Procedure Code Setup module models (Setup -> Procedure Codes).

Backs the procedure-code dev-report gaps that need new tables:
- provider_procedure_codes   M:N provider↔code allow-list (PROC-2 permissions)
- procedure_insurance_rules   per-CDT-code, plan-agnostic coverage rules (PROC-3)

(PROC-1 charting + PROC-4 "Main" fields live as columns on ``procedure_codes``.)
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class ProviderProcedureCode(Base, IntPKMixin, CreatedAtMixin):
    """M:N provider↔procedure-code permission (PROC-2)."""

    __tablename__ = "provider_procedure_codes"
    __table_args__ = (
        UniqueConstraint("provider_id", "procedure_code", name="uq_provider_procedure_code"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)
    procedure_code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"), index=True)


class ProcedureInsuranceRule(Base, IntPKMixin, TimestampMixin):
    """Per-CDT-code, plan-agnostic insurance mapping (PROC-3)."""

    __tablename__ = "procedure_insurance_rules"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    procedure_code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"), index=True)
    coverage_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    frequency_limit: Mapped[str | None] = mapped_column(String(50))
    age_limit: Mapped[str | None] = mapped_column(String(50))
    wait_period: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
