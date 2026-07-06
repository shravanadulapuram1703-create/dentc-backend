# Backend Implementation Response — Final Modules Hand-back

> **Audience:** Frontend team
> **From:** Backend team
> **Date:** 2026-07-05
> **Scope:** Gaps implemented for the five module reports in `docs/Final/`
> (**Help**, **My Page**, **Reports**, **Scheduler**, **Utilities**). The large
> `CONSOLIDATED_BACKEND_GAPS.md` is a superset — most of its clinical/patient/setup
> rows (Perio, Progress Notes, Treatment Plans, Restorative, Patient Insurance,
> Account Ledger, Patient Context, Users, Groups, Insurance Setup, Office Assignment,
> Aux Codes, Charting Setup, Pick Lists, …) were delivered in earlier phases and are
> not re-listed here.

## How to consume
- Run `npm run api:sync` to regenerate the Orval client — every item below is now in `openapi.json`.
- New DB objects ship in migrations `a9b0c1d2e3f4` (scheduler) and `b0c1d2e3f4a5`
  (my-page/help/utilities). Apply with
  `python -c "from alembic.config import main; main(['upgrade','head'])"`, then
  `python -m scripts.seed_account_definitions` (seeds `appt_status` colors/order — Scheduler D1).

---

## Scheduler (`scheduler_consolidated_backend_gaps.md`)

| ID | Status | What shipped |
|----|--------|--------------|
| **G1** | ✅ Done | `GET /appointments/scheduler` rows now carry `has_alert`, `patient_age`, `patient_gender`, `service_summary`, `insurance_eligibility` (`eligible`/`ineligible`/`unknown`/null) — all batch-resolved server-side (no per-block fan-out). |
| **G2** | ✅ Done | Same feed carries `account_balance` per block (batched charges−payments). |
| **G3** | ✅ Done | `PATCH /appointments/{id}/status` now accepts `cancellation_note`, `cancellation_reason`, `add_to_call_list` — persisted on the appointment and echoed on the feed. |
| **G4** | ✅ Done (feed) | Feed carries `responsible_party_id` per block, so the Family same-day section can group client-side with no N+1. |
| **G5** | ✅ Done | Appointments gained `created_by`/`updated_by`; the feed exposes them + resolved `created_by_name`/`updated_by_name`. (Generic create/update stamp them.) |
| **G6** | ✅ Done (field) | `appointment_procedures.est_patient` added (nullable, write/read). Full COB auto-compute is a follow-up; the column unblocks accurate per-line/appointment totals now. |
| **G8** | ✅ Done | Appointments gained `posted_on`; feed exposes `is_posted` + `posted_on`. |
| **D1** | ✅ Done | `appt_status` definitions (10 statuses + colors + `sort_order`) seed via `scripts.seed_account_definitions`. |
| **G7** | ⏳ Deferred | Per-provider / per-weekday working hours + breaks needs a provider-schedules resource (known gated area) — larger, product-spec'd separately. |
| **G9** | ⏳ Deferred | Server-rendered appointment print (routing slip / day sheet) — bundled with the cross-module export effort (Reports G4). |
| **D2** | ⏳ Data | Provider `scheduler_color` seeding is data entry, not code. |

**Also added (serves My Page MP-7 / Reports G8):** `GET /appointments/scheduler` now
accepts `provider_id` and `status` filters (server-side scoping instead of
download-everything-and-filter).

---

## Reports (`reports_backend_devreport.md`)

The aggregation endpoints the report lists as **Open** (G1/G2/G3) already exist —
your `openapi.json` snapshot predates them:
`GET /reports/summary`, `/reports/trends`, `/reports/accounts-receivable`,
`/reports/aging`, `/reports/insurance-verification-summary` (all `office_id`-scoped).

| ID | Status | What shipped |
|----|--------|--------------|
| G1/G2/G3 | ✅ Already live | `/reports/summary`, `/reports/trends`, `/reports/accounts-receivable`, `/reports/aging`. Wire these instead of client fan-out. |
| G6 | ✅ Already live | `office_id` on procedures/payments/claims lists. |
| **G7** | ✅ Done | `PatientProcedureRead` & `PatientPaymentRead` now include `patient_name` + `provider_name`; `InsuranceClaimRead` includes `patient_name` + `carrier_name` — batch-denormalized (no per-row `getPatient`). |
| **G9** | ✅ Done | `TreatmentPlanRead` now includes `patient_name`, `item_count`, `total_fee`, `est_insurance`, `est_patient` (rolled up server-side; no per-plan item N+1). |
| **G10** | ✅ Done | `listInsuranceClaims` gained `submitted_date_from/to`, `paid_date_from/to`, `created_at_from/to` range params. |
| **G8** | ✅ Done | `GET /appointments/scheduler` gained `provider_id` + `status` filters (see Scheduler). Pagination on the feed is still array-based; use `date_from/to` + the new filters to bound it. |
| G4 | ⏳ Deferred | Server-side PDF/XLSX export + email + scheduled reports needs a render + job pipeline — tracked as a cross-cutting effort. Client-side CSV/Excel/PDF remain. |
| G5 | ⏳ Partial | Status vocabularies are seeded in `definitions` (`appt_status`, `claim_status`, …) — read them from `GET /definitions?group_code=`. The read-model fields stay `string` for now. |

---

## My Page (`my_page_backend_devreport.md`)

| ID | Status | What shipped |
|----|--------|--------------|
| **MP-1** | ✅ Done | `PATCH /users/me` (`first_name`, `last_name`, `phone`, `email`) → updated `UserRead`. Self-scoped from the token. |
| **MP-2** | ✅ Done | `POST /users/me/photo` (multipart) → `{image_url}`; `DELETE /users/me/photo`. |
| **MP-3** | ✅ Done | `GET/POST /users/me/tasks`, `PATCH/DELETE /users/me/tasks/{id}` — `{title, priority(high|normal|low), is_done, due_date?, notes?}`, owner-scoped. |
| **MP-4** | ✅ Done | `GET/PUT /users/me/preferences` — an opaque `{preferences: {...}}` JSON blob the FE owns (favorites, layout, folded panels). |
| **MP-6** | ✅ Done | `GET /users/me/notifications` (`{unread_count, items}`), `POST /users/me/notifications/{id}/read`, `POST /users/me/notifications/read-all`. The `notifications` table exists; **event producers** (claim-rejected, lab-received, task-assigned) are a follow-up, so the inbox is empty until those land — replace your derived heuristic incrementally. |
| **MP-7** | ✅ Done | `GET /auth/me-full` now returns `provider_id` (the provider row linked via `Provider.user_id`); `GET /appointments/scheduler` accepts `provider_id`. My Schedule is now authoritative + payload-bounded. |
| **MP-5** | ↪ Folded | Notification preferences live inside the MP-4 prefs blob. |
| **MP-10** | ✅ Confirmed | `last_login_at` **is** stamped on every successful login (`auth_service.login`). |
| MP-8 | ⏳ Deferred | Per-user activity timeline — low value; `audit-logs` exists for admin auditing. |
| MP-9 | ↪ Covered | Personal KPIs: use `provider_id` on the scheduler feed for My Stats bucketing; `/reports/summary` covers office/date roll-ups. |

---

## Help (`help_module_backend_devreport.md`)

| ID | Status | What shipped |
|----|--------|--------------|
| **HELP-1** | ✅ Done | `POST /support/tickets` — accepts your `buildProxyBody` shape, **persists** the ticket, stamps the reporter from the auth token, returns `{issue_key, issue_url}`. |
| **HELP-2** | ✅ Done | `GET /support/tickets` — the caller's tickets, Jira status mapped to `Open`/`In Progress`/`Done`. |
| **HELP-3** | ✅ Wired (config-gated) | The server owns Jira config. **When `JIRA_BASE_URL` + `JIRA_API_TOKEN` are set**, tickets mirror to Jira; **otherwise** they persist locally with a `LOCAL-<id>` key (fully functional, durable — HELP-4). The Atlassian REST calls are isolated in `support_service._create_in_jira` and flip on with config only. |
| **HELP-4** | ✅ Done | Every submission is persisted server-side (durable audit) regardless of Jira. |
| HELP-5 | ⏳ Deferred | Jira status webhook — HELP-2's list read covers v1. |

> **Note:** attachment **metadata** (name/type/size) is persisted; binary upload to
> Jira happens in the Jira-enabled path. You can set `VITE_JIRA_MODE=proxy` +
> `VITE_JIRA_PROXY_URL=/api/v1/support/tickets` today — it works in local mode and
> upgrades to real Jira when the backend env is configured.

---

## Utilities (`utilities_backend_devreport.md`)

| ID | Status | What shipped |
|----|--------|--------------|
| **UTIL-1** | ✅ Contract done | `POST /utilities/{utility_id}/run` (returns a run record with `id`/`status`/`logs`), `GET /utilities/jobs/{job_id}`. Server-side duplicate-run prevention per (utility, office). The **per-utility batch business logic** (claims batch, contract charges, PGID migration, …) is separate work; a run is recorded + marked `completed` with a log note so the UX + audit are real now. |
| **UTIL-2** | ✅ Done | `GET /utilities/audit` (filter by `utility_id`/`office_id`/`run_by`/`date_from`/`date_to`) — durable, tenant-wide execution history. Replace the localStorage audit with this. |
| **UTIL-3** | ✅ Done | Running a utility is guarded server-side (`admin` role) — not just the client role map. |
| UTIL-4 | ⏳ Deferred | Bulk fee-schedule update + validated-template import endpoints. |
| UTIL-5 | ⏳ Deferred | Integrations (Televox/Transworld/DPS/Denticon) connection-status + sync endpoints. |
| UTIL-6 | ⏳ Deferred | Tenant-configurable launch registry. |

---

## Migrations & seeds to apply
1. `python -c "from alembic.config import main; main(['upgrade','head'])"`
   — `a9b0c1d2e3f4` (scheduler cols) + `b0c1d2e3f4a5` (user_tasks, notifications, support_tickets, utility_runs).
2. `python -m scripts.seed_account_definitions` — `appt_status` (+ other) definition groups.

## Deferred (need infra / product decisions — not blocking your wiring)
Server-side PDF/XLSX/email export & scheduled reports (Reports G4 / Scheduler G9);
per-provider working-hours resource (Scheduler G7); notification event producers (MP-6);
utility batch engines + integrations + launch registry (UTIL-4/5/6); Jira status webhook (HELP-5).
