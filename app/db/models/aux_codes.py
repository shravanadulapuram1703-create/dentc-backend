"""Auxiliary code-table models (Setup -> Procedure Codes).

Reference tables that don't fit the generic ``definitions`` (key1/key2/description)
shape:

- place_of_service_codes  tenant-scoped — CMS POS list with a per-office Tax ID (AUX-3)
- icd_codes               global catalog — diagnosis codes + ICD-9/10/SNOMED crosswalk (AUX-4)

(Modifier and Type-of-Service codes are flat 2-column lists → seeded as ``definitions``
groups ``MODIFIER`` / ``TYPEOFSERVICE``; no model needed.)

``icd_codes`` is global (no ``tenant_id``), mirroring ``procedure_codes`` — both are
standard external code sets shared across tenants.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin


class PlaceOfServiceCode(Base, IntPKMixin, CreatedAtMixin):
    """CMS Place-of-Service codes with a per-office Tax ID (AUX-3)."""

    __tablename__ = "place_of_service_codes"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(10), index=True)  # CMS POS code, e.g. "11"
    type: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(255))  # "Name of Place"
    tax_id: Mapped[str | None] = mapped_column(String(50))  # per-office; nullable
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class IcdCode(Base, IntPKMixin, CreatedAtMixin):
    """Diagnosis-code reference set with crosswalk columns (AUX-4). Global, like procedure_codes."""

    __tablename__ = "icd_codes"

    code: Mapped[str] = mapped_column(String(20), index=True)  # display code, e.g. "327.2"
    description: Mapped[str] = mapped_column(String(500))
    icd9: Mapped[str | None] = mapped_column(String(20))
    icd10: Mapped[str | None] = mapped_column(String(20))
    snomed: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
