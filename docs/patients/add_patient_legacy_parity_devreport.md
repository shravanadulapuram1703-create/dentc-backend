# Add New Patient — Legacy-Parity Backend Gap Report (LEG-1 … LEG-16)

**Module:** Patients → Add New Patient
**Last updated:** 2026-07-26
**Frontend status:** complete; `npx tsc -b` clean, `npx eslint` clean, every screen
live-verified at `:5173` except the final save (blocked by §0).

---

## Scope & history

Raised after building the **full legacy Denticon registration wizard**, transcribed
from the legacy screens and option lists supplied by the product owner:

```
Patient Information
  → Responsible Party
  → one Insurance screen PER selected coverage type
      (Primary Dental → Secondary Dental → Primary Medical → Secondary Medical)
  → Medical Alerts
  → Dental + Medical Questionnaires
  → Recall Due Dates
  → Finish
```

**Prior rounds (for context, no action needed):**

| Report | Status |
|---|---|
| [`add_patient_backend_devreport.md`](add_patient_backend_devreport.md) — GAP-AP-1…18 | ✅ **all delivered** by the backend team |
| [`add_patient_backend_response.md`](add_patient_backend_response.md) — backend's reply | ✅ received; Orval re-synced and fully wired frontend-side |

Everything below is **new** — either required by the newly transcribed legacy
screens, or discovered while wiring the delivered endpoints.

### What the frontend already wired from the GAP-AP delivery

So the backend team can see their work is consumed end-to-end:

- All 11 new `PatientCreate` columns (`pronouns`, `driver_license`,
  `student_status`/`school_name`, `preferred_hygienist_id`, `fee_schedule_id`,
  `referred_to`/`referral_to_date`, `responsible_party_relationship`,
  `patient_types[]`, `assign_benefits`/`add_to_quickfill`/`no_correspondence`,
  `hipaa_sharing_notes`) — mapped on **save and read-back**.
- `POST /patients/register` composite — used by both **Finish** and **Quick Save**
  (Quick Save omits the later-step sub-sections).
- `patient-medical-alerts` and `patient-questionnaire-responses` — per-patient answers.
- `PUT /patients/{id}/opening-balance` — the five aging buckets.
- Chart-no auto-generation — frontend no longer sends a `chart_no`.
- `GET /fee-schedules` — replaced the old mock fee-schedule list (GAP-AP-5).

> ⚠️ **Regen side-effect (already fixed frontend-side, FYI only):** the Orval
> re-sync also changed two unrelated models — `TreatmentPlanItemCreateStatus`
> dropped `planned` (we now send `diagnosed`) and `ScheduleReplace` split into
> `AppSchemasOfficeSetupScheduleReplace`. Both broke the build until patched. If
> those were unintended, worth a look.

> 🔴 **READ §0 FIRST** — the patient write path currently 500s, so the final save
> cannot be verified.

---

## 0. BLOCKER — patient write path returns 500

| | |
|---|---|
| **Severity** | **Blocker** — no patient can be created at all |
| **Endpoints** | `POST /api/v1/patients` **and** `POST /api/v1/patients/register` |
| **Observed** | Both return `500 {"error":{"code":"internal_error","message":"An unexpected error occurred","details":null}}` |
| **Expected** | `201` with the created patient / `RegisterResponse` |

**Steps to reproduce** — `POST /api/v1/patients` with this minimal, schema-valid body:

```json
{
  "home_office_id": 1, "first_name": "Nina", "last_name": "Nulltypes",
  "dob": "1981-02-02", "gender": "F", "address_line1": "3 Null Ct",
  "preferred_provider_id": "PRV-103", "referral_type": "Online",
  "marital_status": "Single", "patient_type": "General", "patient_types": null
}
```

**Evidence it is server-side, not payload-side**

- Routes exist: `OPTIONS` → 200, unauthenticated → 401.
- It is a **500, not a 422** → the body passes Pydantic validation; an unhandled
  exception is thrown after validation.
- **Payload-independent:** reproduced with a minimal body, and with
  `patient_types` sent as `[]` *and* as `null`. No field combination avoids it.
- **It is a regression:** plain `POST /api/v1/patients` worked *before* the
  migration-`d5e6f7a8b9c0` redeploy — patients **83878, 83879, 83880, 83881** were
  created through this exact frontend path earlier the same day.

**Likely causes to check** — a column added by `d5e6f7a8b9c0` that is `NOT NULL`
without a server default; a type/serialization mismatch on the new `patient_types`
JSON column; the new server-side `chart_no` auto-generation in `PatientCRUD`
throwing; or app-model ↔ DB drift if the migration only partially applied.

**Ask:** pull the traceback for `POST /api/v1/patients` from the server logs — the
generic error envelope hides the real exception. Repro payload also saved at
[`register_500_repro.json`](register_500_repro.json).

---

## 1. Catalogs & questionnaire structure

### LEG-1 — MEDALERT / DENTQUEST / MEDQUEST catalogs are unseeded

- **Screens:** Medical Alerts, Dental Questionnaire, Medical Questionnaire.
- **Legacy behaviour:** ~90 medical alerts in three groups (*Allergic To*,
  *Check, if applicable*, *Other*), 28 dental questions, and a medical
  questionnaire with *Emergency Contact* / *Medical Questionnaire* / *Women Only*
  / *Additional Comments* sections.
- **Current:** the per-patient **answer** tables now exist (GAP-AP-16/17 ✔), but the
  **question/alert catalogs** live in `definition-groups` + `definitions`
  (`group_type` = `MEDALERT` / `DENTQUEST` / `MEDQUEST`) and are **empty** in this
  tenant. The one MEDALERT row present is a stray test record.
- **Frontend now:** ships the complete legacy catalog as the built-in default
  (`src/features/add-patient/legacyCatalogs.ts`) and *prefers* the tenant catalog
  when seeded, so the screens are fully usable today.
- **Ask:** seed the three catalogs from the legacy lists (a data migration), so
  answers key off tenant-managed codes rather than frontend constants.
- **Guard added (live-verified):** a tenant catalog only replaces the legacy list once
  it holds at least `MIN_TENANT_CATALOG_ITEMS` (10) entries. Without this the single
  stray MEDALERT row silently collapsed the Medical Alerts screen from **88 rows to
  1**. Seeding the catalogs properly clears the bar and takes over automatically.

### LEG-2 — Alert response has no tri-state / no "not asked" distinction

- **Legacy:** each alert row is **Y / N / blank** — blank means *not asked*, which is
  clinically different from an explicit *No*.
- **Current:** `PatientMedicalAlertCreate.response` is a free string. The frontend
  only POSTs rows the user actually answered, so "not asked" is encoded as *absent
  row* — workable, but it makes "answered No" vs "never asked" a client-side
  convention rather than a contract.
- **Ask:** constrain `response` to an enum `yes|no|unknown` and document that a
  missing row means *not asked* (or add an explicit `unknown`).

### LEG-3 — No emergency-contact resource

- **Legacy:** the Medical Questionnaire opens with a dedicated *Emergency Contact*
  block — name, phone, relationship to patient.
- **Current:** no `patient-emergency-contacts` resource (also raised in the earlier
  Patients audit). The wizard stores these three as **questionnaire answers**, which
  means they cannot be surfaced as structured emergency-contact data elsewhere.
- **Ask:** `GET/POST/PATCH/DELETE /api/v1/patient-emergency-contacts`
  `{patient_id, name, relationship, phone, is_primary?}`.

### LEG-4 — Questionnaire sections / ordering / input types are not modelled

- **Legacy:** questions are **grouped** (e.g. *Women Only*) and typed (Yes/No, text,
  date, free-text comment). Grouping drives the collapse/expand UI and the
  conditional "If Yes, …" follow-ups.
- **Current:** `PatientQuestionnaireResponseCreate` carries
  `{questionnaire_type, question_code, question_text, answer}` — no section, no sort
  order, no input type. The frontend supplies all three from its own catalog.
- **Ask:** on the *definition* side add `section`, `sort_order`, and `input_type`
  (`yesno|text|date|textarea`), so the questionnaire renders from backend metadata.

---

## 2. Insurance (one screen per selected coverage)

### LEG-5 — Cannot search insurance plans by Group #

- **Legacy:** *Search Insurance Plan* offers **Search For = Group #** and
  **Search In = All Insurance Plans / Account Plans**.
- **Current:** `listInsuranceCarriers` supports free-text `search` on the carrier;
  `listInsurancePlans` filters by `carrier_id`/`employer_id` but has **no
  `group_number` search** and no "plans already on this account" scope.
- **Frontend now:** exposes the Search-For selector but falls back to carrier-name
  search and labels the limitation inline.
- **Ask:** add `group_number` (and ideally `search`) to `ListInsurancePlansParams`,
  plus a `patient_id`/`account_id` scope for the legacy *Account Plans* option
  (needed for the dependent flow, where the plan is already on the account).

### LEG-6 — "Dentical Share of Cost" block has no backend

- **Legacy:** Month/Year, Share amount, Unused (current month) on the dental plan.
- **Current:** no columns on `insurance_plans` or `patient_insurance`.
- **Ask:** confirm whether this is still in scope; if so add
  `dentical_share_month`, `dentical_share_year`, `dentical_share_amount`,
  `dentical_unused` to `patient_insurance`.

### LEG-7 — Plan "Anni. Date Exp" not exposed

- **Legacy:** plan header shows an anniversary **expiry** alongside
  `anniversary_date`.
- **Current:** `InsurancePlanRead.anniversary_date` only.
- **Ask:** add `anniversary_expiry_date` to the plan, or document that expiry is
  derived.

> **Working today (no gap):** carrier search, plan pick, Group No., SubID,
> Patient-Relation-to-Subscriber, subscriber demographics, plan effective date,
> and the patient's individual deductible/max/ortho **remaining** amounts all
> persist via `insurance-subscribers` + `patient-insurance`. Plan-level maxima are
> correctly read-only from the plan record.

---

## 3. Recall

### LEG-8 — No `interval_type`, and no scheduled date/time on a recall

- **Legacy:** the *Add Recall Due Dates* grid is
  `Code · Int · Int. Type (Month/Year) · Recall Due Date · Sched Dt · Sched Time · Recall Reason`,
  pre-seeded with six rows (D0120/6mo, D0210/3yr, D0330/3yr, D1110/6mo, D1120/6mo,
  D4910/4mo).
- **Current:** `PatientRecallCreate` has `interval_months` only (no Month/Year unit)
  and **no scheduled-appointment date/time**.
- **Frontend now:** normalises Year → months (`3 Year` → `36`) and folds
  `Sched Dt/Time` into the recall `notes` string — lossy.
- **Ask:** add `interval_unit` (`month|year`) so the legacy value round-trips
  without conversion, and `scheduled_date` / `scheduled_time` (or a link to the
  created appointment). Also seed the six default recall types per office.

### LEG-9 — "Schedule Appt" from registration

- **Legacy:** the recall screen can book the appointment inline.
- **Current:** out of scope here — appointments are created from the Scheduler.
  Noted so the omission is deliberate, not an oversight.

---

## 4. Responsible Party (billing entity)

> GAP-AP-15 delivered the patient↔RP **relationship** + self-guarantor link, which
> the wizard uses. The remaining gaps are about the **guarantor as a billing
> entity** — everything on the legacy Step-2 screen other than the relationship.

### LEG-10 — No standalone (non-self) guarantor record

- **Legacy:** a non-self responsible party is a full billing entity: Title,
  Preferred Name, Last/First/MI, Address (2 lines), City/St/Zip, Email, Birth Date
  (+ Age), Marital Status, Sex, SSN, Drive Lic, Home/Cell/Work #.
- **Current:** `responsible_party_id` links an **already-existing** party; there is
  no endpoint to create one. The backend response explicitly flagged this as
  out-of-scope and asked us to confirm if needed — **we are confirming: it is
  needed.** Registering a child whose parent is not yet in the system is a core
  legacy flow (the "Add a Dependent" half of the supplied documentation).
- **Ask:** `POST /api/v1/responsible-parties` returning an id, with the fields
  above; or allow `POST /patients/register` to accept an inline
  `responsible_party.person {…}` and create + link it in the same transaction.

### LEG-11 — Billing behaviour flags live on the patient, not the guarantor

- **Legacy (per responsible party):** *Send Statements*, *No Email Statement*,
  *Send to Collection*, *Apply Finance Charge*, plus a **Coll Agency** selection.
- **Current:** `patients` has `send_statements`, `send_collections`,
  `is_finance_charge` — but these are **per patient**, and billing in the legacy
  model is **per account/guarantor**. There is no `collection_agency` field and no
  collection-agency lookup.
- **Ask:** move (or mirror) these four flags onto the responsible-party/account
  entity, and add a `collection_agencies` lookup + FK.

### LEG-12 — No custom statement message, financial notes, or RP notes

- **Legacy:** *Custom Statement Message* + "print on statement for **N** times",
  *Financial Notes*, *Responsible Party Notes* (all with Insert-Date-Stamp).
- **Current:** no columns anywhere.
- **Ask:** `statement_message`, `statement_message_print_count`,
  `financial_notes`, `responsible_party_notes` on the responsible-party entity.

### LEG-13 — `Resp. Party Type` code list is not backed by a lookup

- **Legacy:** a required *Resp. Party Type* radio list — `CA - Cash`,
  `CO - Collection`, `DI - Discount`, … (drives statement/collection behaviour).
- **Current:** no column and no `definitions` group. The frontend hardcodes the
  codes it can see in the legacy screenshot, which is certainly incomplete.
- **Ask:** a `RESP_PARTY_TYPE` definitions group (seeded with the full legacy list)
  **and** a `resp_party_type` column on the responsible-party entity. Please also
  send the authoritative code list.

### LEG-14 — Account membership ("Responsible for following Patients")

- **Legacy:** Step 2 lists every patient the guarantor is responsible for, with
  Age / Sex / Balance / Recall Date — the account roster.
- **Current:** no way to query "patients by responsible party" (no
  `responsible_party_id` filter on `GET /patients`), so the roster cannot be built.
- **Frontend now:** shows only the patient being registered.
- **Ask:** add `responsible_party_id` to `ListPatientsParams`, ideally with balance
  included, or an `/responsible-parties/{id}/patients` roster endpoint.

---

## 5. Dropdown data sources (found while fixing blank pickers)

Four Add-Patient dropdowns rendered blank. Three were **frontend bugs (now fixed
and live-verified)**; one is a **data gap** for the backend/data team.

| Dropdown | Cause | Status |
|---|---|---|
| Preferred Provider | loaders were chained inside one `try` after `await fetchPatientMetadata()` — a slow/failed definitions call left it empty forever; also listed hygienists | **Fixed** — loaders now run in parallel and settle independently; 77 dentists, labelled with title to disambiguate duplicate names |
| Preferred Hygienist | was populated with **all** providers | **Fixed** — filtered on `ProviderRead.role` (`/hygien/i`); 17 hygienists |
| Fee Schedule | queried with `office_id=<office>`, but schedules are **org-wide** (`fee_type` = carrier/plan/provider/ucr, `office_id` null) → `total: 0` | **Fixed** — office-scoped query first, falls back to the org-wide list; 38 schedules |
| Referred To | was hardcoded mock options ("Specialist A/B") | **Fixed** to query real referrals — but see LEG-15 below |

### LEG-15 — No "Referred To" referral records exist (data gap)

- **Screen:** Patient Information → Referral Information → *Referred To*.
- **Observed:** `GET /api/v1/referrals?referral_type=1` → `{"items":[],"meta":{"total":0}}`.
  The tenant holds **800+ referral rows but every one is `referral_type: "0"`**
  (*Referred By*) — and they are individual people (patients/friends), not practices.
- **Expected:** the practices/specialists the office refers patients **out** to, so
  the legacy *Referred To* picker has something to choose.
- **Frontend now:** queries `referral_type=1` **server-side** (was paging 800+ rows
  client-side just to fill one dropdown) and shows an explicit
  "No referral targets set up" instead of a silently blank control.
- **Ask:** seed / migrate the outbound referral practices with `referral_type = "1"`.
  If the legacy system models outbound targets somewhere other than the `referrals`
  table, tell us where and we will repoint the picker.

### LEG-16 — `PatientRead` carries no `home_office_name` (lookup cost)

- **Screen:** Patient Information → Office & Provider → *Office* (read-only).
- **Requirement:** the Office field must show the office chosen in the global nav —
  by **name**, not the internal key.
- **Current:** `PatientCreate`/`PatientRead` expose only `home_office_id`, so every
  screen that needs to *display* an office must separately `GET /offices?size=200`
  and map `id → name` (GlobalNav already does this; so did we).
- **Frontend now (fixed):** a shared `services/officeLookup.ts` resolves the
  canonical `OFF-{id}` key → `{id, name, short_id}` with a session cache, so the
  field renders "Excel Dental- Moon, PA [108]" and follows the nav selection. This
  is a **frontend fix, not a blocker** — logged only as a contract nicety.
- **Ask (low priority):** add `home_office_name` (and ideally `home_office_code`)
  to `PatientRead`, matching the existing lookup-gap note in the Patients audit.

---

## 6. Frontend defects found & fixed during this phase

Recorded so the backend team knows these were **not** backend problems:

| Defect | Root cause | Fix |
|---|---|---|
| Most UI fields silently not saved | `flattenPatientPayload` mapped ~30 of ~60 fields and dropped the rest **before** the request | Rewrote to map every column `PatientCreate` supports; proved live (`medicaid_id`, `patient_type` now persist) |
| DOB / recall dates off by one day | `new Date("YYYY-MM-DD")` parses as **UTC midnight**, then shifts back a day in negative-offset zones | Format plain dates from their parts in `overview/utils.ts` + `PatientOverview.fmtDate` |
| Medi ID never loaded on Edit | `EditPatientModal` read `patient.medi_id`; the column is `medicaid_id` | Read `medicaid_id` (legacy alias kept as fallback) |
| Provider / Fee Schedule / Hygienist dropdowns blank | loaders chained in one `try` after `await fetchPatientMetadata()` — one slow/failed call blanked them all | 5 independent loaders via `Promise.allSettled`, per-loader loading flags, explicit "Loading…" / "No X" states |
| Fee Schedule empty | queried `office_id=<office>`, but schedules are **org-wide** | office-scoped query first, falls back to org-wide |
| Hygienist listed everyone | picker used all providers | filtered on `ProviderRead.role` |
| Medical Alerts collapsed 88 → 1 row | one stray seeded MEDALERT row replaced the legacy catalog | `MIN_TENANT_CATALOG_ITEMS` guard (see LEG-1) |
| Office field stale / showed `OFF-1` | set once in the `useState` initializer, never re-synced; displayed the raw key | resolves the nav selection to the office **name** and re-runs when it changes |
| "No Coverage" not exclusive | coverage checkboxes were independent | No Coverage clears the four coverage types and vice-versa |

---

## Summary

| ID | Area | Severity | Blocks UI? |
|----|------|----------|-----------|
| **§0** | `POST /patients` + `/register` **500** | **Blocker** | **Yes — nothing can be saved** |
| LEG-1 | Seed alert/question catalogs | High | No (legacy defaults shipped) |
| LEG-2 | Alert response tri-state enum | Low | No |
| LEG-3 | Emergency-contact resource | Medium | Stored as questionnaire answers |
| LEG-4 | Question section/order/input-type | Medium | No (frontend catalog) |
| LEG-5 | Plan search by Group # + Account Plans | Medium | Yes (control disabled) |
| LEG-6 | Dentical Share of Cost | Low | Yes (omitted) |
| LEG-7 | Plan Anni. Date Exp | Low | Yes (omitted) |
| LEG-8 | Recall `interval_unit` + sched date/time | Medium | Lossy (folded into notes) |
| LEG-9 | Schedule Appt from recall | Low | Deliberately out of scope |
| LEG-10 | Non-self guarantor record | **High** | Yes — blocks the dependent flow |
| LEG-11 | Billing flags + collection agency on RP | High | Captured, not stored |
| LEG-12 | Statement message + financial/RP notes | Medium | Captured, not stored |
| LEG-13 | `Resp. Party Type` lookup + column | Medium | Hardcoded codes |
| LEG-14 | Patients-by-responsible-party roster | Medium | Roster shows 1 row |
| LEG-15 | No `referral_type="1"` (Referred To) records seeded | Medium | Picker shows an explicit empty state |
| LEG-16 | `home_office_name` missing on `PatientRead` | Low | No — resolved via `/offices` lookup |

### Suggested order of work

1. **§0 — fix the 500 on `POST /patients`.** Nothing else can be verified until a
   patient can be created. One traceback should explain it.
2. **LEG-10 → LEG-13 (Responsible Party).** These four are one coherent piece of
   work: a guarantor entity with its billing flags, collection agency, statement
   message/notes and a `resp_party_type` lookup. Together they unblock the legacy
   **"Add a Dependent"** workflow, which is currently impossible (a child whose
   parent is not already in the system cannot be registered).
3. **LEG-1 + LEG-15 — seeding.** Data-only: the MEDALERT / DENTQUEST / MEDQUEST
   catalogs and the outbound (`referral_type="1"`) referral practices. No schema work.
4. **LEG-5, LEG-8, LEG-3** — plan search by Group #/Account Plans, recall
   `interval_unit` + scheduled date/time, and an emergency-contact resource.
5. **LEG-2, LEG-4, LEG-6, LEG-7, LEG-14, LEG-16** — contract polish; each is
   currently degraded gracefully with an inline note in the UI.

### Non-functional note

The API instance on `:8000` is **slow to answer bursts of parallel requests** —
a cold Add-Patient load (~13 GETs: 9 definitions + providers + fee-schedules +
referrals + offices) takes roughly **60s** to settle, and login often takes
20–40s. The dropdowns show honest "Loading…" states throughout, so this is not a
correctness problem, but it makes the screen feel broken. Worth checking the
worker count / connection pool on the same instance that is currently 500ing.

---

## Appendix — where this lives in the frontend

| Area | Path |
|---|---|
| Wizard model, dynamic steps, request builders | `src/features/add-patient/wizardModel.ts` |
| Verbatim legacy catalogs (88 alerts, 29 + 22 questions, 6 recall rows, RP types) | `src/features/add-patient/legacyCatalogs.ts` |
| Step components | `src/features/add-patient/steps/*.tsx` |
| Stepper / shared step UI | `src/features/add-patient/WizardStepper.tsx`, `stepUi.tsx` |
| Host screen + Finish/Quick-Save orchestration | `src/components/pages/AddNewPatient.tsx` |
| Save/read mapping + `registerPatientResilient` | `src/services/patientApi.ts` |
| Fee schedules (real endpoint, org-wide fallback) | `src/api/feeSchedules.ts` |
| Office key → name resolver | `src/services/officeLookup.ts` |
| §0 repro payload | `docs/patients/register_500_repro.json` |

**Frontend status:** the entire wizard is built, type-checks (`npx tsc -b` clean) and
lints clean. Every gap above is either gracefully degraded with an inline notice or
captured-but-unstored, so nothing crashes. Once §0 is fixed we can live-verify the
whole flow end-to-end; LEG-10/11/12/13 are the highest-value follow-ups because they
unblock the legacy "Add a Dependent" workflow.
