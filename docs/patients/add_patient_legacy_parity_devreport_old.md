# Add New Patient — Legacy-Parity Backend Gap Report (LEG-1 … LEG-14)

> **Scope.** Raised after building the full legacy Denticon registration wizard
> (Patient Information → Responsible Party → *one insurance screen per selected
> coverage type* → Medical Alerts → Dental + Medical Questionnaires → Recall Due
> Dates → Finish), transcribed from the legacy screens supplied by the product
> owner.
>
> **Prior reports** — [`add_patient_backend_devreport.md`](add_patient_backend_devreport.md)
> (GAP-AP-1…18, all **delivered**, see [`add_patient_backend_response.md`](add_patient_backend_response.md)).
> This report covers only what the *newly transcribed* legacy screens require
> beyond that delivery.
>
> **BLOCKER first:** see [§0](#0-blocker--patient-write-path-returns-500) — the patient
> write path currently 500s, so none of the below can be live-verified yet.

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

**Frontend status:** the entire wizard is built, type-checks (`npx tsc -b` clean) and
lints clean. Every gap above is either gracefully degraded with an inline notice or
captured-but-unstored, so nothing crashes. Once §0 is fixed we can live-verify the
whole flow end-to-end; LEG-10/11/12/13 are the highest-value follow-ups because they
unblock the legacy "Add a Dependent" workflow.
