# Utilities Module — Backend Dev Report

Status of the modernized **Utilities** module (`src/components/utilities/**`) and the
backend endpoints it needs. The frontend is a complete, reusable framework:

- **Dashboard** (`pages/UtilitiesDashboard.tsx`) — categorized, searchable hub that
  replaces the legacy dropdown; RBAC-filtered, with favourites, recently-executed
  shortcuts, a live execution/audit history, and status indicators.
- **Declarative catalog** (`utilityCatalog.ts` + `types.ts`) — every utility is one
  data entry; adding a utility requires no new screen.
- **Generic runner** (`UtilityShell.tsx`) — RBAC gate → parameter form → confirmation
  (for mutating ops) → progress/steps → result summary + log → audit record.
- **Real, fully client-side** features that need no backend: the **Fee Schedule Excel
  Template** (download template + upload-and-validate) and the **Launch** category
  (external app launchers, permission-checked + logged).

The 11 legacy functional areas are preserved and reorganized into 9 modern categories:
Batch & Claims, Billing & Charges, Insurance & Procedures, Data Migration (PGID),
Office-Specific, User Functions, Fee Schedules, Third-Party & Integrations, Launch.

---

## How execution behaves today

The DentC backend exposes **no execution, job, or audit endpoints** for these
administrative batch operations. Rather than fake server calls, utilities with
`backend: "pending"` run a **clearly-labelled in-browser simulation** (see
`lib/useUtilityRun.ts`) that exercises the full UX — confirmation, streamed progress
steps, success/warning/error summary, and an audit entry — and every result banner
states it was simulated. `backend: "live"` utilities (Fee Schedule Excel Template) do
real client-side work. `backend: "external"` utilities (Launch) open real URLs.

Favourites, recents, and the execution/audit history persist per-user to
`localStorage` (`lib/utilitiesStorage.ts`, namespace `dentc:utilities:*`) — genuinely
user-owned state, not mock data. These helpers are the single swap point when the
endpoints below land.

---

## Backend gaps

### UTIL-1 — Utility execution / job API (blocking for real runs)
No endpoint runs any batch utility (claims batch, contract-charge generation,
eligibility, consolidation, code replace, PGID migrations, office exports, etc.).
**Needed:** a job-submission API returning a job id + status stream (or poll) so the
UI can drive real long-running work — `POST /api/v1/utilities/{utility_id}/run`
(async, returns `job_id`), `GET /api/v1/utilities/jobs/{job_id}` (status, progress,
processed/succeeded/failed, logs). Server-side duplicate-run prevention per
(utility, office) is also required (the UI blocks duplicates client-side only).

### UTIL-2 — Audit-log persistence (blocking for compliance)
The audit trail (user, office, date/time, utility, parameters, result) is currently
local per browser. **Needed:** `POST` on execution + `GET /api/v1/utilities/audit`
(filter by user/office/utility/date) so audit history is durable, tenant-wide, and
tamper-evident.

### UTIL-3 — RBAC source of truth
Authorization is currently enforced from the client `role` string against each
utility's `roles` allow-list. **Needed:** server-side permission checks on the
execution endpoint keyed to real permissions/groups, plus (optionally) a
`GET /api/v1/utilities/permitted` so the dashboard reflects server policy rather than
a hard-coded role map.

### UTIL-4 — Fee Schedule bulk operations
`fee-schedule-maintenance` (bulk % adjust) and the template **import** currently
validate/preview client-side only. **Needed:** a bulk fee-schedule update endpoint
and a CSV/Excel import endpoint that accepts the validated template rows.

### UTIL-5 — Integrations status + sync
Televox / Transworld / DPS / Denticon panels show simulated connection + sync state.
**Needed:** per-integration connection-status and sync-trigger/history endpoints so
"integration status, synchronization history, and error logs" are real.

### UTIL-6 — Launch registry (optional)
Launch destinations are hard-coded URLs in the catalog. **Needed (optional):** a
tenant-configurable external-app registry so admins can add/edit launch targets and
credentials without a code change.

---

## Notes for future work
- Deep, per-office nested legacy items not yet cataloged (Office-Specific →
  Universal/DCA sub-exports) can be added as new catalog entries with a `legacyPath`
  when their workflows are specified — the nav redirect + runner pick them up
  automatically via `legacyRedirects()`.
- When UTIL-1/UTIL-2 land, replace the `simulate()` path in `lib/useUtilityRun.ts`
  with the job API and mirror the audit write to UTIL-2; the rest of the UI is
  unchanged.
