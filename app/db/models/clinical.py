"""Clinical records domain models.

patient_procedures · chart_conditions · progress_notes · perio_exams ·
perio_exam_details · prescriptions · perio_chart_settings · perio_chart_activity
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin


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
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ChartCondition(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "chart_conditions"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    activity_date: Mapped[date | None]
    tooth: Mapped[str | None] = mapped_column(String(10))
    surface: Mapped[str | None] = mapped_column(String(20))
    region: Mapped[str | None] = mapped_column(String(20))
    area: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(String(500))
    condition_code: Mapped[str | None] = mapped_column(String(50))
    procedure_code: Mapped[str | None] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    material_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chart_materials.id"))
    chart_as: Mapped[str | None] = mapped_column(String(20))
    is_inactive: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class ProgressNote(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "progress_notes"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    note_date: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)
    notes_html: Mapped[str | None] = mapped_column(Text)
    tooth: Mapped[str | None] = mapped_column(String(255))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PerioExam(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "perio_exams"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    exam_date: Mapped[date] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    is_voided: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PerioExamDetail(Base, IntPKMixin):
    __tablename__ = "perio_exam_details"

    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("perio_exams.id"), index=True)
    tooth_no: Mapped[str] = mapped_column(String(10))
    pd1: Mapped[int | None]; pd2: Mapped[int | None]; pd3: Mapped[int | None]
    pd4: Mapped[int | None]; pd5: Mapped[int | None]; pd6: Mapped[int | None]
    fgm1: Mapped[int | None]; fgm2: Mapped[int | None]; fgm3: Mapped[int | None]
    fgm4: Mapped[int | None]; fgm5: Mapped[int | None]; fgm6: Mapped[int | None]
    mgj1: Mapped[int | None]; mgj2: Mapped[int | None]; mgj3: Mapped[int | None]
    mgj4: Mapped[int | None]; mgj5: Mapped[int | None]; mgj6: Mapped[int | None]
    bleed1: Mapped[bool | None]; bleed2: Mapped[bool | None]; bleed3: Mapped[bool | None]
    bleed4: Mapped[bool | None]; bleed5: Mapped[bool | None]; bleed6: Mapped[bool | None]
    supp1: Mapped[bool | None]; supp2: Mapped[bool | None]; supp3: Mapped[bool | None]
    supp4: Mapped[bool | None]; supp5: Mapped[bool | None]; supp6: Mapped[bool | None]
    furc1: Mapped[int | None]; furc2: Mapped[int | None]; furc3: Mapped[int | None]
    furc4: Mapped[int | None]; furc5: Mapped[int | None]; furc6: Mapped[int | None]
    mobility_buccal: Mapped[int | None]
    mobility_lingual: Mapped[int | None]


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
    __tablename__ = "perio_chart_settings"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True)
    is_forward: Mapped[bool] = mapped_column(Boolean, default=True)
    is_indicator: Mapped[bool] = mapped_column(Boolean, default=True)
    is_mgj: Mapped[bool] = mapped_column(Boolean, default=True)
    pd_level: Mapped[int] = mapped_column(Integer, default=4)
    bp_level: Mapped[int] = mapped_column(Integer, default=2)
    ip_level: Mapped[int] = mapped_column(Integer, default=3)


class PerioChartActivity(Base, IntPKMixin, CreatedAtMixin):
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
