"""Access-rights catalog curation (ACCESS-RIGHTS handover, 2026-09-13).

The ``permissions`` catalog was seeded wholesale from the legacy Denticon rights
export (``data/Groups.txt`` -> ``scripts.seed_permissions``): **529** rows, many of
which map to no DentC screen (scraped audit-metadata rows, other-product features,
client-org custom reports). This module is the **single source of truth** for the
curation the frontend asked for, so the Alembic migration
(``<rev>_curate_access_rights_catalog``) and ``scripts.seed_permissions`` cannot
drift:

* **A1 DELETE 210** obsolete codes (:data:`REMOVED_ROWS`) — and, per **C2**,
  cascade the delete to ``user_group_rights`` so no group references a dead code.
* **A2 INSERT 44** new codes (:data:`ADDED_RIGHTS`) — shipped DentC
  screens/operations that had no right (Charting, Imaging, AppointNow, Messaging,
  Dashboard + gaps in Patient/Transactions/Setup/Help).
* **A3 RENAME** 4 surviving labels (:data:`RENAMES`) — cosmetic, the ``code`` (the
  stable key the FE enforces on) is never touched.

Net result: 319 kept + 44 added = **363** curated rights.

:func:`apply_curation` is idempotent (safe to re-run: it removes what is still
present, upserts the additions, and applies the renames), so it is called by both
the migration ``upgrade()`` and the seeder after it rebuilds the catalog from the
legacy export. :func:`revert_curation` is the migration ``downgrade()`` — it
restores the removed catalog *rows* (their prior group assignments are gone) and
reverts the renames.

``code`` is immutable: a code change is delete-old + add-new, which is exactly how
A1 + A2 express the handful of replacements (e.g. Denticon Practice Analytics ->
Dashboard).
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Permission, UserGroupRight

REMOVED_ROWS: tuple[tuple[str, str, str], ...] = (
    ('appointments_short_call_list', 'Appointments - Short call list', 'Appointments'),
    ('appointments_short_notice_list', 'Appointments - Short notice list', 'Appointments'),
    ('athenanet_search_athenanet_patients', 'AthenaNet - Search AthenaNet Patients', 'AthenaNet'),
    ('charting_ai_assist_screen_full_control', 'Charting - AI Assist Screen Full Control', 'Charting'),
    ('denticon_mobile_access', 'Denticon Mobile Access', 'General'),
    ('denticon_practice_analytics_collection_analysis_full_control', 'Denticon Practice Analytics - Collection Analysis Full Control', 'Denticon Practice Analytics'),
    ('denticon_practice_analytics_executive_dashboard_full_control', 'Denticon Practice Analytics - Executive Dashboard Full Control', 'Denticon Practice Analytics'),
    ('denticon_practice_analytics_front_office_full_control', 'Denticon Practice Analytics - Front Office Full Control', 'Denticon Practice Analytics'),
    ('denticon_practice_analytics_hygiene_recall_full_control', 'Denticon Practice Analytics - Hygiene Recall Full Control', 'Denticon Practice Analytics'),
    ('denticon_practice_analytics_morning_huddle_full_control', 'Denticon Practice Analytics - Morning Huddle Full Control', 'Denticon Practice Analytics'),
    ('denticon_practice_analytics_patient_visit_analysis_full_control', 'Denticon Practice Analytics - Patient Visit Analysis Full Control', 'Denticon Practice Analytics'),
    ('denticon_practice_analytics_production_analysis_full_control', 'Denticon Practice Analytics - Production Analysis Full Control', 'Denticon Practice Analytics'),
    ('denticon_practice_analytics_provider_breakdown_full_control', 'Denticon Practice Analytics - Provider Breakdown Full Control', 'Denticon Practice Analytics'),
    ('denticon_practice_analytics_referral_analytics_full_control', 'Denticon Practice Analytics - Referral Analytics Full Control', 'Denticon Practice Analytics'),
    ('denticon_practice_analytics_treatment_plan_analysis_full_control', 'Denticon Practice Analytics - Treatment Plan Analysis Full Control', 'Denticon Practice Analytics'),
    ('ehr_user_can_edit_instructions_and_bibliography_information', 'EHR - User can edit instructions and bibliography information', 'EHR'),
    ('ehr_user_can_see_and_access_the_infobutton', 'EHR - User can see and access the Infobutton', 'EHR'),
    ('ehr_user_will_see_cds_interventions_based_on_allergies', 'EHR - User will see CDS interventions based on Allergies', 'EHR'),
    ('ehr_user_will_see_cds_interventions_based_on_demographic_information', 'EHR - User will see CDS interventions based on Demographic information', 'EHR'),
    ('ehr_user_will_see_cds_interventions_based_on_lab_results', 'EHR - User will see CDS interventions based on Lab Results', 'EHR'),
    ('ehr_user_will_see_cds_interventions_based_on_medications', 'EHR - User will see CDS interventions based on Medications', 'EHR'),
    ('ehr_user_will_see_cds_interventions_based_on_problems', 'EHR - User will see CDS interventions based on Problems', 'EHR'),
    ('ehr_user_will_see_cds_interventions_based_on_vital_signs', 'EHR - User will see CDS interventions based on Vital Signs', 'EHR'),
    ('ehr_user_will_see_cds_interventions_for_allowed_categories', 'EHR - User will see CDS interventions for allowed categories', 'EHR'),
    ('help_access_invoices', 'Help - Access Invoices', 'Help'),
    ('helpandsupport_api_access_full_control', 'HelpAndSupport - API Access Full Control', 'HelpAndSupport'),
    ('modified_by', 'Modified By:', 'General'),
    ('modified_by_dhileep_jin2829', 'Modified By: DHILEEP.JIN2829', 'General'),
    ('modified_by_elizabethh', 'Modified By: ELIZABETHH', 'General'),
    ('modified_on', 'Modified On:', 'General'),
    ('modified_on_1_14_2022_6_09_00_am_pt', 'Modified On: 1/14/2022 6:09:00 AM PT', 'General'),
    ('modified_on_3_13_2025_10_05_00_am_pt', 'Modified On: 3/13/2025 10:05:00 AM PT', 'General'),
    ('modified_on_3_18_2026_7_05_00_am_pt', 'Modified On: 3/18/2026 7:05:00 AM PT', 'General'),
    ('modified_on_4_3_2025_10_34_00_am_pt', 'Modified On: 4/3/2025 10:34:00 AM PT', 'General'),
    ('modified_on_6_17_2016_6_40_00_pm_pt', 'Modified On: 6/17/2016 6:40:00 PM PT', 'General'),
    ('modified_on_6_3_2026_11_09_00_am_pt', 'Modified On: 6/3/2026 11:09:00 AM PT', 'General'),
    ('modified_on_9_23_2025_6_30_00_am_pt', 'Modified On: 9/23/2025 6:30:00 AM PT', 'General'),
    ('modified_on_9_23_2025_6_43_00_am_pt', 'Modified On: 9/23/2025 6:43:00 AM PT', 'General'),
    ('mytooth_assign_forms_packets_from_scheduler_full_control', 'MyTooth – Assign Forms/Packets from Scheduler Full Control', 'MyTooth'),
    ('mytooth_assign_forms_packets_from_twc_or_messaging_hub_full_control', 'MyTooth – Assign Forms/Packets from TWC or Messaging Hub Full Control', 'MyTooth'),
    ('mytooth_check_the_activity_report_full_control', 'MyTooth – Check the Activity Report Full Control', 'MyTooth'),
    ('patient_add_new_flash_alerts', 'Patient - Add New Flash Alerts', 'Patient'),
    ('patient_caries_risk_assessment_full_control', 'Patient - Caries Risk Assessment Full Control', 'Patient'),
    ('patient_caries_risk_assessment_view_only', 'Patient - Caries Risk Assessment View Only', 'Patient'),
    ('patient_edit_or_deactivate_existing_flash_alerts', 'Patient - Edit Or Deactivate Existing Flash Alerts', 'Patient'),
    ('patient_reallocate_screen_full_control', 'Patient - Reallocate Screen Full Control', 'Patient'),
    ('patient_reallocate_view_only', 'Patient - Reallocate View Only', 'Patient'),
    ('patient_status_tracker_full_control', 'Patient - Status Tracker Full Control', 'Patient'),
    ('patient_status_tracker_view_only', 'Patient - Status Tracker View Only', 'Patient'),
    ('report_batch_schedule_report_access_full_control', 'Report - Batch Schedule Report Access Full Control', 'Report'),
    ('report_batch_schedule_report_add_schedule', 'Report - Batch Schedule Report - Add Schedule', 'Report'),
    ('report_batch_schedule_report_delete_schedule', 'Report - Batch Schedule Report - Delete Schedule', 'Report'),
    ('report_batch_schedule_report_view_only', 'Report - Batch Schedule Report View Only', 'Report'),
    ('reports_batch_collection_letters_full_control', 'Reports - Batch Collection Letters Full Control', 'Reports'),
    ('reports_batch_collection_letters_view_only', 'Reports - Batch Collection Letters View Only', 'Reports'),
    ('reports_blank_insurance_form_screen_full_control', 'Reports - Blank Insurance Form Screen Full Control', 'Reports'),
    ('reports_blank_insurance_form_screen_view_only', 'Reports - Blank Insurance Form Screen View Only', 'Reports'),
    ('reports_custom_postcard_full_control', 'Reports - Custom Postcard Full Control', 'Reports'),
    ('reports_custom_postcard_screen_view_only', 'Reports - Custom Postcard Screen View Only', 'Reports'),
    ('reports_dha_reports_screen_full_control', 'Reports - DHA Reports Screen Full Control', 'Reports'),
    ('reports_dha_reports_screen_view_only', 'Reports - DHA Reports Screen View Only', 'Reports'),
    ('reports_excel_reports_full_control', 'Reports - Excel Reports Full Control', 'Reports'),
    ('reports_excel_reports_view_only', 'Reports - Excel Reports View Only', 'Reports'),
    ('reports_labels_screen_full_control', 'Reports - Labels Screen Full Control', 'Reports'),
    ('reports_labels_screen_view_only', 'Reports - Labels Screen View Only', 'Reports'),
    ('reports_office_reports_abbeydental_full_control', 'Reports - Office Reports-AbbeyDental Full Control', 'Reports'),
    ('reports_office_reports_adrpts_screen_full_con', 'Reports - Office Reports - ADRpts Screen Full Con', 'Reports'),
    ('reports_office_reports_adrpts_screen_view_only', 'Reports - Office Reports - ADRpts Screen View Only', 'Reports'),
    ('reports_office_reports_bnrpts_screen_full_cont', 'Reports - Office Reports - BNRpts Screen Full Cont', 'Reports'),
    ('reports_office_reports_bnrpts_screen_view_only', 'Reports - Office Reports - BNRpts Screen View Only', 'Reports'),
    ('reports_office_reports_chi_st_joseph_children_s_health_reports_full_control', "Reports - Office Reports - CHI St. Joseph Children's Health Reports Full Control", 'Reports'),
    ('reports_office_reports_chi_st_joseph_children_s_health_reports_view_only', "Reports - Office Reports - CHI St. Joseph Children's Health Reports View Only", 'Reports'),
    ('reports_office_reports_dental_care_access', 'Reports - Office Reports - Dental Care Access', 'Reports'),
    ('reports_office_reports_greathillsrpts_access', 'Reports - Office Reports - GreatHillsRpts Access', 'Reports'),
    ('reports_office_reports_hawaiirpts_full_control', 'Reports - Office Reports - HawaiiRpts Full Control', 'Reports'),
    ('reports_office_reports_hawaiirpts_view_only', 'Reports - Office Reports - HawaiiRpts View Only', 'Reports'),
    ('reports_office_reports_healthcare_network_access_full_control', 'Reports - Office Reports - Healthcare Network Access Full Control', 'Reports'),
    ('reports_office_reports_healthysmileskids_full_co', 'Reports - Office Reports-HealthySmilesKids Full Co', 'Reports'),
    ('reports_office_reports_kane_dental_access', 'Reports - Office Reports - Kane Dental Access', 'Reports'),
    ('reports_office_reports_kane_dental_view', 'Reports - Office Reports - Kane Dental View', 'Reports'),
    ('reports_office_reports_kansas_rpts_full_contro', 'Reports - Office Reports - Kansas Rpts Full Contro', 'Reports'),
    ('reports_office_reports_lumina_reports_full_control', 'Reports - Office Reports - Lumina Reports Full Control', 'Reports'),
    ('reports_office_reports_lumina_reports_view_only', 'Reports - Office Reports - Lumina Reports View Only', 'Reports'),
    ('reports_office_reports_nedmrpts_screen_full_co', 'Reports - Office Reports - NEDMRpts Screen Full Co', 'Reports'),
    ('reports_office_reports_nedmrpts_screen_view_on', 'Reports - Office Reports - NEDMRpts Screen View On', 'Reports'),
    ('reports_office_reports_ohc_reports_full_contro', 'Reports - Office Reports - OHC Reports Full Contro', 'Reports'),
    ('reports_office_reports_ottawareports_access', 'Reports - Office Reports - OttawaReports Access', 'Reports'),
    ('reports_office_reports_premier_perio_full_cont', 'Reports - Office Reports - Premier Perio Full Cont', 'Reports'),
    ('reports_office_reports_sgkreports_screen_full_control', 'Reports - Office Reports - SGKReports Screen Full Control', 'Reports'),
    ('reports_office_reports_sgkreports_screen_view_only', 'Reports - Office Reports - SGKReports Screen View Only', 'Reports'),
    ('reports_office_reports_tru_family_rpts_full_control', 'Reports - Office Reports - Tru Family Rpts Full Control', 'Reports'),
    ('reports_office_reports_uop_reports_full_contro', 'Reports - Office Reports - UOP Reports Full Contro', 'Reports'),
    ('reports_office_reports_vhrpts_screen_full_con', 'Reports - Office Reports - VHRpts Screen Full Con', 'Reports'),
    ('reports_office_reports_vhrpts_screen_view_only', 'Reports - Office Reports - VHRpts Screen View Only', 'Reports'),
    ('reports_office_reports_village_family_dental_reports_full_control', 'Reports - Office Reports - Village Family Dental Reports Full Control', 'Reports'),
    ('reports_office_reports_village_family_dental_reports_view_only', 'Reports - Office Reports - Village Family Dental Reports View Only', 'Reports'),
    ('reports_ortho_reports_access_full_control', 'Reports - Ortho Reports Access Full Control', 'Reports'),
    ('reports_ortho_reports_view_only', 'Reports - Ortho Reports View Only', 'Reports'),
    ('reports_postcards_full_control', 'Reports - Postcards Full Control', 'Reports'),
    ('reports_postcards_view_only', 'Reports - Postcards View Only', 'Reports'),
    ('reports_recall_reports_screen_full_control', 'Reports - Recall Reports Screen Full Control', 'Reports'),
    ('reports_recall_reports_screen_view_only', 'Reports - Recall Reports Screen View Only', 'Reports'),
    ('reports_voice_charting_adoption_full_control', 'Reports - Voice Charting Adoption Full Control', 'Reports'),
    ('setup_code_bundling_full_control', 'Setup - Code Bundling - Full Control', 'Setup'),
    ('setup_code_bundling_view_only', 'Setup - Code Bundling - View Only', 'Setup'),
    ('setup_collection_agencies_screen_full_control', 'Setup - Collection Agencies Screen Full Control', 'Setup'),
    ('setup_collection_agencies_screen_view_only', 'Setup - Collection Agencies Screen View Only', 'Setup'),
    ('setup_dentigram_downloads_full_control', 'Setup - Dentigram Downloads Full Control', 'Setup'),
    ('setup_dentigram_downloads_view_only', 'Setup - Dentigram Downloads View Only', 'Setup'),
    ('setup_ehr_cds_rules', 'Setup - EHR - CDS Rules', 'Setup'),
    ('setup_emergency_now', 'Setup - > Emergency Now', 'Setup'),
    ('setup_misc_screen_full_control', 'Setup - Misc. Screen Full Control', 'Setup'),
    ('setup_misc_screen_view_only', 'Setup - Misc. Screen View Only', 'Setup'),
    ('setup_ortho_misc_setup_full_control', 'Setup - Ortho Misc Setup Full Control', 'Setup'),
    ('setup_ortho_misc_setup_view_only', 'Setup - Ortho Misc Setup View Only', 'Setup'),
    ('setup_ortho_questionnaire_full_control', 'Setup - Ortho Questionnaire Full Control', 'Setup'),
    ('setup_ortho_questionnaire_view_only', 'Setup - Ortho Questionnaire View Only', 'Setup'),
    ('setup_provider_goals_screen_full_control', 'Setup - Provider Goals Screen Full Control', 'Setup'),
    ('setup_provider_goals_screen_view_only', 'Setup - Provider Goals Screen View Only', 'Setup'),
    ('setup_reset_benefits_for_all_offices_in_pgid', 'Setup - Reset Benefits for All Offices in PGID', 'Setup'),
    ('setup_reset_benefits_for_current_office_only', 'Setup - Reset Benefits for Current Office Only', 'Setup'),
    ('setup_reset_benefits_view_only', 'Setup - Reset Benefits View Only', 'Setup'),
    ('setup_security_multi_pgid_users_screen_full_control', 'Setup - Security Multi PGID Users Screen Full Control', 'Setup'),
    ('setup_sso_users_setup_screen_full_control', 'Setup - SSO Users Setup Screen Full Control', 'Setup'),
    ('setup_sso_users_setup_screen_view_only', 'Setup - SSO Users Setup Screen View Only', 'Setup'),
    ('transaction_batch_insurance_payment_dentical_full_control', 'Transaction - Batch Insurance Payment Dentical Full Control', 'Transaction'),
    ('transactions_add_post_batch_insurance_payments', 'Transactions - Add/Post Batch Insurance Payments', 'Transactions'),
    ('transactions_add_post_batch_insurance_payments_835', 'Transactions - Add/Post Batch Insurance Payments 835', 'Transactions'),
    ('transactions_add_post_capitation_payments', 'Transactions - Add/Post Capitation Payments', 'Transactions'),
    ('transactions_batch_insurance_payments_835_view_only', 'Transactions - Batch Insurance Payments 835 View Only', 'Transactions'),
    ('transactions_batch_insurance_payments_view_only', 'Transactions - Batch Insurance Payments View Only', 'Transactions'),
    ('utilities_835_hub_full_control', 'Utilities - 835 Hub - Full Control', 'Utilities'),
    ('utilities_835_hub_view_only', 'Utilities - 835 Hub - View Only', 'Utilities'),
    ('utilities_access_to_dentilytics_enterprise', 'Utilities - Access to Dentilytics Enterprise', 'Utilities'),
    ('utilities_automated_campaigns_ad_hoc_campaign_management', 'Utilities - Automated Campaigns Ad-hoc Campaign Management', 'Utilities'),
    ('utilities_automated_campaigns_ad_hoc_campaign_user_specific', 'Utilities - Automated Campaigns Ad-hoc Campaign User Specific', 'Utilities'),
    ('utilities_automated_campaigns_ad_hoc_campaign_view_only', 'Utilities - Automated Campaigns Ad-hoc Campaign View Only', 'Utilities'),
    ('utilities_automated_campaigns_appointment_campaign_management', 'Utilities - Automated Campaigns Appointment Campaign Management', 'Utilities'),
    ('utilities_automated_campaigns_appointment_campaign_user_specific', 'Utilities - Automated Campaigns Appointment Campaign User Specific', 'Utilities'),
    ('utilities_automated_campaigns_appointment_campaign_view_only', 'Utilities - Automated Campaigns Appointment Campaign View Only', 'Utilities'),
    ('utilities_automated_campaigns_dashboard_full_control', 'Utilities - Automated Campaigns Dashboard Full Control', 'Utilities'),
    ('utilities_automated_campaigns_dashboard_view_only', 'Utilities - Automated Campaigns Dashboard View Only', 'Utilities'),
    ('utilities_automated_campaigns_mailing_list_management', 'Utilities - Automated Campaigns Mailing List Management', 'Utilities'),
    ('utilities_automated_campaigns_mailing_list_user_specific', 'Utilities - Automated Campaigns Mailing List User Specific', 'Utilities'),
    ('utilities_automated_campaigns_mailing_list_view_only', 'Utilities - Automated Campaigns Mailing List View Only', 'Utilities'),
    ('utilities_automated_campaigns_patient_care_campaign_management', 'Utilities - Automated Campaigns Patient Care Campaign Management', 'Utilities'),
    ('utilities_automated_campaigns_patient_care_campaign_user_specific', 'Utilities - Automated Campaigns Patient Care Campaign User Specific', 'Utilities'),
    ('utilities_automated_campaigns_patient_care_campaign_view_only', 'Utilities - Automated Campaigns Patient Care Campaign View Only', 'Utilities'),
    ('utilities_automated_campaigns_recurring_campaign_management', 'Utilities - Automated Campaigns Recurring Campaign Management', 'Utilities'),
    ('utilities_automated_campaigns_recurring_campaign_user_specific', 'Utilities - Automated Campaigns Recurring Campaign User Specific', 'Utilities'),
    ('utilities_automated_campaigns_recurring_campaign_view_only', 'Utilities - Automated Campaigns Recurring Campaign View Only', 'Utilities'),
    ('utilities_automated_campaigns_template_management', 'Utilities - Automated Campaigns Template Management', 'Utilities'),
    ('utilities_automated_campaigns_template_user_specific', 'Utilities - Automated Campaigns Template User Specific', 'Utilities'),
    ('utilities_automated_campaigns_template_view_only', 'Utilities - Automated Campaigns Template View Only', 'Utilities'),
    ('utilities_batch_claim_processing_screen_full_control', 'Utilities - Batch Claim Processing Screen Full Control', 'Utilities'),
    ('utilities_batch_claim_processing_screen_view_only', 'Utilities - Batch Claim Processing Screen View Only', 'Utilities'),
    ('utilities_batch_eligibility_full_control', 'Utilities - Batch Eligibility Full Control', 'Utilities'),
    ('utilities_batch_eligibility_view_only', 'Utilities - Batch Eligibility View Only', 'Utilities'),
    ('utilities_consolidate_carriers_full_control', 'Utilities - Consolidate Carriers Full Control', 'Utilities'),
    ('utilities_consolidate_carriers_view_only', 'Utilities - Consolidate Carriers View Only', 'Utilities'),
    ('utilities_data_conversion_mapping_full_control', 'Utilities - Data Conversion Mapping - Full Control', 'Utilities'),
    ('utilities_denticon_download_full_control', 'Utilities - Denticon Download Full Control', 'Utilities'),
    ('utilities_denticon_download_view_only', 'Utilities - Denticon Download View Only', 'Utilities'),
    ('utilities_dentigram_download_full_control', 'Utilities - Dentigram Download Full Control', 'Utilities'),
    ('utilities_dentigram_download_view_only', 'Utilities - Dentigram Download View Only', 'Utilities'),
    ('utilities_dhaclaims837_full_control', 'Utilities - DHAClaims837- Full Control', 'Utilities'),
    ('utilities_dhaclaims837_view_only', 'Utilities - DHAClaims837- View Only', 'Utilities'),
    ('utilities_direct_claims_full_control', 'Utilities - Direct Claims Full Control', 'Utilities'),
    ('utilities_direct_claims_view_only', 'Utilities - Direct Claims View Only', 'Utilities'),
    ('utilities_dldfeeschexls_download_full_control', 'Utilities - DldFeeScheXls Download Full Control', 'Utilities'),
    ('utilities_dldfeeschexls_download_view_only', 'Utilities - DldFeeScheXls Download View Only', 'Utilities'),
    ('utilities_download837_full_control', 'Utilities - Download837 - Full Control', 'Utilities'),
    ('utilities_download837_view_only', 'Utilities - Download837 - View Only', 'Utilities'),
    ('utilities_eclaims_management_screen_full_control', 'Utilities - Eclaims Management Screen Full Control', 'Utilities'),
    ('utilities_ehr_ehrreport_fullcontrol', 'Utilities->EHR-EHRReport-FullControl', 'General'),
    ('utilities_encounter_download_full_control', 'Utilities - Encounter Download Full Control', 'Utilities'),
    ('utilities_encounter_download_view_only', 'Utilities - Encounter Download View Only', 'Utilities'),
    ('utilities_encounterdownload_full_control', 'Utilities - EncounterDownload - Full Control', 'Utilities'),
    ('utilities_encounterdownload_view_only', 'Utilities - EncounterDownload - View Only', 'Utilities'),
    ('utilities_launch_mouthwatch_teledentistry', 'Utilities - Launch Mouthwatch (Teledentistry)', 'Utilities'),
    ('utilities_office_dha_close_mananged_full_control', 'Utilities - Office-DHA-Close Mananged Full Control', 'Utilities'),
    ('utilities_office_dha_close_mananged_view_only', 'Utilities - Office-DHA-Close Mananged View Only', 'Utilities'),
    ('utilities_office_specific_dca_close_out_claims_full_control', 'Utilities - Office Specific - DCA - Close Out Claims Full Control', 'Utilities'),
    ('utilities_office_specific_dha_statementxmldld_full', 'Utilities-Office Specific-DHA-StatementXMLDld Full', 'General'),
    ('utilities_office_specific_dha_statementxmldld_view', 'Utilities-Office Specific-DHA-StatementXMLDld View', 'General'),
    ('utilities_office_specific_mid_atlantic_batchaddflashalerts_full', 'Utilities-Office Specific-Mid Atlantic-BatchAddFlashAlerts Full', 'General'),
    ('utilities_office_specific_mid_atlantic_batchaddflashalerts_view', 'Utilities-Office Specific-Mid Atlantic-BatchAddFlashAlerts View', 'General'),
    ('utilities_office_specific_mid_atlantic_batchdeactivateflashalerts_full', 'Utilities-Office Specific-Mid Atlantic-BatchDeactivateFlashAlerts Full', 'General'),
    ('utilities_office_specific_mid_atlantic_batchdeactivateflashalerts_view', 'Utilities-Office Specific-Mid Atlantic-BatchDeactivateFlashAlerts View', 'General'),
    ('utilities_radius_global_full_access', 'Utilities - Radius Global Full Access', 'Utilities'),
    ('utilities_replace_carriers_full_control', 'Utilities - Replace Carriers Full Control', 'Utilities'),
    ('utilities_replace_carriers_view_only', 'Utilities - Replace Carriers View Only', 'Utilities'),
    ('utilities_replace_insurance_plans_full_control', 'Utilities - Replace Insurance Plans Full Control', 'Utilities'),
    ('utilities_replace_insurance_plans_view_only', 'Utilities - Replace Insurance Plans View Only', 'Utilities'),
    ('utilities_replace_procedure_code_full_control', 'Utilities - Replace Procedure Code Full Control', 'Utilities'),
    ('utilities_replace_procedure_code_view_only', 'Utilities - Replace Procedure Code View Only', 'Utilities'),
    ('utilities_scheduled_reallocation_list', 'Utilities - Scheduled Reallocation List', 'Utilities'),
    ('utilities_task_manager_access', 'Utilities - Task Manager - Access', 'Utilities'),
    ('utilities_task_manager_assign_task', 'Utilities - Task Manager - Assign Task', 'Utilities'),
    ('utilities_task_manager_change_action_of_task', 'Utilities - Task Manager - Change Action of Task', 'Utilities'),
    ('utilities_task_manager_create_task', 'Utilities - Task Manager - Create Task', 'Utilities'),
    ('utilities_task_manager_delete_task', 'Utilities - Task Manager - Delete Task', 'Utilities'),
    ('utilities_task_manager_supervisor_user', 'Utilities - Task Manager - Supervisor User', 'Utilities'),
    ('utilities_tickler_full_control', 'Utilities - Tickler Full Control', 'Utilities'),
    ('utilities_tickler_view_only_control', 'Utilities - Tickler View Only Control', 'Utilities'),
    ('utilities_time_clock_editor_full_control', 'Utilities - Time Clock Editor Full Control', 'Utilities'),
    ('utilities_time_clock_editor_view_only', 'Utilities - Time Clock Editor View Only', 'Utilities'),
    ('utilities_time_clock_full_control', 'Utilities - Time Clock Full Control', 'Utilities'),
    ('utilities_time_clock_view_only', 'Utilities - Time Clock View Only', 'Utilities'),
    ('utilities_transworld_full_access', 'Utilities - Transworld Full Access', 'Utilities'),
)

ADDED_RIGHTS: tuple[dict[str, str], ...] = (
    {"code": 'charting_restorative_full_control', "label": 'Charting - Restorative Chart Full Control', "category": 'Charting'},
    {"code": 'charting_restorative_view_only', "label": 'Charting - Restorative Chart View Only', "category": 'Charting'},
    {"code": 'charting_restorative_delete_condition', "label": 'Charting - Restorative Delete Condition/Procedure', "category": 'Charting'},
    {"code": 'charting_perio_full_control', "label": 'Charting - Perio Chart Full Control', "category": 'Charting'},
    {"code": 'charting_perio_view_only', "label": 'Charting - Perio Chart View Only', "category": 'Charting'},
    {"code": 'charting_perio_compare', "label": 'Charting - Perio Compare Exams', "category": 'Charting'},
    {"code": 'charting_perio_print', "label": 'Charting - Perio Chart Print', "category": 'Charting'},
    {"code": 'imaging_full_control', "label": 'Imaging - X-Rays / Images Full Control', "category": 'Imaging'},
    {"code": 'imaging_view_only', "label": 'Imaging - X-Rays / Images View Only', "category": 'Imaging'},
    {"code": 'imaging_capture_acquire', "label": 'Imaging - Capture / Acquire Image', "category": 'Imaging'},
    {"code": 'imaging_delete_image', "label": 'Imaging - Delete Image', "category": 'Imaging'},
    {"code": 'imaging_export', "label": 'Imaging - Export / Download Image', "category": 'Imaging'},
    {"code": 'patient_lab_cases_full_control', "label": 'Patient - Lab Tracking (Cases) Full Control', "category": 'Patient'},
    {"code": 'patient_lab_cases_view_only', "label": 'Patient - Lab Tracking (Cases) View Only', "category": 'Patient'},
    {"code": 'patient_documents_full_control', "label": 'Patient - Documents Full Control', "category": 'Patient'},
    {"code": 'patient_documents_view_only', "label": 'Patient - Documents View Only', "category": 'Patient'},
    {"code": 'patient_documents_upload', "label": 'Patient - Documents Upload', "category": 'Patient'},
    {"code": 'patient_documents_delete', "label": 'Patient - Documents Delete', "category": 'Patient'},
    {"code": 'patient_letters_full_control', "label": 'Patient - Letters Full Control', "category": 'Patient'},
    {"code": 'patient_letters_view_only', "label": 'Patient - Letters View Only', "category": 'Patient'},
    {"code": 'patient_letters_generate', "label": 'Patient - Letters Generate / Produce', "category": 'Patient'},
    {"code": 'patient_consent_sign', "label": 'Patient - Consent Form e-Signature Capture', "category": 'Patient'},
    {"code": 'patient_emergency_contacts_full_control', "label": 'Patient - Emergency Contacts Full Control', "category": 'Patient'},
    {"code": 'patient_emergency_contacts_view_only', "label": 'Patient - Emergency Contacts View Only', "category": 'Patient'},
    {"code": 'transactions_claims_ada_direct_print', "label": 'Transactions - Claims ADA Direct Print', "category": 'Transactions'},
    {"code": 'transactions_claims_save_draft', "label": 'Transactions - Claims Save as Draft', "category": 'Transactions'},
    {"code": 'transactions_claims_create_secondary_plus', "label": 'Transactions - Create Secondary/Tertiary/Quaternary Claim', "category": 'Transactions'},
    {"code": 'appointments_scheduler_print', "label": 'Appointments - Scheduler Print', "category": 'Appointments'},
    {"code": 'appointnow_request_inbox_full_control', "label": 'AppointNow - Request Inbox Full Control', "category": 'AppointNow'},
    {"code": 'appointnow_request_inbox_view_only', "label": 'AppointNow - Request Inbox View Only', "category": 'AppointNow'},
    {"code": 'appointnow_approve_booking', "label": 'AppointNow - Approve Online Booking', "category": 'AppointNow'},
    {"code": 'appointnow_decline_booking', "label": 'AppointNow - Decline Online Booking', "category": 'AppointNow'},
    {"code": 'setup_appointnow_config_full_control', "label": 'Setup - AppointNow / Public Booking Config Full Control', "category": 'Setup'},
    {"code": 'messaging_direct_messages_full_control', "label": 'Messaging - Direct Messages Full Control', "category": 'Messaging'},
    {"code": 'messaging_direct_messages_view_only', "label": 'Messaging - Direct Messages View Only', "category": 'Messaging'},
    {"code": 'setup_communications_phone_assignments_full_control', "label": 'Setup - Communications / Phone Assignments Full Control', "category": 'Setup'},
    {"code": 'setup_communications_phone_assignments_view_only', "label": 'Setup - Communications / Phone Assignments View Only', "category": 'Setup'},
    {"code": 'setup_signature_pad_device_full_control', "label": 'Setup - Signature Pad Device Full Control', "category": 'Setup'},
    {"code": 'help_center_access', "label": 'Help - Help Center Access', "category": 'Help'},
    {"code": 'help_report_an_issue', "label": 'Help - Report an Issue (Submit Ticket)', "category": 'Help'},
    {"code": 'help_my_tickets_view', "label": 'Help - My Tickets View', "category": 'Help'},
    {"code": 'dashboard_view', "label": 'Dashboard - View', "category": 'Dashboard'},
    {"code": 'my_page_access', "label": 'My Page - Access', "category": 'Dashboard'},
    {"code": 'office_scope_view_all_offices', "label": 'General - View Data Across All Offices', "category": 'General'},
)

RENAMES: tuple[tuple[str, str, str], ...] = (
    ('utilities_two_way_communication_full_control', 'Utilities - Two Way Communication Full Control', 'Utilities - Patient SMS / Two-Way Communication Full Control'),
    ('utilities_two_way_communication_view_only', 'Utilities - Two Way Communication View Only', 'Utilities - Patient SMS / Two-Way Communication View Only'),
    ('patient_messaging_hub_user_full_control', 'Patient - Messaging Hub User Full Control', 'Patient - SMS / Communication Full Control'),
    ('patient_messaging_hub_view_only', 'Patient - Messaging Hub View Only', 'Patient - SMS / Communication View Only'),
)


#: Codes deleted from the catalog (A1). Frozen for cheap membership checks.
REMOVED_CODES: frozenset[str] = frozenset(code for code, _label, _cat in REMOVED_ROWS)
#: Codes inserted into the catalog (A2).
ADDED_CODES: frozenset[str] = frozenset(r["code"] for r in ADDED_RIGHTS)
#: The expected size of the curated catalog (319 kept + 44 added).
CURATED_TOTAL = 363


def apply_curation(db: Session, *, commit: bool = True) -> dict[str, int]:
    """Apply A1 (+C2 cascade), A2 and A3 to ``permissions`` in one transaction.

    Idempotent. Returns a small report of what changed this run — on a
    freshly-seeded catalog every count is populated; on a second run they are all
    zero (nothing left to remove, the additions already present, the renames
    already applied).

    ``commit`` defaults to True (the seeder path). The Alembic migration passes
    ``commit=False`` so it only *flushes* — the migration's own transaction is
    committed by Alembic, matching how the other data migrations behave.
    """
    # ── A1 + C2: delete removed codes, cascading to group assignments first ──
    removed_ids = list(
        db.execute(select(Permission.id).where(Permission.code.in_(REMOVED_CODES))).scalars()
    )
    rights_cascaded = permissions_removed = 0
    if removed_ids:
        rights_cascaded = db.execute(
            delete(UserGroupRight).where(UserGroupRight.permission_id.in_(removed_ids))
        ).rowcount or 0
        permissions_removed = db.execute(
            delete(Permission).where(Permission.id.in_(removed_ids))
        ).rowcount or 0

    # ── A2: upsert the new codes by ``code`` ────────────────────────────────
    existing = {
        p.code: p
        for p in db.execute(
            select(Permission).where(Permission.code.in_(ADDED_CODES))
        ).scalars()
    }
    added = reactivated = 0
    for r in ADDED_RIGHTS:
        row = existing.get(r["code"])
        if row is None:
            db.add(Permission(code=r["code"], label=r["label"],
                              category=r["category"], is_active=True))
            added += 1
        elif not row.is_active or row.label != r["label"] or row.category != r["category"]:
            row.label, row.category, row.is_active = r["label"], r["category"], True
            reactivated += 1

    # ── A3: rename surviving labels (code unchanged) ────────────────────────
    rename_codes = [code for code, _old, _new in RENAMES]
    by_code = {
        p.code: p
        for p in db.execute(select(Permission).where(Permission.code.in_(rename_codes))).scalars()
    }
    renamed = 0
    for code, _old, new_label in RENAMES:
        row = by_code.get(code)
        if row is not None and row.label != new_label:
            row.label = new_label
            renamed += 1

    db.commit() if commit else db.flush()
    return {
        "permissions_removed": permissions_removed,
        "group_rights_cascaded": rights_cascaded,
        "added": added,
        "reactivated": reactivated,
        "renamed": renamed,
    }


def revert_curation(db: Session, *, commit: bool = True) -> dict[str, int]:
    """Reverse :func:`apply_curation` (migration ``downgrade``).

    Removes the 44 added codes (cascading their group assignments), reverts the 4
    renames, and re-inserts the 210 removed catalog rows. The removed rows' prior
    *group assignments* are not restored — a data cull cannot resurrect which
    groups held them — so this is a best-effort catalog restore, not a full undo.

    ``commit`` as in :func:`apply_curation`.
    """
    added_ids = list(
        db.execute(select(Permission.id).where(Permission.code.in_(ADDED_CODES))).scalars()
    )
    added_removed = 0
    if added_ids:
        db.execute(delete(UserGroupRight).where(UserGroupRight.permission_id.in_(added_ids)))
        added_removed = db.execute(
            delete(Permission).where(Permission.id.in_(added_ids))
        ).rowcount or 0

    rename_codes = [code for code, _old, _new in RENAMES]
    by_code = {
        p.code: p
        for p in db.execute(select(Permission).where(Permission.code.in_(rename_codes))).scalars()
    }
    for code, old_label, _new in RENAMES:
        row = by_code.get(code)
        if row is not None:
            row.label = old_label

    already = set(
        db.execute(select(Permission.code).where(Permission.code.in_(REMOVED_CODES))).scalars()
    )
    restored = 0
    for code, label, category in REMOVED_ROWS:
        if code not in already:
            db.add(Permission(code=code, label=label, category=category, is_active=True))
            restored += 1

    db.commit() if commit else db.flush()
    return {"added_removed": added_removed, "removed_restored": restored}


__all__ = [
    "ADDED_CODES",
    "ADDED_RIGHTS",
    "CURATED_TOTAL",
    "REMOVED_CODES",
    "REMOVED_ROWS",
    "RENAMES",
    "apply_curation",
    "revert_curation",
]
