# Reports — Backend Response to FE Gap Report

_Module: Reports. Backend team response to `reports_backend_devreport.md`._
_Date: 2026-06-07. Branch: `feature/phase_data_migration`._

This addresses the 6 gaps the frontend team raised during Reports Unit 1. **Gaps
1, 2, 3 and 6 are now implemented** (new tenant-scoped, office-filterable,
Redis-cached aggregation endpoints). **Gaps 4 and 5** are documented below with a
concrete plan and an interim contract the FE can build against today.

---

## ✅ Gap 1 — Aggregation / roll-up endpoints — **DONE**

New endpoints (all tenant-scoped; optional `office_id`; results cached ~60s):

### `GET /api/v1/reports/summary`
**Query:** `date_from` (req), `date_to` (req), `office_id?`
**Response (`ReportSummary`):**
```json
{
  "production": 328000.0,
  "collections": 309000.0,
  "new_patients": 84,
  "active_patients": 1247,
  "scheduled_appointments": 512,
  "insurance_receivables": 42150.0,
  "outstanding_ar": 96120.0,
  "office_id": null,
  "date_from": "2026-01-01",
  "date_to": "2026-06-30",
  "as_of": "2026-06-07T12:00:00+00:00"
}
```
- `production` = Σ non-void/non-archived `patient_procedures.fee` in the window.
- `collections` = Σ non-void `patient_payments.amount` in the window.
- `new_patients` = `patients` created in the window; `active_patients` = current
  active count (point-in-time, **not** windowed).
- `scheduled_appointments` = non-cancelled, non-blocked, non-archived appts in the window.
- `insurance_receivables` = Σ `max(total_billed − total_paid, 0)` over **active,
  non-settled** claims (see Gap 5 for the settled-status vocabulary).
- `outstanding_ar` = practice-wide AR as of `date_to` (cumulative — see Gap 2).

### `GET /api/v1/reports/trends`
**Query:** `date_from` (req), `date_to` (req), `interval` = `day|week|month` (default `day`), `office_id?`
**Response (`ReportTrends`):**
```json
{
  "interval": "month",
  "buckets": [
    {"period": "2026-01-01", "production": 54000.0, "collections": 51000.0, "new_patients": 14}
  ],
  "office_id": null, "date_from": "2026-01-01", "date_to": "2026-06-30",
  "as_of": "2026-06-07T12:00:00+00:00"
}
```
`period` is the ISO date of the bucket start (day = the day; week = ISO Monday;
month = first of month).

> The FE can now drop the bounded `fetchAllPages` fan-out + "truncated sample"
> warnings for the executive dashboard KPIs and the four analytics charts. These
> totals are exact (full-table aggregation), not a capped sample.

---

## ✅ Gap 2 — Practice-wide AR endpoint — **DONE**

### `GET /api/v1/reports/accounts-receivable`
**Query:** `office_id?`, `as_of?` (default = today)
**Response (`AccountsReceivable`):**
```json
{ "total_ar": 96120.0, "patient_ar": 61120.0, "insurance_ar": 35000.0,
  "office_id": null, "as_of": "2026-06-07T12:00:00+00:00" }
```
- `total_ar` = charges − payments − adjustments, all-time ≤ `as_of` (cumulative).
- `insurance_ar` = outstanding expected-insurance portion (best-effort: Σ procedure
  `insurance_estimate`, clamped to `total_ar`) — mirrors the per-patient
  `/patients/{id}/balance` `insurance_balance`.
- `patient_ar` = `total_ar − insurance_ar`.

> The **Outstanding AR** KPI can now render a real number instead of the
> "Awaiting backend" state. `summary.outstanding_ar` returns the same figure.

---

## ✅ Gap 3 — Aging endpoint (30/60/90/120+) — **DONE**

### `GET /api/v1/reports/aging`
**Query:** `office_id?`, `as_of?` (default = today)
**Response (`Aging`):**
```json
{ "current": 30000.0, "d30": 18000.0, "d60": 12000.0, "d90": 9000.0,
  "d120_plus": 27120.0, "total": 96120.0,
  "office_id": null, "as_of": "2026-06-07T12:00:00+00:00" }
```
Buckets by the **age of each charge's `date_of_service`** relative to `as_of`
(gross-charge dating, "Option A"). This is intentionally **consistent with the
existing per-patient `/patients/{id}/balance` aging** the FE already consumes, so
practice-wide and per-patient views reconcile.

> **Known limitation (future refinement):** these are gross-charge buckets, not
> net-of-payment FIFO aging. A precise A/R aging that ages the *outstanding*
> balance (applying payments to oldest charges first) is planned — it requires
> per-charge payment allocation (`payment_allocations` exists but is not yet
> populated for all payments). Tracked as a follow-up; the current buckets match
> the per-patient contract today.

---

## ✅ Gap 6 — `office_id` list filter — **DONE**

`office_id` is now an OpenAPI-visible, typed query filter on:
- `listPatientProcedures` (`GET /api/v1/patient-procedures?office_id=`)
- `listPatientPayments` (`GET /api/v1/patient-payments?office_id=`)
- `listInsuranceClaims` (`GET /api/v1/insurance-claims?office_id=`)

(parity with `listAppointments.office_id` / `listPatients.home_office_id`.)

> Re-run Orval to pick up the new typed params. For office-scoped views that still
> page these lists, you no longer over-fetch all offices then filter client-side.

---

## ⚠️ Gap 5 — Un-enumerated `status` strings — **PARTIAL (vocabulary documented)**

We did **not** convert the schema fields to hard `enum`s yet, because the migrated
data contains free-form historical values and a strict enum would fail validation
on read. Instead:

1. **The reports aggregation now uses a canonical, case-insensitive vocabulary**
   so server-side counts are stable regardless of casing/spacing.
2. **Insurance claim "settled" set** (excluded from `insurance_receivables` /
   outstanding): `paid`, `closed`, `denied`, `rejected`, `void`, `voided`,
   `cancelled`, `canceled`. **Anything else** with a positive `total_billed −
   total_paid` is treated as outstanding.

**FE action:** match `InsuranceClaimRead.status` against the settled set above
(case-insensitively) for any outstanding-vs-settled logic, instead of guessing.

**Planned (next):** seed `/definitions` groups (`claim_status`, `treatment_plan_status`,
`appointment_status`) so the FE can drive status dropdowns/labels from
`GET /definitions?group_code=…` (the established dropdown pattern). This is
non-breaking and does not require touching the read schemas. Let us know the FE's
preferred `group_code` names and we'll seed them.

---

## ⛔ Gap 4 — Export (PDF/Excel) / email / scheduled reports — **DEFERRED (infra)**

Server-rendered PDF/XLSX, email delivery, and scheduled reports require a
rendering pipeline + a persisted job runner (e.g. Redis/RQ or Celery) and delivery
config, which is a separate workstream from the data endpoints above.

**Interim:** client-side **CSV export** is already implemented in the FE
(`reports/lib/exportCsv.ts`); the new `summary`/`trends`/`aging`/`accounts-receivable`
JSON responses are export-friendly. Keep PDF/Excel buttons disabled with the
existing tooltip.

**Proposed contract (unchanged from your suggestion), when scheduled:**
- `POST /api/v1/reports/{report}/export` (`{ format: "pdf"|"xlsx", params }`) → file/URL
- `POST /api/v1/reports/schedules` (cron + delivery), `GET /api/v1/reports/schedules`

---

## Summary

| # | Gap | Status | Endpoint(s) |
|---|---|---|---|
| 1 | Aggregation/roll-ups | ✅ Done | `GET /reports/summary`, `GET /reports/trends` |
| 2 | Practice-wide AR | ✅ Done | `GET /reports/accounts-receivable` |
| 3 | Aging 30/60/90/120+ | ✅ Done | `GET /reports/aging` |
| 6 | `office_id` list filter | ✅ Done | procedures / payments / claims list params |
| 5 | Un-enumerated `status` | ⚠️ Vocabulary documented; `/definitions` seeding planned | — |
| 4 | Export/email/scheduled | ⛔ Deferred (infra) | proposed contract above |

**Notes for the FE:**
- All new endpoints are tenant-scoped via JWT (`super_admin` may target a tenant
  with `X-Tenant-ID`), authenticated like `/patients/{id}/balance`.
- Responses are Redis-cached ~60s; numbers are exact full-table aggregates.
- Re-run `python -m scripts.export_openapi` → Orval to generate the typed client
  (new `Reports` tag → `endpoints/reports/reports.ts`).
