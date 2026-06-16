"""Procedure codes, fee schedules, code bundles, and clinical reference data.

procedure_codes · fee_schedules · fee_schedule_entries · code_bundles ·
code_bundle_items · chart_materials · note_macros · prescription_library
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class ProcedureCode(Base, CreatedAtMixin):
    __tablename__ = "procedure_codes"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    legacy_code: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(100), index=True)
    default_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    default_duration_minutes: Mapped[int | None]
    requires_tooth: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_surface: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_quadrant: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_lab: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ortho: Mapped[bool] = mapped_column(Boolean, default=False)
    billing_order: Mapped[str | None] = mapped_column(String(10))
    recall_interval: Mapped[int | None]
    recall_unit: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # ── PROC-1: detailed charting config (legacy Charting tab) ───────────────
    chart_category: Mapped[str | None] = mapped_column(String(100))
    tooth_area: Mapped[str | None] = mapped_column(String(50))
    draw_as: Mapped[str | None] = mapped_column(String(50))
    min_surfaces: Mapped[int | None]
    max_surfaces: Mapped[int | None]
    default_material_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chart_materials.id"))
    valid_teeth: Mapped[list | None] = mapped_column(JSON)  # e.g. ["1","2",…,"32"]
    # ── PROC-4: legacy "Main" booleans/codes (Provider Settings) ─────────────
    taxable: Mapped[bool] = mapped_column(Boolean, default=False)
    sales_tax_code: Mapped[str | None] = mapped_column(String(50))
    visit_code: Mapped[str | None] = mapped_column(String(50))
    ledger_code: Mapped[str | None] = mapped_column(String(50))
    ar_code: Mapped[str | None] = mapped_column(String(50))
    is_post_op: Mapped[bool] = mapped_column(Boolean, default=False)
    exempt_from_dental_max: Mapped[bool] = mapped_column(Boolean, default=False)
    lock_default_provider: Mapped[bool] = mapped_column(Boolean, default=False)
    default_provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    default_notes_macro_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("note_macros.id"))
    show_ada_code_in_notes: Mapped[bool] = mapped_column(Boolean, default=False)
    nhs_treatment_category: Mapped[str | None] = mapped_column(String(100))
    nhs_clinical_data_set: Mapped[str | None] = mapped_column(String(100))


class FeeSchedule(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "fee_schedules"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    fee_type: Mapped[str | None] = mapped_column(String(50))
    ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    # FEE-4: schedule-level effective date + versioning lineage ("New Effective Date" workflow).
    effective_date: Mapped[date | None]
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_schedule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("fee_schedules.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FeeScheduleEntry(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "fee_schedule_entries"

    fee_schedule_id: Mapped[int] = mapped_column(Integer, ForeignKey("fee_schedules.id"), index=True)
    procedure_code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    # FEE-2: legacy "AMB Code" (alternate/ambulatory billing code) per fee entry.
    amb_code: Mapped[str | None] = mapped_column(String(20))
    patient_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    insurance_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    effective_date: Mapped[date | None]


class ChartMaterial(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "chart_materials"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    pattern: Mapped[str | None] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(50))


class NoteMacro(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "note_macros"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class CodeBundle(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "code_bundles"
    # Explosion Codes (referral/proc dev-report data note): a migrated bundle is
    # unique per (tenant, legacy_id). Without this the importer's ON CONFLICT was a
    # no-op and re-runs produced duplicate bundles. NULL legacy_id (API-created
    # bundles) is exempt — Postgres treats NULLs as distinct.
    __table_args__ = (
        UniqueConstraint("tenant_id", "legacy_id", name="uq_code_bundles_tenant_legacy"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    display_code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    same_tooth: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class CodeBundleItem(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "code_bundle_items"

    bundle_id: Mapped[int] = mapped_column(Integer, ForeignKey("code_bundles.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    procedure_code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    tooth: Mapped[str | None] = mapped_column(String(10))
    sort_order: Mapped[int] = mapped_column(Integer, default=1)


class PrescriptionLibrary(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "prescription_library"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    drug_name: Mapped[str] = mapped_column(String(255))
    dispense: Mapped[str | None] = mapped_column(String(255))
    sig: Mapped[str | None] = mapped_column(String(500))
    refills: Mapped[int] = mapped_column(Integer, default=0)
    is_as_written: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ChartColor(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "chart_colors"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    category_type: Mapped[int | None]
    name: Mapped[str] = mapped_column(String(100))
    stroke_color: Mapped[str | None] = mapped_column(String(50))
    fill_type: Mapped[str | None] = mapped_column(String(20))
    fill_color: Mapped[str | None] = mapped_column(String(50))
    fill_color2: Mapped[str | None] = mapped_column(String(50))
    fill_pattern: Mapped[str | None] = mapped_column(Text)
    gradient_angle: Mapped[str | None] = mapped_column(String(20))
    gradient_method: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(100))


class CodesView(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "codes_view"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    created_by: Mapped[str | None] = mapped_column(String(100))
