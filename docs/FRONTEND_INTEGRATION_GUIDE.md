# Backend Integration Guide for the Frontend

> **Audience:** UI developers integrating against the Dental PMS backend (`DentC Backend v1.0.0`).
> **Companion docs:** `FE_API_MIGRATION_ANALYSIS.md` (the gap report you wrote) and `BACKEND_IMPLEMENTATION_PLAN.md` (what we built). This guide is the practical "here's what's ready and how to use it" summary.
>
> **Status:** All backend work from the alignment plan is **shipped** — typed filters, date ranges, `definitions` dropdowns, enriched balance, ledger feed, signup, `me-full`, and the user-access resources. Regenerate your Orval client and start migrating.

---

## 1. First step — regenerate the Orval client

The spec now contains every filter as a typed query param (previously they worked but were invisible). Re-export and regenerate:

```bash
# backend repo
python -m scripts.export_openapi      # writes openapi.json
# frontend repo
orval        # picks up the new typed filter args + new endpoints
```

OpenAPI surface now: **169 paths · 403 operations · all snake_case · single `BearerAuth` (JWT) scheme.**

---

## 2. Conventions (unchanged — confirm your adapters)

| Concern | Contract |
|---|---|
| **Field casing** | `snake_case` everywhere — request bodies, query params, responses. No camelCase aliases. Keep snake_case from the generated types; map to UI shapes only where needed. |
| **Pagination** | Every list returns `{ "items": [...], "meta": { "page", "size", "total", "pages" } }`. Use one adapter `toOffsetPagination(meta)` → your `{ total, limit, offset, has_more }`. |
| **Errors** | Every error is `{ "error": { "code", "message", "details" } }`. |
| **Auth** | `Authorization: Bearer <access_token>`. Multi-office/tenant admins may target a tenant with the `X-Tenant-ID` header (normal users don't need it). |
| **Update verb** | **`PATCH`** for all updates (not `PUT`). This was the latent 405 source — switch your mutations to PATCH. |
| **IDs** | Integer-PK entities (patients, offices, users, insurance, …) are **server-assigned** — don't send `id` on create, and drop any `/next-id` prefetch. **String-PK entities** (`appointments` `APPT-*`, `providers` `PRV-*`, `operatories` `OPR-*`, `treatment_plans` `TP-*`, `patient_procedures` `PROC-*`, `patient_payments` `PAY-*`, `insurance_claims` `CLM-*`, `procedure_codes`) require **you to generate and send the `id`** in the create body. |

---

## 3. List filtering & search (NEW — the big unlock)

Every list endpoint accepts, in addition to `page, size, sort, order, search`, **typed filter params** for its relational columns. Orval now generates these as typed arguments. Examples:

| Endpoint | Useful query params |
|---|---|
| `GET /patients` | `search`, `chart_no`, `home_office_id`, `preferred_provider_id`, `is_active` |
| `GET /appointments` | `patient_id`, `provider_id`, `operatory_id`, `office_id`, `date`, `status`, **`date_from`**, **`date_to`** |
| `GET /patient-procedures` | `patient_id`, `appointment_id`, `provider_id`, `procedure_code`, `claim_id`, `billing_status`, **`date_of_service_from`/`_to`** |
| `GET /patient-payments` | `patient_id`, `provider_id`, `payment_type`, **`payment_date_from`/`_to`** |
| `GET /insurance-claims` | `patient_id`, `status`, `claim_type`, `carrier_id`, `ins_plan_id` |
| `GET /treatment-plans` | `patient_id`, `office_id`, `status` |
| `GET /providers` | `office_id`, `is_active` |
| `GET /operatories` | `office_id`, `is_active` |
| `GET /user-offices` | `user_id`, `office_id` |
| `GET /time-clock-entries` | `user_id`, `office_id` |
| `GET /procedure-codes` | `category`, `is_active`, `is_ortho` (+ `search`) |

**Examples**
```
GET /api/v1/appointments?date_from=2026-06-01&date_to=2026-06-07&provider_id=PRV-12&office_id=3
GET /api/v1/insurance-claims?patient_id=1207&status=submitted
GET /api/v1/patients?search=smith&home_office_id=3&is_active=true
GET /api/v1/patients?chart_no=AB1234        # exact chart lookup (replaces /patients/chart/{n})
```

`search` is a free-text ILIKE across each resource's text columns (e.g. patient name/chart_no/email/phone). Use it for type-ahead; use the typed filters for scoping.

---

## 4. Dropdowns / metadata → one endpoint

All legacy `…/metadata/*` calls collapse onto **`GET /definitions?group_code=<code>`** (`DefinitionRead` = `group_code, key1, key2, description, …`). Build one `useDefinitions(groupCode)` hook for all of them.

```
GET /api/v1/definitions?group_code=gender
GET /api/v1/definitions?group_code=marital_status
GET /api/v1/definitions?group_code=payment_method
```

Discover available groups via `GET /api/v1/definition-groups`.

> ⚠️ **Action item (data contract):** the exact `group_code` string values come from the migrated data and may differ from the names you assumed (e.g. `gender` vs `SEX`). Pull `GET /definition-groups` first and we'll agree the canonical codes together before you hardcode them. Procedure categories: use `GET /procedure-codes?category=…` or the distinct categories from definitions.

---

## 5. Endpoint remap cheat-sheet (legacy FE → backend)

Legacy nested/aggregate routes are **not** rebuilt — point the generated client at the canonical resources:

| Legacy FE call | Use instead |
|---|---|
| `GET /users/all-tenants` | `GET /tenants` |
| `PUT /users/{id}`, `/patients/{id}`, `/offices/{id}` | `PATCH /users/{id}` etc. |
| `GET /users/me` | `GET /auth/me` |
| `GET /patients/search?q=` | `GET /patients?search=` |
| `GET /patients/chart/{chartNo}` | `GET /patients?chart_no=` |
| `POST /patients/{id}/procedures` | `POST /patient-procedures` (`patient_id` in body) |
| `POST /patients/{id}/payments` | `POST /patient-payments` |
| `POST /patients/{id}/claims` · `…/claims/{id}` | `POST /insurance-claims` · `PATCH /insurance-claims/{id}` |
| `GET /patients/{id}/claims` | `GET /insurance-claims?patient_id=` |
| `GET /patients/{id}/treatment-plans` | `GET /treatment-plans?patient_id=` |
| `POST/GET/PUT/DELETE /scheduler/appointments[...]` | `…/appointments` (PATCH for updates incl. `{status}`) |
| `GET /scheduler/operatories` · `/scheduler/providers` | `GET /operatories` · `GET /providers` |
| `GET /scheduler/appointments?day` | `GET /appointments?date=&provider_id=&office_id=` |
| `GET /offices/fee-schedules` link | `POST /fee-schedule-assignments` |
| `GET /offices/next-id` | drop — id is server-assigned |
| `GET /metadata/procedure-codes`, `/procedures/codes` | `GET /procedure-codes` |

**Composite grids (client-side join, no backend dependency):** e.g. the Users grid = `GET /users` + `GET /user-offices?user_id=` + `GET /offices` (+ `GET /tenants`) joined in a `mapUsersGrid()` selector. The home-office column comes from `user-offices(is_primary)` → `offices.name`.

---

## 6. Patient balance (enriched) — `GET /patients/{patient_id}/balance`

Response (`PatientBalance`, additive — old fields unchanged):
```jsonc
{
  "patient_id": 1207,
  "total_charged": 1789.0,
  "total_paid": 519.0,
  "balance": 1270.0,
  "account_balance": 1270.0,            // alias of balance
  "estimated_insurance": 519.0,
  "estimated_patient": 0.0,
  "patient_balance": 751.0,             // charges − payments − estimated insurance
  "aging": { "current": 0, "b30": 0, "b60": 0, "b90": 0, "b120": 635.0 },
  "recent_activity": { "today": 0.0, "last_ins": "2015-07-16", "last_pat": "2015-07-16" },
  "as_of": "2026-05-31T10:48:00Z"
}
```
Cached ~30s server-side. Powers the Balances tab directly (aging buckets + insurance/patient split + recent activity).

## 7. Patient ledger feed — `GET /patients/{patient_id}/ledger`

Query: `date_from?`, `date_to?`, `page`, `size`. Response (`LedgerResponse`):
```jsonc
{
  "patient_id": 1207,
  "entries": [
    { "entry_date": "2015-06-20", "entry_type": "procedure", "source_id": "PROC-…",
      "charge": 155.0, "credit": 0.0, "running_balance": 155.0,
      "procedure_code": "D2740", "tooth": "14", "status": "billed" },
    { "entry_date": "2015-07-16", "entry_type": "payment", "source_id": "PAY-…",
      "charge": 0.0, "credit": 519.0, "running_balance": -364.0, "payment_type": "ins" }
  ],
  "opening_balance": 0.0,
  "closing_balance": 635.0,
  "total": 8,
  "as_of": "2026-05-31T10:48:00Z"
}
```
`running_balance` is computed server-side in exact decimal across the full window, so you don't need to re-sum client-side. (You *can* still compose it from `patient-procedures` + `patient-payments` if you prefer — this endpoint is the convenience/precision option.)

---

## 8. Auth

| Endpoint | Purpose |
|---|---|
| `POST /auth/login` → `TokenResponse` | `{ access_token, refresh_token, token_type, expires_in }` |
| `POST /auth/refresh` | rotate tokens |
| `POST /auth/logout` | revoke access (+ optional refresh) token |
| `GET /auth/me` → `UserRead` | current user |
| `GET /auth/me-full` → `MeFull` | **NEW** — `{ user, tenant, offices:[{office_id,name,office_code,is_primary}] }`; replaces `me-full`/`me/access` compose |
| `POST /auth/signup` → `TokenResponse` | **NEW** — self-service: creates a **new practice (tenant) + its admin user** and logs in. Body `{ practice_name, practice_code, email, username, password, first_name?, last_name? }`. Returns 409 on duplicate code/email/username. NOTE: this does **not** add a user to an existing practice — joining an existing practice is invite-only via `POST /users` (admin). |

---

## 9. New user-access resources (UserSetup advanced tabs)

Standard CRUD, all filterable:

| Resource | List filters |
|---|---|
| `GET/POST/PATCH/DELETE /user-preferences` | `user_id`, `pref_key` (key/value rows) |
| `…/user-groups` | `is_active` (+ `search` on name) |
| `…/user-group-memberships` | `user_id`, `group_id` |
| `…/user-ip-rules` | `user_id`, `rule_type`, `is_active` |

Map: legacy `GET /users/{id}/groups` → `GET /user-group-memberships?user_id={id}`; `…/preferences` → `GET /user-preferences?user_id={id}`; `…/ip-rules` → `GET /user-ip-rules?user_id={id}`. (IP rules are **stored** only — enforcement isn't wired yet.)

---

## 10. Corrected assumptions from the gap report

| Your report said | Reality / action |
|---|---|
| `POST /patients/check-duplicate` & `GET /patients/metadata` "exist live, hidden" | Stale legacy — they don't exist in this backend. Use `GET /patients?search=` (or `?chart_no=`) for dup checks and `GET /definitions?group_code=` for metadata. |
| `GET /users/{id}/{id}/ip-rules` | Duplicated path param — frontend bug. Use `GET /user-ip-rules?user_id={id}`. |
| Update verb `PUT` | It's `PATCH`. |
| Lists accept only `search` | They now accept typed filters + date ranges (§3). |
| `POST /patients/{id}/adjustments` (new resource) | Reuse `POST /patient-payments` with an adjustment `payment_type` — no new endpoint. |
| `/offices/next-id` | Dropped — server assigns the id. |

---

## 11. Suggested migration order (mirrors the plan)

1. Regenerate Orval; ship the **Category-A remaps** (auth, tenants, offices, patients CRUD+search, appointments, procedures, payments, claims, procedure-codes, operatories, providers, treatment-plans). Switch `PUT→PATCH`. Add the pagination adapter.
2. Adopt the **typed filters + `definitions` dropdowns** (scheduler day views, claims-by-patient, treatment-plans-by-patient, one `useDefinitions` hook).
3. Wire the **Balances tab** (`/balance`) and **Ledger** (`/ledger`).
4. Wire **signup**, **me-full**, and the **user-access** tabs.

Re-run your `api-drift-report.mjs` after step 1 — the ✅ count should jump now that filters and the new endpoints are in the spec.
