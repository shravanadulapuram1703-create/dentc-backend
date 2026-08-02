"""Clinical records domain models.

patient_procedures · chart_conditions · progress_notes · perio_exams ·
perio_exam_details · prescriptions · perio_chart_settings · perio_chart_activity
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class PatientProcedure(Base, CreatedAtMixin):
    __tablename__ = "patient_procedures"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    appointment_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("appointments.id"))
    procedure_code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    legacy_id: Mapped[str | None] = mapped_column(String(20), index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    date_of_service: Mapped[date] = mapped_column()
    provider_id: Mapped[str] = mapped_column(String(50), ForeignKey("providers.id"))
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"))
    tooth: Mapped[str | None] = mapped_column(String(10))
    surface: Mapped[str | None] = mapped_column(String(20))
    quadrant: Mapped[str | None] = mapped_column(String(10))
    # CHG-6: second (hygiene) provider recorded alongside the treating provider.
    hygienist_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    ucr_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    insurance_estimate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    patient_estimate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    apply_to: Mapped[str | None] = mapped_column(String(5))
    billing_order: Mapped[str | None] = mapped_column(String(10))
    resp_type: Mapped[str | None] = mapped_column(String(10))
    billing_status: Mapped[str] = mapped_column(String(30), default="not_billed")
    claim_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("insurance_claims.id"))
    hold_claim: Mapped[bool] = mapped_column(Boolean, default=False)
    is_void: Mapped[bool] = mapped_column(Boolean, default=False)
    material_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chart_materials.id"))
    # REST: planned→completed lineage — which treatment plan this completed procedure
    # fulfilled (mirrors appointment_procedures.treatment_plan_id).
    treatment_plan_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("treatment_plans.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ChartCondition(Base, IntPKMixin, TimestampMixin):
    """Restorative-charting condition row (one row per charted finding/restoration).

    REST-1/7/9 promote the qualifiers the frontend previously packed into
    ``region`` (``g=`` / ``grade=`` / ``sub=`` / ``rctfill=`` / ``dir=`` / ``wx=`` /
    ``wy=`` / ``root=`` / ``roots=``) to first-class, queryable columns. ``region``
    stays writable for backward-compatibility during the FE transition.
    ``TimestampMixin`` + ``updated_by`` give the "Modified By/On" audit (REST-1)."""

    __tablename__ = "chart_conditions"
    __table_args__ = (
        Index("ix_chart_conditions_group_id", "group_id"),
        Index("ix_chart_conditions_patient_is_inactive", "patient_id", "is_inactive"),
        Index("ix_chart_conditions_patient_procedure_code", "patient_id", "procedure_code"),
    )

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    activity_date: Mapped[date | None]
    tooth: Mapped[str | None] = mapped_column(String(10))
    surface: Mapped[str | None] = mapped_column(String(20))
    region: Mapped[str | None] = mapped_column(String(100))  # legacy interim encoding (kept writable)
    area: Mapped[str | None] = mapped_column(String(20))  # whole|crown|junction|root|surface
    description: Mapped[str | None] = mapped_column(String(500))
    condition_code: Mapped[str | None] = mapped_column(String(50))  # chart GLYPH key
    procedure_code: Mapped[str | None] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    material_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chart_materials.id"))
    chart_as: Mapped[str | None] = mapped_column(String(20))  # module → color
    is_inactive: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    # ── REST-1/7/9: first-class qualifiers (were packed into ``region``) ──────
    group_id: Mapped[str | None] = mapped_column(String(64))  # bridge/denture span (was g=)
    grade: Mapped[str | None] = mapped_column(String(20))  # mobility m1/m2/m3 (was grade=)
    segment: Mapped[str | None] = mapped_column(String(20))  # crown|junction|root|surface (mirrors area)
    root_segment: Mapped[str | None] = mapped_column(String(50))  # anatomical root label (was root=)
    tooth_status: Mapped[str | None] = mapped_column(String(30))  # unerupted|deciduous|supernumerary|permanent (was sub=)
    root_scope: Mapped[str | None] = mapped_column(String(10))  # all|single (was roots=)
    rct_fill: Mapped[str | None] = mapped_column(String(20))  # gutta|other|unknown (was rctfill=)
    watch_dir: Mapped[str | None] = mapped_column(String(5))  # n/ne/e/se/s/sw/w/nw (was dir=)
    watch_x: Mapped[int | None]  # 0..100 % of tooth box (was wx=)
    watch_y: Mapped[int | None]  # 0..100 % of tooth box (was wy=)
    status: Mapped[str | None] = mapped_column(String(20))  # existing|completed|planned|condition
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ProgressNote(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "progress_notes"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    note_date: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)
    notes_html: Mapped[str | None] = mapped_column(Text)
    tooth: Mapped[str | None] = mapped_column(String(255))
    # Patients gap: structured charting + sign workflow.
    surface: Mapped[str | None] = mapped_column(String(50))
    region: Mapped[str | None] = mapped_column(String(50))
    signed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_struck_off: Mapped[bool] = mapped_column(Boolean, default=False)
    # PN-4: stamped when is_struck_off goes false→true (cleared on restore) so the
    # client can gate "Restore" to the same calendar day; struck_off_by = actor.
    struck_off_at: Mapped[datetime | None] = mapped_column(DateTime)
    struck_off_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # REST-10: first-class freehand "Draw Mode" persistence (was packed into
    # notes_html as {"type":"rx-draw",…}). ``drawing_strokes`` = normalized vector
    # strokes; ``drawing_doc_id`` → the rasterized PNG snapshot in patient_documents.
    drawing_strokes: Mapped[list | None] = mapped_column(JSON)
    drawing_doc_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patient_documents.id"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PerioExam(Base, IntPKMixin, TimestampMixin):
    """A periodontal exam (one date-of-service header). Soft-delete = void
    (PERIO-BE-3): ``DELETE`` flips ``is_voided`` and the row is retained for the
    clinical/legal record; the Date-of-Service list filters voided out via the
    ``is_voided`` query param. ``TimestampMixin`` supplies ``created_at`` +
    ``updated_at`` (PERIO-BE-6); ``created_by``/``updated_by`` are stamped by the
    CRUD engine and resolved to display names on the read model."""

    __tablename__ = "perio_exams"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    exam_date: Mapped[date] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    is_voided: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PerioExamDetail(Base, IntPKMixin, TimestampMixin):
    """One row per charted tooth within an exam. ``(exam_id, tooth_no)`` is unique
    (PERIO-BE-1) so a chart can never hold two contradictory rows for the same
    tooth; the bulk-upsert endpoint relies on this. Measurements are 6-site
    (mesial→distal, buccal/lingual). ``cal1..6`` store clinical attachment level
    independently of the PD+FGM derivation (PERIO-BE-4); mobility is decimal to
    allow half-grades (PERIO-BE-2). ``TimestampMixin`` + ``created_by``/
    ``updated_by`` give per-tooth audit (PERIO-BE-5)."""

    __tablename__ = "perio_exam_details"
    __table_args__ = (
        UniqueConstraint("exam_id", "tooth_no", name="uq_perio_exam_details_exam_id_tooth_no"),
    )

    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("perio_exams.id"), index=True)
    tooth_no: Mapped[str] = mapped_column(String(10))
    pd1: Mapped[int | None]; pd2: Mapped[int | None]; pd3: Mapped[int | None]
    pd4: Mapped[int | None]; pd5: Mapped[int | None]; pd6: Mapped[int | None]
    fgm1: Mapped[int | None]; fgm2: Mapped[int | None]; fgm3: Mapped[int | None]
    fgm4: Mapped[int | None]; fgm5: Mapped[int | None]; fgm6: Mapped[int | None]
    mgj1: Mapped[int | None]; mgj2: Mapped[int | None]; mgj3: Mapped[int | None]
    mgj4: Mapped[int | None]; mgj5: Mapped[int | None]; mgj6: Mapped[int | None]
    # PERIO-BE-4: clinical attachment level, stored (not only derived as PD+FGM).
    cal1: Mapped[int | None]; cal2: Mapped[int | None]; cal3: Mapped[int | None]
    cal4: Mapped[int | None]; cal5: Mapped[int | None]; cal6: Mapped[int | None]
    bleed1: Mapped[bool | None]; bleed2: Mapped[bool | None]; bleed3: Mapped[bool | None]
    bleed4: Mapped[bool | None]; bleed5: Mapped[bool | None]; bleed6: Mapped[bool | None]
    supp1: Mapped[bool | None]; supp2: Mapped[bool | None]; supp3: Mapped[bool | None]
    supp4: Mapped[bool | None]; supp5: Mapped[bool | None]; supp6: Mapped[bool | None]
    furc1: Mapped[int | None]; furc2: Mapped[int | None]; furc3: Mapped[int | None]
    furc4: Mapped[int | None]; furc5: Mapped[int | None]; furc6: Mapped[int | None]
    # PERIO-BE-2: half-grade mobility (0.5 / 1.5 / 2.5) → NUMERIC(2,1).
    mobility_buccal: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    mobility_lingual: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class Prescription(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "prescriptions"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    library_rx_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("prescription_library.id"))
    rx_date: Mapped[date | None]
    drug_name: Mapped[str] = mapped_column(String(255))
    dispense: Mapped[str | None] = mapped_column(String(255))
    sig: Mapped[str | None] = mapped_column(String(500))
    refills: Mapped[int] = mapped_column(Integer, default=0)
    is_as_written: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    dosespot_rx_id: Mapped[str | None] = mapped_column(String(50))
    dosespot_status: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PerioChartSetting(Base, IntPKMixin, CreatedAtMixin):
    """Per-user runtime perio-charting preference (one row per user). Distinct from
    PerioChartTemplate, which is the practice-level named template library (CHART-1)."""

    __tablename__ = "perio_chart_settings"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True)
    is_forward: Mapped[bool] = mapped_column(Boolean, default=True)
    is_indicator: Mapped[bool] = mapped_column(Boolean, default=True)
    is_mgj: Mapped[bool] = mapped_column(Boolean, default=True)
    pd_level: Mapped[int] = mapped_column(Integer, default=4)
    bp_level: Mapped[int] = mapped_column(Integer, default=2)
    ip_level: Mapped[int] = mapped_column(Integer, default=3)


class PerioChartTemplate(Base, IntPKMixin, TimestampMixin):
    """CHART-1: named, tenant-scoped Perio Setup Template (the legacy "Perio Setup
    Templates" screen — add/edit/delete named templates). ``auto_advance`` is a JSON
    map of the 8 region keys (ur_facial … ll_lingual) to a direction string like
    "01-08"/"08-01"; mirrors the valid_teeth JSON precedent on procedure_codes."""

    __tablename__ = "perio_chart_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "legacy_id", name="uq_perio_chart_templates_tenant_legacy"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    show_mgj: Mapped[bool] = mapped_column(Boolean, default=False)
    pd_warning_level: Mapped[int] = mapped_column(Integer, default=4)
    cal_warning_level: Mapped[int] = mapped_column(Integer, default=4)
    bp_level: Mapped[int] = mapped_column(Integer, default=2)
    ip_level: Mapped[int] = mapped_column(Integer, default=3)
    fgm_level: Mapped[int] = mapped_column(Integer, default=2)
    start_voice: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_advance: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PerioChartActivity(Base, IntPKMixin, CreatedAtMixin):
    """PERIO-BE-13 — DEPRECATED / migration-only. This is the denormalized legacy
    Denticon perio activity log (``perio_type``/``orientation``/``arch``/
    ``quadrant``/``block_no``/``mxy``/``perio_value``; ``created_by`` is free-text).
    It has **no** relationship to ``perio_exams``/``perio_exam_details`` and is NOT
    kept in sync with them — the new charting UI reads/writes exams+details only.
    Retained read-only so historical migrated rows stay queryable; do not write to
    it from new features."""

    __tablename__ = "perio_chart_activity"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    activity_date: Mapped[date | None]
    perio_type: Mapped[str | None] = mapped_column(String(50))
    orientation: Mapped[str | None] = mapped_column(String(10))
    arch: Mapped[str | None] = mapped_column(String(10))
    quadrant: Mapped[str | None] = mapped_column(String(10))
    tooth_no: Mapped[str | None] = mapped_column(String(10))
    block_no: Mapped[str | None] = mapped_column(String(20))
    add_info: Mapped[str | None] = mapped_column(Text)
    mxy: Mapped[str | None] = mapped_column(String(50))
    perio_value: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[str | None] = mapped_column(String(100))
