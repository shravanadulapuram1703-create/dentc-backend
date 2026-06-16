# Insurance Dashboard (Screen Analysis)

Unit 4 of the Insurance modernization phase. A modern overview landing for the
Insurance module at `/setup/insurance/dashboard` (first item in the Setup →
Insurance nav).

## Screen
| Route | Component | Backend |
| --- | --- | --- |
| `/setup/insurance/dashboard` | `InsuranceDashboard` | plans / carriers / employers / fee-schedules list `meta.total`; claims list `status` filter; `/reports/accounts-receivable` |

File: `src/components/setup/insurance/InsuranceDashboard.tsx`. Built on the shared
dashboard `WidgetCard` + `KpiStat` components and `formatCurrency`.

## KPI cards (all backend-driven, no mock data)
| KPI | Source | Live value |
| --- | --- | --- |
| Total Plans | `listInsurancePlans({size:1}).meta.total` | 31,321 |
| Active Plans | `listInsurancePlans({is_active:true})` | 31,321 |
| Pending Verifications | — (awaiting backend, INS-11) | — |
| Claims Outstanding | `listInsuranceClaims({status})` summed over submitted/pending/draft | 9,934 |
| Claims Denied | summed over denied/rejected | 0 |
| Insurance Receivables | `getReportAccountsReceivable().insurance_ar` | $32,246,958 |

Each count tile is computed from a `size:1` list call reading `meta.total`, so the
dashboard stays cheap (no row scanning). Claim counts use the server `status`
filter. Insurance receivables comes from the new `/reports/accounts-receivable`
aggregation endpoint.

## Quick Actions (route to the real setup screens)
Add Insurance Plan · Add Employer · Dental Carriers · Medical Carriers · Custom
Coverage · Manage Fee Schedules · Fee Schedule Assignments.

## Setup at a Glance
Dental Carriers (1,335) · Medical Carriers (5) · Employers (4,302) · Fee
Schedules (35) · Total Claims (96,291) — each row drills into its setup screen.

## Live verification
- [x] All 6 KPIs render real backend values; Pending Verifications shows the
      honest "awaiting backend" tile (INS-11)
- [x] Insurance Receivables = $32,246,958 from /reports/accounts-receivable
- [x] Quick actions + glance rows navigate to the setup screens
- [x] `npx tsc -b` + `npx eslint` clean
- [x] Resilient: each metric fetch is independently `.catch`-guarded (AR failure
      shows "—" without breaking the others)

## Backend gap
- **INS-11** ✅ **resolved** (backend): `listInsuranceSubscribers` now accepts an
  `elig_status` (and `office_id`) filter, and a dedicated roll-up
  `GET /api/v1/reports/insurance-verification-summary` returns
  `{ by_status, total, verified, pending, … }` from a single GROUP BY. Wire the
  **Pending Verifications** KPI to `summary.pending` (or
  `listInsuranceSubscribers({ elig_status, size: 1 }).meta.total` for a specific
  status). Live `elig_status` is still uniformly `"unknown"` (a data state until
  eligibility checks run), so the tile will read ~all-pending until then — that's
  expected, not a backend gap. See `insurance_backend_devreport.md` INS-11.
