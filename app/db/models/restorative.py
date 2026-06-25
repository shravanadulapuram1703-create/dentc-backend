"""Restorative-charting net-new tables (frontend restorative dev-report).

chart_status_templates (REST-2) · chart_settings (REST-3) · chart_tooth_notes (REST-4)
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPKMixin, TimestampMixin


class ChartStatusTemplate(Base, IntPKMixin, TimestampMixin):
    """REST-2: tenant-level bridge/denture preset catalog (practice-editable; the
    frontend previously hardcoded these in ``restorationTemplates.ts``)."""

    __tablename__ = "chart_status_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "legacy_id", name="uq_chart_status_templates_tenant_legacy"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))  # "Upper Anterior 4-Unit (Zircon)"
    label_key: Mapped[str | None] = mapped_column(String(100))  # optional i18n key
    template_type: Mapped[str] = mapped_column(String(50))  # span|arch-bridge|partial-removable|full-removable|bar-denture
    arch: Mapped[str | None] = mapped_column(String(10))  # upper|lower
    material: Mapped[str | None] = mapped_column(String(50))  # zircon|metal-ceramic|emax|gold|acrylic
    teeth: Mapped[dict | None] = mapped_column(JSON)  # {"pillars": int[], "pontics": int[]}
    implants: Mapped[list | None] = mapped_column(JSON)  # int[]
    missing: Mapped[list | None] = mapped_column(JSON)  # int[]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ChartSettings(Base, TimestampMixin):
    """REST-3: per-patient chart view state (1:1 with the patient; replaces the
    frontend's ``restorative:settings:<patient_id>`` localStorage)."""

    __tablename__ = "chart_settings"

    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patients.id"), primary_key=True
    )
    numbering_system: Mapped[str] = mapped_column(String(20), default="UNIVERSAL")  # UNIVERSAL|FDI|PALMER
    wisdom_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    occlusal_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    show_base: Mapped[bool] = mapped_column(Boolean, default=True)
    show_healthy_pulp: Mapped[bool] = mapped_column(Boolean, default=False)
    edentulous: Mapped[bool] = mapped_column(Boolean, default=False)
    arch_mode: Mapped[str] = mapped_column(String(10), default="both")  # both|upper|lower
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ChartToothNote(Base, IntPKMixin, TimestampMixin):
    """REST-4: a free-text note attached to a tooth (not a specific condition).
    One note per (patient, tooth) — replaces the ``condition_code='NOTE'`` interim."""

    __tablename__ = "chart_tooth_notes"
    __table_args__ = (
        UniqueConstraint("patient_id", "tooth", name="uq_chart_tooth_notes_patient_id_tooth"),
    )

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    tooth: Mapped[str] = mapped_column(String(10))  # Universal "1".."32" (or "A".."T")
    note: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
