"""
migration/steps/__init__.py
Import all step modules so run_migration.py can do a single `from migration.steps import *`.
"""

from migration.steps import (
    s01_tenants, s02_offices, s03_providers,
    s03b_seed_users, s03c_user_offices,          # users + user_offices (were missing)
    s04_operatories,
    s05_employers, s06_insurance_carriers, s07_insurance_plans,
    s08_insurance_coverage_rules, s09_fee_schedules, s10_procedure_codes,
    s11_fee_schedule_entries, s12_chart_materials, s13_note_macros,
    s14_code_bundles, s15_code_bundle_items, s16_prescription_library,
    s17_patients, s18_insurance_subscribers, s19_patient_insurance,
    s20_patient_alerts, s21_account_notes, s22_patient_signatures,
    s23_medical_history_records, s24_referrals, s25_treatment_plans,
    s26_appointments, s27_appointment_procedures,
    s27b_treatment_plan_items,                   # treatment_plan_items (was missing)
    s28_patient_procedures, s29_patient_payments,
    s30_insurance_claims, s31_claim_submissions,
    s32_ledger_insurance_details, s33_payment_allocations,
    s34_chart_conditions, s35_progress_notes,
    s36_perio_exams, s37_perio_exam_details,
    s38_prescriptions, s39_sms_messages, s40_time_clock_entries,
    s41_letter_templates, s42_postcard_templates, s43_definitions,
    s44_imaging_templates, s45_perio_chart_settings,
    s46_questionnaire_headers, s47_questionnaire_options,
    # New steps — complete source file coverage
    s48_chart_colors, s49_codes_view, s50_definition_groups,
    s51_fee_schedule_assignments, s52_empty_tables_stubs,
)
