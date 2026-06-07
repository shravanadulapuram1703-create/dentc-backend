# Patients — Backend Dev Report (gaps & contract mismatches)

Gaps found during the Patients modernization audit where the frontend cannot be completed with the
existing `openapi.json` / generated Orval client. Format per project convention.

> Note: the bulk of the Patients module is **already covered** by existing endpoints (see
> [`patients_audit.md`](./patients_audit.md) §0). The items below are the genuine gaps.

---

## Missing API — Patient Documents

Module: Patients
Screen: Patient Documents (`/patient/:id/documents`, currently `PlaceholderPage`)
Business Requirement: Upload / list / download / delete patient documents (insurance cards, IDs,
consent forms, medical records).
Current Status: No suitable endpoint found in `openapi.json`. Only `patient-signatures` exists, which
is not generic document storage.
Suggested Endpoint: `GET/POST /api/v1/patient-documents`, `GET/DELETE /api/v1/patient-documents/{id}`,
plus a file-upload (multipart) path.
Expected Request Model: `{ patient_id, office_id, document_type, file (multipart), description? }`
Expected Response Model: `{ id, patient_id, document_type, file_name, content_type, size, url, created_at }`
Reason Required: Document management workflow has no backend.
Impact on Frontend: Documents screen cannot be implemented; remains a placeholder.

---

## Missing API — Emergency Contacts (separate entity)

Module: Patients
Screen: Registration / Profile — Emergency Contacts
Business Requirement: Store one or more emergency contacts (name, relationship, phone).
Current Status: Patient record only has inline `guardian_name`/`guardian_phone`. No
`patient-emergency-contacts` resource. `EditPatientModalRefactored` references `emergencyContact`/
`emergencyPhone` fields that do not exist on `PatientCreate/Update`.
Suggested Endpoint: `GET/POST/PATCH/DELETE /api/v1/patient-emergency-contacts`
Expected Request Model: `{ patient_id, name, relationship, phone }`
Expected Response Model: `{ id, patient_id, name, relationship, phone, created_at }`
Reason Required: Plan requires multiple emergency contacts; only a single guardian pair exists today.
Impact on Frontend: Emergency-contact sub-form maps to guardian fields only (single contact) unless added.

---

## Missing API — Advanced / field-specific patient search

Module: Patients
Screen: Patient Search (`Patient.tsx`)
Business Requirement: Search by exact SSN, Medicaid ID, DOB, preferred provider, insurance carrier,
patient status, registration date; distinguish patient vs. responsible-party; filter by office group;
filter by patient type (general/ortho).
Current Status: `ListPatientsParams` supports only free-text `search`, exact `chart_no`, single
`home_office_id`, and `is_active`. The UI exposes ~16 `searchBy` options + `searchFor` + `patientType`
+ office-group scope that have no backend mapping.
Suggested Endpoint: extend `GET /api/v1/patients` params: `dob`, `ssn`, `medicaid_id`, `email`,
`phone`, `preferred_provider_id`, `ins_plan_id`, `patient_type`/`is_ortho`, `responsible_party_id`,
`office_group_id`, plus `order`/pagination already present.
Expected Request Model: query params as above.
Expected Response Model: existing `PaginatedResponsePatientRead`.
Reason Required: Field-specific lookups and advanced filters are core to the search screen.
Impact on Frontend: Most search controls are non-functional; will be removed or disabled until added.

---

## Contract mismatch — Patient balances shape (RESOLVED frontend-side)

Module: Patients
Screen: Patient Ledger → Balances tab (`PatientLedger.tsx`)
Observed (live, 2026-06-05): `GET /api/v1/patients/{id}/balances` (plural) → **404**. The real
endpoint is `GET /api/v1/patients/{id}/balance` (singular, generated `getPatientBalance`), returning
`PatientBalance` with `aging{current,b30,b60,b90,b120}` and `recent_activity{today, last_ins,
last_pat}` (last-payment **dates only**, no amounts).
Fix (shipped): `ledgerApi.getPatientBalances` now wraps the generated `getPatientBalance` and adapts
`PatientBalance` → the ledger UI shape (aging b30→age_30 …; recent activity shows today's payments +
last-payment dates). The "Today's Charges" cell was relabeled "Today's Payments" (the backend field is
today's payments, not charges) and the last-payment **amount** rows were dropped (not in the contract).
Remaining backend asks: add `insurance_balance`, today's **charges**, and last-payment **amounts** to
`PatientBalance` if the UI should show them.

---

## Missing API — patient-scoped ledger writes (phantom endpoints)

Module: Patients
Screen: Patient Ledger / PaymentsAdjustments / ClaimDetail
Observed (live, 2026-06-05): `services/ledgerApi.ts` targets a patient-scoped ledger surface that
**does not exist** — all 404:
`GET /patients/{id}/balances`, `POST /patients/{id}/payments`, `POST /patients/{id}/adjustments`,
`/patients/{id}/procedures`, `/patients/{id}/claims`, and the metadata codes
`/metadata/payment-codes`, `/metadata/adjustment-codes`. Also `GET /patient-adjustments` → **404**
(no adjustments resource at all).
What DOES exist (generated client): `/patients/{id}/ledger` ✓, `/patients/{id}/balance` ✓,
`patient-payments` ✓, `insurance-claims` ✓, `patient-procedures` ✓.
Suggested: either implement the patient-scoped ledger routes `ledgerApi` assumes, OR (frontend will)
migrate payments→`patient-payments`, claims→`insurance-claims`, procedures→`patient-procedures`, and
provide an **adjustments** resource + payment/adjustment **code** lookups (none exist today).
Impact on Frontend: Add Payment / Add Adjustment / claim create/detail in `PaymentsAdjustments` and
`ClaimDetail` are non-functional against these phantom paths; payments/claims can be re-pointed at the
generated endpoints, but **adjustments and code lookups are hard-blocked** until a backend exists.

---

## Contract mismatch — Claim endpoints (patient-scoped vs org-scoped)

Module: Patients
Screen: Claim Detail (`ClaimDetail.tsx`), Ledger “create claim”
Business Requirement: Create a claim from selected procedures, load claim detail, update notes,
delete/close, submit e-claim, refresh status.
Current Status: `ledgerApi` calls patient-scoped routes (`/patients/{id}/claims…`) that **404**. The
generated `insurance-claims` resource exists (200, and `InsuranceClaimRead` does carry `patient_id`),
**but it is a flat claim record** — `id, claim_number, status, claim_type, billing_order,
date_of_service_from/to, total_billed, total_paid, est_insurance, …provider_ids, carrier_id,
ins_plan_id, notes`. It has **none** of the composed detail `ClaimDetail.tsx` renders: no
`procedures[]`, `coverage_info`, `patient_info`, `payment_info`, or `attachments[]`. So the rich
claim-detail screen cannot be backed by `insurance-claims` without a composed claim-detail endpoint —
re-pointing it would render an empty UI. Save/delete/close/validate/e-claim/update-status remain
`alert()` stubs.
Suggested Endpoint: either (a) add patient-scoped claim routes returning a claim-detail shape with a
`procedures[]` breakdown and coverage/payment info, or (b) document that the frontend must use
`insurance-claims` + a procedures join, and provide claim lifecycle actions
(`/insurance-claims/{id}/validate|submit|status|close`).
Expected Request/Response Model: claim with `procedures[]`, `amounts`, `coverage_info`, `payment_info`,
`status`, `claim_type`.
Reason Required: Claim detail screen has no working persistence.
Impact on Frontend: Claim actions remain stubs until routes/shapes are reconciled.

---

## Missing API — Claim clearinghouse operations & attachments

Module: Patients
Screen: Claim Detail
Business Requirement: Validate claim with clearinghouse, submit e-claim, refresh status,
manage claim attachments, record insurance payment against a claim.
Current Status: No endpoints; all are `alert()` stubs.
Suggested Endpoint: `POST /api/v1/insurance-claims/{id}/validate|submit|status`,
`GET/POST/DELETE /api/v1/insurance-claims/{id}/attachments`, insurance-payment-entry endpoint.
Expected Request/Response Model: clearinghouse status payloads; attachment metadata.
Reason Required: Claims lifecycle cannot be completed.
Impact on Frontend: Claim action bar stays non-functional.

---

## Missing API — Progress Notes (clinical) feature set

Module: Patients
Screen: Progress Notes (`ProgressNotesListing.tsx`, `AddEditProgressNote.tsx`)
Business Requirement: List/create/edit progress notes with tooth/surface/region categorization,
note macros, attachments, linked procedures, and a sign (re-auth) workflow with `signed_by`.
Current Status: Confirm whether a progress-note endpoint exists in the clinical module. If it maps to
a single `notes`/`tooth` field, it lacks: `signed_by`/`signature_date`, structured
tooth/surface/region, macro management, attachments, linked-procedure associations, and a
“struck-off” state distinct from `is_deleted`.
Suggested Endpoint: progress-note CRUD with the fields above, a `POST .../sign`, and a macros endpoint.
Expected Request/Response Model: `{ patient_id, office_id, note_date, notes, tooth[], surface,
region, signed_by, signed_at, is_struck_off, attachments[] }`.
Reason Required: UI feature set exceeds current schema.
Impact on Frontend: Progress Notes can only partially persist; advanced features blocked.

---

## Missing API — Patient Note audit author + attachments

Module: Patients
Screen: Add/Edit Patient Note
Business Requirement: Show created-by / last-modified-by user names; attach documents to a note.
Current Status: `PatientNoteRead` has `created_at`/`updated_at` but no `updated_by` (and
`created_by` is numeric id, not a display name). No note-attachment fields.
Suggested Endpoint: include `created_by_name`/`updated_by`/`updated_by_name`; note-attachment support.
Reason Required: Audit panel currently hardcodes author/date.
Impact on Frontend: Audit fields shown from `created_at`/`created_by` only; “modified by” unavailable.

---

## Missing API — patient duplicate-check (phantom endpoint)

Module: Patients
Screen: Add New Patient → "Check Patient"
Observed (live, 2026-06-05): `/api/v1/patients/check-duplicate` **does not exist**. `POST` → 405
(`Allow: GET`); any `GET` is swallowed by `/api/v1/patients/{item_id}` and 422s with
`int_parsing` on `item_id` (it tries to parse "check-duplicate" as the id). So the original
`patient.service.checkDuplicatePatient` (raw-axios `POST`) was **dead on arrival** here.
Frontend workaround (shipped): `checkDuplicatePatient` now composes duplicate detection client-side
via the generated `listPatients` (free-text search by name, then exact last/first-name + DOB match).
This works but is heuristic.
Suggested Endpoint: a real `POST /api/v1/patients/check-duplicate` (or `GET` with query params)
returning candidate matches with a match score.
Impact on Frontend: works today via the `listPatients` heuristic; a dedicated endpoint would be more
precise (e.g., fuzzy/soundex matching, match scores).

---

## Out-of-spec endpoints (exist at runtime, not in Orval)

- `GET /api/v1/patients/metadata` (+ sub-endpoints: titles, pronouns, states, genders, marital
  statuses, referral types…) — used by `patientMetadataApi.ts` via raw axios; not in the generated
  client (so it must stay raw axios). Add to spec, or confirm these are intentionally outside Orval.

---

## Missing capability — Patient row/record print

Module: Patients
Screen: Patient Listing (and profile)
Business Requirement: Print a patient summary / record from the search results.
Current Status: No print view or backend export exists; the old `Print` button was an `alert()` stub
and was removed from the list during the rewrite.
Suggested: a printable patient-summary view (frontend) and/or a backend export endpoint
(`GET /api/v1/patients/{id}/summary.pdf`).
Impact on Frontend: Print deferred until a print view/export exists.

---

## Contract behavior — `listPatientNotes` returns soft-deleted notes

Module: Patients
Screen: Patient Notes
Observed (live, 2026-06-05): `DELETE /api/v1/patient-notes/{id}` soft-deletes (sets
`is_deleted=true`, returns 204), but `GET /api/v1/patient-notes?patient_id=…` still returns those
rows, and `ListPatientNotesParams` exposes no `is_deleted`/`is_archived` filter. The frontend
currently filters `is_deleted` client-side.
Suggested: add `is_deleted`/`is_archived` query params (default exclude deleted), or have the list
endpoint exclude soft-deleted rows by default.
Impact on Frontend: without client-side filtering, deleted notes would keep appearing.

---

## Lookup gaps for the list/profile composition

- No `home_office_name` on `PatientRead` (must resolve via `listOffices`).
- No next-appointment / insurance-summary / balance embedded on `PatientRead` — must compose from
  `listAppointments` / `listPatientInsurance` / `getPatientBalance`, or prefer `getPatientContext`
  which already aggregates balance + insurance + visit info.
