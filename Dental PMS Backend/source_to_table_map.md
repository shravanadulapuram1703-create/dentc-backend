# Denticon → Dental PMS — Source-to-Table Map
**Total:** 75 tables (72 source-mapped + 3 infrastructure)  
**Source items:** 81 → 72 unique tables after merging archives/duplicates  
**Last updated:** 2026-05-30

---

## Merge rules applied (10 pairs → 1 table each)

| Source A | Source B | Merged into | Reason |
|---|---|---|---|
| AppointmentDetails | AppointmentDetail_ARCHIVE | `appointment_procedures` | archive |
| AppointmentHeader | APPTH_ARCHIVE | `appointments` | archive |
| DEFINITIONS | STATUSTRACK | `definitions` | same table, different group |
| PATNOTES | PATNOTES_ARCHIVE | `patient_notes` | archive |
| TREATPLAN | TREATPLAN_ARCHIVE | `treatment_plans` | archive |
| TREATPLANINSD | TREATPLANINSD_ARCHIVE | `treatment_plan_insurance_details` | archive |
| PATIENT | RespParty | `patients` | same data, different alias |
| PROGRESSNOTES | ProgressNotes_Archive | `progress_notes` | same data, different alias |
| LEDGERINSD | LedgerInsDetail_Archive | `ledger_insurance_details` | same data, different alias |
| LEDGERPAYALLOC | LedgerPymtAllocation_Archive | `payment_allocations` | same data, different alias |

## Split rule applied (1 source → 2 tables)

| Source | Table 1 | Table 2 | Split rule |
|---|---|---|---|
| LEDGER + Ledger_archive | `patient_procedures` | `patient_payments` | `LTYPE=C` → procedures; `LTYPE=P/I/A` → payments |

---

## All 72 Source-Mapped Tables

| # | Target Table | Source File(s) | Has Data | Migration Step | Notes |
|---|---|---|---|---|---|
| 1 | `appointment_procedures` | AppointmentDetails + AppointmentDetail_ARCHIVE | ✅ | s27 | ARCHIVE rows: is_archived=true |
| 2 | `appointments` | AppointmentHeader + APPTH_ARCHIVE | ✅ | s26 | ARCHIVE rows: is_archived=true |
| 3 | `insurance_carriers` | Carrier.txt | ✅ | s06 | |
| 4 | `chart_conditions` | ChartActivity.txt | ✅ | s34 | |
| 5 | `chart_colors` | CHARTCOLORS.txt | ✅ | s48 | Added in schema additions |
| 6 | `chart_materials` | ChartMaterials.txt | ✅ | s12 | |
| 7 | `note_macros` | ChartNotesMacros.txt | ✅ | s13 | |
| 8 | `perio_chart_activity` | ChartPerioActivity.txt | ❌ empty | s52 stub | Schema only — no data in export |
| 9 | `perio_chart_settings` | CHARTPERIOSETUP.txt | ✅ | s45 | USERID is username string → users.legacy_id |
| 10 | `claim_submissions` | ClaimsDetail.txt | ✅ | s31 | Raw EDI X12 text stored as-is |
| 11 | `procedure_codes` | Codes.txt | ✅ | s10 | PK is the code string itself |
| 12 | `code_bundle_items` | CODESEXPLOSIOND.txt | ✅ | s15 | |
| 13 | `code_bundles` | CODESEXPLOSIONH.txt | ✅ | s14 | |
| 14 | `codes_view` | CODESVIEW.txt | ✅ | s49 | Per-office code visibility |
| 15 | `collection_agencies` | COLAGENCY.txt | ❌ empty | s52 stub | Schema only |
| 16 | `definitions` | DEFINITIONS.txt + STATUSTRACK.txt | ✅ | s43 | STATUSTRACK gets group='STATUSTRACK' |
| 17 | `definition_groups` | DEFINITIONSH.txt | ✅ | s50 | Metadata about each definitions group |
| 18 | `employers` | Employers.txt | ✅ | s05 | |
| 19 | `fee_schedule_assignments` | FeeScheA.txt | ✅ | s51 | PROVIDERID/OID/INSPLANID=0 means no filter (global) |
| 20 | `fee_schedule_entries` | FeeScheD.txt | ✅ | s11 | Depends on procedure_codes + fee_schedules |
| 21 | `fee_schedules` | FeeScheH.txt | ✅ | s09 | |
| 22 | `image_details` | IMAGEDETAIL.txt | ❌ empty | s52 stub | Schema only |
| 23 | `image_groups` | IMAGEGROUP.txt | ❌ empty | s52 stub | Schema only |
| 24 | `imaging_templates` | IMAGETEMPLATE.txt | ✅ | s44 | |
| 25 | `ins_custom_coverage` | InsCustCoverage.txt | ❌ empty | s52 stub | Schema only |
| 26 | `insurance_plans` | InsPlans.txt | ✅ | s07 | |
| 27 | `ledger_insurance_details` | LedgerInsDetail_Archive.txt (= LEDGERINSD) | ✅ | s32 | |
| 28 | `payment_allocations` | LedgerPymtAllocation_Archive.txt (= LEDGERPAYALLOC) | ✅ | s33 | Links payments → procedures |
| 29 | `patient_procedures` | LEDGER/*.txt (LTYPE=C) + Ledger_archive.txt | ✅ | s28 | 36 split files; PK = "PROC-{LEDGERID}" |
| 30 | `patient_payments` | LEDGER/*.txt (LTYPE=P/I/A) + Ledger_archive.txt | ✅ | s29 | Same 36 files, different rows; PK = "PAY-{LEDGERID}" |
| 31 | `letter_templates` | LETTERS.txt | ✅ | s41 | HTML body with #MERGE_FIELD# tokens |
| 32 | `offices` | Office.txt | ✅ | s02 | 12 offices |
| 33 | `office_groups` | OGROUP.txt | ❌ empty | s52 stub | Schema only |
| 34 | `operatories` | Operatory.txt | ✅ | s04 | |
| 35 | `caries_risk_assessments` | PatCariesRisk1340.txt | ❌ empty | s52 stub | ADA 1340 form; schema only |
| 36 | `patient_payment_plans` | PatContractBilling.txt | ❌ empty | s52 stub | In-house patient payment plans; schema only |
| 37 | `patient_alerts` | PatFlashAlerts.txt | ✅ | s20 | Flash alerts shown on chart open |
| 38 | `patient_ins_payment_plans` | PatInsContractBilling.txt | ❌ empty | s52 stub | Insurance billing schedule; schema only |
| 39 | `patient_insurance` | PatInsPlans.txt | ✅ | s19 | Patient ↔ plan link + remaining benefits |
| 40 | `medical_history_records` | PatMedicalHistoryH.txt | ✅ | s23 | Header only; answers in medical_history_details |
| 41 | `ortho_plans` | PATORTHOPLAN.txt | ❌ empty | s52 stub | Full ortho + payment plan schema; no data |
| 42 | `patient_reg_plans` | PatRegPlan.txt | ❌ empty | s52 stub | Regular/recall payment plans; schema only |
| 43 | `prescriptions` | PatRx.txt | ✅ | s38 | Per-patient Rx; links to prescription_library |
| 44 | `patient_sec_ins_payment_plans` | PATSECINSCONTRACTBILLING.txt | ❌ empty | s52 stub | Secondary insurance billing; schema only |
| 45 | `patient_signatures` | PATSIGNATURE.txt | ✅ | s22 | Signature data stored encoded as-is |
| 46 | `perio_exam_details` | PERIOCHARTDETAIL.txt | ✅ | s37 | Per-tooth probing depths (6 points × 32 teeth) |
| 47 | `perio_exams` | PERIOCHARTHEADER.txt | ✅ | s36 | |
| 48 | `tenants` | PGroup.txt | ✅ | s01 | PGID=2829; 1 row |
| 49 | `prescription_library` | PGRX.txt | ✅ | s16 | Practice-level drug templates |
| 50 | `postcard_templates` | POSTCARDS.txt | ✅ | s42 | Recall/reminder postcards |
| 51 | `progress_notes` | ProgressNotes_Archive.txt (= PROGRESSNOTES) | ✅ | s35 | |
| 52 | `provider_insurance_ids` | PROVIDERINSID.txt | ❌ empty | s52 stub | Provider IDs per carrier; schema only |
| 53 | `provider_route_slips` | PROVIDERROUTESLIP.txt | ❌ empty | s52 stub | Route slip / superbill procedures; schema only |
| 54 | `providers` | Providers.txt | ✅ | s03 | ~20 providers; PK = "PRV-{PROVIDERID}" |
| 55 | `questionnaire_options` | QALISTD.txt | ✅ | s47 | Answer options per questionnaire |
| 56 | `questionnaire_headers` | QALISTH.txt | ✅ | s46 | |
| 57 | `referral_demog_details` | REFERRALDEMOGD.txt | ❌ empty | s52 stub | Schema only |
| 58 | `referral_demog_headers` | REFERRALDEMOGH.txt | ❌ empty | s52 stub | Schema only |
| 59 | `referrals` | Referrals.txt | ✅ | s24 | |
| 60 | `insurance_subscribers` | RespInsplan.txt | ✅ | s18 | Subscriber demographics + eligibility |
| 61 | `account_notes` | RESPNOTES.txt | ✅ | s21 | Account/billing notes on responsible party |
| 62 | `patients` | RespParty.txt (= PATIENT) | ✅ | s17 | Every RPID is a patient; batch commits every 500 |
| 63 | `sms_messages` | SMS.txt | ✅ | s39 | |
| 64 | `time_clock_entries` | TCLOCK.txt | ✅ | s40 | USERID is username string → users.legacy_id |
| 65 | `insurance_claims` | CLAIMH/*.txt (2 split files) | ✅ | s30 | PK = "CLM-{CLAIMID}" |
| 66 | `insurance_coverage_rules` | INSCOVERAGE/*.txt (11 split files) | ✅ | s08 | Coverage % per ADA code range per plan |
| 67 | `patient_notes` | PATNOTES + PATNOTES_ARCHIVE (no export file) | ❌ logical | s52 stub | Logical entity; no Denticon export |
| 68 | `patient_recalls` | PATRECALL (no export file) | ❌ logical | s52 stub | Logical entity; no Denticon export |
| 69 | `medical_history_details` | PATMEDICALHISTORYD (no export file) | ❌ logical | s52 stub | Med history answers; no Denticon export |
| 70 | `treatment_plans` | TREATPLAN + TREATPLAN_ARCHIVE (= AppointmentDetails TREATPLANID) | ✅ derived | s25 | Derived from AppointmentDetails rows with TREATPLANID≠0 |
| 71 | `treatment_plan_insurance_details` | TREATPLANINSD + TREATPLANINSD_ARCHIVE (no export file) | ❌ logical | s52 stub | Logical entity; pre-auth estimates |
| 72 | `treatment_plan_items` | Derived from AppointmentDetails (TREATPLANID≠0) | ✅ derived | s27 | Items created when appointment_procedures are inserted with a plan |

---

## +3 Infrastructure Tables (not from source files)

| # | Table | Purpose | Populated by |
|---|---|---|---|
| 73 | `users` | App login accounts | Derived from Providers.txt + manual setup |
| 74 | `refresh_tokens` | JWT auth token management | Application at runtime |
| 75 | `user_offices` | User ↔ office access control | Application at runtime |

---

## Step count explanation

| Category | Tables | Steps | Notes |
|---|---|---|---|
| Migrated with own step | 51 | 51 | Steps 1–54 (each step → 1 table, except LEDGER) |
| Empty source / logical entity | 20 | 1 shared | Step 55 (s52_empty_tables_stubs) verifies all 20 |
| App-only, no migration | 1 | 0 | refresh_tokens — created at runtime |
| **Total** | **72** | **55** | |

**Total steps: 55** (s01–s52, plus s03b, s03c, s27b inserted at positions 4, 5, 30)

## Data Status Summary

| Status | Count | Description |
|---|---|---|
| ✅ migrated | 51 | Has Denticon data; migration step exists (steps 1–54) |
| ❌ schema only (empty export) | 16 | Source file exists but had no rows; step 55 verifies schema |
| ❌ logical entity | 4 | No Denticon export file; schema ready for future data |
| ✅ derived | 2 | No direct source file; populated from another source during migration |
| infra (no migration ever) | 1 | refresh_tokens — app creates at login |
| infra (seeded) | 2 | users + user_offices — seeded from Providers.txt (steps 4–5) |

---

## Key ID Conventions

| Table | PK type | PK pattern | Why |
|---|---|---|---|
| tenants, offices, patients, employers, … | `SERIAL` (int) | Auto-assigned | Stable integer FKs |
| providers | `VARCHAR(50)` | `PRV-{PROVIDERID}` | Deterministic, safe re-run |
| operatories | `VARCHAR(50)` | `OPR-{OPERATORYID}` | Deterministic |
| appointments | `VARCHAR(50)` | `APPT-{APPTID}` | Deterministic |
| treatment_plans | `VARCHAR(50)` | `TP-{TREATPLANID}` | Deterministic |
| patient_procedures | `VARCHAR(50)` | `PROC-{LEDGERID}` | Deterministic |
| patient_payments | `VARCHAR(50)` | `PAY-{LEDGERID}` | Deterministic |
| insurance_claims | `VARCHAR(50)` | `CLM-{CLAIMID}` | Deterministic |

> All tables with `SERIAL` PKs use `ON CONFLICT (legacy_id) DO UPDATE` for idempotency.  
> All tables with `VARCHAR` PKs use the deterministic prefix above — `ON CONFLICT (id) DO NOTHING` is sufficient.

---

## Subfolder Source Files

| Subfolder | File count | Target table | Notes |
|---|---|---|---|
| `LEDGER/` | 36 files | `patient_procedures` + `patient_payments` | Same columns; concat all; route by LTYPE |
| `INSCOVERAGE/` | 11 files | `insurance_coverage_rules` | Same columns; concat all |
| `CLAIMH/` | 2 files | `insurance_claims` | Same columns; concat both |
| `APPTH_ARCHIVE/` | 2 files | `appointments` (is_archived=true) | Same columns as AppointmentHeader |
