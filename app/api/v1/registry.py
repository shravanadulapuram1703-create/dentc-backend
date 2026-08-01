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
from app.services.enrich_service import (
    enrich_ortho_plan,
    enrich_patient_carrier,
    enrich_patient_office,
    enrich_patient_provider,
    enrich_payment_plan,
    enrich_treatment_plan,
)
from app.services.payment_plan_service import PaymentPlanCRUD
from app.services.patient_service import PatientCRUD
from app.services.perio_service import attach_actor_names
from app.services.progress_notes_service import ProgressNoteCRUD, enrich_progress_notes
from app.services.treatment_service import TreatmentPlanItemCRUD
from app.schemas.fee_schedule import (
    FeeScheduleCreate,
    FeeScheduleRead,
    FeeScheduleUpdate,
)
from app.schemas.insurance import (
    InsuranceCarrierCreate,
    InsuranceCarrierRead,
    InsuranceCarrierUpdate,
)
from app.schemas.perio import (
    PerioChartSettingCreate,
    PerioChartSettingRead,
    PerioChartSettingUpdate,
    PerioChartTemplateCreate,
    PerioChartTemplateRead,
    PerioChartTemplateUpdate,
    PerioExamCreate,
    PerioExamDetailCreate,
    PerioExamDetailRead,
    PerioExamDetailUpdate,
    PerioExamRead,
    PerioExamUpdate,
)
from app.schemas.enriched import (
    InsuranceClaimCreate,
    InsuranceClaimRead,
    InsuranceClaimUpdate,
    PatientPaymentCreate,
    PatientPaymentRead,
    PatientPaymentUpdate,
    PatientProcedureCreate,
    PatientProcedureRead,
    PatientProcedureUpdate,
    TreatmentPlanCreate,
    TreatmentPlanRead,
    TreatmentPlanUpdate,
)
from app.schemas.patient import PatientCreate, PatientRead, PatientUpdate
from app.schemas.payment_plan import (
    OrthoPlanCreate,
    OrthoPlanRead,
    OrthoPlanUpdate,
    PatientPaymentPlanCreate,
    PatientPaymentPlanRead,
    PatientPaymentPlanUpdate,
)
from app.schemas.patient_catalog import (
    PatientMedicalAlertCreate,
    PatientMedicalAlertRead,
    PatientMedicalAlertUpdate,
)
from app.schemas.progress_notes import (
    ProgressNoteCreate,
    ProgressNoteRead,
    ProgressNoteUpdate,
)
from app.schemas.treatment import (
    TreatmentPlanItemCreate,
    TreatmentPlanItemRead,
    TreatmentPlanItemUpdate,
)
from app.schemas.procedure_code import (
    ProcedureCodeCreate,
    ProcedureCodeRead,
    ProcedureCodeUpdate,
)

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
    search_relations: tuple[tuple[str, type, tuple[str, ...]], ...] = (),
    sortable: tuple[str, ...] = _DEFAULT_SORT,
    filters: tuple[str, ...] = (),
    ranges: tuple[str, ...] = (),
    soft_field: str | None = "is_active",
    soft_value: bool = False,
    default_sort: str = "created_at",
    read_exclude: tuple[str, ...] = (),
    hide_soft_deleted: bool = False,
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
        search_relations=search_relations,
        sortable_fields=sortable,
        filter_fields=filters,
        range_fields=ranges,
        soft_delete_field=soft_field,
        soft_delete_value=soft_value,
        default_sort=default_sort,
        hide_soft_deleted=hide_soft_deleted,
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
    # Custom crud_class auto-generates chart_no when omitted (GAP-AP-14). New
    # Add-Patient columns (pronouns/fee_schedule_id/patient_types/… ) are picked up
    # automatically by build_schemas — no schema hand-edits needed.
    CrudConfig(
        model=m.Patient,
        create_schema=PatientCreate,
        update_schema=PatientUpdate,
        read_schema=PatientRead,
        prefix="patients", tag="Patients",
        singular="patient", plural="patients",
        search_fields=("first_name", "last_name", "chart_no", "email", "phone"),
        sortable_fields=("created_at", "id", "last_name", "first_name", "dob"),
        filter_fields=("home_office_id", "is_active", "preferred_provider_id", "chart_no",
                       "dob", "ssn", "medicaid_id", "email", "phone", "gender",
                       "patient_type", "responsible_party_id", "preferred_hygienist_id",
                       "fee_schedule_id"),
        range_fields=("created_at", "dob"),
        default_sort="created_at",
        crud_class=PatientCRUD,
        read_enrich=enrich_patient_office,  # LEG-16: home_office_name/code
    ),
    # legacy_plan_type ("D"/"M") + insurance_type ("primary"…) address one slot
    # (INS-PT); is_active toggles a slot on/off.
    _cfg(m.PatientInsurance, "PatientInsurance", "patient-insurance", "Patients",
         "patient_insurance", "patient_insurance",
         filters=("patient_id", "insurance_type", "ins_plan_id",
                  "legacy_plan_type", "is_active")),
    _cfg(m.PatientAlert, "PatientAlert", "patient-alerts", "Patients",
         "patient_alert", "patient_alerts", filters=("patient_id", "is_active")),
    _cfg(m.AccountNote, "AccountNote", "account-notes", "Patients",
         "account_note", "account_notes", filters=("patient_id",), soft_field=None),
    _cfg(m.PatientSignature, "PatientSignature", "patient-signatures", "Patients",
         "patient_signature", "patient_signatures", filters=("patient_id",), soft_field=None),
    # PLAN-7: per-patient consent capture (template rendered with patient/plan data,
    # optionally signed + stored). Distinct from tenant-level account consents.
    _cfg(m.PatientConsent, "PatientConsent", "patient-consents", "Patients",
         "patient_consent", "patient_consents",
         filters=("patient_id", "plan_id", "template_id", "status"),
         soft_field="is_deleted", soft_value=True),
    _cfg(m.MedicalHistoryRecord, "MedicalHistoryRecord", "medical-history-records", "Patients",
         "medical_history_record", "medical_history_records",
         filters=("patient_id",), soft_field="is_archived", soft_value=True),
    _cfg(m.Referral, "Referral", "referrals", "Patients", "referral", "referrals",
         search=("first_name", "last_name", "specialty", "practice_name"),
         # Left-rail SEARCH ON (referral_type direction) + TYPE (reason_code) server filters.
         # PO-6: legacy_id lets the FE resolve patients.referred_by (a legacy referral id).
         filters=("patient_id", "office_id", "referral_type", "reason_code", "legacy_id"),
         soft_field=None),
    _cfg(m.PatientNote, "PatientNote", "patient-notes", "Patients",
         "patient_note", "patient_notes",
         filters=("patient_id", "note_type", "is_deleted", "is_archived"),
         soft_field="is_deleted", soft_value=True),
    _cfg(m.PatientRecall, "PatientRecall", "patient-recalls", "Patients",
         "patient_recall", "patient_recalls", filters=("patient_id", "status", "is_active")),
    # GAP-AP-16: per-patient Yes/No medical-alert responses (MEDALERT catalog).
    # LEG-2: custom schemas constrain response to the tri-state yes|no|unknown.
    CrudConfig(
        model=m.PatientMedicalAlert,
        create_schema=PatientMedicalAlertCreate,
        update_schema=PatientMedicalAlertUpdate,
        read_schema=PatientMedicalAlertRead,
        prefix="patient-medical-alerts", tag="Patients",
        singular="patient_medical_alert", plural="patient_medical_alerts",
        filter_fields=("patient_id", "alert_code", "response", "is_active"),
        default_sort="created_at",
    ),
    # GAP-AP-17: per-patient Dental/Medical questionnaire answers.
    _cfg(m.PatientQuestionnaireResponse, "PatientQuestionnaireResponse",
         "patient-questionnaire-responses", "Patients",
         "patient_questionnaire_response", "patient_questionnaire_responses",
         filters=("patient_id", "questionnaire_type", "question_code", "is_active")),
    _cfg(m.PatientEmergencyContact, "PatientEmergencyContact", "patient-emergency-contacts",
         "Patients", "patient_emergency_contact", "patient_emergency_contacts",
         filters=("patient_id", "is_active", "is_primary")),
    # LEG-10/11/12/13: standalone guarantor / billing entity (non-self responsible
    # party). Generic CRUD gives POST /responsible-parties returning an id; the
    # register endpoint can also create one inline.
    _cfg(m.ResponsibleParty, "ResponsibleParty", "responsible-parties", "Patients",
         "responsible_party", "responsible_parties",
         search=("first_name", "last_name", "email", "ssn"),
         # PO-2b: legacy_id lets the FE resolve a migrated guarantor id; PO-11 home_office_id.
         filters=("resp_party_type", "collection_agency_id", "is_active",
                  "legacy_id", "home_office_id")),
    _cfg(m.PatientAdjustment, "PatientAdjustment", "patient-adjustments", "Billing",
         "patient_adjustment", "patient_adjustments",
         sortable=("adjustment_date", "created_at"), ranges=("adjustment_date",),
         filters=("patient_id", "office_id", "provider_id", "procedure_id"),
         soft_field="is_void", soft_value=True),
]

# ── Insurance ──────────────────────────────────────────────────────────────
_INSURANCE = [
    _cfg(m.Employer, "Employer", "employers", "Insurance", "employer", "employers",
         search=("name", "city"), soft_field=None),
    # Carrier uses a custom Read schema (computed ``is_dental``, INS-2) and exposes
    # the server-side ``carrier_type`` filter that splits Dental/Medical (INS-1).
    CrudConfig(
        model=m.InsuranceCarrier,
        create_schema=InsuranceCarrierCreate,
        update_schema=InsuranceCarrierUpdate,
        read_schema=InsuranceCarrierRead,
        prefix="insurance-carriers", tag="Insurance",
        singular="insurance_carrier", plural="insurance_carriers",
        search_fields=("name", "payer_id"),
        sortable_fields=_DEFAULT_SORT,
        filter_fields=("is_active", "carrier_type", "insurance_type"),
        default_sort="created_at",
    ),
    _cfg(m.InsurancePlan, "InsurancePlan", "insurance-plans", "Insurance",
         "insurance_plan", "insurance_plans", search=("group_number", "plan_type"),
         # INS-9: also match a plan by its carrier/employer name (plans store only ids).
         search_relations=(
             ("carrier_id", m.InsuranceCarrier, ("name", "payer_id")),
             ("employer_id", m.Employer, ("name",)),
         ),
         # LEG-5: exact Group # filter (the legacy "Search For = Group #" option);
         # free-text `search` already covers group_number too.
         filters=("carrier_id", "employer_id", "is_active", "group_number")),
    _cfg(m.InsuranceSubscriber, "InsuranceSubscriber", "insurance-subscribers", "Insurance",
         "insurance_subscriber", "insurance_subscribers",
         search=("sub_first_name", "sub_last_name", "sub_member_id"),
         # INS-11: elig_status (+ office_id) filter so verification queues are countable.
         filters=("ins_plan_id", "subscriber_patient_id", "office_id", "elig_status", "is_active")),
    _cfg(m.InsuranceCoverageRule, "InsuranceCoverageRule", "insurance-coverage-rules", "Insurance",
         "insurance_coverage_rule", "insurance_coverage_rules",
         filters=("ins_plan_id",), soft_field=None),
]

# ── Procedures, fees & codes ───────────────────────────────────────────────
_CODES = [
    # ProcedureCode uses custom schemas (valid_teeth array, PROC-1) shared with the
    # stats/insurance-rules supplemental router.
    CrudConfig(
        model=m.ProcedureCode,
        create_schema=ProcedureCodeCreate,
        update_schema=ProcedureCodeUpdate,
        read_schema=ProcedureCodeRead,
        prefix="procedure-codes", tag="Procedures",
        singular="procedure_code", plural="procedure_codes",
        pk_type=str, pk_name="code",
        search_fields=("code", "description", "category"),
        sortable_fields=("code", "category"),
        filter_fields=("category", "is_active", "is_ortho", "chart_category"),
        default_sort="created_at",
    ),
    # FeeSchedule uses shared schemas (reused by the restore/new-version router)
    # and exposes the schedule-level effective_date range + version lineage (FEE-4).
    CrudConfig(
        model=m.FeeSchedule,
        create_schema=FeeScheduleCreate,
        update_schema=FeeScheduleUpdate,
        read_schema=FeeScheduleRead,
        prefix="fee-schedules", tag="Procedures",
        singular="fee_schedule", plural="fee_schedules",
        search_fields=("name",),
        sortable_fields=("created_at", "id", "effective_date", "name"),
        filter_fields=("ins_plan_id", "office_id", "is_active", "parent_schedule_id"),
        range_fields=("effective_date",),
        default_sort="created_at",
    ),
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
         "note_macro", "note_macros", search=("name", "category"),
         # NM-1: server-side "Select Macro Category" filter (was client-side only).
         filters=("category",), soft_field=None),
    _cfg(m.PrescriptionLibrary, "PrescriptionLibrary", "prescription-library", "Procedures",
         "prescription_library_item", "prescription_library", search=("drug_name",),
         filters=("is_active",)),
    # Auxiliary code tables (Setup -> Procedure Codes). AUX-3 POS is tenant-scoped;
    # AUX-4 ICD is a global catalog (like procedure_codes) — paginated + searchable.
    _cfg(m.PlaceOfServiceCode, "PlaceOfServiceCode", "place-of-service-codes", "Procedures",
         "place_of_service_code", "place_of_service_codes",
         search=("code", "type", "name"), sortable=("code", "created_at"),
         filters=("office_id", "is_active")),
    _cfg(m.IcdCode, "IcdCode", "icd-codes", "Procedures",
         "icd_code", "icd_codes", search=("code", "description", "icd10", "snomed"),
         sortable=("code", "created_at"), filters=("is_active",)),
]

# ── Scheduling ─────────────────────────────────────────────────────────────
_SCHEDULING = [
    _cfg(m.Appointment, "Appointment", "appointments", "Appointments",
         "appointment", "appointments", pk_type=str,
         search=("procedure_label", "notes"), sortable=("date", "start_time", "created_at"),
         # PO-5: is_archived filter so archived + active appts aren't returned interleaved.
         filters=("patient_id", "provider_id", "operatory_id", "office_id", "date",
                  "status", "is_archived"),
         ranges=("date",), soft_field="is_archived", soft_value=True),
    _cfg(m.AppointmentProcedure, "AppointmentProcedure", "appointment-procedures", "Appointments",
         "appointment_procedure", "appointment_procedures",
         filters=("appointment_id", "procedure_code", "provider_id"),
         soft_field="is_archived", soft_value=True),
    # AppointNow reason catalog (Setup surface for the online-booking reasons that
    # drive chair-time duration). The public AN-1/AN-3 endpoints read it directly;
    # this generic CRUD lets staff customise it per office.
    _cfg(m.AppointNowReason, "AppointNowReason", "appointnow-reasons", "Appointments",
         "appointnow_reason", "appointnow_reasons",
         search=("label", "reason_code"),
         sortable=("display_order", "created_at"), default_sort="display_order",
         filters=("office_id", "is_active", "requires_provider")),
]

# ── Treatment plans ────────────────────────────────────────────────────────
_TREATMENT = [
    # G9: read carries patient_name + rolled-up totals (Treatment Plan report).
    CrudConfig(
        model=m.TreatmentPlan,
        create_schema=TreatmentPlanCreate, update_schema=TreatmentPlanUpdate,
        read_schema=TreatmentPlanRead,
        prefix="treatment-plans", tag="Treatment Plans",
        singular="treatment_plan", plural="treatment_plans", pk_type=str,
        search_fields=("name",),
        filter_fields=("patient_id", "office_id", "status"),
        soft_delete_field=None, default_sort="created_at",
        read_enrich=enrich_treatment_plan,
    ),
    # Items: custom schemas add phase_id/dates/provider_id/discount + status enum
    # (PLAN-1/2/5/10); is_archived soft-delete (PLAN-14) via TreatmentPlanItemCRUD,
    # which also archives the item's insurance-details so a detail FK can't make the
    # item undeletable (PLAN-13). is_archived/phase_id/provider_id are filterable.
    CrudConfig(
        model=m.TreatmentPlanItem,
        create_schema=TreatmentPlanItemCreate,
        update_schema=TreatmentPlanItemUpdate,
        read_schema=TreatmentPlanItemRead,
        prefix="treatment-plan-items", tag="Treatment Plans",
        singular="treatment_plan_item", plural="treatment_plan_items",
        pk_type=str,
        sortable_fields=("priority", "created_at"),
        filter_fields=("plan_id", "procedure_code", "status", "phase_id",
                       "provider_id", "is_archived"),
        soft_delete_field="is_archived", soft_delete_value=True,
        default_sort="created_at",
        crud_class=TreatmentPlanItemCRUD,
    ),
]

# ── Clinical records ───────────────────────────────────────────────────────
_CLINICAL = [
    # G7: denormalized patient_name/provider_name on the read (Production report).
    CrudConfig(
        model=m.PatientProcedure,
        create_schema=PatientProcedureCreate, update_schema=PatientProcedureUpdate,
        read_schema=PatientProcedureRead,
        prefix="patient-procedures", tag="Clinical",
        singular="patient_procedure", plural="patient_procedures", pk_type=str,
        sortable_fields=("date_of_service", "created_at"),
        # treatment_plan_id: planned→completed lineage filter (REST).
        filter_fields=("patient_id", "appointment_id", "provider_id", "procedure_code",
                       "claim_id", "office_id", "billing_status", "treatment_plan_id", "is_void"),
        range_fields=("date_of_service",), soft_delete_field="is_void", soft_delete_value=True,
        default_sort="created_at", read_enrich=enrich_patient_provider,
    ),
    # Server-side chart filters (REST capability §6): procedure_code / chart_as /
    # is_inactive / group_id / status so the chart can be queried by ADA code,
    # module, span, or active-state instead of pulling size=200 and filtering client-side.
    _cfg(m.ChartCondition, "ChartCondition", "chart-conditions", "Clinical",
         "chart_condition", "chart_conditions",
         filters=("patient_id", "tooth", "provider_id", "procedure_code",
                  "chart_as", "is_inactive", "group_id", "status", "material_id"),
         soft_field="is_inactive", soft_value=True),
    # Progress notes. Custom Read adds struck_off audit + resolved names + computed
    # is_locked + attachment_count (PN-4/5/7/3); ProgressNoteCRUD enforces lock +
    # strike-off transitions on PATCH (PN-7/4).
    CrudConfig(
        model=m.ProgressNote,
        create_schema=ProgressNoteCreate,
        update_schema=ProgressNoteUpdate,
        read_schema=ProgressNoteRead,
        prefix="progress-notes", tag="Clinical",
        singular="progress_note", plural="progress_notes",
        search_fields=("notes",),
        sortable_fields=("note_date", "created_at"),
        filter_fields=("patient_id", "office_id", "is_struck_off"),
        range_fields=("note_date",),
        soft_delete_field="is_deleted", soft_delete_value=True,
        default_sort="created_at",
        read_enrich=enrich_progress_notes,
        crud_class=ProgressNoteCRUD,
    ),
    # Perio exam header. Custom Read embeds resolved actor names (PERIO-BE-6);
    # is_voided soft-delete (PERIO-BE-3) + is_voided filter so the Date-of-Service
    # list can exclude voided; exam_date range filter (PERIO-BE-9).
    CrudConfig(
        model=m.PerioExam,
        create_schema=PerioExamCreate,
        update_schema=PerioExamUpdate,
        read_schema=PerioExamRead,
        prefix="perio-exams", tag="Clinical",
        singular="perio_exam", plural="perio_exams",
        sortable_fields=("exam_date", "created_at"),
        filter_fields=("patient_id", "office_id", "is_voided"),
        range_fields=("exam_date",),
        soft_delete_field="is_voided", soft_delete_value=True,
        default_sort="exam_date",
        read_enrich=attach_actor_names,
    ),
    # Per-tooth detail. Custom Create/Update enforce clinical value ranges
    # (PERIO-BE-7); Read carries audit cols + names (PERIO-BE-5). One row per
    # tooth is enforced by the (exam_id, tooth_no) unique constraint (PERIO-BE-1).
    CrudConfig(
        model=m.PerioExamDetail,
        create_schema=PerioExamDetailCreate,
        update_schema=PerioExamDetailUpdate,
        read_schema=PerioExamDetailRead,
        prefix="perio-exam-details", tag="Clinical",
        singular="perio_exam_detail", plural="perio_exam_details",
        sortable_fields=("id", "tooth_no", "created_at"),
        default_sort="id",
        filter_fields=("exam_id", "tooth_no"),
        soft_delete_field=None,
        read_enrich=attach_actor_names,
    ),
    _cfg(m.Prescription, "Prescription", "prescriptions", "Clinical",
         "prescription", "prescriptions", search=("drug_name",),
         filters=("patient_id", "provider_id", "is_active")),
    # Per-user perio prefs. See /perio-chart-settings/me (PERIO-BE-11) for the
    # token-resolved, self-seeding convenience accessor.
    CrudConfig(
        model=m.PerioChartSetting,
        create_schema=PerioChartSettingCreate,
        update_schema=PerioChartSettingUpdate,
        read_schema=PerioChartSettingRead,
        prefix="perio-chart-settings", tag="Clinical",
        singular="perio_chart_setting", plural="perio_chart_settings",
        sortable_fields=_DEFAULT_SORT,
        filter_fields=("user_id",),
        soft_delete_field=None,
        default_sort="created_at",
    ),
    # CHART-1: named, tenant-scoped Perio Setup Templates (distinct from the per-user
    # perio_chart_settings above). Backs the "Perio Setup Templates" screen.
    # Custom schemas type the auto_advance structure (PERIO-BE-12).
    CrudConfig(
        model=m.PerioChartTemplate,
        create_schema=PerioChartTemplateCreate,
        update_schema=PerioChartTemplateUpdate,
        read_schema=PerioChartTemplateRead,
        prefix="perio-chart-templates", tag="Clinical",
        singular="perio_chart_template", plural="perio_chart_templates",
        search_fields=("name",),
        sortable_fields=_DEFAULT_SORT,
        soft_delete_field=None,
        default_sort="created_at",
    ),
    _cfg(m.PerioChartActivity, "PerioChartActivity", "perio-chart-activity", "Clinical",
         "perio_chart_activity", "perio_chart_activity", filters=("patient_id",), soft_field=None),
    # REST-2: practice-editable bridge/denture preset catalog.
    _cfg(m.ChartStatusTemplate, "ChartStatusTemplate", "chart-status-templates", "Clinical",
         "chart_status_template", "chart_status_templates", search=("name",),
         filters=("template_type", "arch", "material", "is_active")),
    # REST-4: per-tooth notes (also has /chart-tooth-notes/upsert for upsert-by-tooth).
    _cfg(m.ChartToothNote, "ChartToothNote", "chart-tooth-notes", "Clinical",
         "chart_tooth_note", "chart_tooth_notes",
         filters=("patient_id", "tooth"), soft_field=None),
]

# ── Billing & claims ───────────────────────────────────────────────────────
_BILLING = [
    # G7: denormalized patient_name/provider_name (Collections report).
    CrudConfig(
        model=m.PatientPayment,
        create_schema=PatientPaymentCreate, update_schema=PatientPaymentUpdate,
        read_schema=PatientPaymentRead,
        prefix="patient-payments", tag="Billing",
        singular="patient_payment", plural="patient_payments", pk_type=str,
        sortable_fields=("payment_date", "created_at"),
        filter_fields=("patient_id", "payment_type", "provider_id", "office_id", "is_void"),
        range_fields=("payment_date",), soft_delete_field="is_void", soft_delete_value=True,
        default_sort="created_at", read_enrich=enrich_patient_provider,
    ),
    # G7: patient_name/carrier_name; G10: submitted/paid/created date-range filters.
    CrudConfig(
        model=m.InsuranceClaim,
        create_schema=InsuranceClaimCreate, update_schema=InsuranceClaimUpdate,
        read_schema=InsuranceClaimRead,
        prefix="insurance-claims", tag="Billing",
        singular="insurance_claim", plural="insurance_claims", pk_type=str,
        search_fields=("claim_number",),
        filter_fields=("patient_id", "status", "claim_type", "carrier_id", "ins_plan_id",
                       "office_id", "is_active"),
        range_fields=("submitted_date", "paid_date", "created_at"),
        default_sort="created_at", read_enrich=enrich_patient_carrier,
    ),
    _cfg(m.ClaimSubmission, "ClaimSubmission", "claim-submissions", "Billing",
         "claim_submission", "claim_submissions", filters=("claim_id", "batch_id"), soft_field=None),
    _cfg(m.LedgerInsuranceDetail, "LedgerInsuranceDetail", "ledger-insurance-details", "Billing",
         "ledger_insurance_detail", "ledger_insurance_details",
         filters=("patient_id", "claim_id", "procedure_id"), soft_field=None),
    _cfg(m.PaymentAllocation, "PaymentAllocation", "payment-allocations", "Billing",
         "payment_allocation", "payment_allocations",
         filters=("patient_id", "payment_id", "procedure_id", "claim_id"), soft_field=None),
    # AL-3: plan_type discriminates Regular-Patient vs Ortho-Patient contracts.
    # PP-1: a DELETEd contract must not come back on the next page load.
    # PP-7/PP-8: PaymentPlanCRUD stamps created_by_id; the write schemas constrain
    # plan_type; enrich_payment_plan resolves the Created/Modified By names.
    CrudConfig(
        model=m.PatientPaymentPlan,
        create_schema=PatientPaymentPlanCreate,
        update_schema=PatientPaymentPlanUpdate,
        read_schema=PatientPaymentPlanRead,
        prefix="patient-payment-plans", tag="Billing",
        singular="patient_payment_plan", plural="patient_payment_plans",
        sortable_fields=_DEFAULT_SORT,
        filter_fields=("patient_id", "is_active", "plan_type", "treatment_plan_id"),
        range_fields=("setup_date", "first_due_date"),
        crud_class=PaymentPlanCRUD,
        read_enrich=enrich_payment_plan,
        hide_soft_deleted=True,
    ),
    # PP-6: ortho_plan_id ties an instalment row back to the contract that made it.
    _cfg(m.PatientInsPaymentPlan, "PatientInsPaymentPlan", "patient-ins-payment-plans", "Billing",
         "patient_ins_payment_plan", "patient_ins_payment_plans",
         filters=("patient_id", "is_billed", "ortho_plan_id"), ranges=("periodic_date",),
         soft_field=None),
    _cfg(m.PatientSecInsPaymentPlan, "PatientSecInsPaymentPlan", "patient-sec-ins-payment-plans",
         "Billing", "patient_sec_ins_payment_plan", "patient_sec_ins_payment_plans",
         filters=("patient_id", "is_billed", "ortho_plan_id"), ranges=("periodic_date",),
         soft_field=None),
    # OPP-9 / RPP-5: the patient-side instalment store (both contract kinds).
    _cfg(m.PatientPlanInstallment, "PatientPlanInstallment", "patient-plan-installments",
         "Billing", "patient_plan_installment", "patient_plan_installments",
         filters=("patient_id", "is_billed", "plan_side", "ortho_plan_id", "payment_plan_id"),
         ranges=("periodic_date",), soft_field=None),
    _cfg(m.PatientRegPlan, "PatientRegPlan", "patient-reg-plans", "Billing",
         "patient_reg_plan", "patient_reg_plans", filters=("patient_id", "is_active"),
         hide_soft_deleted=True),
    CrudConfig(
        model=m.OrthoPlan,
        create_schema=OrthoPlanCreate,
        update_schema=OrthoPlanUpdate,
        read_schema=OrthoPlanRead,
        prefix="ortho-plans", tag="Billing",
        singular="ortho_plan", plural="ortho_plans",
        sortable_fields=_DEFAULT_SORT,
        filter_fields=("patient_id", "is_active", "pref_provider_id", "ins_plan_id"),
        range_fields=("banding_date", "treat_start_date"),
        crud_class=PaymentPlanCRUD,
        read_enrich=enrich_ortho_plan,
        hide_soft_deleted=True,
    ),
]

# ── Config & reference ─────────────────────────────────────────────────────
_REFERENCE = [
    _cfg(m.Definition, "Definition", "definitions", "Metadata",
         "definition", "definitions", search=("description", "key1"),
         filters=("group_code", "is_active")),
    _cfg(m.DefinitionGroup, "DefinitionGroup", "definition-groups", "Metadata",
         "definition_group", "definition_groups", search=("description", "group_code"),
         # MED-1 / TB-1: feature-scoped fetch (MEDALERT/MEDQUEST/DENTQUEST/TOOLBAR…)
         # so the medical & toolbar setup screens stop fetching every group.
         filters=("group_type",), soft_field=None),
    _cfg(m.ImagingTemplate, "ImagingTemplate", "imaging-templates", "Metadata",
         "imaging_template", "imaging_templates", search=("name",),
         filters=("office_id",), soft_field=None),
    _cfg(m.QuestionnaireHeader, "QuestionnaireHeader", "questionnaire-headers", "Metadata",
         "questionnaire_header", "questionnaire_headers", search=("description",),
         # PICK-3: is_custom splits "Manage Pick Lists" (false) from "Custom Pick Lists".
         filters=("is_active", "is_custom")),
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
         filters=("fee_schedule_id", "ins_plan_id", "provider_id", "office_id",
                  "office_group_id", "carrier_id"), soft_field=None),
    _cfg(m.MedicalHistoryDetail, "MedicalHistoryDetail", "medical-history-details", "Patients",
         "medical_history_detail", "medical_history_details",
         filters=("history_id",), soft_field=None),
    _cfg(m.CariesRiskAssessment, "CariesRiskAssessment", "caries-risk-assessments", "Clinical",
         "caries_risk_assessment", "caries_risk_assessments",
         filters=("patient_id", "risk_level"), soft_field=None),
    # is_archived filterable so the list can exclude archived rows (PLAN-13).
    _cfg(m.TreatmentPlanInsuranceDetail, "TreatmentPlanInsuranceDetail",
         "treatment-plan-insurance-details", "Treatment Plans",
         "treatment_plan_insurance_detail", "treatment_plan_insurance_details",
         filters=("plan_item_id", "ins_plan_id", "is_archived"),
         soft_field="is_archived", soft_value=True),
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
    # Referral demographics feed (referral dev-report gap 5). Tagged "Patients" so it
    # lands in the same generated client file as referrals (was "Imaging" → undiscovered).
    _cfg(m.ReferralDemogHeader, "ReferralDemogHeader", "referral-demog-headers", "Patients",
         "referral_demog_header", "referral_demog_headers", search=("description",), soft_field=None),
    _cfg(m.ReferralDemogDetail, "ReferralDemogDetail", "referral-demog-details", "Patients",
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

# ── Office Assignment catalog (Setup -> Offices -> Office Assignment) ────────
_OFFICE_CATALOG = [
    _cfg(m.ProductionType, "ProductionType", "production-types", "Office Setup",
         "production_type", "production_types", search=("name",),
         filters=("is_active", "is_inactive")),
]

ALL_CONFIGS: list[CrudConfig] = [
    *_ORG, *_PATIENTS, *_INSURANCE, *_CODES, *_SCHEDULING, *_TREATMENT,
    *_CLINICAL, *_BILLING, *_REFERENCE, *_COMMS, *_STAFF, *_MISC, *_ACCESS,
    *_OFFICE_CATALOG,
]


def build_entity_router() -> APIRouter:
    router = APIRouter()
    for cfg in ALL_CONFIGS:
        router.include_router(register_crud(cfg))
    return router
