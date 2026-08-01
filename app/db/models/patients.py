"""Patient domain models.

patients · patient_insurance · patient_alerts · account_notes ·
patient_signatures · medical_history_records · referrals · patient_notes ·
patient_recalls · caries_risk_assessments
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
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
    # Add-Patient gap GAP-AP-6: "Referred To" party + "Referral To Date" (distinct
    # from the referred_by/referral_type inbound-referral pair above).
    referred_to: Mapped[str | None] = mapped_column(String(255))
    referral_to_date: Mapped[date | None]
    patient_notes: Mapped[str | None] = mapped_column(Text)
    # GAP-AP-11: HIPAA Information-Sharing free text (separate from patient_notes).
    hipaa_sharing_notes: Mapped[str | None] = mapped_column(Text)
    # Scheduler gap #8: responsible-party link + patient type (general/ortho).
    responsible_party_id: Mapped[str | None] = mapped_column(String(50))
    # GAP-AP-7/15: the patient's relationship to their responsible party
    # (self/spouse/parent/guardian/child/other), set at registration.
    responsible_party_relationship: Mapped[str | None] = mapped_column(String(50))
    patient_type: Mapped[str | None] = mapped_column(String(50))
    # GAP-AP-9: the legacy multi-tag model (CH/CP/EF/OR/SN/SR/SS/UP) — a set of
    # patient_type codes. ``patient_type`` above stays the single primary tag.
    patient_types: Mapped[list | None] = mapped_column(JSON)
    # GAP-AP-1..5: Add-Patient demographic/office fields with no prior column.
    pronouns: Mapped[str | None] = mapped_column(String(20))
    driver_license: Mapped[str | None] = mapped_column(String(50))
    student_status: Mapped[str | None] = mapped_column(String(20))  # none|part_time|full_time
    school_name: Mapped[str | None] = mapped_column(String(255))
    preferred_hygienist_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    fee_schedule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("fee_schedules.id"))
    # GAP-AP-10: Patient-Status flags with no prior column.
    assign_benefits: Mapped[bool] = mapped_column(Boolean, default=False)
    add_to_quickfill: Mapped[bool] = mapped_column(Boolean, default=False)
    no_correspondence: Mapped[bool] = mapped_column(Boolean, default=False)
    # PO-10: the patient-document that is this patient's profile photo (Overview Photo box).
    photo_document_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patient_documents.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # PE-4: last-editor attribution ("Modified By"); CRUDBase.update stamps it on PATCH.
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientInsurance(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "patient_insurance"
    # BUG-3: a slot is (plan_type × ordinal) — Dental primary and Medical primary
    # must coexist. The legacy migrated DB carried a unique on (patient_id,
    # insurance_type) only, which blocked that; the slot key includes legacy_plan_type.
    __table_args__ = (
        UniqueConstraint(
            "patient_id", "legacy_plan_type", "insurance_type",
            name="uq_patient_insurance_patient_slot",
        ),
    )

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    subscriber_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_subscribers.id"))
    legacy_plan_type: Mapped[str | None] = mapped_column(String(5))
    insurance_type: Mapped[str] = mapped_column(String(20))
    relationship: Mapped[str | None] = mapped_column(String(50))
    # INS-PT-3: on secondary/tertiary/quaternary slots — this subscriber's
    # relationship to the PRIMARY subscriber.
    sec_sub_rel_to_prim_sub: Mapped[str | None] = mapped_column(String(50))
    deductible_remaining: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    max_remaining: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ortho_remaining: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # LEG-6: legacy "Dentical Share of Cost" block on the dental plan.
    dentical_share_month: Mapped[int | None] = mapped_column(Integer)
    dentical_share_year: Mapped[int | None] = mapped_column(Integer)
    dentical_share_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    dentical_unused: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
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
    # LEG-8: legacy "Int. Type" (Month/Year) so the entered value round-trips
    # without the frontend converting Year→months; plus the scheduled-appt slot.
    interval_unit: Mapped[str | None] = mapped_column(String(10))  # month|year
    scheduled_date: Mapped[date | None]
    scheduled_time: Mapped[str | None] = mapped_column(String(10))  # HH:MM (24h)
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


class PatientMedicalAlert(Base, IntPKMixin, TimestampMixin):
    """GAP-AP-16: a patient's Yes/No response to a single medical-alert item
    (from the MEDALERT definition catalog), captured at registration or later.
    Distinct from ``patient_alerts`` (free-text banner alerts)."""

    __tablename__ = "patient_medical_alerts"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    alert_code: Mapped[str] = mapped_column(String(50))  # code from definitions 'MEDALERT'
    alert_label: Mapped[str | None] = mapped_column(String(255))
    response: Mapped[str | None] = mapped_column(String(10))  # yes|no
    comments: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientQuestionnaireResponse(Base, IntPKMixin, TimestampMixin):
    """GAP-AP-17: a patient's answer to a single Dental/Medical questionnaire
    question (from the DENTQUEST/MEDQUEST definition catalogs)."""

    __tablename__ = "patient_questionnaire_responses"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    questionnaire_type: Mapped[str] = mapped_column(String(20))  # dental|medical
    question_code: Mapped[str] = mapped_column(String(50))
    question_text: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class PatientOpeningBalance(Base, IntPKMixin, TimestampMixin):
    """GAP-AP-12: opening A/R (aging buckets) seeded when a migrated/transferred
    patient is registered. One row per patient (upserted). Surfaces in the computed
    /patients/{id}/balance so a new patient no longer always shows $0.00."""

    __tablename__ = "patient_opening_balances"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patients.id"), unique=True, index=True
    )
    as_of_date: Mapped[date | None]
    current: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    over_30: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    over_60: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    over_90: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    over_120: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ResponsibleParty(Base, IntPKMixin, TimestampMixin):
    """LEG-10/11/12/13: a guarantor / billing entity that may be a *non-patient*.

    Registering a dependent whose parent is not yet in the system (the legacy
    "Add a Dependent" flow) needs a standalone responsible party. A patient links
    to one via ``patients.responsible_party_id`` (string; holds this row's id, or
    the patient's own id for a self-guarantor). Billing behaviour (statements,
    collections, finance charge) is modelled here — per-account, as in legacy —
    mirroring the per-patient flags that still live on ``patients``.
    """

    __tablename__ = "responsible_parties"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    # PO-2: the legacy guarantor id migrated patients point at via
    # patients.responsible_party_id — indexed + filterable so the record is
    # resolvable once legacy guarantors are migrated in.
    legacy_id: Mapped[str | None] = mapped_column(String(20), index=True)
    # PO-11: legacy shows Home Office on the Responsible Party panel.
    home_office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    # Demographics (LEG-10).
    title: Mapped[str | None] = mapped_column(String(20))
    preferred_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    first_name: Mapped[str | None] = mapped_column(String(100))
    middle_initial: Mapped[str | None] = mapped_column(String(10))
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    dob: Mapped[date | None]
    marital_status: Mapped[str | None] = mapped_column(String(20))
    sex: Mapped[str | None] = mapped_column(String(20))
    ssn: Mapped[str | None] = mapped_column(String(20))
    driver_license: Mapped[str | None] = mapped_column(String(50))
    home_phone: Mapped[str | None] = mapped_column(String(20))
    cell_phone: Mapped[str | None] = mapped_column(String(20))
    work_phone: Mapped[str | None] = mapped_column(String(20))
    employer: Mapped[str | None] = mapped_column(String(255))
    # LEG-13: Resp. Party Type (code from the RESP_PARTY_TYPE definitions group).
    resp_party_type: Mapped[str | None] = mapped_column(String(20))
    # LEG-11: per-account billing behaviour + collection agency lookup.
    collection_agency_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("collection_agencies.id")
    )
    send_statements: Mapped[bool] = mapped_column(Boolean, default=True)
    no_email_statement: Mapped[bool] = mapped_column(Boolean, default=False)
    send_collections: Mapped[bool] = mapped_column(Boolean, default=False)
    is_finance_charge: Mapped[bool] = mapped_column(Boolean, default=False)
    # LEG-12: statement message + financial / RP notes.
    statement_message: Mapped[str | None] = mapped_column(Text)
    statement_message_print_count: Mapped[int | None] = mapped_column(Integer)
    financial_notes: Mapped[str | None] = mapped_column(Text)
    responsible_party_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
