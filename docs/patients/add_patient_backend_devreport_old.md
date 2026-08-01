# Add New Patient — Backend Gap Report

> Scope: the **Add New Patient** screen (`/patient/new`, `src/components/pages/AddNewPatient.tsx`)
> and its save path (`services/patientApi.ts` → `POST /api/v1/patients`). Produced from a live
> end-to-end validation on 2026-07-24 against the running stack (frontend `:5173`, backend
> `:8000`), creating real dummy patients **83878** and **83879**.
>
> This report lists **only the genuine backend gaps** — UI fields/features the frontend cannot
> persist or drive because the backend contract (`PatientCreate`/`PatientRead`, and the
> supporting resources) has no field or endpoint for them. Frontend-only defects found during
> the same pass were fixed in this branch and are summarised at the end.

---

## 0. How this was validated (repro harness)

1. Log in (`admin`/`admin`), select an office, open `/patient/new`.
2. Fill every section of the form, including fields suspected of being dropped
   (Medi ID, Pronouns, Driver License, Patient Type = Ortho, Rel. to Resp = Self).
3. Click **Quick Save** → `POST /api/v1/patients` → read the **201** response body (the
   canonical persisted record) and the follow-up `GET /api/v1/patients/{id}`.
4. Diff *entered* vs *persisted*.

Ground-truth persisted record for patient **83878** (before the frontend mapper fix) showed
`medicaid_id: null` and `patient_type: null` **even though** those columns exist on
`PatientCreate` — i.e. the values were dropped client-side. After the mapper fix, patient
**83879** persisted `medicaid_id: "MEDI-FIX-12345"` and `patient_type: "Ortho"`. Everything in
this report is the residue: fields with **no backend column/endpoint at all**.

`PatientCreate` (source of truth, generated Orval model) accepts:
`home_office_id, chart_no, first_name, last_name, preferred_name, title, middle_initial, dob,
gender, ssn, medicaid_id, marital_status, phone, cell_phone, work_phone, email,
preferred_contact, address_line1, address_line2, city, state, zip, preferred_provider_id,
preferred_language, first_visit, last_visit, next_recall, is_finance_charge, send_statements,
send_collections, no_auto_email, no_auto_sms, is_locked, hipaa_agreement, guardian_name,
guardian_phone, referral_type, referred_by, patient_notes, responsible_party_id, patient_type,
is_active`.

Every UI field **outside** that list is a gap below.

---

## GAP-AP-1 — Pronouns has no backend column

- **Module / Screen:** Patients → Add New Patient → "Additional Details"
- **Business requirement:** Store the patient's pronouns (He/Him, She/Her, They/Them, …).
- **Steps to reproduce:** Set Pronouns = "They/Them", Quick Save, `GET /patients/{id}`.
- **Expected:** response carries a `pronouns` value.
- **Actual:** response has **no `pronouns` field**; the value is discarded.
- **API / DB impact:** `PatientCreate`/`PatientRead` have no `pronouns` column. The pronoun
  `/definitions` group (`group_code=pronoun`) is seeded and drives the dropdown, but there is
  nowhere to store the selection.
- **Suggested backend change:** add nullable `pronouns` (string) to the patient model + create/
  update/read schemas.

---

## GAP-AP-2 — Driver License has no backend column

- **Screen:** Add New Patient → "Additional Identification" → Driver License
- **Repro:** Driver License = "DL-TEST-777", Quick Save, re-read.
- **Expected/Actual:** expected a persisted `driver_license`; **no such field** on the model —
  discarded (verified on 83878).
- **API/DB impact:** add nullable `driver_license` (string).

---

## GAP-AP-3 — Student status & School name have no backend columns

- **Screen:** Add New Patient → "Additional Identification" → Student (No/Part-time/Full-time) +
  School Name.
- **API/DB impact:** no `student_status` / `school_name` columns. Add nullable
  `student_status` (enum/string) and `school_name` (string). Relevant for dependents/full-time
  students on parents' insurance.

---

## GAP-AP-4 — Preferred Hygienist has no backend column

- **Screen:** Add New Patient → "Office & Provider" → Preferred Hygienist
- **Current:** `PatientCreate` has `preferred_provider_id` only. The UI collects a separate
  preferred **hygienist**, which is dropped.
- **API/DB impact:** add nullable `preferred_hygienist_id` (string, FK → providers), or document
  that hygienist preference is out of scope for the patient record.

---

## GAP-AP-5 — Patient-level Fee Schedule assignment: no column **and** phantom service

- **Screen:** Add New Patient → "Office & Provider" → Fee Schedule
- **Two problems:**
  1. **No persistence field.** `PatientCreate` has no `fee_schedule_id`; the selected schedule is
     dropped on save.
  2. **Phantom data source.** `src/api/feeSchedules.ts` fetches `GET {VITE_API_BASE_URL || 
     http://localhost:3000/api}/fee-schedules` — the wrong origin/prefix (backend is
     `:8000/api/v1`). The request always fails and the dropdown silently falls back to **7
     hardcoded mock schedules** (`FS-001`…`FS-007`, "CP-50"). Observed live: the dropdown lists
     fictional schedules that do not exist in the tenant.
- **Expected:** the Fee Schedule dropdown lists the tenant's real fee schedules
  (`GET /api/v1/fee-schedules`), and the chosen schedule is stored on the patient.
- **API/DB impact:** (a) add nullable `fee_schedule_id` to the patient model, **or** confirm fee
  schedule is derived from office/insurance and should be read-only here; (b) frontend must
  repoint `feeSchedules.ts` at the generated `/api/v1/fee-schedules` client (a separate
  frontend task — flagged, not yet done, to avoid touching the shared treatment-plan preview).

---

## GAP-AP-6 — Referral: "Referred To" and "Referral To Date" have no columns (+ fake options)

- **Screen:** Add New Patient → "Referral Information"
- **Current:** backend has `referral_type` + `referred_by` only (both persist correctly). The UI
  also collects **Referred To** and **Referral To Date**, which are dropped. Worse, the Referred
  To dropdown is populated with **hardcoded fake options** ("Specialist A", "Specialist B").
- **API/DB impact:** add nullable `referred_to` (string / FK → referrals) and `referral_to_date`
  (date); the dropdown should be backed by the `/api/v1/referrals` resource (referral_type
  code `"1"` = Referred-To), not literals.

---

## GAP-AP-7 — Responsible Party **relationship** cannot be stored on create

- **Screen:** Add New Patient → "Responsible Party Relationship" → Rel. to Resp
  (Self/Spouse/Parent/Guardian/Child/Other)
- **Current:** `PatientCreate` exposes `responsible_party_id` (a link to an existing RP) but **no
  relationship field**, and no way to *create* the responsible-party/billing record inline. Set
  "Rel. to Resp = Self" → persisted `responsible_party_id: null` (verified on 83878).
- **Legacy behaviour (Denticon):** "Responsible Party Payment/Billing Information" + "Responsible
  Party Type"; a self-responsible patient auto-populates the billing section.
- **API/DB impact:** add a way to set the RP relationship/type at create time — either a
  `responsible_party_relationship` field on the patient, or a `POST` that creates the RP record
  and links it (`{ patient_id, relationship, is_self, billing_* }`).

---

## GAP-AP-8 — Coverage-type selections are not persistable

- **Screen:** Add New Patient → "Coverage Type" (No Coverage / Primary Dental / Secondary Dental /
  Primary Medical / Secondary Medical)
- **Current:** these are workflow hints for which insurance slots to open (legacy uses them to
  branch into the insurance wizard). No backend field captures the intended coverage set, and the
  Add flow has no insurance step to consume them.
- **API/DB impact:** either (a) treat as transient UI state feeding an insurance sub-flow (then no
  backend needed), or (b) if a "coverage intent" must persist, add fields. Recommend (a) +
  wiring the existing `patient-insurance` screens into the add flow (see GAP-AP-13).

---

## GAP-AP-9 — Patient-type **multi-select** vs single `patient_type` string

- **Screen:** Add New Patient → right rail "Patient Type" (CH, CP, EF, OR, SN, SR, SS, UP — 8
  independent checkboxes) and the `patient_types[]` array in the payload.
- **Current:** backend stores a **single** `patient_type` string. The frontend currently collapses
  the checkboxes to `"Ortho"` (if OR) or `"General"` and sends that one value (now persisted
  after the mapper fix). All other selected types and multi-select combinations are lost.
- **API/DB impact:** to preserve the legacy multi-tag model, add a `patient_types` (string[] /
  join table) column, or a set of booleans (`is_child, is_collection_problem, is_employee_family,
  is_short_notice, is_senior, is_spanish_speaking, needs_update`). The `patient_type` `/definitions`
  group is already seeded with these codes.

---

## GAP-AP-10 — Status flags with no backend column

- **Screen:** Add New Patient → "Patient Status"
- **Fields with no column:** **Assign Benefits to Patient** (`assign_benefits`), **Add Patient to
  Quick-Fill List** (`add_to_quickfill`).
- **`No Correspondence`:** no dedicated column; the frontend now maps it (inverted) to the
  backend's `send_statements` as the closest semantic — but `send_collections` and true
  "suppress all correspondence" intent are not captured. A dedicated `no_correspondence` column
  is recommended.
- **API/DB impact:** add `assign_benefits` (bool), `add_to_quickfill` (bool), and ideally
  `no_correspondence` (bool). (`hipaa_agreement`, `no_auto_email`, `no_auto_sms`, `is_active`
  already persist.)

---

## GAP-AP-11 — HIPAA Information Sharing note has no column

- **Screen:** Add New Patient → "Notes" → HIPAA Information Sharing (separate from Patient Notes).
- **Current:** only `patient_notes` exists (persists). The second free-text "HIPAA Information
  Sharing" box is dropped.
- **API/DB impact:** add nullable `hipaa_sharing_notes` (text), or a typed patient-notes category.

---

## GAP-AP-12 — Starting Balances (opening A/R) cannot be recorded

- **Screen:** Add New Patient → "Starting Balances" (Current / Over 30 / 60 / 90 / 120)
- **Current:** no fields on `PatientCreate`; nothing is written. New patient always starts at
  `$0.00` (verified — 83878/83879 balance `$0.00`).
- **API/DB impact:** opening balances belong in the ledger, not the patient row. Provide an
  endpoint to seed opening A/R (e.g. `POST /api/v1/patients/{id}/opening-balance` with the 5
  aging buckets, or an adjustment/transaction with an "opening balance" type). Until then the
  aging inputs are non-functional and should arguably be hidden.

---

## GAP-AP-13 — No inline multi-step registration (legacy wizard parity)

- **Screen:** Add New Patient (single-page "Quick Save") vs legacy Denticon wizard.
- **Legacy flow (from "How to Add a Patient and a Dependent"):**
  Patient info + coverage → **Responsible Party / Billing** → **Primary Dental Insurance**
  (Search Insurance Plan → Select → SubID → Add Medical Information) → **Medical Alerts** (+
  Additional Comments, "No to all") → **Dental Questionnaire** + **Medical Questionnaire** →
  **Recall Information** (next-due dates) → **Finish** → Patient Overview. Plus **Add New Member**
  (dependent) with **Rel. to Resp** and an "Account Plans" insurance search that reuses the
  account's existing plans.
- **Current:** the Add screen collects patient demographics only; the "Responsible Party >>"
  button is an `alert("Future implementation")` stub, and there is no insurance / medical-alert /
  questionnaire / recall step in the create flow.
- **Backend status:** the *resources* mostly exist as standalone screens/endpoints
  (`patient-insurance`, insurance plans/carriers, `perio`/medical definitions, `patient-recalls`),
  but there is **no orchestration** and no single "register patient with insurance + alerts +
  questionnaire + recall" transaction. Medical **Alerts** and **Questionnaires** in particular
  have no dedicated backend resource (they are repurposed `definitions` today — see
  `docs/pick-list/pick_list_setup_backend_devreport.md` §3).
- **Suggested backend change:** either (a) document that registration is composed client-side by
  chaining the existing resources after patient create, and fill the missing ones (medical-alert
  and questionnaire *response* storage per patient, dependent linkage), or (b) provide a composite
  `POST /api/v1/patients/register` accepting patient + responsible-party + insurance + alerts +
  questionnaire + recall in one call.

---

## GAP-AP-14 — Chart number is not auto-generated on create

- **Screen:** Add New Patient (Chart No left blank).
- **Expected (per UI comment "Chart number is auto-generated if not provided"):** backend assigns
  a chart number.
- **Actual:** `POST /patients` with `chart_no: null` persists `chart_no: null`; the Overview falls
  back to displaying the numeric `id` as the chart number (verified — 83878/83879 show CHART # =
  ID).
- **API/DB impact:** either auto-generate `chart_no` server-side when omitted, or confirm chart
  numbers are intentionally optional and the frontend should stop implying auto-generation.

---

## GAP-AP-15 — Responsible Party create-with-relationship (wizard Step 2)

- **Screen:** Add Patient wizard → Step 2 "Responsible Party".
- **Business requirement:** at registration, set the Responsible Party **type** and the patient's
  **relationship** to them, and (for a non-self guarantor) create a billing record with name / DOB /
  SSN / address / phone / email / employer.
- **Current:** `PatientCreate` exposes only `responsible_party_id` (a link to an already-existing
  RP) — no relationship field and no endpoint to create the guarantor inline. The wizard collects
  the data and auto-links a self-responsible patient, but a non-self guarantor cannot be persisted.
- **Suggested backend change:** a responsible-party/guarantor resource
  (`POST /api/v1/responsible-parties {patient_id, relationship, is_self, first_name, last_name,
  dob, ssn, address…, employer}`) that returns an id to store on the patient, **or** a
  `responsible_party_relationship` + inline billing fields on the patient model.

---

## GAP-AP-16 — Per-patient Medical-Alert responses (wizard Step 4)

- **Screen:** Add Patient wizard → Step 4 "Medical Alerts".
- **Business requirement:** record each medical alert's Yes/No for the patient, plus free-text
  "Additional Comments" (legacy "No to all" convenience).
- **Current:** the MEDALERT catalog exists as Setup-only `definition-groups`/`definitions` (see
  `docs/pick-list/pick_list_setup_backend_devreport.md` §3). There is **no per-patient medical-alert
  response resource**, so the wizard's answers are not saved. (The catalog is also unseeded in this
  tenant, so the step falls back to a default alert list.)
- **Suggested backend change:** `GET/POST /api/v1/patient-medical-alerts
  {patient_id, alert_code, response('yes'/'no'), comments}` (or a JSON responses blob on the
  patient), plus seeding of the MEDALERT catalog.

---

## GAP-AP-17 — Per-patient Questionnaire responses (wizard Step 5)

- **Screen:** Add Patient wizard → Step 5 "Dental + Medical Questionnaire".
- **Business requirement:** store the patient's answers to the Dental and Medical questionnaires.
- **Current:** DENTQUEST/MEDQUEST are Setup-only definition catalogs (question *definitions*), with
  **no per-patient response store**. The wizard collects answers (defaulting the question list when
  the catalog is unseeded) but cannot persist them.
- **Suggested backend change:** `GET/POST /api/v1/patient-questionnaire-responses
  {patient_id, questionnaire_type('dental'/'medical'), question_code, answer}` (or a responses blob),
  plus seeding of the question catalogs.

---

## GAP-AP-18 — Composite "register patient" transaction (wizard Finish)

- **Screen:** Add Patient wizard → Finish.
- **Observation:** the wizard now composes registration client-side by chaining existing resources
  after the patient is created — `createPatientInsurance` + `createInsuranceSubscriber` (Step 3) and
  `createPatientRecall` (Step 6) both work and persist. The gapped steps (2/4/5 above) are collected
  but not saved. This means a partial failure mid-chain leaves a created patient with only some
  related records.
- **Suggested backend change (optional):** a single `POST /api/v1/patients/register` accepting
  `{patient, responsible_party, insurance[], medical_alerts, questionnaire_responses, recalls[]}`
  in one transaction, so registration is atomic. Until then the frontend chains calls best-effort
  and reports any per-item failures on Finish.

---

## Frontend defects fixed in this branch (not backend gaps)

These were client-side and are already resolved + live-verified:

1. **Silent field drop on save (root cause).** `flattenPatientPayload` in
   `services/patientApi.ts` mapped only a subset of fields, so backend-supported values were
   discarded before the request. Now maps **all** `PatientCreate`-supported fields — notably
   `medicaid_id` (UI "Medi ID"), `patient_type`, and `send_statements` (from "No Correspondence").
   Verified: patient 83879 persists `medicaid_id` and `patient_type`.
2. **Medi ID read-side name mismatch.** `EditPatientModal` loaded `patient.medi_id`; the backend
   column is `medicaid_id`. Fixed (reads `medicaid_id`), and `toPatientDetails` now surfaces
   `medicaid_id` + `patient_type`.
3. **DOB off-by-one on display.** `PatientOverview`/`PatientShellLayout` formatted `dob` via
   `new Date("YYYY-MM-DD")` → UTC-midnight → rendered one day earlier in negative-offset
   timezones (stored `1985-11-20` shown as `11/19/1985`). Both formatters now format date-only
   strings from their parts. Verified: shows `11/20/1985`.
