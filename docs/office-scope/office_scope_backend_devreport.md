# Office Scope — Backend Dev Report (OFF-SCOPE-1 … 19)

> **Module:** cross-cutting (office context) · **Date:** 2026-09-12 · **Backend:** DentC Backend v1.0.0 (`/api/v1`)
> **Frontend layer:** `src/features/office-scope/**` (plan: `~/.claude/plans/okay-now-help-me-transient-wren.md`)

## Decision the frontend implements

**Office = the user's working context, not a fence.** Tenant is the security boundary. The selected
office is (a) the default read filter for operational day-data (scheduler, dashboard, reports, inboxes),
(b) the write stamp for point-of-service records, and (c) the selector for office-owned setup. Patients,
the chart, the ledger, catalogs, users and Setup stay organization-wide; `patients.home_office_id` is an
ownership attribute shown as a badge. This mirrors Open Dental Clinics / Dentrix Enterprise / Epic.

Everything the client does today (switcher grouping, defaults, badges, per-screen "This office / My
offices / All offices") is **workflow convenience, not confidentiality**. Anything bypassable by editing
a query string is a server concern — the items below.

## What the contract looks like today (verified against `openapi.json`)

- 53 list endpoints accept an **optional** `office_id` / `home_office_id` (`/fee-schedule-assignments`
  also `office_group_id`). None has a default; omitting = tenant-wide (only the 5 `/reports/*` say so).
- No endpoint documents validating `office_id` against the caller's `user_offices`; the only documented
  rule is "403 if office not in tenant" (`docs/setup/offices/OFFICE_ASSIGNMENT_BACKEND_NOTES.md`).
- 178 of 225 office properties are optional+nullable → `office_id: null` rows exist on nearly every
  clinical/financial entity, and `?office_id=N` hides them (PLAN-8 already bit patient documents).
- `GET /patients` has only `home_office_id`; there is no "seen-at office" concept (0 hits for
  `seen_at`, `search_scope`, `/patients/search`).
- `MeFull` returns `offices[] { office_id, name?, office_code?, is_primary }`, `permissions[]` (the legacy
  Denticon rights catalog, e.g. `appointments_add_appointment_in_other_office`),
  `permissions_enforced: true`, `groups[]`, `provider_id`, `last_patient_id`. **Even the seeded admin
  (`super_admin`) has an empty `offices[]`.**
- `ProviderRead.office_id` is a single home-office scalar; rosters via `/offices/{id}/providers/effective`
  are 93 / 1 / 1 / 0 for offices 1 / 4 / 9 / 10.
- Per-office catalog overlays exist (`GET/PUT /offices/{id}/{procedure-codes|exp-codes|production-types|
  providers|note-macros|prescription-library|letter-templates|users}`) but only providers and
  letter-templates have an `/effective` (assigned ∪ full catalog) view; `AccountSettings.only_show_office_items`
  is stored and never enforced.

## Requirements

| Id | Endpoint(s) | Current | Required | Blocks (FE phase) |
|---|---|---|---|---|
| **OFF-SCOPE-1 🔴** | every `office_id` / `home_office_id` query, every Create/Update body with `office_id`, all `/offices/{office_id}/*` | tenant membership only; generic 403 | `403 {code:"office_not_assigned", office_id}` unless `office_id ∈ user_offices(caller)` or caller holds `offices:view_all` / `offices:switch_any` | Phase 5 — until this lands the switcher restriction is UX only (`OFFICE_ASSIGNMENT_ENFORCED=false` in `officeScopeModel.ts`) |
| **OFF-SCOPE-2 🔴** | the ~45 list endpoints whose `office_id` is undocumented (`/appointments/scheduler`, `/patients`, `/operatories`, `/patient-documents`, …) and `/reports/*` | omitted = tenant-wide | document per endpoint; for non-privileged callers omitted = caller's assigned offices (∪ null-office rows where OFF-SCOPE-4 applies); `all_offices=true` = tenant-wide and requires permission. The FE already sends `all_offices=true` on deliberate all-office reads (`allOfficesParam`) so nothing narrows silently when this ships | Phase 5 |
| **OFF-SCOPE-3 🟠** | request header; `GET /auth/me-full`; `PATCH /users/me` (`UserSelfUpdate`) | no server-side working office; no header; `last_patient_id` returned, never written | optional `X-Office-ID` validated against assignments, recorded on every mutation's audit row, used as the default write stamp when the body omits `office_id`; add it to the CORS allow-list; `MeFull.current_office_id` + `UserSelfUpdate.current_office_id` + `last_patient_id` writable (cross-device restore) | Phase 5 |
| **OFF-SCOPE-4 🟠** | lists over nullable-office rows: `/fee-schedules`, `/labs`, `/referrals`, `/place-of-service-codes`, `/explosion-codes`, `/patient-documents`, `/image-groups`, `/sms-templates`, `/postcard-templates`, `/tenants/{id}/holidays`, provider schedule days | `?office_id=N` excludes `office_id IS NULL` (PLAN-8) | `include_global` flag — default **true** for catalogs with an optional office pin, **false** for day-data | Phase 6 (scoped catalog pickers) — until then the FE fetches these unfiltered and sorts the working office first |
| **OFF-SCOPE-5 🟠** | `GET /patients` | only `home_office_id` | `seen_at_office_id` (join appointments / procedures) and `search_scope=current\|all\|group` (the FE-authored contract in `docs/api-contracts/PATIENT_MANAGEMENT_API_CONTRACT.md`) | Phase 5 — patient search default stays "All offices" (office-first sort + home badge) until then |
| **OFF-SCOPE-6 🟠** | `GET /patients/{id}` and every `patient_id`-scoped read | no visibility policy | for callers without `patients:view_cross_office`: 403 unless home ∈ assigned or seen at an assigned office | Phase 5 |
| **OFF-SCOPE-7 🟡** | `/patient-notes`, `/patient-recalls` (+`due_date_from/to`), `/chart-conditions`, `/prescriptions`, `/ortho-plans`, `/patient-payment-plans`, `/patient-reg-plans`, `/ledger-insurance-details`, `/image-details`, `/postcard-templates`, `/caries-risk-assessments`, `/perio-chart-activity`, `/treatment-plan-items`, `/patients/{id}/refunds`, `/patients/{id}/statements` | rows carry `office_id`, list has no filter | `office_id` honouring 1 / 2 / 4 | dashboard recall KPI (today client-filtered; null-office rows counted as "Unassigned"), office-level lists |
| **OFF-SCOPE-8 🟡** | `/reports/*`, all day-data lists, `GET /offices`, `GET /appointnow/requests` | single `office_id`; only `/fee-schedule-assignments` has `office_group_id` | repeated `office_id` (`office_ids[]`) and `office_group_id`; `GET /offices?assigned_to_me=true` **opt-in only** (the default list must stay tenant-wide — it is the label table for badges) | Phase 5 "My offices" (today client-filtered union), regional/office-group mode |
| **OFF-SCOPE-9 🟡** | `/offices/{id}/{procedure-codes,exp-codes,production-types,note-macros,prescription-library}/effective`; `GET /patients/{id}/fee`; `POST /patients/{id}/estimate` | only providers + letter-templates have `/effective`; `only_show_office_items` inert; FEE-1 (`coverage_pct: 0`) | `/effective` for the five (assigned else full catalog); define `only_show_office_items` = filter by the **patient's home-office** assignment (legacy semantic, `ACCOUNT_SETUP_DATA_DEFINITION.md:82`); fix coverage + resolve `office_group_id` server-side so `feeScheduleResolver.ts` can retire | Phase 6 |
| **OFF-SCOPE-10 🟠** | `provider_offices`, `/offices/{id}/providers/effective`, `MeFull.offices` | rosters 93/1/1/0; `OfficeAssignment` lacks `short_id`, `is_active`, `office_group_id`, `timezone` | backfill `provider_offices` from home office + historical `patient_procedures.provider_id × office_id`; guarantee ≥1 active dentist per active office; enrich `OfficeAssignment` | data now (pickers already "prefer, never exclude"); exclusion semantics Phase 5 |
| **OFF-SCOPE-11 🟠** | Create bodies on payments, adjustments, claims, notes, documents, prescriptions, recalls, treatment plans, sms, time clock, `PostInstallmentRequest` | `office_id` nullable, null persisted | **require `office_id` on point-of-service creates (422 when absent)**; validate ∈ assigned; `created_office_id` on payments; document the installment office rule | Phase 5 |
| **OFF-SCOPE-12 🟡** | `POST /appointments`, `PATCH /appointments/{id}` | `office_id` trusted; operatory unchecked | validate `operatory.office_id == office_id` (422); derive `office_id` from the operatory and `provider_id` from `operatory.provider_id` when omitted | client validation ships in Phase 2–3 |
| **OFF-SCOPE-13 🔴** | `GET /auth/me-full` permissions | `permissions_enforced=true` refers to the legacy rights catalog; no office rights exist | define `offices:view_all`, `offices:switch_any`, `patients:view_cross_office`, `reports:all_offices`; map roles (owner/admin/manager → all); keep `appointments_add_appointment_in_other_office` as the coverage alias the FE already honours | Phase 5 |
| **OFF-SCOPE-14 🟡** | `POST /sms/send`, `GET /sms/inbox/summary`, `GET /sms/sender`, `/messaging/conversations` | `office_id` optional; inbox summary unused; messaging office policy open | document: an existing thread keeps its office; a new outbound thread defaults from `X-Office-ID`; null-office inbox bucket = "Unmatched"; messaging stays tenant-wide | Phase 5 |
| **OFF-SCOPE-15 🟡** | `GET /appointnow/requests`, WS | staff rows `office_code: null` (AN-17); no per-office channel | non-null `office_code`; `office_ids[]` filter; WS subscription per office list | Phase 5 |
| **OFF-SCOPE-16 🟡** | `POST /utilities/{utility_id}/run`, `GET /utilities/jobs/{job_id}`, `GET /utilities/audit` | endpoints exist but have 0 callers; runs are simulated client-side | `office_id` required (422) for `officeScoped` utilities; validate ∈ assigned; per-(utility, office) duplicate guard | Phase 5 |
| **OFF-SCOPE-17 🟡** | `/audit-logs`, `/patients/{id}/audit-logs`, signature audit | no office dimension | record `X-Office-ID` + row `office_id`; `?office_id=` filter (HIPAA access-by-location) | Phase 5 |
| **OFF-SCOPE-18 🟡** | dashboard aggregates | KPIs computed client-side after page caps | office view = the existing DASH-1..5 `/offices/{id}/*` roll-ups; privileged "All offices" = `/reports/summary\|trends` with `office_id` omitted until `GET /dashboard/summary?office_id=&all_offices=&date=` exists — never a client loop over offices | Phase 2 partial |
| **OFF-SCOPE-19 🟡** | `PATCH /tenants/{id}/account-settings`, `OfficeRead.timezone` | `payment_portal_posting_office` is a sentinel string; `model_office_id` undocumented; timezone unused | document the sentinel and `model_office_id`; confirm partial-PATCH preservation; "today" for office-scoped screens = the office's timezone (expose it on `OfficeAssignment`) | Phase 6 |

**Data hygiene (no code):** every real user must have `user_offices` rows (`MeFull.offices` is empty
for the seeded admin); `is_primary` set for one of them.

**Not backend gaps (closed frontend-side):** operatory default provider — `OperatoryCreate.provider_id` /
`OperatoryUpdate.provider_id` already exist, the frontend never sent them (stale "gap #23");
office↔group assignment — `PATCH /offices/{id}` `office_group_id` already exists (stale "gap #18").

## Frontend status

| Phase | Status |
|---|---|
| 0 Foundations + bug bundle | ✅ shipped 2026-09-12 (`src/features/office-scope/**`, one parser, remembered office, switcher on assignments, no lockout) |
| 1 Providers: prefer, never exclude | ✅ shipped (`fetchProviders` returns everyone with `in_office`; `ProviderOptionGroups`; `staffBooking` off the scalar) |
| 2 Read scoping + switch hygiene | 🔄 in progress (`useReadScope`, `ScopeToggle`, server-side KPI filters, runner remount, patient search default All + badge, AppointNow modes) |
| 3 Patient-shell plumbing | 🔄 in progress (`usePatientOffice`, snake_case `home_office_id` / `posting_office_id` on the outlet context, record-first updates) |
| 4 Point-of-service posting office | ✅ shipped 2026-09-13 (PO sign-off) — posting = working office at chart open, editable PostingOfficeBar, home-class plans keep home office, plan-item reprice, specialty-match fix |
| 5 Server-enforced scoping | ⛔ blocked on OFF-SCOPE-1/2/3/5/6/7/8/10/11/13/14/15/16/17 |
| 6 Catalog polish | ⏳ partially blocked on OFF-SCOPE-4/9/19 |
