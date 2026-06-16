"""Patient domain models.

patients · patient_insurance · patient_alerts · account_notes ·
patient_signatures · medical_history_records · referrals · patient_notes ·
patient_recalls · caries_risk_assessments
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class Patient(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "patients"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    home_office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    chart_no: Mapped[str | None] = mapped_column(String(50), unique=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    preferred_name: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(20))
    middle_initial: Mapped[str | None] = mapped_column(String(10))
    dob: Mapped[date | None]
    gender: Mapped[str | None] = mapped_column(String(20))
    ssn: Mapped[str | None] = mapped_column(String(20))
    medicaid_id: Mapped[str | None] = mapped_column(String(50))  # Patients gap: field-specific search
    marital_status: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    cell_phone: Mapped[str | None] = mapped_column(String(20))
    work_phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    preferred_contact: Mapped[str | None] = mapped_column(String(50))
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    preferred_provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    preferred_language: Mapped[str] = mapped_column(String(50), default="English")
    first_visit: Mapped[date | None]
    last_visit: Mapped[date | None]
    next_recall: Mapped[date | None]
    is_finance_charge: Mapped[bool] = mapped_column(Boolean, default=False)
    send_statements: Mapped[bool] = mapped_column(Boolean, default=True)
    send_collections: Mapped[bool] = mapped_column(Boolean, default=False)
    no_auto_email: Mapped[bool] = mapped_column(Boolean, default=False)
    no_auto_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    hipaa_agreement: Mapped[bool] = mapped_column(Boolean, default=False)
    guardian_name: Mapped[str | None] = mapped_column(String(255))
    guardian_phone: Mapped[str | None] = mapped_column(String(20))
    referral_type: Mapped[str | None] = mapped_column(String(50))
    referred_by: Mapped[str | None] = mapped_column(String(255))
    patient_notes: Mapped[str | None] = mapped_column(Text)
    # Scheduler gap #8: responsible-party link + patient type (general/ortho).
    responsible_party_id: Mapped[str | None] = mapped_column(String(50))
    patient_type: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientInsurance(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "patient_insurance"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    subscriber_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_subscribers.id"))
    legacy_plan_type: Mapped[str | None] = mapped_column(String(5))
    insurance_type: Mapped[str] = mapped_column(String(20))
    relationship: Mapped[str | None] = mapped_column(String(50))
    deductible_remaining: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    max_remaining: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ortho_remaining: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PatientAlert(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "patient_alerts"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    alert: Mapped[str] = mapped_column(Text)
    blocks_charges: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deactivated_on: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class AccountNote(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "account_notes"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    note_type: Mapped[str | None] = mapped_column(String(10))
    notes: Mapped[str] = mapped_column(Text)
    is_struck_off: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientSignature(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "patient_signatures"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    signature_data: Mapped[str | None] = mapped_column(Text)
    signature_len: Mapped[int | None]
    device_source: Mapped[str | None] = mapped_column(String(20))
    is_user_sig: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class MedicalHistoryRecord(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "medical_history_records"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    signature_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patient_signatures.id"))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class Referral(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "referrals"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    referral_type: Mapped[str | None] = mapped_column(String(10))
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    npi: Mapped[str | None] = mapped_column(String(50))
    specialty: Mapped[str | None] = mapped_column(String(100))
    reason_code: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    # Referral Info grid (referral dev-report gaps 1–4): legacy columns with no home.
    e_referral_id: Mapped[str | None] = mapped_column(String(50))
    practice_name: Mapped[str | None] = mapped_column(String(255))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientNote(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "patient_notes"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    note_date: Mapped[date | None]
    note_type: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str] = mapped_column(Text)
    notes_html: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientRecall(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "patient_recalls"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    recall_type: Mapped[str | None] = mapped_column(String(50))
    procedure_code: Mapped[str | None] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    due_date: Mapped[date | None]
    interval_months: Mapped[int | None]
    last_completed: Mapped[date | None]
    status: Mapped[str] = mapped_column(String(20), default="due")
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class MedicalHistoryDetail(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "medical_history_details"

    history_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_history_records.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    question_code: Mapped[str] = mapped_column(String(50))
    question_text: Mapped[str | None] = mapped_column(Text)
    answer_code: Mapped[str | None] = mapped_column(String(20))
    answer_text: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class CariesRiskAssessment(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "caries_risk_assessments"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    risk_date: Mapped[date | None]
    vis_cavities: Mapped[bool | None]
    les_not_dentin: Mapped[bool | None]
    surf_white_spots: Mapped[bool | None]
    rest_in_3yrs: Mapped[bool | None]
    cav_rad_dentin: Mapped[bool | None]
    prox_enamel_les: Mapped[bool | None]
    act_white_spot_surf: Mapped[bool | None]
    fir_vis_rest_lst_3yrs: Mapped[bool | None]
    foll_up_vis_rest_yr: Mapped[bool | None]
    vis_plaque: Mapped[bool | None]
    freq_snack: Mapped[bool | None]
    pits_and_fissures: Mapped[bool | None]
    acidic_ph: Mapped[bool | None]
    atp: Mapped[bool | None]
    xerostomia: Mapped[bool | None]
    cari_read_above_1500: Mapped[bool | None]
    vis_heavy_plaque: Mapped[bool | None]
    freq_snack_gt3x: Mapped[bool | None]
    deep_pits_fissures: Mapped[bool | None]
    recreat_drug: Mapped[bool | None]
    saliva_flow_reduced: Mapped[bool | None]
    ortho_appliance: Mapped[bool | None]
    fluoride_toothpaste: Mapped[bool | None]
    fluoride_rinse: Mapped[bool | None]
    hx_peridex: Mapped[bool | None]
    office_flour_6mon: Mapped[bool | None]
    live_work_fw_water: Mapped[bool | None]
    f_toothpaste_1x: Mapped[bool | None]
    f_toothpaste_2x: Mapped[bool | None]
    f_mouth_rinse: Mapped[bool | None]
    f_toothpaste_5000ppm: Mapped[bool | None]
    f_varnish_6mon: Mapped[bool | None]
    office_f_topical_6mon: Mapped[bool | None]
    chx_1wk_per_mon: Mapped[bool | None]
    xylitol_6mon: Mapped[bool | None]
    adeaq_saliva_flow: Mapped[bool | None]
    risk_level: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(100))
