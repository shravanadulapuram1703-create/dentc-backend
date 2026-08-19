"""Office Assignment module models (Setup -> Offices -> Office Assignment).

Many-to-many link tables that scope tenant-wide catalogs to a specific office
(mirroring the existing ``user_offices`` pattern), plus the one genuinely new
catalog the screen needs (``production_types``). Resolves gaps #24, #25*, #26,
#28, #29, #30, #31.

(* #25 "Exp Codes" reuses the existing ``code_bundles`` catalog — the Denticon
CODESEXPLOSION* source — so only a link table is new here.)

Every link row carries ``tenant_id`` + ``office_id`` and is unique per
(office, target) so assignment is idempotent.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin


class ProductionType(Base, IntPKMixin, CreatedAtMixin):
    """New tenant-wide catalog (gap #26). Assigned to offices via the link below."""

    __tablename__ = "production_types"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    appointnow_visible: Mapped[bool] = mapped_column(default=False)
    appointnow_duration: Mapped[int | None]
    is_inactive: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)


class OfficeProcedureCode(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "office_procedure_codes"
    __table_args__ = (UniqueConstraint("office_id", "procedure_code", name="uq_office_procedure_code"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    procedure_code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"))


class OfficeCodeBundle(Base, IntPKMixin, CreatedAtMixin):
    """Exp Codes (#25) — code_bundles assigned to an office."""

    __tablename__ = "office_code_bundles"
    __table_args__ = (UniqueConstraint("office_id", "bundle_id", name="uq_office_code_bundle"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    bundle_id: Mapped[int] = mapped_column(Integer, ForeignKey("code_bundles.id"))


class OfficeProductionType(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "office_production_types"
    __table_args__ = (UniqueConstraint("office_id", "production_type_id", name="uq_office_production_type"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    production_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("production_types.id"))


class ProviderOffice(Base, IntPKMixin, CreatedAtMixin):
    """M:N provider↔office (gap #28) — a provider may serve multiple offices."""

    __tablename__ = "provider_offices"
    __table_args__ = (UniqueConstraint("office_id", "provider_id", name="uq_provider_office"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    # PROV-1: read from the provider direction too — `GET /providers?office_id=`
    # unions this assignment with the legacy `providers.office_id` home scalar.
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"), index=True)


class OfficeNoteMacro(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "office_note_macros"
    __table_args__ = (UniqueConstraint("office_id", "note_macro_id", name="uq_office_note_macro"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    note_macro_id: Mapped[int] = mapped_column(Integer, ForeignKey("note_macros.id"))


class OfficePrescriptionLibrary(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "office_prescription_library"
    __table_args__ = (UniqueConstraint("office_id", "prescription_library_id", name="uq_office_rx"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    prescription_library_id: Mapped[int] = mapped_column(Integer, ForeignKey("prescription_library.id"))


class OfficeLetterTemplate(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "office_letter_templates"
    __table_args__ = (UniqueConstraint("office_id", "letter_template_id", name="uq_office_letter_template"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    letter_template_id: Mapped[int] = mapped_column(Integer, ForeignKey("letter_templates.id"))
