# Patients Module — Functional Audit & Fix Plan

_Generated from a screen-by-screen audit of the Patients module against `openapi.json`, the
generated Orval client (`src/api/generated/**`), and the migrated schema. This is the working
reference for the Patients modernization phase._

## 0. Executive summary

The **backend is rich and largely complete**. The generated Orval client already exposes 16+
working endpoint groups for patients:

| Capability | Generated endpoints |
| --- | --- |
| Patient CRUD | `listPatients`, `getPatient`, `createPatient`, `updatePatient`, `deletePatient` |
| Aggregated context | `getPatientContext` (`/patients/{id}/context`) |
| Balance / Ledger | `getPatientBalance` (`/patients/{id}/balance`), `getPatientLedger` (`/patients/{id}/ledger`) |
| Insurance | `listPatientInsurance`, `get/create/update/deletePatientInsurance` |
| Notes | `listPatientNotes`, `get/create/update/deletePatientNote` |
| Alerts | `listPatientAlerts`, `get/create/update/deletePatientAlert` |
| Recalls | `listPatientRecalls`, `get/create/update/deletePatientRecall` |
| Signatures | `listPatientSignatures`, `get/create/update/deletePatientSignature` |
| Payments / Plans | `listPatientPayments`, `listPatientPaymentPlans`, `…InsPaymentPlans`, `…SecInsPaymentPlans`, `…RegPlans` |
| Procedures | `listPatientProcedures` … (clinical module) |
| Medical history | `listMedicalHistoryRecords` / `…Details` |
| Referrals | `listReferrals` … |

**Therefore most work is wiring the existing UI to endpoints that already exist**, not building new
backend. The recurring problems are:

1. **Entire screens running on mock data** — Patient Notes & Progress Notes are 100% mocked despite
   full backend CRUD support.
2. **`alert()` stubs** standing in for real workflows — Add/Edit/Print on the list, claim actions,
   payments/adjustments, add-member, insurance-status, sign-note.
3. **camelCase on API-facing data** — local `Patient`/`PatientFormData`/`PatientNote`/overview
   `types.ts` interfaces diverge from the snake_case generated models (violates project convention).
4. **Hardcoded display values** — `$0.00` aging, `Modified By: UDAFIX`, age `32`, `NICOLASM`,
   `Specialist A/B`, masked-SSN placeholder, empty insurance/balance/office columns.
5. **Redundant / divergent data fetching** — `getPatientContext` exists but is never used; shell and
   overview each fetch the patient separately; some services use raw axios instead of the client.

Genuine backend gaps are catalogued in [`patients_backend_devreport.md`](./patients_backend_devreport.md).

---

## 1. Patient Listing & Search — `src/components/pages/Patient.tsx`

> **✅ DONE (2026-06-05).** Rewritten to bind directly to `PatientRead` (snake_case; removed the local
> camelCase `Patient` interface + `convertApiPatientToDisplay` mapper). Now uses
> `useListPatients(params)` with **server-side pagination** (page/size, pager UI) — essential since a
> single office returned 7,781 patients. `useListOffices` resolves office names without per-row calls.
> **Add New Patient** routes to `/patient/new`; **Overview** opens `/patient/:id/overview`. SSN is masked
> (last 4). Loading/error/empty states from the query. Removed the dead controls (`searchFor`
> patient/responsible, `patientType` general/ortho, office-group scope, and the 14 misleading
> field-specific `searchBy` options) — `ListPatientsParams` only supports `search`, `chart_no`,
> `home_office_id`, `is_active`, `preferred_provider_id`, `sort`/`order`. Search is now honest:
> free-text (name/email/phone) or exact Chart #, office scope (current/all), include-inactive, and
> A→Z/Z→A sort. Dropped the empty composed columns (insurance/next-appt/balance) — those live on the
> profile. **Last Search** restores + re-runs the previous committed search. All params live-verified
> against the backend. Edit-from-list and Print were removed (edit lives on the profile; print has no
> backend) — see devreport.

**Status (original): partially working, many dead controls.**

| Workflow | Status | Notes |
| --- | --- | --- |
| Basic text search | ✅ working | `listPatients({ search })` free-text ILIKE over name/chart_no/email/phone |
| Chart # search | ✅ working | exact `chart_no` filter |
| Include Inactive | ✅ working | `is_active` param |
| Current-office scope | ⚠️ partial | only `current` maps to `home_office_id`; `all`/`group` ignored |
| `searchBy` field choices | ⚠️ partial | 14 of 16 options collapse to generic `search`; SSN/Medicaid/DOB/phone exact lookups non-functional |
| `searchFor` (patient/responsible) | ❌ broken | UI-only, never sent |
| `patientType` (general/ortho) | ❌ broken | UI-only, never sent |
| Pagination | ❌ missing | hardcoded `page:1, size:100`, no pager UI |
| Last Search | ❌ broken | `lastSearchQuery` is a display string, never reconstructed into params |
| Add New Patient | ❌ stub | `handleAddNewPatient` → `alert()` (should route to `/patient/new`) |
| Edit | ❌ stub | `handleEdit` → `alert()` |
| Print | ❌ stub | `handlePrint` → `alert()` |

**Defects**
- Local **camelCase `Patient` interface** (`firstName`, `lastName`, `officeId`, `chartNumber`,
  `emergencyContact`…) + `convertApiPatientToDisplay` mapper — convention violation; bind to
  `PatientRead` snake_case instead.
- Placeholder columns hardcoded empty: `insurance`, `nextAppointment`, `balance`, `officeName`.
- SSN placeholder `***-**-****`; if backend returns SSN it is shown unmasked.

**Fix direction:** rebind to `PatientRead`; route Add→`/patient/new`, Edit→`/patient/:id/...`;
add pagination; either remove non-functional search controls or gate them behind documented backend
gaps; resolve office name via `listOffices`, balance via `getPatientBalance`, insurance via
`listPatientInsurance` (or prefer `getPatientContext`).

---

## 2. Patient Profile / Overview shell

Files: `PatientShellLayout.tsx`, `patient/overview/*`, `PatientContextHeader.tsx`, `PatientSecondaryNav.tsx`.

> **✅ Largely DONE (2026-06-05).**
> - **Deleted dead `PatientContextHeader.tsx`** (hardcoded `age=34`/`sex='M'`/office) — it had no active
>   importer.
> - **Removed the 5 unused mock generators** (`getMockDentalInsurance/AccountMembers/Appointments/
>   Recalls/BalanceData`) from `overview/utils.ts`.
> - **Wired real data** into `PatientOverview` (all live-verified): **balances** via `useGetPatientBalance`
>   → `PatientBalance` (account balance, estimates, last-payment dates), **appointments** via
>   `useListAppointments`, **recalls** via `useListPatientRecalls`. These share React Query cache keys
>   with the shell, so no extra requests. Removed the fabricated `$0.00` per-appointment aging (now `—`,
>   since aging is account-level, not per-appointment) and the hardcoded member-balance cells.
> - **Finding:** `getPatientContext` is a *lightweight* nav endpoint (patient + balance dict + insurance
>   *summary* + visit) — it does **not** carry account members, appointments, recalls, or detailed
>   insurance, so it can't replace the overview's per-resource composition. Wiring the real endpoints (as
>   above) is the correct backend-driven approach. `getPatientByChartNo` **is** defined — the audit's
>   "ReferenceError" was a false positive.
> - **Insurance card now shows real data (2026-06-05):** the overview `InsuranceCard` was showing "—"
>   for carrier/group/phone/subscriber because those live on the plan/carrier/subscriber, not the
>   patient-insurance link record. `PatientOverview` now loads `listPatientInsurance` and resolves each
>   record by id — `getInsurancePlan(ins_plan_id)` → `getInsuranceCarrier(plan.carrier_id)` and
>   `getInsuranceSubscriber(subscriber_id)` — to fill carrier name/phone, group, subscriber, and the
>   remaining amounts (which are on the record). **Resolution is by-id, not a size-200 list**, because the
>   reference tables are large (e.g. plan id 11667). `InsuranceCard` was rewritten to render dental
>   primary/secondary + real **medical** consistently via a shared plan renderer. Category =
>   `legacy_plan_type` ("D"/"M"); order = `insurance_type` ("primary"/"secondary"). Live-verified.
> - **Remaining:** the demographic mapper (`mapPatientToViewModel`) still expects a nested
>   `PatientDetails` shape and uses camelCase view types (`overview/types.ts`); account-members has no
>   backend endpoint (gap); the responsible-party edit affordance is inert; `PatientOverview` still calls
>   the imperative `getPatientDetails` for identity+insurance (not React-Query-deduped with the shell);
>   insurance is read-only here (add/update/remove + eligibility verification not yet built).

**Status (original): functional but architecturally redundant.**

- Shell loads patient via `useGetPatient` + parallel `getPatientBalance`/`listOffices`/
  `listAppointments`/`listPatientAlerts`. Overview **separately** calls legacy
  `getPatientDetails()` → another `getPatient`. **`getPatientContext` exists and is never used.**
- Hardcoded `$0.00` for appointment aging (`current/over30/…/estPat/estIns`).
- `alert()` stubs: add account member, insurance-status click, Imaging, Print, Search Responsible Party.
- `PatientContextHeader` hardcodes `age=34, sex='M', office='Cranberry Dental Arts [108]'`.
- camelCase API-bound interfaces throughout `overview/types.ts` and `PatientShellLayout` (`chartNo`,
  `officeId`, `cellPhone`, `carrierName`, `est_*`…).

**Fix direction:** consolidate on `getPatientContext` for the aggregated panel; pass real
patient props into `PatientContextHeader`; source aging from balance/ledger; rename API-bound types
to snake_case; wire or formally defer the stubs.

---

## 3. Add / Edit Patient

Files: `pages/AddNewPatient.tsx`, `modals/EditPatientModal.tsx`, `modals/EditPatientModalRefactored.tsx`, `modals/patient/*`.

**Status: the production path WORKS; a parallel refactor scaffold is dead/mock.**

- ✅ `AddNewPatient` → `createPatientFull` → `createPatient` (Orval). Validations for sex/address/
  provider/referral present. Duplicate check via `checkDuplicatePatient`.
- ✅ `EditPatientModal` → `getPatientDetails` + `updatePatientFull` → `updatePatient` (Orval).
- ❌ **`EditPatientModalRefactored.tsx`** — hardcoded `INITIAL_FORM_DATA` (Nicolas Miller…), and
  `handleSave()` **never calls the API**. Decide: delete or finish. (Verify it is unreferenced.)
- ⚠️ `getPatientByChartNo` is referenced in `patientApi.ts:getPatientDetails` — **verify it is
  defined/imported** (audit flagged a possible ReferenceError).
- Hardcoded: age `32` (`PatientIdentitySection`), `Modified By: UDAFIX` (`PatientHeader`),
  `Specialist A/B` referral options, header `PGID/OID`.
- Delete patient = stub; `deletePatient` (Orval) unused.
- camelCase form keys in `modals/patient/types.ts` and `PatientFormData` (flattened before send, so
  functionally OK, but flag per convention).
- `alert()` for success/validation/errors — replace with toast/inline.

---

## 4. Patient Notes & Progress Notes — **entirely mocked (critical)**

Files: `patient/PatientNotesListing.tsx`, `AddEditPatientNote.tsx`, `ProgressNotesListing.tsx`, `AddEditProgressNote.tsx`.

> **✅ Patient Notes DONE (2026-06-05).** `PatientNotesListing` + `AddEditPatientNote` are now fully
> backend-driven: list via `useListPatientNotes({ patient_id })`, create via `useCreatePatientNote`,
> edit via `useUpdatePatientNote`, delete via `useDeletePatientNote`, with loading/error/empty states
> and React Query invalidation. Removed mock array, `setTimeout` saves, hardcoded `NICOLASM`/dates,
> the system-note concept (no backend flag), and hardcoded RP/insurance summary. Audit panel now shows
> real `created_by`/`created_at`/`updated_at`. Document note types keep their UI but show a "storage
> pending backend" notice (file/sub-type not persisted). **Live-verified** end-to-end against the
> running backend (list→create→edit→delete); discovered the soft-delete list behavior (now filtered
> client-side, logged in the devreport).
> **Progress Notes remain pending** — blocked on backend (signature, tooth/surface, macros,
> attachments); see devreport.

**Status: no backend integration at all — despite full backend CRUD existing.**

- `PatientNotesListing` renders `mockPatientNotes`; delete only `console.log`s.
- `AddEditPatientNote` save = `setTimeout` + `console.log` (no `createPatientNote`/`updatePatientNote`).
- `ProgressNotesListing` renders `mockProgressNotes`; edit blocked by `alert()`.
- `AddEditProgressNote` save = simulated; sign = `alert()`; macros = `mockMacros`.
- Audit fields hardcoded (`created_by: NICOLASM`, fixed dates), `Last Visit`/`Active Treatment` hardcoded.
- camelCase note interfaces diverge from `PatientNoteRead/Create/Update`.

**Fix direction (high value, self-contained):** wire **Patient Notes** to
`listPatientNotes/createPatientNote/updatePatientNote/deletePatientNote`, mapping snake_case fields
(`patient_id`, `office_id`, `note_date`, `note_type`, `notes`, `notes_html`, `is_archived`,
`is_deleted`, `created_at`). Use auth context for the author. **Progress Notes** depend on a backend
progress-note endpoint + signature/tooth-surface/macro support — confirm availability before wiring;
otherwise document as gaps.

---

## 5. Ledger / Claims / Insurance

Files: `pages/PatientLedger.tsx`, `patient/ClaimDetail.tsx`, `patient/PaymentsAdjustments.tsx`, `services/ledgerApi.ts`.

> **✅ Balances tab fixed (2026-06-05).** Probed the backend live: the entire patient-scoped ledger
> surface `ledgerApi` assumes is **phantom** — `/patients/{id}/balances` (plural), `/payments`,
> `/adjustments`, `/procedures`, `/claims`, and `/metadata/{payment,adjustment}-codes` all **404**;
> `patient-adjustments` 404 too. Only `/ledger` and `/balance` (singular) exist. Reimplemented
> `ledgerApi.getPatientBalances` to wrap the generated `getPatientBalance` and adapt `PatientBalance`
> (`aging.b30…`, `recent_activity.today/last_ins/last_pat`) → the ledger UI shape; relabeled "Today's
> Charges" → "Today's Payments" and dropped the last-payment **amount** rows (not in the contract).
> The Balances tab now loads (200) instead of 404. See devreport for the phantom-surface catalogue.
>
> **✅ Add Payment wired (2026-06-05).** `PaymentsAdjustments` "Apply" now records a real payment via the
> generated `createPatientPayment` (`patient-payments`) — client-supplied UUID `id` (required by the
> contract), real `patient_id`/`office_id`, `payment_date`, `amount`, `payment_type:'patient'`,
> `payment_method`, `check_number`, `notes` — with a saving state, and refreshes the ledger/balances on
> success (new `office`/`onApplied` props from `PatientLedger`). Removed the mock outstanding-procedure
> rows (no allocation endpoint). **Payment create live-verified** end-to-end (create→list→delete).
> **Backend-blocked (documented):** Add Adjustment (no `/adjustments` nor `patient-adjustments`),
> payment/adjustment **code** lookups (`/metadata/*-codes` 404), and per-procedure payment allocation —
> the adjustments "Apply" now shows an honest "no backend" message.
> **Claims:** `insurance-claims` exists but is a **flat** record (no `procedures[]`/`coverage`/`payment`/
> `attachments`), so `ClaimDetail`'s rich view can't be backed without a composed claim-detail endpoint
> — left as a documented gap (see devreport).

**Status (original): ledger reads work; claims/payments are stubbed; insurance unwired.**

- ✅ Ledger entries via `getPatientLedger`.
- ⚠️ **Balances tab**: `ledgerApi.getPatientBalances` expects a `BalancesResponse` (aging buckets,
  recent activity) but Orval `getPatientBalance` returns `PatientBalance` — **field-shape mismatch,
  likely runtime breakage**. Verify and reconcile to the real `PatientBalance` shape.
- ❌ `ClaimDetail` — `save/validate/attachments/insurance-payment/delete/close/eclaim/update-status`
  are all `alert()` stubs.
- ⚠️ `ledgerApi.createClaim`/`getClaim` use patient-scoped routes that don't match Orval's
  org-scoped `insurance-claims` endpoints — reconcile route + schema.
- ❌ `PaymentsAdjustments` — hardcoded payment/adjustment code lists; apply handlers `alert()` only.
- ❌ Insurance routes are `PlaceholderPage` stubs; `listPatientInsurance` exists but is unused in the ledger.
- camelCase interface fields (`estPat`, `hasNotes`, `insPayD`, `reasonCo`, `writeOff1`…).

---

## 6. Services / Types / Metadata

Files: `services/patient.service.ts`, `patientApi.ts`, `patientMetadataApi.ts`, `types/patient.ts`.

> **✅ DONE (2026-06-05).**
> - **Removed dead raw-axios code** from `patientApi.ts`: `getPatients()` (unused; used wrong
>   `limit`/`offset` params), `deletePatient()` (unused), the `PatientListResponse` type, the unused
>   `extractOfficeId` helper, and the now-unneeded `api` (raw axios) import. `patientApi.ts` is now
>   100% generated-client.
> - **Reimplemented `checkDuplicatePatient`** (`patient.service.ts`) to compose via the generated
>   `listPatients` (search + client-side last/first-name + DOB match) instead of the **phantom**
>   `POST /patients/check-duplicate` endpoint (which 405s — it doesn't exist). Removed the raw axios,
>   the hardcoded `status: 'Active'`, and the fabricated empty fields; `status` now reflects real
>   `is_active`. **Live-verified** (positive match + negative DOB). See devreport.
> - **camelCase `Patient` DTO layer removed (2026-06-05):** deleted the camelCase `Patient`,
>   `PatientCreateRequest`, `PatientUpdateRequest` interfaces + the `toPatient` mapper + the dead
>   `getPatientById` and simple `createPatient`/`updatePatient` wrappers from `patientApi.ts`. The two
>   consumers (`AddEditAppointmentForm`, `NewAppointmentModal`) now call the generated
>   `createPatient(PatientCreate)` with snake_case bodies; `getPatientByChartNo` now returns
>   `PatientRead`. Patient create **live-verified** with the new body shape. `patientApi.ts` no longer
>   re-declares any API model in camelCase.
> - **Still deferred (large form rename):** the nested `PatientCreateRequestFull`/`PatientUpdateRequestFull`
>   types + the `flattenPatientPayload` mapper + the `AddNewPatient`/`EditPatientModal` camelCase form
>   state, and the (now frontend-internal) `DuplicatePatient`/`CheckDuplicatePayload`. These belong to a
>   single AddNewPatient/EditPatientModal form-layer rename; doing them piecemeal would leave that file
>   in mixed casing. Flag before doing (per CLAUDE.md). `patientMetadataApi.ts` stays raw axios
>   (`/patients/metadata` out-of-spec).

- ✅ Create/Read/Update wrap the Orval client correctly.
- ⚠️ `getPatients()` and `deletePatient()` use **raw axios** instead of `listPatients`/`deletePatient`.
- ⚠️ `patient.service.ts` `checkDuplicatePatient` uses raw axios + **camelCase payload**
  (`firstName/lastName/office`) and hardcodes `status: 'Active'` + empty `officeShortId/email/provider`.
- ⚠️ camelCase `Patient`/`DuplicatePatient`/`CheckDuplicatePayload` interfaces (convention).
- `check-duplicate` and `/patients/metadata*` are **not in the generated client** (not in OpenAPI, or
  out-of-spec) — see backend devreport.

---

## 7. Validation checklist (target state)

- [x] **Listing**: grid loads, pagination works, search params all functional or formally deferred
- [x] **Search**: backend-driven; no client-side filtering of large sets
- [ ] **Registration**: create persists via `createPatient`; duplicate check; required-field validation
- [x] **Profile**: real balance/appointments/recalls wired; mock generators + dead header removed _(demographic mapper modernization remains)_
- [ ] **Updates**: demographic/contact/insurance/status persist via `updatePatient`/insurance endpoints
- [x] **Notes**: list/create/edit/delete via `*PatientNote` endpoints; real author/audit fields _(Patient Notes done; Progress Notes pending backend)_
- [ ] **Insurance**: add/update/remove via `*PatientInsurance`; primary/secondary panels live
- [x] **Ledger/Balances**: balances tab now uses real `getPatientBalance` _(payments/adjustments/claims remain; adjustments + codes backend-blocked)_
- [ ] **Documents**: pending backend (see devreport)
- [ ] **Scheduler integration**: appointments shown from appointments API; schedule/reschedule links
- [ ] **No camelCase on API data**; **no mock/hardcoded business data**

---

## 8. Recommended execution order

1. **Patient Notes** — wire to existing CRUD (high impact, self-contained, backend-ready).
2. **Listing & Search** — snake_case rebind, route Add/Edit, pagination, real columns.
3. **Profile/Overview** — consolidate on `getPatientContext`, kill duplicate fetch & hardcoded header.
4. **Services cleanup** — raw-axios → Orval; snake_case the duplicate-check payload/types.
5. **Ledger/Balances** — reconcile `PatientBalance` shape; wire payments/adjustments.
6. **Claims** — reconcile routes; wire or formally defer clearinghouse actions.
7. **Insurance panels**, **Documents**, **Progress Notes** — pending backend confirmation/gaps.
