# Reports Module — Screen Audit & Integration Map

_Phase: Reports modernization. Unit 1 = audit + backend-driven executive dashboard._
_Last updated: 2026-06-07._

## 1. Current state (pre-modernization)

The Reports module is a **single page** (`src/components/pages/Reports.tsx`) rendering
**100% hardcoded mock data** and making **zero backend calls**:

| Element | Mock value(s) in code | Status |
|---|---|---|
| KPI — Total Revenue (6mo) | `$328,000`, `+12.5%` | hardcoded |
| KPI — Total Patients | `1,247`, `+8.3%` | hardcoded |
| KPI — Avg Revenue/Patient | `$263`, `+3.8%` | hardcoded |
| KPI — Collection Rate | `94.2%`, `+1.2%` | hardcoded |
| Chart — Revenue vs Expenses | `revenueData` array (Jan–Jun) | hardcoded |
| Chart — Patient Trends | `patientData` array | hardcoded |
| Chart — Procedure Distribution | `procedureData` array | hardcoded |
| Quick Reports (6 buttons) | static labels, no `onClick` | dead buttons |
| Date-range `<select>` | static `<option>`s, no state | non-functional |
| Export Report button | no handler | non-functional |

There is **no filtering, no office scoping, no real aggregation, no export**.

## 2. Navigation surface

`GlobalNav.tsx` (`reportsMenuItems`, ~L499–680) exposes a large Reports menu. All entries
currently route to `PlaceholderPage` except `/reports` (the page above).

**Top-level categories** → routes:
`/reports/daily`, `/reports/monthly`, `/reports/ledger`, `/reports/management`,
`/reports/insurance`, `/reports/appointment`, `/reports/treatment-plan`, `/reports/referral`,
`/reports/recall`, `/reports/ortho`, `/reports/statements`.

**Submenus:**
- **Lists** → `/reports/lists/{patient-list,responsible-party-list,provider-list,security-list,setup-list}`
- **Interactive** → `/reports/interactive/{unsigned-progress-notes,eligibility-verification}`
- **Office Reports** → `/reports/office/{abbey-dental,access-dental,brightnow,…}` (~20 office variants)

**`App.tsx` routes (L180–207):** `/reports` → `Reports`; every `/reports/lists/*`,
`/reports/interactive/*`, `/reports/office/*` → `PlaceholderPage`. The top-level category routes
(`/reports/daily` etc.) are referenced by nav but rendered as placeholders / not yet defined as
dedicated components — these are **later units**.

## 3. Backend integration map (verified against generated Orval client)

The backend has **no reporting/aggregation endpoints** (0 of 228 OpenAPI paths). Every metric is
aggregated **client-side** by paging CRUD list endpoints (size ≤ 200) and reducing in the browser —
the pattern the Dashboard phase established (`src/components/dashboard/lib/aggregate.ts`).

| KPI / chart | Endpoint fn | Source file | Params | Response fields used |
|---|---|---|---|---|
| Total Production | `listPatientProcedures` | `endpoints/clinical/clinical.ts` | `date_of_service_from/to`, `is_void` | `fee`, `date_of_service`, `office_id`, `procedure_code` |
| Total Collections | `listPatientPayments` | `endpoints/billing/billing.ts` | `payment_date_from/to`, `is_void` | `amount`, `payment_date`, `office_id` |
| New Patients (count) | `listPatients` | `endpoints/patients/patients.ts` | `created_at_from/to`, `home_office_id` | `meta.total` |
| Active Patients (count) | `listPatients` | `endpoints/patients/patients.ts` | `is_active:true`, `home_office_id` | `meta.total` |
| Scheduled Appointments | `listAppointments` | `endpoints/appointments/appointments.ts` | `date_from/to`, `office_id` | `is_cancelled`, `is_blocked` |
| Insurance Receivables | `listInsuranceClaims` | `endpoints/billing/billing.ts` | `is_active:true` | `status`, `total_billed`, `total_paid`, `office_id` |
| Procedure Distribution | `listPatientProcedures` | clinical | date range, `is_void:false` | group by `procedure_code`, sum `fee` |
| **Outstanding AR / Aging** | — | — | — | **no endpoint** (see devreport gap #2/#3) |

### Integration caveats
- **No `office_id` query param** on `listPatientProcedures`, `listPatientPayments`,
  `listInsuranceClaims` → fetch then filter rows by `office_id` client-side. (devreport gap #6)
- **`status`** on claims/treatment-plans/appointments is a free-form string (no schema enum) →
  matched case-insensitively. (devreport gap #5)
- Counts read `meta.total` from a `size:1` page — no full paging required.
- All client-side fan-outs are **bounded** (`fetchAllPages` `maxPages`) and surface `truncated`
  honestly in the widget footer.

## 4. Unit 1 deliverable (this PR)

Replaced the mock page with a **backend-driven executive dashboard**:
- **Executive Summary** KPI grid: Production, Collections, New Patients, Active Patients,
  Scheduled Appointments, Insurance Receivables (all live, office + date-range scoped);
  **Outstanding AR** rendered as honest `awaiting backend`.
- **Analytics** (opt-in): Revenue/Collections trend, Production trend, Patient Growth,
  Procedure Distribution — recharts over real data, truncation surfaced.
- **Report Categories** quick-access cards → existing `/reports/*` routes.
- **Filter bar**: date-range presets (Today … This Year, Custom) + CSV export. PDF/Excel disabled
  with a backend-gap tooltip.

New module: `src/components/reports/` (`lib/reportRange.ts`, `lib/reportMetrics.ts`,
`lib/exportCsv.ts`, `components/ReportFilterBar.tsx`) reusing `dashboard/components/{KpiStat,WidgetCard}`
and `dashboard/lib/aggregate.ts`.

## 5. Out of scope (later units)
Dedicated report screens (Financial, Patient, Appointment, Clinical, Operational, Provider),
the `/reports/lists|interactive|office/*` placeholders, scheduled reports, and PDF/Excel/email
export — all backend-gap or follow-on work. See `reports_backend_devreport.md`.
