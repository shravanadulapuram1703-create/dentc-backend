# Frontend ↔ Backend API Alignment & Migration Analysis

> Inputs: live `openapi.json` (`DentC Backend v1.0.0`, 158 paths / 380 operations / 313 schemas) + full `src/` scan + live probes (2026-05-31). Supersedes the earlier `API_DRIFT_FINDINGS.md`, which under-counted reuse because it matched endpoints by exact path only. Reproduce inventories with `node scripts/api-inventory.mjs`.
>
> **Guiding principle: the backend is the source of truth.** The frontend adapts to the backend's resource model; we recreate legacy endpoints only as a last resort.

---

## 1. Executive Summary

The backend is a **normalized, uniform REST API**: every domain entity exposes the same five operations — `GET /x` (paginated list), `POST /x`, `GET /x/{id}`, `PATCH /x/{id}`, `DELETE /x/{id}` — with list responses wrapped as `{ items, meta:{page,size,total,pages} }`. The legacy frontend instead expects **aggregate, nested, and legacy-named endpoints** (`/users/all-tenants`, `/patients/{id}/ledger`, `/scheduler/appointments`).

The good news, and the correction to the earlier report: **almost everything the frontend needs already exists on the backend — just under different names and shapes.**

| Metric | Value |
|---|---|
| Backend endpoints (operations) | **380** |
| Distinct **logical** frontend endpoints | **81** |
| ✅ **A — UI change only** (direct match or rename remap, *no backend work*) | **38 (47%)** |
| 🟡 **B — OpenAPI exposure only** (route exists live, missing from schema) | **2 (2%)** |
| 🟠 **C — Minor backend enhancement** (filter params / fields / aggregate) | **36 (44%)** |
| 🔴 **D — Net-new backend** (no equivalent exists) | **5 (6%)** |
| **Backend already has a basis (A+B+C)** | **76 / 81 = 94%** |

**The 44% in Category C is not 36 unrelated tasks — it collapses into ~3 cross-cutting backend enhancements:**

1. **C-1 — Relational filter params** on list endpoints (`patient_id`, `office_id`, `user_id`, `provider_id`, date range, status). The backend's lists today accept only a generic `search` string. Adding filters turns ~15 C-items into trivial A remaps and is the **single highest-leverage backend change.**
2. **C-2 — A `group_code` filter on `GET /definitions`.** The backend already stores all dropdown/lookup data (genders, titles, states, payment/adjustment/claim codes, appointment types/statuses, procedure categories) in one `definitions` table. One filter param replaces **~13** legacy metadata endpoints.
3. **C-3 — A richer patient balance / ledger view.** `GET /patients/{id}/balance` exists but is minimal (`total_charged/total_paid/balance`); the UI needs aging buckets, insurance split, and a running-balance feed. The feed is *composable* from existing `patient-procedures` + `patient-payments` + `insurance-claims` once C-1 lands.

Only **5 endpoints (6%) are truly net-new (D)**, all narrow: self-service `signup`, and four user sub-resources (`groups`, `ip-rules`, `preferences` — `time-clock` already has a backend resource).

**Recommendation:** adapt the frontend to the backend resource model (Category A is ~half the surface and needs zero backend work), land the 3 cross-cutting C enhancements to unlock the rest, expose 2 hidden routes, and defer/scope the 5 net-new items. Do **not** rebuild the legacy nested endpoints.

---

## 2. Detailed API Mapping Report

Legend: **A-Direct** (same path/method) · **A-Remap** (different name/verb, data fully present, frontend-only change) · **B** (exists live, add to OpenAPI) · **C** (minor backend enhancement) · **D** (net-new).

### 2.1 Auth & Identity — `AuthContext`, `authService`, `SignUpPage`

| FE endpoint | Backend target | Cat | Notes |
|---|---|---|---|
| `POST /auth/login` | `POST /auth/login` → `TokenResponse` | **A-Direct** | |
| `POST /auth/logout` | `POST /auth/logout` | **A-Direct** | |
| `POST /auth/refresh` | `POST /auth/refresh` → `TokenResponse` | **A-Direct** | |
| `GET /users/me` | `GET /auth/me` → `UserRead` | **A-Remap** | Retarget; identical intent |
| `GET /auth/me-full` | `GET /auth/me` + `GET /user-offices` (+`/tenants`) | **C** | "full" = identity + assigned offices/tenant; needs `user_id` filter (C-1) to compose efficiently |
| `GET /users/me/access` | compose `GET /auth/me` (role) + `GET /user-offices` | **C** | Access context; role on `UserRead`, offices via `user-offices` (C-1). No permission-matrix resource exists |
| `POST /auth/signup` | — | **D** | No self-registration route. Alternative: invite-only via `POST /users` (admin). Confirm product need |

### 2.2 Users / Staff setup — `UserSetup`

| FE endpoint | Backend target | Cat | Notes |
|---|---|---|---|
| `GET /users/all-tenants` | `GET /tenants` → `PaginatedResponse_TenantRead_` | **A-Remap** | The canonical example: tenants moved to their own resource |
| `GET /users/{id}` | `GET /users/{user_id}` | **A-Direct** | |
| `POST /users` | `POST /users` | **A-Direct** | |
| `PUT /users/{id}` | `PATCH /users/{user_id}` | **A-Remap** | **Verb fix** (was a latent 405) |
| `GET /users/list-with-home-office` | `GET /users` + `GET /user-offices` + `GET /offices` | **C** | Join client-side; `UserRead` has no office. Needs `user_id`/`office_id` filters (C-1) for scale |
| `GET /users/setup` | compose `/tenants` + `/offices` + `/definitions` | **C** | Form-option aggregate; composable once C-2 lands |
| `GET /users/{id}/time-clock` | `GET /time-clock-entries` | **C** | Resource exists (Staff tag); needs `user_id` filter (C-1) |
| `GET /users/{id}/groups` | — | **D** | No user-group membership resource |
| `GET /users/{id}/ip-rules` | — | **D** | No IP-rules resource |
| `GET /users/{id}/preferences` | — | **D** | No user-preferences resource; `UserRead` has none |
| `GET /users/{id}/{id}/ip-rules` | — | **D** | Also a **frontend bug** (duplicated path param) |

### 2.3 Offices — `OfficeSetup` + tabs, `GlobalNav`, `OrganizationSwitcher`

| FE endpoint | Backend target | Cat | Notes |
|---|---|---|---|
| `GET /offices` | `GET /offices` | **A-Direct** | |
| `POST /offices` | `POST /offices` | **A-Direct** | |
| `PUT /offices/{id}` | `PATCH /offices/{item_id}` | **A-Remap** | Verb fix |
| `POST /fee-schedules` | `POST /fee-schedules` | **A-Direct** | |
| `POST /offices/fee-schedules` | `POST /fee-schedule-assignments` | **A-Remap** | Office↔fee-schedule link is its own resource |
| `GET /offices/next-id` | — (server-generated id on `POST`) | **A-Remap** | Drop; backend assigns id. Redesign the form to not pre-fetch |
| `GET /offices/{id}/setup` | `GET /offices/{id}` + `/operatories` + `/fee-schedule-assignments` | **C** | `OfficeRead` already holds schedule hours/slot interval; needs `office_id` filter (C-1) |
| `GET /offices/{id}/providers` | `GET /providers` | **C** | Resource exists; needs `office_id` filter (C-1) |
| `GET /offices/metadata` | compose `/definitions` | **C** | Resolve via C-2 |
| `POST /offices/billing-providers` | `/provider-insurance-ids` or join | **C** | Clarify intended model with backend |

### 2.4 Patients (search / CRUD) — `patientApi`, `patient.service`

| FE endpoint | Backend target | Cat | Notes |
|---|---|---|---|
| `GET /patients` | `GET /patients` | **A-Direct** | |
| `POST /patients` | `POST /patients` | **A-Direct** | |
| `GET /patients/{id}` | `GET /patients/{item_id}` → `PatientRead` | **A-Direct** | `PatientRead` is rich (chart_no, gender, marital_status, …) |
| `DELETE /patients/{id}` | `DELETE /patients/{item_id}` | **A-Direct** | |
| `PUT /patients/{id}` | `PATCH /patients/{item_id}` | **A-Remap** | Verb fix |
| `GET /patients/search` | `GET /patients?search=` | **A-Remap** | List endpoint has a `search` param |
| `GET /patients/chart/{chartNo}` | `GET /patients?search={chartNo}` | **C** | Works via search; an exact `chart_no` filter (C-1) is cleaner |
| `POST /patients/check-duplicate` | exists live, **not in schema** | **B** | Returned `401` live; expose in OpenAPI to generate it |

### 2.5 Patient metadata dropdowns — `patientMetadataApi`

All ten collapse onto the **`/definitions`** system (`DefinitionRead` has `group_code, key1, key2, description`).

| FE endpoint | Backend target | Cat |
|---|---|---|
| `GET /patients/metadata` | exists live, not in schema | **B** |
| `GET /patients/metadata/genders` | `GET /definitions?group_code=gender` | **C** (C-2) |
| `GET /patients/metadata/titles` | `GET /definitions?group_code=title` | **C** (C-2) |
| `GET /patients/metadata/states` | `GET /definitions?group_code=state` | **C** (C-2) |
| `GET /patients/metadata/marital-statuses` | `GET /definitions?group_code=marital_status` | **C** (C-2) |
| `GET /patients/metadata/patient-types` | `GET /definitions?group_code=patient_type` | **C** (C-2) |
| `GET /patients/metadata/pronouns` | `GET /definitions?group_code=pronoun` | **C** (C-2) |
| `GET /patients/metadata/referral-types` | `GET /definitions?group_code=referral_type` | **C** (C-2) |
| `GET /patients/metadata/responsible-party-relationships` | `GET /definitions?group_code=resp_party_rel` | **C** (C-2) |
| `GET /patients/metadata/contact-preferences` | `GET /definitions?group_code=contact_pref` | **C** (C-2) |

> Without C-2 these are technically achievable by fetching all definitions and filtering `group_code` client-side (Category A), but a `group_code` filter is the right, efficient fix.

### 2.6 Patient Ledger / Billing — `ledgerApi`

| FE endpoint | Backend target | Cat | Notes |
|---|---|---|---|
| `GET /metadata/procedure-codes` | `GET /procedure-codes` | **A-Remap** | `ProcedureCodeRead` maps to FE `ProcedureCode` |
| `POST /patients/{id}/procedures` | `POST /patient-procedures` (`patient_id` in body) | **A-Remap** | |
| `GET /patients/{id}/procedures/{id}` | `GET /patient-procedures/{item_id}` | **A-Remap** | |
| `PUT /patients/{id}/procedures/{id}` | `PATCH /patient-procedures/{item_id}` | **A-Remap** | |
| `DELETE /patients/{id}/procedures/{id}` | `DELETE /patient-procedures/{item_id}` | **A-Remap** | |
| `POST /patients/{id}/payments` | `POST /patient-payments` | **A-Remap** | |
| `GET /patients/{id}/payments/{id}` | `GET /patient-payments/{item_id}` | **A-Remap** | |
| `POST /patients/{id}/claims` | `POST /insurance-claims` | **A-Remap** | |
| `GET /patients/{id}/claims/{id}` | `GET /insurance-claims/{item_id}` | **A-Remap** | |
| `PUT /patients/{id}/claims/{id}` | `PATCH /insurance-claims/{item_id}` | **A-Remap** | |
| `GET /metadata/payment-codes` | `GET /definitions?group_code=payment_method` | **C** (C-2) | |
| `GET /metadata/adjustment-codes` | `GET /definitions?group_code=adjustment` | **C** (C-2) | |
| `GET /metadata/claim-statuses` | `GET /definitions?group_code=claim_status` | **C** (C-2) | |
| `GET /metadata/transaction-types` | `GET /definitions?group_code=txn_type` | **C** (C-2) | |
| `GET /offices/{id}/providers` | `GET /providers` | **C** (C-1) | |
| `GET /patients/{id}/claims` | `GET /insurance-claims?patient_id=` | **C** (C-1) | |
| `POST /patients/{id}/claims/{id}/send` | `POST /claim-submissions` | **C** | Link resource exists; confirm payload |
| `GET /patients/{id}/balances` | enhance `GET /patients/{id}/balance` | **C** (C-3) | Missing aging buckets, insurance split, recent activity |
| `GET /patients/{id}/ledger` | compose `patient-procedures`+`patient-payments`+`insurance-claims` | **C** (C-1+C-3) | Data exists; **running balance computed client-side**. Not net-new |
| `POST /patients/{id}/adjustments` | — (model TBD) | **C** | No explicit adjustments resource; clarify (payment type? new resource?) |
| `GET /patients/{id}/adjustments/{id}` | — (model TBD) | **C** | Same |

### 2.7 Scheduler & Appointments — `schedulerApi`

| FE endpoint | Backend target | Cat | Notes |
|---|---|---|---|
| `POST /scheduler/appointments` | `POST /appointments` | **A-Remap** | `AppointmentRead` is rich (status, times, operatory, …) |
| `GET /scheduler/appointments/{id}` | `GET /appointments/{item_id}` | **A-Remap** | |
| `PUT /scheduler/appointments/{id}` | `PATCH /appointments/{item_id}` | **A-Remap** | |
| `DELETE /scheduler/appointments/{id}` | `DELETE /appointments/{item_id}` | **A-Remap** | |
| `PATCH /scheduler/appointments/{id}/status` | `PATCH /appointments/{item_id}` (`{status}`) | **A-Remap** | |
| `GET /scheduler/operatories` | `GET /operatories` | **A-Remap** | |
| `GET /scheduler/providers` | `GET /providers` | **A-Remap** | |
| `GET /procedures/codes` | `GET /procedure-codes` | **A-Remap** | |
| `GET /scheduler/appointments` | `GET /appointments?date=&provider_id=&office_id=` | **C** (C-1) | Day/provider views need filters |
| `GET /scheduler/appointment-types` | `GET /definitions?group_code=appt_type` | **C** (C-2) | |
| `GET /scheduler/appointment-statuses` | `GET /definitions?group_code=appt_status` | **C** (C-2) | |
| `GET /scheduler/procedure-types` | `GET /definitions?group_code=procedure_type` | **C** (C-2) | |
| `GET /procedures/categories` | distinct `category` from `/procedure-codes` or `/definitions` | **C** (C-2) | |
| `GET /scheduler/config` | compose `GET /offices/{id}` (slot/hours) + definitions | **C** | `OfficeRead` already has `slot_interval_minutes`, `schedule_start/end_hour` |
| `GET /patients/{id}/treatment-plans` | `GET /treatment-plans?patient_id=` | **C** (C-1) | Resource exists |

---

## 3. Data-Model Gap Report (key screens)

### 3.1 Users grid (UserSetup) — needs a client-side join
```
FE row (UserDetails grid)            Backend (UserRead)              Gap / transform
---------------------------------    ----------------------------   --------------------------------
id            "U-123"                id (number)                    prefix "U-" in mapper
firstName / lastName                 first_name / last_name         rename (snake→camel via Orval types)
username, email, role, active        username,email,role,is_active  direct
homeOffice (name)                    —  (in UserOfficeRead+Office)  JOIN: user-offices(is_primary) → offices.name
assignedOfficeNames[]                —  (UserOfficeRead[])          JOIN: user-offices(user_id) → offices
lastLogin                            last_login_at                  format
pgid / pgidName                      tenant_id (+ /tenants.name)    JOIN tenants
groupMemberships, permittedIPs,      — (no resource)                Category D (out of scope until backend adds)
preferences, timeClock               time-clock-entries (Staff)     time-clock via C-1 filter
```
**Approach:** `useListUsers()` + `useListUserOffices()` + `useListOffices()` (+`useListTenants()`), joined in a `mapUsersGrid()` selector. Drops only the D-fields (groups/ip/preferences) until the backend provides them.

### 3.2 Patient — strong direct fit
`PatientRead` carries `chart_no, first_name, last_name, dob, gender, marital_status, phone, email, address_*, referral_type, home_office_id, is_active, …` — covers the search results and detail header directly. Dropdown **options** for the edit form come from `/definitions` (C-2); the patient's stored values are already on `PatientRead`.

### 3.3 Patient balance — fields missing
```
FE BalancesResponse                       Backend PatientBalance       Gap
account_balance, patient_balance          balance, total_paid,...      partial map
estimated_insurance, estimated_patient    —                            MISSING (C-3)
aging{current,30,60,90,120}               —                            MISSING (C-3)
recent_activity{today,last_ins,last_pat}  —                            MISSING (C-3)
```

### 3.4 Ledger row — composable
`PatientProcedureRead` (`fee, insurance_estimate, patient_estimate, tooth, surface, apply_to, billing_status, claim_id`), `PatientPaymentRead` (`amount, payment_type, payment_method`), and `InsuranceClaimRead` together provide every ledger column **except `running_balance`**, which is a client-side cumulative sum after sorting by date. Requires C-1 (`patient_id` filter) on all three.

### 3.5 Pagination — universal transform
Backend returns `{ items, meta:{ page, size, total, pages } }`; FE code assumes `{ data, pagination:{ total, limit, offset, has_more } }`. One adapter (`toOffsetPagination(meta)`) bridges every list. Orval generates the `PageMeta` type.

---

## 4. Backend Action Report (only true backend work)

Ordered by leverage. Everything else is frontend-only (Category A).

| ID | Action | Type | Unlocks | Effort |
|---|---|---|---|---|
| **C-1** | Add relational filter query params to list endpoints: `patient_id`, `office_id`, `user_id`, `provider_id`, `status`, date range (`date_from`/`date_to`) | C | ~15 endpoints (ledger sources, claims, treatment-plans, scheduler day views, user-offices, time-clock, providers-by-office) | **High value, low effort** — usually a few lines per list route |
| **C-2** | Add `group_code` filter to `GET /definitions` (or `GET /definitions/groups/{code}`) | C | ~13 metadata/dropdown endpoints | Low |
| **C-3** | Extend patient balance with aging buckets + insurance/patient estimates + recent activity; optionally a `GET /patients/{id}/ledger` aggregate (or rely on C-1 + client aggregation) | C | Balances tab, Ledger running view | Medium |
| **B-1** | Expose already-working routes in OpenAPI (`include_in_schema=True`): `POST /patients/check-duplicate`, `GET /patients/metadata` | B | 2 endpoints + any other hidden routes | Trivial |
| **D-1** | Decide model for **adjustments** (new resource vs. payment-type) | C/D | Ledger adjustments | Medium |
| **D-2** | User sub-resources if still required: `groups`, `ip-rules`, `preferences` | D | UserSetup advanced tabs | Medium each — **confirm need before building** |
| **D-3** | `POST /auth/signup` if self-registration is a product requirement (else invite-only via `POST /users`) | D | SignUpPage | Medium |
| **P2-verb** | Confirm `PATCH` is the canonical update verb (frontend will switch from `PUT`) | — | users/patients/offices updates | None (frontend change) |

---

## 5. Frontend Refactoring Plan

1. **Regenerate the Orval client** — already covers all Category-A targets today (`/tenants`, `/offices`, `/patients`, `/appointments`, `/patient-procedures`, `/patient-payments`, `/insurance-claims`, `/procedure-codes`, `/operatories`, `/providers`, `/treatment-plans`, `/definitions`, `/user-offices`, `/time-clock-entries`).
2. **Build thin feature selectors/mappers** (per `features/*/`) that:
   - join resources for composite views (`mapUsersGrid`, `mapLedger`),
   - convert `{items,meta}` → the UI's list shape via one shared `toOffsetPagination`,
   - keep snake_case from the generated types (per the locked decision) — map only where the UI demands a different shape.
3. **Delete legacy services as each feature migrates** — `userApi`, `patientApi`, `patientMetadataApi`, `ledgerApi`, `schedulerApi`, `organizationApi`, `feeSchedules` retire incrementally.
4. **Switch update verbs** `PUT → PATCH` for users/patients/offices.
5. **Drop dead patterns** — `/offices/next-id` (server-assigned), the duplicated `users/{id}/{id}/ip-rules` bug.
6. **Centralize dropdowns** — one `useDefinitions(groupCode)` hook replaces the 13 metadata calls.
7. **Re-run `node scripts/api-drift-report.mjs`** after each backend change to watch ✅ counts rise.

---

## 6. Final Migration Recommendation (prioritized roadmap)

### Phase 1 — Quick wins, zero/near-zero backend (Category A + B)
- Remap and migrate, feature by feature, every **A-Direct/A-Remap** endpoint (47% of surface): auth, tenants, offices, patients CRUD+search, appointments, procedures, payments, claims, procedure-codes, operatories, providers, treatment-plan CRUD.
- Verb fixes `PUT→PATCH`.
- Backend **B-1**: expose `check-duplicate` + `patients/metadata` (trivial).
- **Recommended first pilot:** the **Users grid** via `useListUsers` + `useListUserOffices` + `useListOffices` join — proves the compose-and-map pattern end-to-end with no backend dependency (home-office column restored via the join, resolving the blocker from the earlier pilot attempt).

### Phase 2 — Cross-cutting backend enablers, then remap (Category C-1, C-2)
- Backend ships **C-1 (filters)** and **C-2 (`definitions` group filter)**.
- Frontend collapses the ~28 dependent endpoints into clean generated queries: scheduler day views, claims-by-patient, treatment-plans-by-patient, all dropdowns, providers-by-office, time-clock-by-user, user-offices joins.

### Phase 3 — Billing/Ledger depth (Category C-3)
- Backend enriches patient balance (aging/insurance/recent) and/or adds a ledger aggregate.
- Frontend builds the Ledger view by composing the (now filterable) procedure/payment/claim resources + client-side running balance; restore the Balances tab fully.

### Phase 4 — Net-new, only if justified (Category D)
- Decide per-feature: **adjustments** model, user **groups/ip-rules/preferences**, **signup**. Build only what product confirms; otherwise retire the corresponding UI or use existing alternatives (invite-only user creation).

> Net effect: ~94% of the frontend's needs are served by adapting to the existing backend; the remaining work is concentrated into 3 small cross-cutting enhancements plus ≤5 genuinely new endpoints — exactly the "maximize reuse, minimize backend build" outcome targeted.
