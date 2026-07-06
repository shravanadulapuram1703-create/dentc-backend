# Reports — Consolidated Backend Gap Report

_Module: **Reports** (executive dashboard + report-runner framework with 6 dedicated
report screens). Consolidated after Unit 1 (dashboard) and Unit 2 (report runner)._
_Last updated: 2026-07-05. Verified against the generated Orval client / `openapi.json`._

The Reports frontend is fully backend-driven **where endpoints exist**, aggregating CRUD
list endpoints client-side (the established Dashboard-phase pattern). The gaps below force
client-side fan-out, block accurate financials, force id-only displays, or block whole
report features. Each is actionable for the backend team.

---

## Status summary

| # | Gap | Severity | Status | FE workaround today |
|---|---|---|---|---|
| G1 | No aggregation / roll-up endpoints | **High** | Open | bounded client fan-out + truncation warnings |
| G2 | No practice-wide A/R endpoint | **High** | Open | Outstanding A/R shows "Awaiting backend" |
| G3 | No aging endpoint (30/60/90/120+) | **High** | Open | Aging report not built |
| G4 | No server-side export (PDF/XLSX) / email / scheduled reports | Medium | Open | client-side CSV + `.xls` (SpreadsheetML) + jsPDF |
| G5 | `status` fields are un-enumerated free strings | Medium | Open | hardcoded vocab, matched case-insensitively |
| G6 | `office_id` missing as a list filter param | Medium | ✅ **Resolved** | now present on procedures/payments/claims |
| G7 | List reads carry **no denormalized names** (patient/provider/carrier) | **High** | Open | tables show `patient_id`; provider joined client-side |
| G8 | Scheduler feed has **no pagination / provider / status** params | Medium | Open | fetch whole array, filter client-side (unbounded) |
| G9 | Treatment-plan list has **no rolled-up totals** | Medium | Open | plan-level only; item totals = N+1, omitted |
| G10 | Insurance-claims list has **no date-range filter** | Medium | Open | claims report can't be date-scoped |

---

## G1 — No aggregation / roll-up endpoints

**Screens:** Executive Dashboard + every report screen.
**Business requirement:** KPIs and trends (production, collections, counts, time-series)
across a date range / office / provider.
**Current status:** No reporting/analytics/aggregation path in `openapi.json` (0 of ~228).
The FE lists endpoints (`size ≤ 200`, capped via `fetchAllPages` `maxPages`) and reduces in
the browser.
**Suggested endpoints:**
- `GET /api/v1/reports/summary?office_id=&provider_id=&date_from=&date_to=`
  → `{ production, collections, new_patients, active_patients, scheduled_appointments,
  insurance_receivables, outstanding_ar }`
- `GET /api/v1/reports/trends?...&granularity=day|week|month`
  → daily/weekly/monthly buckets `[{ bucket, production, collections, new_patients }]`
- `GET /api/v1/reports/procedure-mix?...` → `[{ procedure_code, count, total_fee }]`
**Why required:** Client-side fan-out is slow and, for large practices, **truncated** — the
FE surfaces "based on a capped sample" warnings. Accurate totals need server aggregation.
**FE impact:** KPI/trend numbers are best-effort within the page cap; analytics is opt-in.

## G2 — No practice-wide A/R / outstanding-balance endpoint

**Screens:** Executive Dashboard (Outstanding A/R KPI), future A/R report.
**Current status:** `GET /api/v1/patients/{patient_id}/balance` exists **per patient only**;
there is no practice-wide total. Looping `getPatientBalance` over every patient does not
scale; an all-time `charges − payments − adjustments` client fan-out is badly truncated.
**Suggested endpoint:** `GET /api/v1/reports/accounts-receivable?office_id=&as_of=`
→ `{ total_ar, patient_ar, insurance_ar, as_of }`
**Why required:** A/R is cumulative/all-time; cannot be computed correctly from a bounded
page sample.
**FE impact:** Outstanding A/R KPI renders an honest **"Awaiting backend"** state.

## G3 — No aging endpoint (30 / 60 / 90 / 120+)

**Screens:** Aging report, Outstanding Balances.
**Current status:** No endpoint exposes per-charge age buckets; patient list rows have no
balance/aging field.
**Suggested endpoint:** `GET /api/v1/reports/aging?office_id=&as_of=`
→ `{ current, d30, d60, d90, d120_plus, by_responsible_party?: [...] }`
**Why required:** Aging requires server-side per-charge dating against payments; not
derivable from list rows.
**FE impact:** Aging report is blocked (not built).

## G4 — No server-side export (PDF / XLSX) / email / scheduled reports

**Screens:** Every report (Export / Email / Schedule).
**Current status:** No export, email-delivery, or scheduled-report endpoints exist.
**Suggested endpoints:**
- `POST /api/v1/reports/{report}/export` (`format: pdf|xlsx`) → file / signed URL.
- `POST /api/v1/reports/schedules` (cron + delivery: email / download-center);
  `GET /api/v1/reports/schedules`.
**Why required:** Server-rendered PDF/XLSX matches print layouts and handles large datasets;
scheduling + email require persistence and a job runner.
**FE impact today:** **CSV**, **Excel** (dependency-free SpreadsheetML `.xls`), and **PDF**
(jsPDF + autotable) are all generated **client-side** from the loaded page. This is limited
to what the FE fetched (page cap) and can't be emailed/scheduled.

## G5 — `status` fields are un-enumerated strings (contract gap)

**Screens:** Insurance Claims, Treatment Plan, Appointment reports.
**Current status:** `InsuranceClaimRead.status`, `TreatmentPlanRead.status`,
`AppointmentRead.status` are typed as free-form `string` (no `enum`). The FE hardcodes/guesses
the vocabulary (`paid`, `denied`, `accepted`, `rejected`, `submitted`…) and matches
case-insensitively.
**Suggested fix:** Define string `enum`s (or a `/definitions`-backed status list) for these
fields, and honor them in the list `status` filter param.
**FE impact:** Status filters + status-based aggregation are brittle and can silently
miscount if the seeded vocabulary differs from the FE's guesses.

## G6 — `office_id` list filter — ✅ RESOLVED

**Was:** `listPatientProcedures` / `listPatientPayments` / `listInsuranceClaims` accepted no
`office_id` param, forcing over-fetch + client-side row filtering.
**Now:** All three expose `office_id` (verified in `ListPatientProceduresParams`,
`ListPatientPaymentsParams`, `ListInsuranceClaimsParams`). The report screens pass it
server-side. **No further action needed** — recorded for continuity.

---

## G7 — List reads carry no denormalized names (patient / provider / carrier)  ⟵ NEW

**Screens:** Production, Collections, Insurance Claims, Treatment Plan reports.
**Current status:** `PatientProcedureRead`, `PatientPaymentRead`, `InsuranceClaimRead`,
`TreatmentPlanRead` expose only **ids** — `patient_id`, `provider_id`, `carrier_id` — with
**no** `patient_name` / `provider_name` / `carrier_name`. There is no bulk "get patients by
id list" endpoint, so a report of N distinct patients would need N `getPatient` calls.
**Contrast:** `AppointmentSchedulerRead` **does** denormalize (`patient_name`,
`provider_name`, `operatory_name`) — that pattern is exactly what the money reports need.
**Suggested fix (any one):**
1. Add denormalized `patient_name` (+ `provider_name`, `carrier_name`) to these list reads
   (mirror the scheduler feed), **or**
2. Support `?include=patient,provider,carrier` (expand) on the list endpoints, **or**
3. Add a bulk lookup `GET /api/v1/patients?ids=1,2,3` (and same for providers/carriers).
**Why required:** A production/collections/claims report keyed by numeric patient id is not
usable by front-desk/billing staff.
**FE impact today:** Reports display **Patient ID** (numeric) only. Provider names are joined
client-side from a small `listProviders` fetch; patient/carrier names are not resolved.

## G8 — Scheduler feed lacks pagination / provider / status filters  ⟵ NEW

**Screen:** Appointment report.
**Current status:** `GET /api/v1/appointments/scheduler`
(`ListSchedulerAppointmentsParams`) accepts **only** `date_from`, `date_to`, `office_id` and
returns a **plain array** (no `meta`, no paging). The denormalized-name variant of
`/appointments` has no provider/status server filter and no page bound here.
**Suggested fix:** Add `provider_id`, `status`, and `page`/`size` (paginated response) to the
scheduler feed — parity with `listAppointments` — **or** add the denormalized names to the
paginated `listAppointments`.
**Why required:** A wide date range returns the **entire** appointment set in one unbounded
payload; provider/status filtering must happen client-side after downloading everything.
**FE impact today:** Appointment report fetches the full feed for the range and filters
provider/status in the browser; large ranges are heavy.

## G9 — Treatment-plan list has no rolled-up totals  ⟵ NEW

**Screen:** Treatment Plan report.
**Current status:** `TreatmentPlanRead` has `id, patient_id, office_id, name, status,
created_at` — **no** plan-level `total_fee` / `est_insurance` / `est_patient`. Totals live on
`TreatmentPlanItemRead`, fetched per-plan via `listTreatmentPlanItems` (N+1).
**Suggested fix:** Add `total_fee`, `est_insurance`, `est_patient` (and `item_count`) to
`TreatmentPlanRead`, **or** support `?include=totals` on `listTreatmentPlans`.
**Why required:** A treatment-plan report without per-plan value/acceptance totals has little
analytical value; N+1 item fetches don't scale.
**FE impact today:** Report is **plan-level only** (id / patient / name / status / created);
no fee or estimate columns.

## G10 — Insurance-claims list has no date-range filter  ⟵ NEW

**Screen:** Insurance Claims report.
**Current status:** `ListInsuranceClaimsParams` = `patient_id, status, claim_type,
carrier_id, ins_plan_id, office_id, is_active, page, size, sort, order, search` — **no**
date-range param, though `InsuranceClaimRead` carries `submitted_date`, `paid_date`,
`date_of_service_from/to`, `created_at`.
**Suggested fix:** Add `submitted_from/to` (and/or `service_date_from/to`,
`created_at_from/to`) to `listInsuranceClaims`, matching procedures/payments.
**Why required:** Claims reporting is inherently period-based (submitted this month, paid
this quarter); today the report can only scope by office/status, not by date.
**FE impact today:** The Insurance Claims report has no date-range filter (unlike Production
/ Collections); it lists by office/status/active only.

---

## Endpoints already sufficient (no change needed)

For reference, these back the current report screens directly and are working well:
`listPatientProcedures` (production — has `office_id`, `provider_id`, `date_of_service_*`,
`search`), `listPatientPayments` (collections — same filter set), `listPatients` (patient
list — `home_office_id`, `is_active`, `search`, `meta.total`), `listOffices` / `listProviders`
(filter dropdowns + provider name map).
