# Reports — Backend Dev Report (Gaps)

_Module: Reports. Generated during Unit 1 (executive dashboard). Last updated: 2026-06-07._

The Reports frontend is fully backend-driven where endpoints exist, aggregating CRUD list
endpoints client-side (the established Dashboard-phase pattern). The gaps below force client-side
fan-out, block accurate financials, or block whole report features. Each is actionable for the
backend team.

---

## Gap 1 — No aggregation / roll-up endpoints

**Module:** Reports
**Screen:** Executive Dashboard + every report screen
**Business Requirement:** KPIs and trends (production, collections, counts, time-series) across a
date range / office.
**Current Status:** No suitable endpoint found in `openapi.json` (0 of 228 paths are
reporting/analytics/aggregation). The FE pages list endpoints (`size ≤ 200`, capped via
`fetchAllPages` `maxPages`) and reduces in the browser.
**Suggested Endpoint:** `GET /api/v1/reports/summary`
**Expected Request:** `{ office_id?, date_from, date_to }`
**Expected Response:** `{ production, collections, new_patients, active_patients,
scheduled_appointments, insurance_receivables, outstanding_ar }` (+ a `GET /api/v1/reports/trends`
returning daily/weekly/monthly buckets).
**Reason Required:** Client-side fan-out is slow and, for large practices, **truncated** — the FE
surfaces "based on a capped sample" warnings. Accurate totals need server aggregation.
**Impact on Frontend:** KPI/trend numbers are best-effort within the page cap; analytics is opt-in
to avoid heavy fetches.

## Gap 2 — No practice-wide AR / outstanding-balance endpoint

**Screen:** Executive Dashboard (Outstanding Balances KPI), future Aging/AR report.
**Current Status:** `GET /api/v1/patients/{patient_id}/balance` exists **per patient only**; there
is no practice-wide total. Looping `getPatientBalance` over every patient does not scale, and an
all-time `charges − payments − adjustments` client fan-out would be badly truncated (misleading).
**Suggested Endpoint:** `GET /api/v1/reports/accounts-receivable?office_id=&as_of=`
**Expected Response:** `{ total_ar, patient_ar, insurance_ar, as_of }`
**Reason Required:** AR is cumulative/all-time; cannot be computed correctly from a bounded page
sample.
**Impact on Frontend:** The Outstanding AR KPI renders an honest **"Awaiting backend"** state
instead of a wrong number.

## Gap 3 — No aging endpoint (30/60/90/120+)

**Screen:** Aging Report, Outstanding Balances.
**Current Status:** No endpoint exposes per-charge age buckets; the patients list row has no
balance/aging field.
**Suggested Endpoint:** `GET /api/v1/reports/aging?office_id=&as_of=`
**Expected Response:** `{ current, d30, d60, d90, d120_plus, by_responsible_party?: [...] }`
**Reason Required:** Aging requires server-side per-charge dating against payments; not derivable
from list rows.
**Impact on Frontend:** Aging report is blocked.

## Gap 4 — No export (PDF/Excel) or email / scheduled-report endpoints

**Screen:** Every report (Export / Print / Email / Schedule).
**Current Status:** No export, email-delivery, or scheduled-report endpoints exist.
**Suggested Endpoints:** `POST /api/v1/reports/{report}/export` (`format: pdf|xlsx`) returning a
file/URL; `POST /api/v1/reports/schedules` (cron + delivery: email/download-center);
`GET /api/v1/reports/schedules`.
**Reason Required:** Server-rendered PDF/XLSX matches print layouts and handles large datasets;
scheduling + email delivery require persistence and a job runner.
**Impact on Frontend:** **CSV export is implemented client-side** (`reports/lib/exportCsv.ts`).
PDF/Excel buttons are disabled with a tooltip; scheduled-reports UI is deferred.

## Gap 5 — `status` fields are un-enumerated strings (contract gap)

**Screen:** Insurance Receivables, Treatment Acceptance, Appointment Status reports.
**Current Status:** `InsuranceClaimRead.status`, `TreatmentPlanRead.status`, `AppointmentRead.status`
are typed as free-form `string` in the OpenAPI schema (no `enum`). The FE must hardcode/guess the
vocabulary (e.g. `paid`, `denied`, `accepted`, `rejected`) and match case-insensitively.
**Suggested Fix:** Define string `enum`s (or a `/definitions`-backed status list) for these fields.
**Impact on Frontend:** Status-based aggregation (outstanding vs paid claims, accepted vs rejected
plans) is brittle and can silently miscount if backend vocabulary differs.

## Gap 6 — `office_id` missing as a list filter param

**Screen:** Production / Collections / Insurance metrics.
**Current Status:** `listPatientProcedures`, `listPatientPayments`, `listInsuranceClaims` accept no
`office_id` query param, though each row carries `office_id`. The FE must over-fetch all offices
then filter client-side, worsening the truncation in Gap 1.
**Suggested Fix:** Add `office_id` filter param to these list endpoints (parity with
`listAppointments` / `listPatients.home_office_id`).
**Impact on Frontend:** Office-scoped KPIs over-fetch and are more likely truncated than necessary.

---

## Summary

| # | Gap | Severity | FE workaround |
|---|---|---|---|
| 1 | No aggregation/roll-up endpoints | High | bounded client fan-out + truncation warnings |
| 2 | No practice-wide AR endpoint | High | Outstanding AR shows "Awaiting backend" |
| 3 | No aging endpoint | High | Aging report blocked |
| 4 | No PDF/Excel/email/scheduled export | Medium | client-side CSV only; PDF/Excel disabled |
| 5 | Un-enumerated `status` strings | Medium | case-insensitive vocabulary matching |
| 6 | No `office_id` list filter | Medium | client-side row filtering / over-fetch |
