"""Config & reference data models.

definitions · definition_groups · imaging_templates · questionnaire_headers ·
questionnaire_options
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin


class Definition(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "definitions"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    group_code: Mapped[str] = mapped_column(String(50))
    key1: Mapped[str] = mapped_column(String(50))
    key2: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(255))
    # Scheduler gap #4: centralised color + ordering for definition-driven dropdowns
    # (e.g. appointment status colors).
    color: Mapped[str | None] = mapped_column(String(20))
    sort_order: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_flash_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    blocks_charges: Mapped[bool] = mapped_column(Boolean, default=False)


class DefinitionGroup(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "definition_groups"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(50))
    group_code: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(255))
    key1_label: Mapped[str | None] = mapped_column(String(100))
    key2_label: Mapped[str | None] = mapped_column(String(100))
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True)
    can_add: Mapped[bool] = mapped_column(Boolean, default=True)
    group_type: Mapped[str | None] = mapped_column(String(10))


class ImagingTemplate(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "imaging_templates"

    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    template_type: Mapped[str | None] = mapped_column(String(20))
    dentition: Mapped[str | None] = mapped_column(String(5))


class QuestionnaireHeader(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "questionnaire_headers"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(255))
    is_multi_select: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class QuestionnaireOption(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "questionnaire_options"

    questionnaire_id: Mapped[int] = mapped_column(Integer, ForeignKey("questionnaire_headers.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    answer_code: Mapped[str] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
