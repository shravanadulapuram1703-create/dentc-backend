"""Declarative registry of every CRUD entity exposed in API v1.

Each ``CrudConfig`` is one table's full CRUD surface. Schemas are generated from
the model by :func:`app.schemas.factory.build_schemas`; the router factory turns
the config into 5 routes. Adding an entity = adding one ``_cfg(...)`` row.

Tenancy: models carrying ``tenant_id`` are auto-scoped. Child tables that don't
(e.g. ``patient_alerts``) expose their parent FK as a ``filter`` so the frontend
always narrows by patient/office within the authenticated tenant.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.crud.router_factory import CrudConfig, register_crud
from app.db import models as m
from app.schemas.factory import build_schemas

_DEFAULT_SORT = ("created_at", "id")


def _cfg(
    model: type,
    name: str,
    prefix: str,
    tag: str,
    singular: str,
    plural: str,
    *,
    pk_type: type = int,
    pk_name: str = "id",
    search: tuple[str, ...] = (),
    sortable: tuple[str, ...] = _DEFAULT_SORT,
    filters: tuple[str, ...] = (),
    ranges: tuple[str, ...] = (),
    soft_field: str | None = "is_active",
    soft_value: bool = False,
    default_sort: str = "created_at",
    read_exclude: tuple[str, ...] = (),
) -> CrudConfig:
    create_s, update_s, read_s = build_schemas(model, name, read_exclude=read_exclude)
    return CrudConfig(
        model=model,
        create_schema=create_s,
        update_schema=update_s,
        read_schema=read_s,
        prefix=prefix,
        tag=tag,
        singular=singular,
        plural=plural,
        pk_type=pk_type,
        pk_name=pk_name,
        search_fields=search,
        sortable_fields=sortable,
        filter_fields=filters,
        range_fields=ranges,
        soft_delete_field=soft_field,
        soft_delete_value=soft_value,
        default_sort=default_sort,
    )


# ── Organisation ───────────────────────────────────────────────────────────
_ORG = [
    _cfg(m.Tenant, "Tenant", "tenants", "Organization", "tenant", "tenants",
         search=("name", "code"), filters=("is_active",)),
    _cfg(m.Office, "Office", "offices", "Organization", "office", "offices",
         search=("name", "office_code", "city"), filters=("is_active",)),
    _cfg(m.Provider, "Provider", "providers", "Organization", "provider", "providers",
         pk_type=str, search=("name", "specialty", "npi"), filters=("office_id", "is_active")),
    _cfg(m.Operatory, "Operatory", "operatories", "Organization", "operatory", "operatories",
         pk_type=str, search=("name",), filters=("office_id", "is_active")),
    _cfg(m.UserOffice, "UserOffice", "user-offices", "Organization", "user_office", "user_offices",
         filters=("user_id", "office_id"), soft_field=None),
    _cfg(m.OfficeGroup, "OfficeGroup", "office-groups", "Organization", "office_group", "office_groups",
         search=("name",), soft_field=None),
]

# ── Patients ───────────────────────────────────────────────────────────────
_PATIENTS = [
    _cfg(m.Patient, "Patient", "patients", "Patients", "patient", "patients",
         search=("first_name", "last_name", "chart_no", "email", "phone"),
         sortable=("created_at", "id", "last_name", "first_name"),
         filters=("home_office_id", "is_active", "preferred_provider_id", "chart_no")),
    _cfg(m.PatientInsurance, "PatientInsurance", "patient-insurance", "Patients",
         "patient_insurance", "patient_insurance",
         filters=("patient_id", "insurance_type", "ins_plan_id")),
    _cfg(m.PatientAlert, "PatientAlert", "patient-alerts", "Patients",
         "patient_alert", "patient_alerts", filters=("patient_id", "is_active")),
    _cfg(m.AccountNote, "AccountNote", "account-notes", "Patients",
         "account_note", "account_notes", filters=("patient_id",), soft_field=None),
    _cfg(m.PatientSignature, "PatientSignature", "patient-signatures", "Patients",
         "patient_signature", "patient_signatures", filters=("patient_id",), soft_field=None),
    _cfg(m.MedicalHistoryRecord, "MedicalHistoryRecord", "medical-history-records", "Patients",
         "medical_history_record", "medical_history_records",
         filters=("patient_id",), soft_field="is_archived", soft_value=True),
    _cfg(m.Referral, "Referral", "referrals", "Patients", "referral", "referrals",
         search=("first_name", "last_name", "specialty"), filters=("patient_id", "office_id"),
         soft_field=None),
    _cfg(m.PatientNote, "PatientNote", "patient-notes", "Patients",
         "patient_note", "patient_notes", filters=("patient_id",),
         soft_field="is_deleted", soft_value=True),
    _cfg(m.PatientRecall, "PatientRecall", "patient-recalls", "Patients",
         "patient_recall", "patient_recalls", filters=("patient_id", "status", "is_active")),
]

# ── Insurance ──────────────────────────────────────────────────────────────
_INSURANCE = [
    _cfg(m.Employer, "Employer", "employers", "Insurance", "employer", "employers",
         search=("name", "city"), soft_field=None),
    _cfg(m.InsuranceCarrier, "InsuranceCarrier", "insurance-carriers", "Insurance",
         "insurance_carrier", "insurance_carriers", search=("name", "payer_id"),
         filters=("is_active",)),
    _cfg(m.InsurancePlan, "InsurancePlan", "insurance-plans", "Insurance",
         "insurance_plan", "insurance_plans", search=("group_number", "plan_type"),
         filters=("carrier_id", "employer_id", "is_active")),
    _cfg(m.InsuranceSubscriber, "InsuranceSubscriber", "insurance-subscribers", "Insurance",
         "insurance_subscriber", "insurance_subscribers",
         search=("sub_first_name", "sub_last_name", "sub_member_id"),
         filters=("ins_plan_id", "subscriber_patient_id", "is_active")),
    _cfg(m.InsuranceCoverageRule, "InsuranceCoverageRule", "insurance-coverage-rules", "Insurance",
         "insurance_coverage_rule", "insurance_coverage_rules",
         filters=("ins_plan_id",), soft_field=None),
]

# ── Procedures, fees & codes ───────────────────────────────────────────────
_CODES = [
    _cfg(m.ProcedureCode, "ProcedureCode", "procedure-codes", "Procedures",
         "procedure_code", "procedure_codes", pk_type=str, pk_name="code",
         search=("code", "description", "category"), sortable=("code", "category"),
         filters=("category", "is_active", "is_ortho")),
    _cfg(m.FeeSchedule, "FeeSchedule", "fee-schedules", "Procedures",
         "fee_schedule", "fee_schedules", search=("name",),
         filters=("ins_plan_id", "office_id", "is_active")),
    _cfg(m.FeeScheduleEntry, "FeeScheduleEntry", "fee-schedule-entries", "Procedures",
         "fee_schedule_entry", "fee_schedule_entries",
         filters=("fee_schedule_id", "procedure_code"), soft_field=None),
    _cfg(m.CodeBundle, "CodeBundle", "code-bundles", "Procedures",
         "code_bundle", "code_bundles", search=("name", "display_code"), soft_field=None),
    _cfg(m.CodeBundleItem, "CodeBundleItem", "code-bundle-items", "Procedures",
         "code_bundle_item", "code_bundle_items", filters=("bundle_id",), soft_field=None),
    _cfg(m.ChartMaterial, "ChartMaterial", "chart-materials", "Procedures",
         "chart_material", "chart_materials", search=("name",), soft_field=None),
    _cfg(m.NoteMacro, "NoteMacro", "note-macros", "Procedures",
         "note_macro", "note_macros", search=("name", "category"), soft_field=None),
    _cfg(m.PrescriptionLibrary, "PrescriptionLibrary", "prescription-library", "Procedures",
         "prescription_library_item", "prescription_library", search=("drug_name",),
         filters=("is_active",)),
]

# ── Scheduling ─────────────────────────────────────────────────────────────
_SCHEDULING = [
    _cfg(m.Appointment, "Appointment", "appointments", "Appointments",
         "appointment", "appointments", pk_type=str,
         search=("procedure_label", "notes"), sortable=("date", "start_time", "created_at"),
         filters=("patient_id", "provider_id", "operatory_id", "office_id", "date", "status"),
         ranges=("date",), soft_field="is_archived", soft_value=True),
    _cfg(m.AppointmentProcedure, "AppointmentProcedure", "appointment-procedures", "Appointments",
         "appointment_procedure", "appointment_procedures",
         filters=("appointment_id", "procedure_code", "provider_id"),
         soft_field="is_archived", soft_value=True),
]

# ── Treatment plans ────────────────────────────────────────────────────────
_TREATMENT = [
    _cfg(m.TreatmentPlan, "TreatmentPlan", "treatment-plans", "Treatment Plans",
         "treatment_plan", "treatment_plans", pk_type=str, search=("name",),
         filters=("patient_id", "office_id", "status"), soft_field=None),
    _cfg(m.TreatmentPlanItem, "TreatmentPlanItem", "treatment-plan-items", "Treatment Plans",
         "treatment_plan_item", "treatment_plan_items", pk_type=str,
         filters=("plan_id", "procedure_code", "status"), soft_field=None),
]

# ── Clinical records ───────────────────────────────────────────────────────
_CLINICAL = [
    _cfg(m.PatientProcedure, "PatientProcedure", "patient-procedures", "Clinical",
         "patient_procedure", "patient_procedures", pk_type=str,
         sortable=("date_of_service", "created_at"),
         filters=("patient_id", "appointment_id", "provider_id", "procedure_code",
                  "claim_id", "billing_status", "is_void"),
         ranges=("date_of_service",), soft_field="is_void", soft_value=True),
    _cfg(m.ChartCondition, "ChartCondition", "chart-conditions", "Clinical",
         "chart_condition", "chart_conditions",
         filters=("patient_id", "tooth", "provider_id"),
         soft_field="is_inactive", soft_value=True),
    _cfg(m.ProgressNote, "ProgressNote", "progress-notes", "Clinical",
         "progress_note", "progress_notes", search=("notes",),
         filters=("patient_id",), soft_field="is_deleted", soft_value=True),
    _cfg(m.PerioExam, "PerioExam", "perio-exams", "Clinical",
         "perio_exam", "perio_exams", sortable=("exam_date", "created_at"),
         filters=("patient_id",), soft_field="is_voided", soft_value=True),
    _cfg(m.PerioExamDetail, "PerioExamDetail", "perio-exam-details", "Clinical",
         "perio_exam_detail", "perio_exam_details", sortable=("id",),
         default_sort="id", filters=("exam_id", "tooth_no"), soft_field=None),
    _cfg(m.Prescription, "Prescription", "prescriptions", "Clinical",
         "prescription", "prescriptions", search=("drug_name",),
         filters=("patient_id", "provider_id", "is_active")),
    _cfg(m.PerioChartSetting, "PerioChartSetting", "perio-chart-settings", "Clinical",
         "perio_chart_setting", "perio_chart_settings", filters=("user_id",), soft_field=None),
    _cfg(m.PerioChartActivity, "PerioChartActivity", "perio-chart-activity", "Clinical",
         "perio_chart_activity", "perio_chart_activity", filters=("patient_id",), soft_field=None),
]

# ── Billing & claims ───────────────────────────────────────────────────────
_BILLING = [
    _cfg(m.PatientPayment, "PatientPayment", "patient-payments", "Billing",
         "patient_payment", "patient_payments", pk_type=str,
         sortable=("payment_date", "created_at"),
         filters=("patient_id", "payment_type", "provider_id", "is_void"),
         ranges=("payment_date",), soft_field="is_void", soft_value=True),
    _cfg(m.InsuranceClaim, "InsuranceClaim", "insurance-claims", "Billing",
         "insurance_claim", "insurance_claims", pk_type=str, search=("claim_number",),
         filters=("patient_id", "status", "claim_type", "carrier_id", "ins_plan_id", "is_active")),
    _cfg(m.ClaimSubmission, "ClaimSubmission", "claim-submissions", "Billing",
         "claim_submission", "claim_submissions", filters=("claim_id", "batch_id"), soft_field=None),
    _cfg(m.LedgerInsuranceDetail, "LedgerInsuranceDetail", "ledger-insurance-details", "Billing",
         "ledger_insurance_detail", "ledger_insurance_details",
         filters=("patient_id", "claim_id", "procedure_id"), soft_field=None),
    _cfg(m.PaymentAllocation, "PaymentAllocation", "payment-allocations", "Billing",
         "payment_allocation", "payment_allocations",
         filters=("patient_id", "payment_id", "procedure_id", "claim_id"), soft_field=None),
    _cfg(m.PatientPaymentPlan, "PatientPaymentPlan", "patient-payment-plans", "Billing",
         "patient_payment_plan", "patient_payment_plans", filters=("patient_id", "is_active")),
    _cfg(m.PatientInsPaymentPlan, "PatientInsPaymentPlan", "patient-ins-payment-plans", "Billing",
         "patient_ins_payment_plan", "patient_ins_payment_plans",
         filters=("patient_id", "is_billed"), soft_field=None),
    _cfg(m.PatientSecInsPaymentPlan, "PatientSecInsPaymentPlan", "patient-sec-ins-payment-plans",
         "Billing", "patient_sec_ins_payment_plan", "patient_sec_ins_payment_plans",
         filters=("patient_id", "is_billed"), soft_field=None),
    _cfg(m.PatientRegPlan, "PatientRegPlan", "patient-reg-plans", "Billing",
         "patient_reg_plan", "patient_reg_plans", filters=("patient_id", "is_active")),
    _cfg(m.OrthoPlan, "OrthoPlan", "ortho-plans", "Billing",
         "ortho_plan", "ortho_plans", filters=("patient_id", "is_active")),
]

# ── Config & reference ─────────────────────────────────────────────────────
_REFERENCE = [
    _cfg(m.Definition, "Definition", "definitions", "Metadata",
         "definition", "definitions", search=("description", "key1"),
         filters=("group_code", "is_active")),
    _cfg(m.DefinitionGroup, "DefinitionGroup", "definition-groups", "Metadata",
         "definition_group", "definition_groups", search=("description", "group_code"),
         soft_field=None),
    _cfg(m.ImagingTemplate, "ImagingTemplate", "imaging-templates", "Metadata",
         "imaging_template", "imaging_templates", search=("name",),
         filters=("office_id",), soft_field=None),
    _cfg(m.QuestionnaireHeader, "QuestionnaireHeader", "questionnaire-headers", "Metadata",
         "questionnaire_header", "questionnaire_headers", search=("description",),
         filters=("is_active",)),
    _cfg(m.QuestionnaireOption, "QuestionnaireOption", "questionnaire-options", "Metadata",
         "questionnaire_option", "questionnaire_options",
         filters=("questionnaire_id", "is_active")),
    _cfg(m.ChartColor, "ChartColor", "chart-colors", "Metadata",
         "chart_color", "chart_colors", search=("name",), soft_field=None),
    _cfg(m.CodesView, "CodesView", "codes-view", "Metadata",
         "codes_view_entry", "codes_view", filters=("office_id", "code"), soft_field=None),
    _cfg(m.InsCustomCoverage, "InsCustomCoverage", "ins-custom-coverage", "Insurance",
         "ins_custom_coverage", "ins_custom_coverage", soft_field=None),
    _cfg(m.FeeScheduleAssignment, "FeeScheduleAssignment", "fee-schedule-assignments", "Procedures",
         "fee_schedule_assignment", "fee_schedule_assignments",
         filters=("fee_schedule_id", "ins_plan_id", "provider_id", "office_id"), soft_field=None),
    _cfg(m.MedicalHistoryDetail, "MedicalHistoryDetail", "medical-history-details", "Patients",
         "medical_history_detail", "medical_history_details",
         filters=("history_id",), soft_field=None),
    _cfg(m.CariesRiskAssessment, "CariesRiskAssessment", "caries-risk-assessments", "Clinical",
         "caries_risk_assessment", "caries_risk_assessments",
         filters=("patient_id", "risk_level"), soft_field=None),
    _cfg(m.TreatmentPlanInsuranceDetail, "TreatmentPlanInsuranceDetail",
         "treatment-plan-insurance-details", "Treatment Plans",
         "treatment_plan_insurance_detail", "treatment_plan_insurance_details",
         filters=("plan_item_id", "ins_plan_id"), soft_field="is_archived", soft_value=True),
]

# ── Communications ─────────────────────────────────────────────────────────
_COMMS = [
    _cfg(m.SmsMessage, "SmsMessage", "sms-messages", "Communications",
         "sms_message", "sms_messages", search=("sent_text", "sent_phone"),
         filters=("patient_id", "appointment_id", "message_type", "is_read"), soft_field=None),
    _cfg(m.LetterTemplate, "LetterTemplate", "letter-templates", "Communications",
         "letter_template", "letter_templates", search=("name", "title"),
         filters=("letter_type", "is_active")),
    _cfg(m.PostcardTemplate, "PostcardTemplate", "postcard-templates", "Communications",
         "postcard_template", "postcard_templates", search=("name",), soft_field=None),
]

# ── Staff & operations ─────────────────────────────────────────────────────
_STAFF = [
    _cfg(m.TimeClockEntry, "TimeClockEntry", "time-clock-entries", "Staff",
         "time_clock_entry", "time_clock_entries", sortable=("clock_in", "created_at"),
         filters=("user_id", "office_id"), soft_field=None),
    _cfg(m.ProviderInsuranceId, "ProviderInsuranceId", "provider-insurance-ids", "Staff",
         "provider_insurance_id", "provider_insurance_ids",
         filters=("provider_id", "carrier_id", "in_network"), soft_field=None),
    _cfg(m.ProviderRouteSlip, "ProviderRouteSlip", "provider-route-slips", "Staff",
         "provider_route_slip", "provider_route_slips", filters=("provider_id",), soft_field=None),
]

# ── Imaging, collections, referral demographics ────────────────────────────
_MISC = [
    _cfg(m.ImageGroup, "ImageGroup", "image-groups", "Imaging",
         "image_group", "image_groups", search=("name",),
         filters=("patient_id", "office_id"), soft_field="is_deleted", soft_value=True),
    _cfg(m.ImageDetail, "ImageDetail", "image-details", "Imaging",
         "image_detail", "image_details", filters=("image_group_id",),
         soft_field="is_deleted", soft_value=True),
    _cfg(m.CollectionAgency, "CollectionAgency", "collection-agencies", "Imaging",
         "collection_agency", "collection_agencies", search=("name",), soft_field=None),
    _cfg(m.ReferralDemogHeader, "ReferralDemogHeader", "referral-demog-headers", "Imaging",
         "referral_demog_header", "referral_demog_headers", search=("description",), soft_field=None),
    _cfg(m.ReferralDemogDetail, "ReferralDemogDetail", "referral-demog-details", "Imaging",
         "referral_demog_detail", "referral_demog_details",
         filters=("referral_id", "demog_header_id"), soft_field=None),
]

# ── User access sub-resources (Phase 4, net-new) ───────────────────────────
_ACCESS = [
    _cfg(m.UserPreference, "UserPreference", "user-preferences", "Staff",
         "user_preference", "user_preferences", filters=("user_id", "pref_key"), soft_field=None),
    _cfg(m.UserGroup, "UserGroup", "user-groups", "Staff",
         "user_group", "user_groups", search=("name",), filters=("is_active",)),
    _cfg(m.UserGroupMembership, "UserGroupMembership", "user-group-memberships", "Staff",
         "user_group_membership", "user_group_memberships",
         filters=("user_id", "group_id"), soft_field=None),
    _cfg(m.UserIpRule, "UserIpRule", "user-ip-rules", "Staff",
         "user_ip_rule", "user_ip_rules", filters=("user_id", "rule_type", "is_active")),
]

ALL_CONFIGS: list[CrudConfig] = [
    *_ORG, *_PATIENTS, *_INSURANCE, *_CODES, *_SCHEDULING, *_TREATMENT,
    *_CLINICAL, *_BILLING, *_REFERENCE, *_COMMS, *_STAFF, *_MISC, *_ACCESS,
]


def build_entity_router() -> APIRouter:
    router = APIRouter()
    for cfg in ALL_CONFIGS:
        router.include_router(register_crud(cfg))
    return router
