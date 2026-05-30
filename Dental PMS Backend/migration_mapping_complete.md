# Dental PMS — Complete Migration Mapping
**Source:** Denticon export (Excel Dental, PGID 2829)  
**Target:** Custom Dental PMS  
**Files scanned:** 82 source files across 6 subfolders  
**Schema tables:** 75 total (51 original + 24 additions + 3 infra not from source files)  
**Source-mapped tables:** 72 (your 81 source items → 72 unique tables after merging archives/duplicates)  
**Migration steps:** 52 (steps 1–47 original + steps 48–52 new)

---

## Source File Inventory

### Files WITH Data (migrate these)

| Source File / Folder | Records | Target Table(s) |
|---|---|---|
| `PGroup.txt` | 1 tenant | `tenants` |
| `Office.txt` | 12 offices | `offices` |
| `Providers.txt` | ~20 providers | `providers` |
| `Operatory.txt` | ~30 operatories | `operatories` |
| `RespParty.txt` | All patients/guarantors | `patients` |
| `PatInsPlans.txt` | Patient↔plan links | `patient_insurance` |
| `RespInsplan.txt` | Subscriber records | `insurance_subscribers` |
| `InsPlans.txt` | Insurance plans | `insurance_plans` |
| `Carrier.txt` | Insurance companies | `insurance_carriers` |
| `Employers.txt` | Employer companies | `employers` |
| `INSCOVERAGE/*.txt` (11 files) | Coverage rules per plan | `insurance_coverage_rules` |
| `FeeScheH.txt` | Fee schedule headers | `fee_schedules` |
| `FeeScheD.txt` | Fee amounts per code | `fee_schedule_entries` |
| `FeeScheA.txt` | Fee schedule assignments | *(reference only — used to resolve FEEIDs)* |
| `Codes.txt` | Procedure codes | `procedure_codes` |
| `ChartMaterials.txt` | Material types | `chart_materials` |
| `ChartNotesMacros.txt` | Note templates | `note_macros` |
| `CODESEXPLOSIONH.txt` | Code bundle headers | `code_bundles` |
| `CODESEXPLOSIOND.txt` | Code bundle items | `code_bundle_items` |
| `PGRX.txt` | Practice drug library | `prescription_library` |
| `AppointmentHeader.txt` | Active appointments | `appointments` |
| `APPTH_ARCHIVE/*.txt` (2 files) | Archived appointments | `appointments` (is_archived=true) |
| `AppointmentDetails.txt` | Active appt procedures | `appointment_procedures` |
| `AppointmentDetail_ARCHIVE.txt` | Archived appt procedures | `appointment_procedures` (is_archived=true) |
| `LEDGER/*.txt` (36 files, LTYPE=C) | Completed procedures | `patient_procedures` |
| `Ledger_archive.txt` (LTYPE=C) | Archived procedures | `patient_procedures` (is_archived=true) |
| `LEDGER/*.txt` (LTYPE=P/I/A) | Payments & adjustments | `patient_payments` |
| `Ledger_archive.txt` (LTYPE=P/I/A) | Archived payments | `patient_payments` (is_archived=true) |
| `LedgerInsDetail_Archive.txt` | Per-procedure ins detail | `ledger_insurance_details` |
| `LedgerPymtAllocation_Archive.txt` | Payment-to-proc links | `payment_allocations` |
| `CLAIMH/*.txt` (2 files) | Insurance claims | `insurance_claims` |
| `ClaimsDetail.txt` | EDI claim text/batches | `claim_submissions` |
| `ChartActivity.txt` | Tooth conditions/findings | `chart_conditions` |
| `ProgressNotes_Archive.txt` | Clinical notes | `progress_notes` |
| `PERIOCHARTHEADER.txt` | Perio exam headers | `perio_exams` |
| `PERIOCHARTDETAIL.txt` | Per-tooth measurements | `perio_exam_details` |
| `PatRx.txt` | Patient prescriptions | `prescriptions` |
| `PatFlashAlerts.txt` | Patient alerts | `patient_alerts` |
| `RESPNOTES.txt` | Account/billing notes | `account_notes` |
| `PATSIGNATURE.txt` | Digital signatures | `patient_signatures` |
| `PatMedicalHistoryH.txt` | Medical history headers | `medical_history_records` |
| `Referrals.txt` | Referral records | `referrals` |
| `SMS.txt` | SMS message history | `sms_messages` |
| `LETTERS.txt` | Letter templates | `letter_templates` |
| `POSTCARDS.txt` | Postcard templates | `postcard_templates` |
| `TCLOCK.txt` | Time clock entries | `time_clock_entries` |
| `DEFINITIONS.txt` | System reference codes | `definitions` |
| `IMAGETEMPLATE.txt` | Imaging templates | `imaging_templates` |
| `CHARTPERIOSETUP.txt` | Perio display settings | `perio_chart_settings` |
| `QALISTH.txt` | Questionnaire headers | `questionnaire_headers` |
| `QALISTD.txt` | Questionnaire options | `questionnaire_options` |
| `STATUSTRACK.txt` | Treatment status codes | `definitions` (group='STATUSTRACK') |
| `DEFINITIONSH.txt` | Definition group metadata | `definition_groups` |
| `CODESVIEW.txt` | Per-office code visibility | `codes_view` |
| `CHARTCOLORS.txt` | Chart color/pattern categories | `chart_colors` |
| `FeeScheA.txt` | Fee schedule assignments | `fee_schedule_assignments` |

### Files WITH Headers But NO DATA — Schema Created, Ready for Future Migration

All tables below have been created in `schema.sql`. When data becomes available (e.g. after
the practice starts using these features), run the corresponding migration step or INSERT directly.

| Source File | Target Table | Notes |
|---|---|---|
| `ChartPerioActivity.txt` | `perio_chart_activity` | Perio activity events |
| `COLAGENCY.txt` | `collection_agencies` | Collection agencies |
| `IMAGEDETAIL.txt` | `image_details` | X-ray/image file records |
| `IMAGEGROUP.txt` | `image_groups` | Patient imaging groups |
| `InsCustCoverage.txt` | `ins_custom_coverage` | Custom coverage overrides |
| `OGROUP.txt` | `office_groups` | Office groupings |
| `PatCariesRisk1340.txt` | `caries_risk_assessments` | ADA 1340 caries risk form |
| `PatContractBilling.txt` | `patient_payment_plans` | Patient in-house payment plans |
| `PatInsContractBilling.txt` | `patient_ins_payment_plans` | Insurance billing schedules |
| `PATORTHOPLAN.txt` | `ortho_plans` | Orthodontic payment plans |
| `PatRegPlan.txt` | `patient_reg_plans` | Patient regular/recall plans |
| `PATSECINSCONTRACTBILLING.txt` | `patient_sec_ins_payment_plans` | Secondary ins billing |
| `PROVIDERINSID.txt` | `provider_insurance_ids` | Provider IDs per carrier |
| `PROVIDERROUTESLIP.txt` | `provider_route_slips` | Route slip / superbill procedures |
| `REFERRALDEMOGD.txt` | `referral_demog_details` | Referral demographics responses |
| `REFERRALDEMOGH.txt` | `referral_demog_headers` | Referral demographics templates |

### Logical Entities — Schema Created, No Source Export File

These tables represent Denticon concepts that either had no dedicated export or whose
data is derivable from existing files. Schemas are in place for future use.

| Logical Name | Target Table | How to populate |
|---|---|---|
| `TREATPLAN` | `treatment_plans` | **Already populated** (derived from AppointmentDetails TREATPLANID) |
| `TREATPLAN_ARCHIVE` | `treatment_plans` (is_archived=true) | **Already populated** via APPTH_ARCHIVE |
| `TREATPLANINSD` | `treatment_plan_insurance_details` | Pre-auth estimates — enter when pre-auth workflow is built |
| `TREATPLANINSD_ARCHIVE` | `treatment_plan_insurance_details` (is_archived=true) | Same |
| `PATIENT` | `patients` | **Already populated** (RespParty.txt is the Denticon patient export) |
| `PATNOTES` | `patient_notes` | Clinical chart notes — enter going forward |
| `PATNOTES_ARCHIVE` | `patient_notes` (is_archived=true) | Archive of old notes |
| `PATRECALL` | `patient_recalls` | Recall scheduling — populate when recall feature is built |
| `PATMEDICALHISTORYD` | `medical_history_details` | Med history answers — enter when e-forms are built |
| `PROGRESSNOTES` | `progress_notes` | **Already populated** (ProgressNotes_Archive.txt) |
| `LEDGERINSD` | `ledger_insurance_details` | **Already populated** (LedgerInsDetail_Archive.txt) |
| `LEDGERPAYALLOC` | `payment_allocations` | **Already populated** (LedgerPymtAllocation_Archive.txt) |

---

## Migration Run Order

Run in this strict order (each step satisfies FKs for the next):

```
STEP  1: tenants                ← PGroup.txt
STEP  2: offices                ← Office.txt
STEP  3: providers              ← Providers.txt
STEP  4: operatories            ← Operatory.txt
STEP  5: employers              ← Employers.txt
STEP  6: insurance_carriers     ← Carrier.txt
STEP  7: insurance_plans        ← InsPlans.txt
STEP  8: insurance_coverage_rules ← INSCOVERAGE/*.txt (concat 11 files)
STEP  9: fee_schedules          ← FeeScheH.txt
STEP 10: procedure_codes        ← Codes.txt
STEP 11: fee_schedule_entries   ← FeeScheD.txt (needs procedure_codes + fee_schedules)
STEP 12: chart_materials        ← ChartMaterials.txt
STEP 13: note_macros            ← ChartNotesMacros.txt
STEP 14: code_bundles           ← CODESEXPLOSIONH.txt
STEP 15: code_bundle_items      ← CODESEXPLOSIOND.txt
STEP 16: prescription_library   ← PGRX.txt
STEP 17: patients               ← RespParty.txt
STEP 18: insurance_subscribers  ← RespInsplan.txt (needs patients + insurance_plans)
STEP 19: patient_insurance      ← PatInsPlans.txt (needs patients + insurance_subscribers)
STEP 20: patient_alerts         ← PatFlashAlerts.txt
STEP 21: account_notes          ← RESPNOTES.txt
STEP 22: patient_signatures     ← PATSIGNATURE.txt
STEP 23: medical_history_records ← PatMedicalHistoryH.txt
STEP 24: referrals              ← Referrals.txt
STEP 25: treatment_plans        ← Derived from AppointmentDetails (TREATPLANID != 0)
STEP 26: appointments           ← AppointmentHeader.txt + APPTH_ARCHIVE/*.txt
STEP 27: appointment_procedures ← AppointmentDetails.txt + AppointmentDetail_ARCHIVE.txt
STEP 28: patient_procedures     ← LEDGER/*.txt (LTYPE=C) + Ledger_archive.txt
STEP 29: patient_payments       ← LEDGER/*.txt (LTYPE=P/I/A) + Ledger_archive.txt
STEP 30: insurance_claims       ← CLAIMH/*.txt (concat 2 files)
STEP 31: claim_submissions      ← ClaimsDetail.txt
STEP 32: ledger_insurance_details ← LedgerInsDetail_Archive.txt
STEP 33: payment_allocations    ← LedgerPymtAllocation_Archive.txt
STEP 34: chart_conditions       ← ChartActivity.txt
STEP 35: progress_notes         ← ProgressNotes_Archive.txt
STEP 36: perio_exams            ← PERIOCHARTHEADER.txt
STEP 37: perio_exam_details     ← PERIOCHARTDETAIL.txt
STEP 38: prescriptions          ← PatRx.txt
STEP 39: sms_messages           ← SMS.txt
STEP 40: time_clock_entries     ← TCLOCK.txt
STEP 41: letter_templates       ← LETTERS.txt
STEP 42: postcard_templates     ← POSTCARDS.txt
STEP 43: definitions            ← DEFINITIONS.txt + STATUSTRACK.txt
STEP 44: imaging_templates      ← IMAGETEMPLATE.txt
STEP 45: perio_chart_settings   ← CHARTPERIOSETUP.txt
STEP 46: questionnaire_headers  ← QALISTH.txt
STEP 47: questionnaire_options     ← QALISTD.txt

─── New steps (complete source file coverage) ───────────────────────────────
STEP 48: chart_colors              ← CHARTCOLORS.txt            [HAS DATA]
STEP 49: codes_view                ← CODESVIEW.txt              [HAS DATA]
STEP 50: definition_groups         ← DEFINITIONSH.txt           [HAS DATA]
STEP 51: fee_schedule_assignments  ← FeeScheA.txt               [HAS DATA]
STEP 52: empty/stub verification   ← All header-only + logical  [SCHEMA ONLY]

Tables created but NOT migrated (empty source / logical entities — ready for future data):
  perio_chart_activity, collection_agencies, image_details, image_groups,
  ins_custom_coverage, office_groups, caries_risk_assessments,
  patient_payment_plans, patient_ins_payment_plans, patient_sec_ins_payment_plans,
  ortho_plans, patient_reg_plans, provider_insurance_ids, provider_route_slips,
  referral_demog_headers, referral_demog_details,
  patient_notes, patient_recalls, medical_history_details,
  treatment_plan_insurance_details
```

---

## Key Lookup Maps to Build in Python

Build these in-memory dicts at the start of migration — they let every subsequent step resolve IDs without DB queries:

```python
# After each step, build its lookup map:
tenant_map      = { pgid: db_id }                      # Step 1
office_map      = { oid: db_id }                        # Step 2
provider_map    = { providerid: db_id }                 # Step 3
operatory_map   = { operatoryid: db_id }                # Step 4
employer_map    = { empid: db_id }                      # Step 5
carrier_map     = { carrierid: db_id }                  # Step 6
ins_plan_map    = { insplanid: db_id }                  # Step 7
fee_sched_map   = { feeid: db_id }                      # Step 9
proc_code_set   = set(all codes in procedure_codes)     # Step 10
material_map    = { materialid: db_id }                 # Step 12
bundle_map      = { codesexplosionid: db_id }           # Step 14
patient_map     = { rpid: db_id }                       # Step 17
sub_map         = { respplanid: db_id }                 # Step 18
txplan_map      = { treatplanid: db_id }                # Step 25
appt_map        = { apptid: db_id }                     # Step 26
procedure_map   = { ledgerid: db_id }                   # Step 28
payment_map     = { ledgerid: db_id }                   # Step 29
claim_map       = { claimid: db_id }                    # Step 30
perio_exam_map  = { perioexamid: db_id }                # Step 36
```

---

## New Table Field Mappings (additions to previous mapping doc)

### insurance_subscribers ← `RespInsplan.txt`

| Source Field | Target Field | Notes |
|---|---|---|
| `RESPPLANID` | `legacy_id` | |
| `INSPLANID` | `ins_plan_id` | Lookup `ins_plan_map` |
| `RPID` | `subscriber_patient_id` | Lookup `patient_map` (the subscriber person) |
| `OID` | `office_id` | Lookup `office_map` |
| `SUBFNAME` | `sub_first_name` | |
| `SUBLNAME` | `sub_last_name` | |
| `SUBMI` | `sub_mi` | |
| `SUBADDRESS` | `sub_address` | |
| `SUBCITY` | `sub_city` | |
| `SUBSTATE` | `sub_state` | |
| `SUBZIP` | `sub_zip` | |
| `SUBBIRTHDATE` | `sub_dob` | Parse date, null if 1900 |
| `SEX` | `sub_gender` | `'M'`→`'Male'`, `'F'`→`'Female'` |
| `SUBSSN` | `sub_ssn` | Encrypt in app layer |
| `SUBID` | `sub_member_id` | Subscriber/member ID |
| `GROUPNO` | `group_number` | |
| `SUBPLANEFFDATE` | `effective_date` | |
| `SUBPLANTERMDATE` | `term_date` | |
| `FAMMAXREM` | `family_max_remaining` | |
| `FAMDEDREM` | `family_ded_remaining` | |
| `FAMORTHOREM` | `ortho_remaining` | |
| `ANNIVDATE` | `anniversary_date` | |
| `ELIGVERIFIED` | `elig_status` | `'U'`=unknown, `'Y'`=verified, `'N'`=not eligible |
| `ELIGVERIFIEDON` | `elig_verified_on` | |
| `ELIGVERIFIEDBY` | `elig_verified_by` | |
| `ELIGNOTES` | `elig_notes` | |
| `NOTES` | `notes` | |

### insurance_coverage_rules ← `INSCOVERAGE/*.txt`

Concat all 11 files. They share identical columns.

| Source Field | Target Field | Notes |
|---|---|---|
| `INSPLANID` | `ins_plan_id` | Lookup `ins_plan_map` |
| `INSCOVERAGEID` | `legacy_id` | |
| `STARTCODE` | `start_code` | ADA code range start |
| `ENDCODE` | `end_code` | ADA code range end |
| `INSCATEGORY` | `category` | Integer → text (see category map in previous doc) |
| `DESCR` | `description` | |
| `PCT` | `coverage_pct` | e.g. `100` = 100% covered |
| `DEDWAIVED` | `ded_waived` | `'1'`→true |
| `FREQLIMIT` | `freq_limit` | |
| `AGELIMIT` | `age_limit` | |
| `WAITPERIOD` | `wait_period` | |

### fee_schedules ← `FeeScheH.txt`

| Source Field | Target Field | Notes |
|---|---|---|
| `FEEID` | `legacy_id` | |
| `DESCR` | `name` | |
| `FEETYPE` | `fee_type` | `1`=UCR, `2`=assign-to-plan, `3`=assign-to-carrier |
| `INSPLANID` | `ins_plan_id` | Lookup |
| `OID` | `office_id` | Lookup |

### fee_schedule_entries ← `FeeScheD.txt`

| Source Field | Target Field | Notes |
|---|---|---|
| `FEEID` | `fee_schedule_id` | Lookup `fee_sched_map` |
| `CODE` | `procedure_code` | Skip if code not in `proc_code_set` |
| `PATAMT` | `patient_fee` | |
| `INSAMT` | `insurance_fee` | |
| `EFFECTIVEDATE` | `effective_date` | |

### chart_materials ← `ChartMaterials.txt`

| Source Field | Target Field |
|---|---|
| `MATERIALID` | `legacy_id` |
| `MATNAME` | `name` |
| `MATPATTERN` | `pattern` |
| `MATCOLOR` | `color` |

### note_macros ← `ChartNotesMacros.txt`

| Source Field | Target Field |
|---|---|
| `MACROID` | `legacy_id` |
| `MACRONAME` | `name` |
| `MACROVALUE` | `content` |
| `Macrocat` | `category` |

### code_bundles ← `CODESEXPLOSIONH.txt`

| Source Field | Target Field |
|---|---|
| `CODESEXPLOSIONID` | `legacy_id` |
| `CODE` | `display_code` |
| `DESCR` | `description` + `name` |
| `SAMETOOTHNO` | `same_tooth` | `'True'`→true |

### code_bundle_items ← `CODESEXPLOSIOND.txt`

| Source Field | Target Field |
|---|---|
| `CODESEXPLOSIONDID` | `legacy_id` |
| `CODESEXPLOSIONID` | `bundle_id` | Lookup `bundle_map` |
| `CODE` | `procedure_code` | |
| `TH` | `tooth` | |
| `SORTORDER` | `sort_order` | |

### prescription_library ← `PGRX.txt`

| Source Field | Target Field |
|---|---|
| `RXRefID` | `legacy_id` |
| `DrugName` | `drug_name` |
| `Dispense` | `dispense` |
| `Sig` | `sig` |
| `Refill` | `refills` |
| `IsAsWritten` | `is_as_written` | `'True'`→true |

### ledger_insurance_details ← `LedgerInsDetail_Archive.txt`

| Source Field | Target Field |
|---|---|
| `LEDGERID` | `legacy_ledger_id` |
| `PATID` | `patient_id` | Lookup `patient_map` |
| `CLAIMID` | `claim_id` | Lookup `claim_map` |
| `OID` | `office_id` | Lookup |
| `PRIMEST` | `prim_estimated` |
| `PRIMINDMAX` | `prim_ind_max` |
| `PRIMDED` | `prim_deductible` |
| `PRIMINSPAID` | `prim_ins_paid` |
| `PRIMINSADJUST` | `prim_ins_adjust` |
| `SECINSPAID` | `sec_ins_paid` |
| `SECINSADJUST` | `sec_ins_adjust` |
| `TERINSPAID` | `ter_ins_paid` |
| `PRIMINSPLANID` | `prim_ins_plan_id` | Lookup `ins_plan_map` |
| `SECINSPLANID` | `sec_ins_plan_id` | Lookup |
| `TERINSPLANID` | `ter_ins_plan_id` | Lookup |
| `PRIMINSPOSTED` | `prim_posted` | `'True'`→true |
| `SECINSPOSTED` | `sec_posted` | |

### payment_allocations ← `LedgerPymtAllocation_Archive.txt`

| Source Field | Target Field |
|---|---|
| `PAYALLOCID` | `legacy_id` |
| `PATID` | `patient_id` | Lookup |
| `PROCLEDGERID` | `procedure_id` | Lookup `procedure_map` |
| `PAYLEDGERID` | `payment_id` | Lookup `payment_map` |
| `CLAIMID` | `claim_id` | Lookup `claim_map` |
| `INSPLANID` | `ins_plan_id` | Lookup |
| `PROVIDERID` | `provider_id` | Lookup |
| `ALLOCDATE` | `alloc_date` | |
| `AMOUNT` | `amount` | |
| `LTYPE` | `alloc_type` | |

### claim_submissions ← `ClaimsDetail.txt`

| Source Field | Target Field |
|---|---|
| `CLAIMID` | `legacy_id` + `claim_id` | Lookup `claim_map` |
| `CLAIMBATCHID` | `batch_id` |
| `ISPREAUTH` | `is_preauth` | `'True'`→true |
| `TOTALCHARGES` | `total_charges` |
| `NUMLINES` | `num_lines` |
| `STATUS` | `submission_status` |
| `CLAIMTEXT` | `claim_text` | Raw EDI text |

### perio_exams ← `PERIOCHARTHEADER.txt`

| Source Field | Target Field |
|---|---|
| `PerioExamID` | `legacy_id` |
| `PATID` | `patient_id` | Lookup |
| `OID` | `office_id` | Lookup |
| `ACTDATE` | `exam_date` | |
| `NOTES` | `notes` | |
| `ISVOIDED` | `is_voided` | `'True'`→true |
| `CreatedBy` | `created_by` | Map username → user_id |

### perio_exam_details ← `PERIOCHARTDETAIL.txt`

| Source Field | Target Field |
|---|---|
| `PerioExamID` | `exam_id` | Lookup `perio_exam_map` |
| `TOOTHNO` | `tooth_no` | |
| `PD1`–`PD6` | `pd1`–`pd6` | Probing depths |
| `FGM1`–`FGM6` | `fgm1`–`fgm6` | Free gingival margin |
| `MGJ1`–`MGJ6` | `mgj1`–`mgj6` | Mucogingival junction |
| `Bleeding1`–`Bleeding6` | `bleed1`–`bleed6` | `'True'`→true |
| `Suppuration1`–`Suppuration6` | `supp1`–`supp6` | `'True'`→true |
| `Furcation1`–`Furcation6` | `furc1`–`furc6` | |
| `Mobility2` | `mobility_buccal` | |
| `Mobility5` | `mobility_lingual` | |

### account_notes ← `RESPNOTES.txt`

| Source Field | Target Field |
|---|---|
| `RESPNOTESID` | `legacy_id` |
| `RPID` | `patient_id` | Lookup `patient_map` |
| `NTYPE` | `note_type` | `'R'`=regular |
| `NOTES` | `notes` | |
| `STRIKEOFF` | `is_struck_off` | `'True'`→true |

### patient_signatures ← `PATSIGNATURE.txt`

| Source Field | Target Field |
|---|---|
| `SIGNATUREID` | `legacy_id` |
| `PATID` | `patient_id` | Lookup |
| `SIGNATURE` | `signature_data` | Large encoded string |
| `SIGNATURELEN` | `signature_len` | |
| `DEVICESOURCE` | `device_source` | |
| `ISUSER` | `is_user_sig` | `'True'`→true |

### sms_messages ← `SMS.txt`

| Source Field | Target Field |
|---|---|
| `SMSMSGID` | `legacy_id` |
| `OID` | `office_id` | Lookup |
| `PATID` | `patient_id` | Lookup |
| `APPTID` | `appointment_id` | Lookup `appt_map` (if non-zero) |
| `SENTTEXT` | `sent_text` | |
| `SENTPHONE` | `sent_phone` | |
| `SENTSTATUS` | `send_status` | |
| `SENDELIVERYON` | `delivered_on` | |
| `REPLYTEXT` | `reply_text` | |
| `REPLYPHONE` | `reply_phone` | |
| `REPLYRECEIVEDON` | `reply_received_on` | |
| `MESSAGETYPE` | `message_type` | |
| `ISREAD` | `is_read` | `'True'`→true |

### time_clock_entries ← `TCLOCK.txt`

| Source Field | Target Field |
|---|---|
| `TCLOCKID` | `legacy_id` |
| `USERID` | `user_id` | Map username string → users.id via `legacy_id` |
| `OID` | `office_id` | Lookup |
| `LIN` | `clock_in` | Parse datetime |
| `LOUT` | `clock_out` | Parse datetime; null if empty |
| `LTOTAL` | `total_hours` | Decimal hours |

### definitions ← `DEFINITIONS.txt` + `STATUSTRACK.txt`

| Source Field | Target Field |
|---|---|
| `DEFINITIONSID` | `legacy_id` |
| `DEFGROUP` | `group_code` |
| `DEFKEY1` | `key1` |
| `DEFKEY2` | `key2` |
| `DESCR` | `description` |
| `ISFLASHALERT` | `is_flash_alert` | `'True'`→true |
| `ISBLOCKCHARGES` | `blocks_charges` | `'True'`→true |
| For STATUSTRACK: `CODE` | `key1` | |
| For STATUSTRACK: `DESCR` | `description` | Group as `'STATUSTRACK'` |

### letter_templates ← `LETTERS.txt`

| Source Field | Target Field |
|---|---|
| `LETTERID` | `legacy_id` |
| `NAME` | `name` |
| `TYPE` | `letter_type` | `'A'`=appointment, `'R'`=recall, `'C'`=collection |
| `LType` | `channel` | `'L'`=letter, `'E'`=email |
| `TITLE` | `title` |
| `BODY` | `body_html` | HTML with #MERGE_FIELD# tokens |
| `Active` | `is_active` | `'Y'`→true |

### imaging_templates ← `IMAGETEMPLATE.txt`

| Source Field | Target Field |
|---|---|
| `TEMPLATEID` | `legacy_id` |
| `OID` | `office_id` | Lookup |
| `TEMPLATENAME` | `name` |
| `TEMPLATETYPE` | `template_type` |
| `DENTITION` | `dentition` | `'A'`=adult, `'P'`=pediatric |

### perio_chart_settings ← `CHARTPERIOSETUP.txt`

| Source Field | Target Field |
|---|---|
| `USERID` (string) | `user_id` | Map username → users.id |
| `ISFORWARD` | `is_forward` | `'True'`→true |
| `ISINDICATOR` | `is_indicator` | |
| `ISMGJ` | `is_mgj` | |
| `PDLEVEL` | `pd_level` | Int threshold |
| `BPLEVEL` | `bp_level` | |
| `IPLEVEL` | `ip_level` | |

---

## Common Transformation Rules

### File Parsing
```python
import csv
def read_denticon_file(path):
    with open(path, 'r', encoding='cp1252') as f:
        reader = csv.reader(f, delimiter='\t', quotechar='"')
        headers = next(reader)
        for row in reader:
            if not row or not row[0].strip():
                continue  # skip empty trailing rows
            yield dict(zip(headers, row))
```

### Multi-file Folders (concat all files)
```python
import os, glob
def read_folder(folder_path):
    for fpath in sorted(glob.glob(os.path.join(folder_path, '*.txt'))):
        yield from read_denticon_file(fpath)
```

### Date Parsing
```python
from datetime import datetime
PLACEHOLDER_DATES = {'01/01/1900', '01/01/1990'}
def parse_date(val):
    if not val or not val.strip():
        return None
    for fmt in ('%m/%d/%Y %H:%M:%S', '%m/%d/%Y'):
        try:
            d = datetime.strptime(val.strip(), fmt)
            if d.year == 1900 or d.year == 1990:
                return None
            return d
        except ValueError:
            continue
    return None
```

### Boolean Parsing
```python
def parse_bool(val):
    return str(val).strip().lower() == 'true'
```

### Ledger LTYPE Routing
```python
def route_ledger_row(row):
    ltype = row['LTYPE'].strip()
    is_void = parse_bool(row.get('ISVOID', 'False'))
    if ltype == 'C':
        return 'patient_procedures'
    elif ltype in ('P', 'I', 'A'):
        return 'patient_payments'
    else:
        return None  # skip unknown types
```

### Appointment Status Mapping
```python
APPT_STATUS_MAP = {
    '1': 'Scheduled', '2': 'Unconfirmed', '3': 'Confirmed',
    '4': 'Left Message', '5': 'In Reception', '6': 'Available',
    '7': 'In Operatory', '8': 'Checked Out', 'X': 'Checked Out',
}
def map_appt_status(row):
    if parse_bool(row.get('ISCANCELLED')):
        return 'Cancelled'
    if parse_bool(row.get('ISMISSED')):
        return 'Missed'
    code = row.get('APPTSTATUS', '').strip()
    return APPT_STATUS_MAP.get(code, 'Scheduled')
```

### Claim Status Mapping
```python
CLAIM_STATUS_MAP = {
    'S': 'submitted', 'P': 'pending', 'R': 'paid',
    'H': 'draft', 'D': 'denied', 'C': 'closed',
}
```

### Payment Method Mapping
```python
PAYMENT_METHOD_MAP = {
    'CA': 'cash', 'CK': 'check', 'CC': 'card',
    'EFT': 'ach', 'MC': 'card', 'VI': 'card',
    'AM': 'card', 'DS': 'card',
}
```

---

## Data Quirks to Handle

| Issue | Source | Fix |
|---|---|---|
| PATID=0 appointments | AppointmentHeader | Skip or store as `is_blocked=true` |
| Blocked calendar time | AppointmentHeader, ISBLOCKED='True' | `is_blocked=true`, no patient_id |
| LEDGER split 36 files | LEDGER/*.txt | Concat all, same columns |
| APPTH_ARCHIVE split 2 files | APPTH_ARCHIVE/*.txt | Concat, set `is_archived=true` |
| CLAIMH split 2 files | CLAIMH/*.txt | Concat both |
| INSCOVERAGE split 11 files | INSCOVERAGE/*.txt | Concat all |
| Staff username in USERID | TCLOCK, CHARTPERIOSETUP | Map string → users.id via legacy_id |
| BILLINGORDER has trailing spaces | LEDGER | `'D   '` → `'primary'`, `'S   '` → `'secondary'` (strip then map) |
| Encoded signature data | PATSIGNATURE | Store as-is in text field; don't try to decode |
| EDI claim text is raw X12 | ClaimsDetail | Store as-is in text field |
| Windows-1252 encoding | All files | `open(path, encoding='cp1252')` |
| Empty last row in files | All files | Skip rows where PGID is blank |
| PATSIGNATURE: 3 rows per patient | PATSIGNATURE | Multiple consent form signatures; create one row per SIGNATUREID |
| RespInsplan NOTES field | RespInsplan | Often contains "From Conversion Carrier: X" — clean up or store as notes |

---

## New Table Field Mappings (Steps 48–52)

### chart_colors ← `CHARTCOLORS.txt`

| Source Field | Target Field | Notes |
|---|---|---|
| `CATEGORYID` | `legacy_id` | |
| `PGID` | `tenant_id` | Lookup `tenant_map` |
| `CATTYPE` | `category_type` | Integer (1=condition, 2=treatment, etc.) |
| `CATNAME` | `name` | |
| `STROKECOLOR` | `stroke_color` | Color name string e.g. "Blue" |
| `FILLTYPE` | `fill_type` | |
| `FILLCOLOR` | `fill_color` | |
| `FILLCOLOR2` | `fill_color2` | Gradient second color |
| `FILLPATTERN` | `fill_pattern` | May contain whitespace padding |
| `GRADANGLE` | `gradient_angle` | |
| `GRADMETHOD` | `gradient_method` | |
| `CREATEDBY` | `created_by` | Username string |

### codes_view ← `CODESVIEW.txt`

| Source Field | Target Field | Notes |
|---|---|---|
| `PGID` | `tenant_id` | Lookup `tenant_map` |
| `OID` | `office_id` | Lookup `office_map` — skip if not found |
| `CODE` | `code` | FK to procedure_codes — skip if not in proc_code_set |
| `CREATEDBY` | `created_by` | Username string |

### definition_groups ← `DEFINITIONSH.txt`

| Source Field | Target Field | Notes |
|---|---|---|
| `DEFGROUP` | `group_code` + `legacy_id` | Primary identifier |
| `PGID` | `tenant_id` | Lookup |
| `DESCR` | `description` | Human-readable group name |
| `KEY1DESCR` | `key1_label` | What KEY1 means in this group |
| `KEY2DESCR` | `key2_label` | What KEY2 means (if applicable) |
| `ISEDITABLE` | `is_editable` | `'Y'`→true |
| `CANADD` | `can_add` | `'Y'`→true |
| `TYPE` | `group_type` | `'A'`=ADA category, `'B'`=basic lookup |

### fee_schedule_assignments ← `FeeScheA.txt`

| Source Field | Target Field | Notes |
|---|---|---|
| `FEESCHEDAID` | `legacy_id` | |
| `PGID` | `tenant_id` | Lookup `tenant_map` |
| `INSPLANID` | `ins_plan_id` | Lookup; `0`=no plan filter (global) |
| `CARRIERID` | `carrier_id` | Lookup; `0`=no carrier filter |
| `PROVIDERID` | `provider_id` | Lookup; `0`=all providers |
| `OID` | `office_id` | Lookup; `0`=all offices |
| `FEEID` | `fee_schedule_id` | Lookup `fee_sched_map` — required |
| `SPECIALTYID` | `specialty_id` | |
| `CREATEDBY` | `created_by` | |

---

## Complete Table Inventory (69 tables)

### Already in schema.sql (original 51 — the "45" in previous versions was wrong):
tenants, users, refresh_tokens, offices, providers, operatories, user_offices,
employers, insurance_carriers, insurance_plans, insurance_subscribers,
insurance_coverage_rules, fee_schedules, fee_schedule_entries,
procedure_codes, chart_materials, note_macros, code_bundles, code_bundle_items,
prescription_library, patients, patient_insurance, patient_alerts, account_notes,
patient_signatures, medical_history_records, referrals,
treatment_plans, treatment_plan_items,
appointments, appointment_procedures,
patient_procedures, chart_conditions, progress_notes,
perio_exams, perio_exam_details, prescriptions,
patient_payments, ledger_insurance_details, payment_allocations,
insurance_claims, claim_submissions,
sms_messages, letter_templates, postcard_templates,
time_clock_entries,
definitions, imaging_templates, perio_chart_settings,
questionnaire_headers, questionnaire_options

### Added in schema.sql Domain 11 (new 24):
fee_schedule_assignments, ins_custom_coverage, provider_insurance_ids,
patient_payment_plans, patient_ins_payment_plans, patient_sec_ins_payment_plans,
patient_reg_plans, ortho_plans, caries_risk_assessments,
patient_notes, patient_recalls, medical_history_details,
chart_colors, codes_view, provider_route_slips,
perio_chart_activity, treatment_plan_insurance_details,
referral_demog_headers, referral_demog_details,
definition_groups, image_groups, image_details,
office_groups, collection_agencies
