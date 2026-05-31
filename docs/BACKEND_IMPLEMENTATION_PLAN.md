# Backend Implementation & Enhancement Plan — Dental PMS (FastAPI)

> **Scope context:** Reconciliation of the Frontend API Migration report against the *actual* `app/` backend (the greenfield rebuild, not `legacy_app/`). All findings below are code-verified. The headline conclusion: **~94% of the requested surface is already serviceable with zero or config-only backend change.** The dominant real work is a single, cross-cutting **OpenAPI-exposure** enhancement to the CRUD engine — not new query logic, and emphatically not rebuilding the legacy nested endpoints.

---

## 1. Backend Gap Analysis

### 1.1 Classification of each reported mismatch class

| Class | Report framing | **Verified classification** | Rationale (code-backed) | Dependencies | Risks |
|---|---|---|---|---|---|
| **A** (47%, "no backend change") | FE-only remaps / verb / pagination | **No-change** ✅ | PATCH confirmed (`router_factory.py:135`); `{items,meta}` confirmed (`common.py:32-39`); `{"error":{...}}` confirmed (`exceptions.py:74-75`); single `HTTPBearer` (`deps.py:27`, `main.py:90-95`); all 8 A-Remap CRUD targets exist in `registry.py`. | None | None — schedule **zero** backend work. |
| **B** (2%, "exists live, hidden from schema") | `include_in_schema=True` flip, "Trivial" | **INCORRECT → Net-new / Drop** | `check-duplicate` & `patients/metadata` exist **only in `legacy_app/`**; **zero** matches in `app/`. No `include_in_schema=False` route to flip. The `401` probe hit a stale/legacy target. | — | Scheduling these as "trivial" would be wrong work against a non-existent route. |
| **C-1** (relational filters) | "lists accept only `search`; add filters" | **OpenAPI-only** (equality) **+ Minor-enhancement** (date-range) | Equality filters **already work at runtime**: `CRUDBase.list` applies them (`base.py:76-79`), `register_crud` passes them (`router_factory.py:97-106`), and `registry.py` already declares them for ~all target entities. They are simply **invisible in OpenAPI** (read from `request.query_params`, not declared `Query(...)` params). | The engine change must land before FE Orval regen | Medium — dynamic `__signature__` is the one delicate spot. |
| **C-2** (definitions `group_code`) | "add `group_code` filter" | **OpenAPI-only** (code) **+ data-alignment** (real work) | Filter already declared (`registry.py:237-239`) and functional. The genuine risk is **data**: the 16 FE `group_code` literals are FE-invented snake_case and likely do **not** match migrated Denticon codes; `seed.py` seeds no definitions. | C-1 engine change (shared mechanism); DB enumeration | **Medium (data)** — silently-empty dropdowns if codes unreconciled. |
| **C-3** (balance/ledger enrichment) | enrich balance; add ledger | **Minor-enhancement** (balance) **+ optional Net-new** (ledger aggregate) | `GET /patients/{id}/balance` exists but minimal (`balance_service.py:28-61`); enrichment is additive aggregates. Ledger is **composable client-side** (all three source lists exist); optional thin server aggregate recommended for `running_balance` precision. | C-1 exposure (so Orval sees `patient_id`); `payment_type` data semantics | Medium — Decimal precision, `is_archived` handling, `payment_type` classification unknown. |
| **D** (6%, net-new) | new resources | **Net-new — confirmed** (build only if product confirms) | `user_preferences`, `user_groups`/membership, `user_ip_rules`, `signup` exist **only in `legacy_app/`**; none in `app/db/models/` nor the migration schema. | New tables → models → Alembic → `_cfg` rows | Varies; signup is **high** (tenant assignment/security). |

### 1.2 Frontend assumptions to correct (PROMINENT)

These are stale or incorrect claims in the FE report that must be struck or re-scoped **before** any work is scheduled. Each would otherwise cause wasted or broken work.

| # | FE assumption | Reality (code-verified) | Correct action |
|---|---|---|---|
| **FA-1** | `POST /patients/check-duplicate` "exists live, just hidden from schema" (returned `401`) | Exists **only in `legacy_app/`**. In current `app/` it would `404`. The `401` came from an unauthenticated probe or a **stale/legacy deployment**. | **Strike B-1.** Use existing `GET /patients?search=` (search covers name/chart_no/email/phone — `registry.py:81`). Only build a strict boolean route if product insists (Minor-enh, ~0.5d). |
| **FA-2** | `GET /patients/metadata` "exists live, just hidden" | Exists **only in `legacy_app/`**. Not in current `app/`. | **Drop entirely.** Fully redundant with C-2 (`GET /definitions?group_code=`). Recommend **never build**. |
| **FA-3** | `GET /users/{id}/{id}/ip-rules` (duplicated `{id}` path param) | **Frontend bug** — duplicated path parameter. Not a backend concern. | FE fixes the path. Target resource (if built) is `GET /user-ip-rules?user_id={id}`. |
| **FA-4** | `/offices/next-id` prefetch needed, and the "server assigns id" pattern generalizes | True **only for offices** (`offices.id` is auto-int → excluded from `OfficeCreate`, `factory.py:53,61`). **String-PK entities** (appointments, providers, operatories, treatment-plans, patient-procedures, patient-payments, insurance-claims, procedure-codes) require the **FE to generate & send the `id`** (`factory.py:10`). | Drop `next-id` for offices. For string-PK POSTs, FE must **generate client-side IDs** (e.g. `APPT-*`) — still FE-only, but *not* a rename. Do **not** over-generalize. |
| **FA-5** | Update verb is `PUT` | Backend is **PATCH everywhere** (`router_factory.py:135`, `users.py:80`); no PUT routes exist. | FE switches `PUT→PATCH`. Zero backend work. |
| **FA-6** | Lists "accept only a generic `search` string" (C-1) | **FALSE.** Equality filters function today (`base.py:76-79`). | Reframe C-1 as **OpenAPI exposure**, not new filter logic. |
| **FA-7** | `time-clock`, `adjustments`, `auth/me-full`, `users/me/access` need C-1 first | The `user_id` / `patient_id` / `payment_type` filters they depend on **already exist** in `registry.py`. | All four work **today** via existing filters/compose. No C-1 prerequisite. |
| **FA-8** | Category B = 2% of surface | Should be **0%** — both B items move to Net-new/Drop. | Adjust report counts. |

---

## 2. Backend Architecture Review

### 2.1 Module structure (as-built, conformant)

| Layer | Location | Notes |
|---|---|---|
| Entry / app factory | `app/main.py` | CORS → `RequestContextMiddleware`; mounts v1 under `/api/v1`; asserts unique `operation_id`s (fail-fast); injects global `BearerAuth`. |
| Routing assembly | `app/api/router.py` | Mounts `auth, users, billing, treatment, balances, audit` **then** the generated CRUD entity router. |
| CRUD engine | `app/crud/base.py`, `app/crud/router_factory.py` | `CRUDBase` (tenant-aware list/get/create/update/soft-delete) + `register_crud` (5 standard routes). |
| Schema factory | `app/schemas/factory.py` | `build_schemas()` derives named `Create`/`Update`/`Read` components from ORM models. |
| Entity registry | `app/api/v1/registry.py` | One `_cfg(...)` row per entity (73 CRUD). |
| Service overrides | `app/services/*.py`, supplemental routers (`billing.py`, `treatment.py`, `balances.py`, `audit.py`) | For entities with real rules. |

### 2.2 Service layer & data access

- **No repository layer** — `CRUDBase` *is* the data-access abstraction, instantiated per entity. This is deliberate and works; do not introduce a repository pattern.
- **Tenant scoping** is enforced centrally in `CRUDBase._scope_tenant` (`base.py:49-52`) and `get_tenant_id` (`deps.py:64-74`). Column-based, no `SET search_path`, no tenant middleware. **Preserve this invariant** in every new aggregate (balance, ledger).
- **Services** (`balance_service`, billing/treatment services) hold the only hand-written SQL/business logic; they must always re-apply the `tenant_id` guard explicitly (as `balance_service.py:33-37` does).

### 2.3 Validation, DTO design, pagination/filtering standards

- **DTOs** are generated (`{Name}Read/Create/Update`) — named components, snake_case, string PKs required in Create, auto-int PKs excluded. Honor this; do not hand-write DTOs for generated entities.
- **Pagination** = `PaginatedResponse[T]` → `{items, meta:{page,size,total,pages}}` (`common.py:32-39`); typed params via `get_pagination` (`deps.py:99-106`): `page, size, sort, order, search`.
- **Error contract** = `{"error":{code,message,details}}` (`exceptions.py:74-75`), four handlers, named `ErrorResponse`/`ErrorDetail` components.

### 2.4 KEY INSIGHT — filters work functionally but are OpenAPI-invisible

This is the architectural crux of the entire plan:

> `CRUDBase.list` applies equality filters (`base.py:76-79`); `register_crud` forwards them (`router_factory.py:97-106`); but the values are read from **`request.query_params` inside the handler body** via `_coerce` (`router_factory.py:44-60`) — **not** declared as `Query(...)` function parameters.

**Consequence:** FastAPI derives query params from the handler **signature**, which today exposes only `db, tenant_id, page, request`. Therefore the filter params **never appear in `openapi.json`**, and **Orval cannot generate typed filter arguments**. A caller can hit `GET /insurance-claims?patient_id=123` and it works — but the generated client has no `patient_id` argument.

**The single highest-leverage fix:** generate explicit typed `Query(...)` params on the list route **from `CrudConfig.filter_fields`**, by building a dynamic `inspect.Signature` (one `inspect.Parameter` per filter field, `Annotated[<col python_type> | None, Query(None, ...)]`, deriving `python_type` from `sa_inspect(model).columns[f].type.python_type` — the same source `_coerce` already uses). This makes filters **validated, coerced, AND documented** in one engine change covering all 73 routers, and lets `_coerce` be retired.

> **Constraint:** `router_factory.py` must **not** add `from __future__ import annotations` (`router_factory.py:8`) — the `body: cfg.create_schema` annotation must remain a real class. The dynamic `__signature__` work must preserve this.

### 2.5 Auth/z

JWT access+refresh, Redis whitelist/blacklist, single `users.role` varchar (Phase-1). Guard with `require_roles(...)`. Full RBAC deferred to Phase 4 — **do not** pre-empt it with the D-2a user-groups work unless product accepts the overlap.

---

## 3. Phase-wise Roadmap

### Phase 1 — Quick Wins (config & confirmation only; **zero engine risk**)

| Task | Type | Detail |
|---|---|---|
| **P1-verb** | Confirm/FE | Backend already PATCH. Confirm, document, no code. |
| **P1-pageadapter** | Confirm/FE | `{items,meta}` stable & named. FE writes `toOffsetPagination`. No code. |
| **P1-remaps** | Confirm/FE | All 8 A-Remap targets + compose-sources (`/tenants`, `/user-offices`, `/operatories`, `/providers`, `/time-clock-entries`, `/definitions`, `/claim-submissions`) verified present. No code. |
| **P1-chartno** | Registry | Add `"chart_no"` to the Patient `filters` tuple (`registry.py:80-83`). One-word edit. |
| **P1-strikeB** | Doc | Strike B-1; fold metadata into C-2; redirect check-duplicate to `?search=`. |
| **P1-idgen** | FE flag | Document that string-PK POSTs need FE-generated IDs (FA-4). |

### Phase 2 — Cross-cutting OpenAPI exposure (the core engineering work)

| Task | Type | Detail |
|---|---|---|
| **C-1 (typed filters)** | Engine | In `router_factory.py` `list_items`: build dynamic typed `Query(None)` params from `cfg.filter_fields`; assign `__signature__`; read from `**kwargs`; retire `_coerce`; drop `request` once unused. One change → all 73 routers exposed. |
| **C-1 (date-range)** | Engine | Add `range_fields: tuple[str,...] = ()` to `CrudConfig`; emit `{field}_from`/`{field}_to` typed `Query(None)` params; add optional `range_filters` arg to `CRUDBase.list` applying `>= lo` / `<= hi` (guarded by `hasattr` + `not None`). Additive; existing routes unaffected. Apply `date` range to `appointments`, `patient_procedures`, `patient_payments`. |
| **C-2 (code)** | Confirm | `group_code` already exposed once C-1 engine lands — no separate code. |
| **C-2 (data)** | Data | Enumerate distinct `definitions.group_code` in `recondental_migrated`; build FE-name→real-code map; decide contract (FE adopts real codes **or** backend seeds canonical groups). Point FE discovery at existing `GET /definition-groups` (`registry.py:240`). **Blocker for C-2 "FE-ready".** |

### Phase 3 — Billing / Ledger enrichment

| Task | Type | Detail |
|---|---|---|
| **C-3 (balance enrich)** | Service+schema | Extend `balance_service.get_patient_balance` with estimates split, aging buckets, recent-activity; extend `PatientBalance` + 2 nested models in `schemas/billing.py`. Additive/optional fields → backward-compatible. Route file unchanged. |
| **C-3 (ledger, optional)** | Net-new (thin) | New supplemental router `app/api/v1/ledger.py` + service fn + `LedgerEntry`/`LedgerResponse`; server-side `Decimal` `running_balance`; date-range narrowing. Recommended but optional (composable client-side otherwise). |
| **C-3 prereq** | Data | Confirm `payment_type` insurance-vs-patient values against migrated data. |

### Phase 4 — Net-new (build only if product confirms)

| Task | Detail |
|---|---|
| **D-1 signup** | `POST /auth/signup`, reuses `users` table. **High security risk** (tenant assignment for unauthenticated caller). Prefer invite-only via `POST /users`. Defer pending design. |
| **D-2a user-groups** | +2 tables (`user_groups`, `user_group_memberships`) → models → Alembic → 2 `_cfg` rows. FE `GET /users/{id}/groups` → `GET /user-group-memberships?user_id=`. Overlaps Phase-4 RBAC. |
| **D-2b ip-rules** | +1 table (`user_ip_rules`) → model → Alembic → 1 `_cfg`. Storage only; **enforcement is a separate, larger task**. |
| **D-2c preferences** | +1 table (`user_preferences`, KV design) → model → Alembic → 1 `_cfg`. Low risk. |
| **D-adjustments** | **Reuse** `patient_payments` with `payment_type='adjustment'` — **zero backend** (matches Denticon source semantics). Do NOT build a new table. |
| **me-full / me/access** | Compose client-side today. Optional `GET /auth/me-full` convenience aggregate (no DB). `me/access` waits for RBAC. |

---

## 4. API Design Recommendations

### 4.1 C-1 — Typed filter params (engine-level, applies to all list routes)

- **Endpoint shape (per entity):** `GET /{plural}` gains, in OpenAPI, one optional typed param per `filter_fields` entry plus `{field}_from`/`{field}_to` per `range_fields` entry, alongside existing `page, size, sort, order, search`.
- **Query params (example, `GET /appointments`):** `patient_id:int?`, `provider_id:str?`, `operatory_id:str?`, `office_id:int?`, `date:date?`, `status:str?`, `date_from:date?`, `date_to:date?`, `page, size, sort, order, search`.
- **Response:** unchanged — `PaginatedResponse[AppointmentRead]`.
- **Validation:** FastAPI-coerced from declared types (replaces manual `_coerce` casting).
- **Security/pagination:** unchanged.
- **OpenAPI:** all filters now documented; Orval generates typed args.

### 4.2 C-3 — Enriched patient balance (additive)

- **Endpoint:** `GET /patients/{patient_id}/balance` (unchanged path/op-id).
- **Response model** `PatientBalance` (additive, snake_case, all money as `Decimal`):

```
patient_id, total_charged, total_paid, balance        # existing — unchanged
account_balance                                        # = balance (FE alias)
estimated_insurance, estimated_patient                 # SUM over non-void, non-archived procedures
patient_balance                                        # patient-responsible open
aging: { current, b30, b60, b90, b120 }                # nested: BalanceAging
recent_activity: { today, last_ins, last_pat }         # nested: BalanceRecentActivity
as_of                                                  # existing
```

- **Computation:** estimates = `SUM(insurance_estimate)` / `SUM(patient_estimate)` on `PatientProcedure` (non-void, non-archived); aging = **Option A** (procedure-charge buckets via CASE on `CURRENT_DATE - date_of_service`: 0–30 / 31–60 / 61–90 / 91–120 / 120+); recent_activity over `PatientPayment` (today's sum, latest insurance, latest patient). All `coalesce(...,0)`, kept `Decimal`.
- **Caveat:** exclude `is_archived` rows (current code ignores this — must fix for consistency). `payment_type` classification values **must be confirmed against migrated data**.
- **Cache:** keep existing key `balance:{tenant_id}:{patient_id}`, 30s TTL. No write-path invalidation added (TTL-only is sufficient for C-3).

### 4.3 C-3 — Optional ledger aggregate

- **Endpoint:** `GET /patients/{patient_id}/ledger` (supplemental router, not a registry row).
- **Query params:** `date_from?`, `date_to?`, `page`, `size`.
- **Response:**

```
LedgerEntry: { entry_date, entry_type ("procedure"|"payment"|"claim"|"adjustment"),
               source_id, description, charge, credit, running_balance,
               procedure_code?, tooth?, payment_type?, claim_number?, status? }
LedgerResponse: { patient_id, entries:[...], opening_balance, closing_balance, as_of }
```

- **Logic:** UNION non-void/non-archived procedures (charge=fee), payments (credit=amount), optional claims; sort by `(entry_date, entry_type, source_id)`; compute `running_balance` server-side in `Decimal` over full set before slicing. Tenant-scoped.
- **Security:** same auth/tenant guard; not cached initially.

### 4.4 Net-new resources (Phase 4, if confirmed)

- **`POST /auth/signup`** — public route; body `{tenant_context, email, password, ...}`; hashes password (mirror `users.py:66-71`); the **tenant-assignment policy is the design gate**.
- **`/user-groups`, `/user-group-memberships`, `/user-ip-rules`, `/user-preferences`** — standard generated CRUD via `_cfg` once tables exist; filters: groups `("is_active",)`, memberships `("user_id","group_id")`, ip-rules `("user_id","is_active")`, preferences `("user_id",)`.
- **`GET /auth/me-full`** (optional) — composed `MeFullRead` = `UserRead` + assigned offices + tenant; no DB change.

---

## 5. Database Impact Analysis

### 5.1 Zero-schema-change items (STRESS)

> **C-1, C-2, and C-3 require ZERO schema changes.** C-1/C-2 are OpenAPI exposure over existing columns; C-3 aggregates over existing `PatientProcedure` / `PatientPayment` columns. `audit_logs` already exists (Alembic `a1b2c3d4e5f6`). Adjustments **reuse** `patient_payments` (no table).

### 5.2 New tables — only the D items (build only if product confirms)

| Table | Columns (sketch) | Relationships | Indexes |
|---|---|---|---|
| `user_preferences` | `id PK, tenant_id FK, user_id FK→users, pref_key VARCHAR(100), pref_value JSONB/TEXT NULL, updated_at` | FK user; `unique(user_id, pref_key)` | `(tenant_id, user_id)` |
| `user_groups` | `id PK, tenant_id FK, name VARCHAR(255), description TEXT NULL, is_active BOOL, created_at` | FK tenant | `(tenant_id, is_active)` |
| `user_group_memberships` | `id PK, tenant_id FK, user_id FK→users, group_id FK→user_groups, created_at` | FK user, group; `unique(user_id, group_id)` | `(tenant_id, user_id)`, `(group_id)` |
| `user_ip_rules` | `id PK, tenant_id FK, user_id FK→users, ip_address VARCHAR(45), rule_type VARCHAR(10) ('allow'\|'deny'), description VARCHAR(255) NULL, is_active BOOL, created_at` | FK user | `(tenant_id, user_id)` |
| `patient_adjustments` *(NOT recommended)* | mirrors payments | — | — | **Reuse `patient_payments` instead.** |

### 5.3 Migration & compatibility

- **Alembic:** each D table = one autogenerate revision (`revision --autogenerate -m`, then `upgrade head`). New tables only; **no alterations** to existing tables.
- **Backward compatibility:** all C-* changes are additive (new optional response fields, new optional query params) — no breaking changes; existing consumers unaffected. New models register on `Base.metadata` via `app.db.models`.
- **Signup (D-1):** **no schema change** (reuses `users`).

---

## 6. OpenAPI Strategy

| Aspect | Direction |
|---|---|
| **Filter visibility** (top priority) | Generate explicit typed `Query(...)` params from `CrudConfig.filter_fields` + `range_fields` so every list filter appears in `openapi.json` and Orval emits typed args. Single engine change. |
| **Organization / tags** | Keep domain tags (Organization, Patients, Insurance, Procedures, Appointments, Treatment Plans, Clinical, Billing, Metadata, Communications, Staff, Imaging) → Orval `tags-split`. New routers (`ledger`, signup) tagged into existing domains (Billing, Auth). |
| **operation_id** | Keep `list_/create_/get_/update_/delete_{singular\|plural}` convention; uniqueness asserted at startup (`main.py:71-76`). New aggregates get explicit ids (`get_patient_ledger`, `get_me_full`). |
| **Schema reuse** | Reuse generated `{Name}Read/Create/Update`, `PaginatedResponse[T]`, `ErrorResponse`, `PageMeta`. New nested models (`BalanceAging`, `BalanceRecentActivity`, `LedgerEntry`, `LedgerResponse`) as named components. |
| **Response/error standardization** | All new endpoints use `{items,meta}` (lists) and `{"error":{...}}` (errors); declare error responses for Orval typing. |
| **Orval compatibility** | snake_case enforced (no `alias`/`by_alias`). Regenerate client after C-1 lands so filter args appear. |

---

## 7. Implementation Priority Matrix

| Change ID | Description | Business Impact | Eng. Effort | Tech Risk | Dependencies | Priority |
|---|---|---|---|---|---|---|
| **P2-verb** | Confirm PATCH (FE switches PUT→PATCH) | Med (unblocks all writes) | 0 (BE) | None | — | **P0** |
| **P1-pageadapter** | FE pagination adapter | Med | 0 (BE) | None | — | **P0** |
| **P1-remaps** | Confirm 8 A-Remap targets + compose sources | High | 0 (BE) | None | — | **P0** |
| **P1-chartno** | Add `chart_no` to Patient filters | Med | 1 line | Trivial | C-1 (for OpenAPI) | **P0** |
| **C-1** | Typed filter `Query` params from `filter_fields` (all 73 routers) | **High** (unlocks Orval typed filters, ledger, dropdowns) | ~1 day +tests | **Medium** (dynamic `__signature__`) | none (enabler for rest) | **P0** |
| **C-1r** | Date-range (`range_fields` + `CRUDBase` `>=`/`<=`) | Med (day/range views) | ~0.5 day | Low (additive) | C-1 | **P1** |
| **C-2** | `group_code` exposure (code) | Med | 0 (rides C-1) | Low | C-1 | **P1** |
| **C-2d** | Definitions `group_code` **data alignment** | **High** (dropdowns work) | ~0.5–1 day | **Medium (data)** | DB enumeration | **P1** |
| **C-3** | Enriched balance (estimates/aging/recent) | High | ~0.5 day | Med (Decimal, `is_archived`, `payment_type`) | C-3 data check | **P1** |
| **C-3l** | Optional ledger aggregate | Med (perf/precision) | ~Medium | Med | C-1, C-3 | **P2** |
| **B-1** | check-duplicate / metadata | Low | Drop (use `?search=` / C-2) | Low | — | **Drop** |
| **D-adj** | Adjustments via `patient_payments` | Med | 0 (FE remap) | Low | — | **P1 (FE)** |
| **D-1** | `POST /auth/signup` | Cond. | 1–2 days | **High** (tenant/security) | Product + security design | **P3 (gated)** |
| **D-2a** | user-groups + membership | Cond. | ~1 day | Med (RBAC overlap) | Product | **P3 (gated)** |
| **D-2b** | user-ip-rules (storage) | Cond. | ~1 day | Med (enforcement separate) | Product | **P3 (gated)** |
| **D-2c** | user-preferences | Cond. | ~0.5–1 day | Low | Product | **P3 (gated)** |
| **D-mefull** | `GET /auth/me-full` aggregate | Low | ~0.5 day | Low | — | **P3 (optional)** |

---

## 8. Final Execution Plan

### 8.1 Exact sequence

1. **Phase 1 (Quick Wins, ~0.5 day, trivial complexity).**
   - Confirm PATCH, `{items,meta}`, error contract, single bearer — document, no code.
   - Verify all 8 A-Remap targets + compose sources exist.
   - `registry.py`: add `"chart_no"` to Patient `filters`.
   - Strike B-1 from the FE report; redirect to `?search=` / C-2; document FA-1…FA-8 (esp. **FA-4** client-side ID generation for string-PK POSTs).
2. **Phase 2 (Cross-cutting, ~1.5 days, medium complexity — the keystone).**
   - **C-1:** implement dynamic typed `Query(...)` signature in `router_factory.py` `list_items` from `cfg.filter_fields`; retire `_coerce`; **preserve the `body: cfg.create_schema` real-annotation rule (no `from __future__`)**. Test the generated `openapi.json` + a couple of live list calls across entities.
   - **C-1r:** add `range_fields` + `CRUDBase.list` range support; apply `date` ranges to appointments/procedures/payments.
   - **C-2 code** rides C-1 (no extra code).
   - **C-2 data:** enumerate real `definitions.group_code`, agree FE↔data contract, point FE discovery at `GET /definition-groups`.
3. **Phase 3 (Billing/Ledger, ~1 day + optional, medium complexity).**
   - Confirm `payment_type` semantics (data).
   - **C-3:** enrich `balance_service` + extend `PatientBalance` (+ `BalanceAging`, `BalanceRecentActivity`); fix `is_archived` exclusion.
   - **C-3l (optional):** add `ledger.py` aggregate with `Decimal` running balance.
4. **Phase 4 (Net-new, gated, variable complexity).** Only on product confirmation: adjustments (FE remap, free), preferences (low), groups/ip-rules (med, mind RBAC overlap), signup (high — design tenant assignment first), optional `me-full`.

### 8.2 Task dependencies

- **C-1 is the linchpin** — C-2 (code), C-3 Orval visibility, and ledger source queries all depend on it. Land it first in Phase 2.
- C-2 "FE-ready" depends on the **data enumeration**, not code.
- C-3 enrichment depends on the **`payment_type` data check** for `recent_activity` and the insurance/patient split.
- D-2a (groups) should **not** precede a Phase-4 RBAC design decision.

### 8.3 Risks & mitigations

| Risk | Mitigation |
|---|---|
| Dynamic `__signature__` breaks body annotation or a route | Keep the real `body: create_schema` annotation; **never** add `from __future__ import annotations`; assert spec validity + live list calls in tests; it's one engine change, so a single thorough test pass covers all 73 routers. |
| C-2 silently-empty dropdowns (code mismatch) | Enumerate real `group_code`s **before** marking C-2 FE-ready; agree explicit FE↔data contract; use `GET /definition-groups` for discovery. |
| C-3 Decimal drift / archived rows / `payment_type` ambiguity | Keep aggregation in `Decimal`; exclude `is_void` **and** `is_archived`; verify `payment_type` values against migrated data before coding. |
| Signup tenant leakage / spam | Gate on product + security design (invite token vs new tenant); prefer invite-only `POST /users`. |
| Over-generalizing offices "server-assigns id" | Document FA-4 explicitly; FE generates string PKs for appointments/procedures/payments/claims/treatment-plans. |

### 8.4 Recommended deployment order

`Phase 1 (config)` → `C-1 engine + C-1r` (regenerate Orval client immediately after) → `C-2 data alignment` → `C-3 balance enrichment` → `C-3 ledger (optional)` → `Phase 4 gated net-new`. Deploy each phase independently; all C-* changes are additive and backward-compatible, so no coordinated FE/BE cutover is required except the **Orval regeneration after C-1** (which only *adds* typed filter args).

### 8.5 Reinforcement

- **~94% reuse.** Category A (47%) is backend-free; C-1/C-2/C-3 are exposure/enrichment over **existing** columns and routes; only the D items (6%, all gated on product) are truly net-new.
- **Do NOT rebuild the legacy nested endpoints.** `check-duplicate`, `patients/metadata`, `users/{id}/groups|ip-rules|preferences`, `me-full`, `adjustments` are either stale legacy artifacts, redundant with existing resources, composable client-side, or satisfiable by a single `_cfg` row — never a reimplementation of `legacy_app/`.
- **One change dominates everything:** make the **already-working filters OpenAPI-visible** in `app/crud/router_factory.py`. That single engine enhancement delivers the bulk of the FE report's "Category C" value.