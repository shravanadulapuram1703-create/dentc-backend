# FE ↔ BE Integration Findings (Investigation)

> ⚠️ **Superseded by [`API_MIGRATION_ANALYSIS.md`](./API_MIGRATION_ANALYSIS.md).** This doc matched endpoints by exact path only and therefore over-counted "missing" routes. The migration analysis adds semantic (renamed-resource) mapping and shows ~94% of frontend needs already have a backend equivalent. Keep this only for the live 404-vs-401 verification detail.

> Companion analysis to the auto-generated [`API_DRIFT_REPORT.md`](./API_DRIFT_REPORT.md).
> Date of live verification: 2026-05-31, backend `DentC Backend v1.0.0` at `http://127.0.0.1:8000`.

## Headline

The frontend was built against an API contract (see [`docs/api-contracts/`](./api-contracts/)) that the **current running backend only partially implements**, and the backend's **OpenAPI schema is incomplete** — several working routes are not advertised in `openapi.json`.

Because Orval generates strictly from the schema, this matters: a route that works in the browser but is missing from the schema **cannot** get a generated client until the backend exposes it.

## Backend action checklist (hand to backend team)

**P1 — Expose already-working routes in OpenAPI** (`include_in_schema=True`, or mount the router into the documented app). These return `401` live but are absent from `openapi.json`, so Orval can't generate them yet:

- [ ] `GET /api/v1/users/list-with-home-office`  ← unblocks the Users-grid pilot
- [ ] `GET /api/v1/users/all-tenants`
- [ ] `GET /api/v1/users/me`
- [ ] `GET /api/v1/offices`
- [ ] `GET /api/v1/patients/search`
- [ ] `POST /api/v1/patients/check-duplicate`
- [ ] `GET /api/v1/patients/metadata`

**P2 — Align update verbs.** Decide `PUT` vs `PATCH` and make the schema authoritative:

- [ ] `PATCH/PUT /api/v1/users/{id}` (frontend sends `PUT`, schema says `PATCH`)
- [ ] `PATCH/PUT /api/v1/patients/{id}` (same)

**P3 — Decide the fate of unimplemented features** (implement, or confirm the UI should be rebuilt onto the existing resource model such as `/insurance-claims`, `/appointments`):

- [ ] Patient Ledger / Billing (`/patients/{id}/ledger|balances|claims|procedures|payments|adjustments`, `/metadata/*` code lists)
- [ ] Scheduler (`/scheduler/*`, `/procedures/codes`, `/procedures/categories`)
- [ ] Patient metadata dropdowns (`/patients/metadata/genders|titles|states|…`)
- [ ] User sub-resources (`/users/{id}/groups|ip-rules|preferences|time-clock`)
- [ ] Misc (`/users/me/access`, `/auth/signup`, `/patients/chart/{chartNo}`)

**Verify after P1/P2:** `npm run api:sync && node scripts/api-drift-report.mjs` — the report should move the P1 rows from ❌ to ✅ and the P2 rows off METHOD-MISMATCH.

## Three categories (live-verified)

Every endpoint the frontend calls falls into one of three buckets. HTTP status from an **unauthenticated** probe distinguishes them: `401` = route exists (auth required), `404` = route not registered.

### 1. ✅ In schema — Orval covers today
`POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`,
`GET /users`, `POST /users`, `GET /users/{id}`, `PATCH /users/{id}`, `DELETE /users/{id}`,
`GET /patients`, `POST /patients`, `GET /patients/{id}`, `PATCH /patients/{id}`, `DELETE /patients/{id}`,
`GET /patients/{id}/balance`.

### 2. 🟡 Works live, but **missing from the schema** (backend should expose)
Confirmed `401` (real) yet absent from `openapi.json`:

| Endpoint | Used by |
|---|---|
| `GET /users/list-with-home-office` | UserSetup (the user grid) |
| `GET /users/all-tenants` | UserSetup |
| `GET /users/me` | Auth / profile |
| `GET /patients/metadata` | Patient forms |
| `GET /patients/search` | Patient search |
| `POST /patients/check-duplicate` | Add patient |
| `GET /offices` | UserSetup, office pickers |

> **Backend action:** these are almost certainly registered with `include_in_schema=False`, or on a router not mounted into the documented app. Exposing them in OpenAPI is a low-effort, high-value fix — it immediately makes them Orval-generatable.

### 3. ❌ Truly absent (404) — not implemented on this backend
Whole feature areas the UI expects are not present:

- **Patient Ledger / Billing** — `/patients/{id}/ledger`, `/patients/{id}/balances` (note: schema has singular `/balance` with a different shape), `/patients/{id}/claims`, `/patients/{id}/procedures`, `/patients/{id}/payments`, `/patients/{id}/adjustments`, `/metadata/*` code lists.
- **Scheduler** — the entire `/scheduler/*` namespace + `/procedures/codes`, `/procedures/categories`.
- **Patient metadata dropdowns** — `/patients/metadata/genders`, `/titles`, `/states`, etc.
- **User sub-resources** — `/users/{id}/groups`, `/ip-rules`, `/preferences`, `/time-clock`.
- **Misc** — `/users/me/access`, `/auth/signup`, `/patients/chart/{chartNo}`.

The backend exposes generic CRUD equivalents for some of these (`/insurance-claims`, `/ledger-insurance-details`, `/appointments` under different tags) — i.e. the **resource model is shaped differently** than the UI's aggregate/patient-scoped endpoints.

## Two method mismatches (real bugs)
The schema defines `PATCH` for updates, but the frontend sends `PUT` — these would 405 against this backend:

- `updateUser` → `PUT /users/{id}` (backend: `PATCH`)
- `updatePatient` → `PUT /patients/{id}` (backend: `PATCH`)

## Implications for the migration

- **The schema is not yet a complete source of truth.** Orval-from-schema only safely covers Category 1 today. Category 2 needs a backend schema fix first; Category 3 needs backend implementation (or confirmation the UI should adopt the backend's different resource model).
- **The Users-list pilot has a shape gap.** `UserSetup` renders home-office columns sourced from the undocumented `list-with-home-office`. The documented `list_users` returns `UserRead` (`id, tenant_id, email, username, first_name, last_name, phone, role, is_active, must_change_password, last_login_at, created_at`) — **no home-office data**. Migrating the grid to `useListUsers` as-is would drop those columns (a regression on a currently-working screen).

## Recommended next steps (in order)

1. **Backend: expose Category-2 routes in OpenAPI** (`include_in_schema=True` / mount the routers). Cheapest win; unblocks real Orval coverage for search, metadata, user grid, profile.
2. **Backend: align update verbs** or accept both — decide `PUT` vs `PATCH` and make the schema authoritative.
3. **Product/Backend: decide the fate of Category-3 features** (ledger, scheduler, dropdowns). Either implement them, or confirm the UI should be rebuilt onto the backend's existing resource model (`/insurance-claims`, `/appointments`, …).
4. **Then pilot.** Once `list-with-home-office` (or an equivalent with home-office data) is in the schema, the Users grid becomes a clean, no-regression Orval pilot.

Until step 1 lands, any pilot either (a) targets only the small Category-1 set, or (b) knowingly accepts a UI regression. This is the decision to make before writing pilot code.
