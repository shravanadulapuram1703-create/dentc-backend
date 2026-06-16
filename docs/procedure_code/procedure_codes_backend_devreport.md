# Procedure Code Setup — Screen Analysis & Backend Dev Report

Route: `/setup/procedure-codes/procedure-codes`
Component: `src/components/setup/procedure-codes/ProcedureCodeSetup.tsx`
Status: **Shipped & live-verified** (local :5173, backend :8000 — 1,108 codes loaded)

Sibling screen: **Explosion Codes Setup** — `/setup/procedure-codes/explosion-codes`,
`src/components/setup/procedure-codes/ExplosionCodeSetup.tsx` (+ `IncludedCodes.tsx`).
**Shipped & live-verified** (40 code-bundles loaded; detail + included-codes grid + picker).
See §8.

---

## 1. Screen Analysis

**Purpose** — Manage the practice's CDT/procedure-code catalog: general info, fees,
clinical charting rules, recall/scheduling defaults, and a read view of per-schedule
pricing. Replaces the `PlaceholderPage` that previously occupied this route.

**Workflow** (from legacy screenshots, used as reference only — UI is modernized to
match the existing Provider/Insurance setup design system):

- Left rail: sort by Code/Description, filter by category, free-text search, scrollable list.
- Detail pane: three tabs — **Main**, **Charting**, **Fee Schedules**.
- Add / Edit / Delete a code.

**Modern implementation** — master-detail (list ⇄ tabbed detail) identical in look to
`ProviderSetup`, plus a **KPI dashboard strip** (Total / Active / Inactive / Categories /
Ortho) computed client-side from the full code set. snake_case throughout, no mock data.

**UI components**: `KpiStat` (shared dashboard tile), `MainTab`, `ChartingTab`,
`FeeSchedulesTab`, `procedureCodeData.ts` (form model + builders).

---

## 2. Existing API Mapping

| Action | Endpoint | Orval fn |
|---|---|---|
| List (paged, all pages loaded) | `GET /api/v1/procedure-codes` | `listProcedureCodes` |
| Create | `POST /api/v1/procedure-codes` | `createProcedureCode` |
| Update | `PATCH /api/v1/procedure-codes/{code}` | `updateProcedureCode` |
| Delete | `DELETE /api/v1/procedure-codes/{code}` | `deleteProcedureCode` |
| Fee schedule entries (per code) | `GET /api/v1/fee-schedule-entries?procedure_code=…` | `listFeeScheduleEntries` |
| Fee schedule names (join) | `GET /api/v1/fee-schedules` | `listFeeSchedules` |

**Primary key note** — `ProcedureCodeRead` has **no numeric `id`**; the `{item_id}` path
param is the `code` string itself. The frontend keys all read/update/delete on `code`.

**DTO fields used** (`ProcedureCodeRead` / `Create` / `Update`, all snake_case):
`code`, `legacy_code`, `description`, `category`, `default_fee` (numeric string),
`default_duration_minutes`, `requires_tooth`, `requires_surface`, `requires_quadrant`,
`requires_lab`, `is_ortho`, `billing_order`, `recall_interval`, `recall_unit`,
`is_active`, `created_at`.

---

## 3. Legacy Screen Analysis → Modernization Decisions

| Legacy element | Decision |
|---|---|
| MAIN tab (Description, Code, Category, Recall, Proc Time, Billing Order, Active flag, Ortho, etc.) | Mapped 1:1 to the backend fields above on the **Main** tab. Legacy "Default Notes Macro / Show ADA code / Taxable / Visit Code / Ledger Code / A/R Code…" booleans have **no backing columns** → omitted (see gaps). |
| CHARTING tab (Chart Category, Tooth Area, Draw As, surface min/max, Materials, **Valid Teeth** grid) | Backend exposes only `requires_tooth/surface/quadrant` booleans → surfaced as the **Charting** tab. Finer config flagged as a gap with an honest in-UI notice. |
| FEE SCHEDULES tab (Schedule / Fee Type / Fee-Pat / Ins / AMB) | Rebuilt as **Fee Schedules** tab — read view of `fee-schedule-entries` joined to schedule name + type. Editing stays in Fee Schedule Setup (single source of truth). |
| Category dropdown (DIAGNOSTIC, …) | **Derived from backend data** (distinct `category` values), not hardcoded. Create form uses a `<datalist>` so new categories are allowed. |

---

## 4. Workflow Completion

- ✅ Procedure listing (search / sort / category filter / status filter / KPIs)
- ✅ Procedure create / edit / delete
- ✅ Activate / deactivate (status field)
- ✅ Clinical config (tooth / surface / quadrant requirements + requires-lab)
- ✅ Financial config (default fee) + per-schedule fee view
- ✅ Scheduling defaults (duration minutes), recall interval/unit
- ✅ Ortho flag

---

## 5. Backend Gaps — RESOLVED (backend team shipped; frontend wired)

> **Update (2026-06-14):** the backend team implemented PROC-1, PROC-3, PROC-4, PROC-5
> (and the provider-side PROC-2). The Orval client was re-synced (`npm run api:sync`)
> and the frontend is now wired to the new fields/endpoints. Status below.

### ✅ PROC-1 — Per-procedure detailed charting config — **DONE**
`ProcedureCodeRead/Create/Update` now carry `chart_category`, `tooth_area`, `draw_as`,
`min_surfaces`, `max_surfaces`, `default_material_id`, and `valid_teeth: string[]`.
**Wired**: Charting tab now edits all of these; `default_material_id` is a select over
`GET /api/v1/chart-materials`; `valid_teeth` is a Universal-numbering tooth grid
(permanent 1–32 + primary A–T). The "awaiting backend" notice was removed.

### ✅ PROC-2 — Provider / specialty procedure permissions — **BACKEND DONE (provider-side)**
Endpoints `GET/PUT /api/v1/providers/{provider_id}/procedure-codes`
(`listProviderProcedureCodes` / `setProviderProcedureCodes`, body `ProcedureCodesSet`,
returns `AssignedProviderProcedureCodeRead[]`). These are **provider-scoped**, so the UI
belongs on the **Provider Setup** screen (a "Procedure Codes" tab), not on this screen —
tracked as a Provider Setup follow-up, not wired here.

### ✅ PROC-3 — Per-procedure insurance mapping — **DONE**
`GET/POST /api/v1/procedure-codes/{code}/insurance-rules` and
`PATCH/DELETE …/{rule_id}` (`ProcedureInsuranceRuleRead/Create/Update`: `coverage_pct`,
`frequency_limit`, `age_limit`, `wait_period`, `notes`, `is_active`).
**Wired**: new **Insurance** tab with inline CRUD. (Note: the list endpoint returns a
plain array, not a paginated envelope.)

### ✅ PROC-4 — Legacy "Main" booleans — **DONE**
`ProcedureCodeRead` now has `taxable`, `sales_tax_code`, `visit_code`, `ledger_code`,
`ar_code`, `is_post_op`, `exempt_from_dental_max`, `lock_default_provider`,
`default_provider_id`, `default_notes_macro_id`, `show_ada_code_in_notes`,
`nhs_treatment_category`, `nhs_clinical_data_set`.
**Wired**: Main tab gained "Billing & Tax Codes", "Provider & Notes Defaults" (selects over
`GET /providers` and `GET /note-macros`), and "NHS" sections.

### ✅ PROC-5 — Aggregation endpoint for KPIs — **DONE**
`GET /api/v1/procedure-codes/stats` → `ProcedureCodeStats { total, active, inactive,
ortho, by_category }`. **Wired**: KPI cards now read from this endpoint; the category
filter prefers `by_category` keys (falls back to derived). The full-catalog load remains
only for the client-side searchable list table.

### ◑ PROC-6 — `fee-schedules` list latency — **OPEN (perf)**
`GET /api/v1/fee-schedules?size=200` is still multi-second; the Fee Schedules tab needs it
only to resolve `fee_schedule_id → name`. **Suggested**: denormalize
`fee_schedule_name`/`fee_type` onto `FeeScheduleEntryRead`, or a lightweight `id,name`
projection. Non-blocking.

---

## 6. Validation Checklist

| Item | Status |
|---|---|
| List loads from backend | ✅ 1,108 codes, paged |
| Search / sort / category / status filters | ✅ client-side, derived options |
| KPI cards (backend-driven counts) | ✅ Total 1108, Categories 3, Ortho 33 |
| Open detail (code-locked, fields populated) | ✅ verified (10061) |
| Main tab edit fields | ✅ all bound to snake_case |
| Charting tab toggles | ✅ |
| Fee Schedules tab (entries joined to names) | ✅ verified (UCR-Excel Dental, CP-50) |
| Create / Update / Delete wired | ✅ (create/update/delete call generated client) |
| KPI cards from `/procedure-codes/stats` (PROC-5) | ✅ wired |
| Main tab billing/tax/defaults/NHS (PROC-4) | ✅ wired (provider + note-macro selects) |
| Charting tab full config + valid-teeth grid (PROC-1) | ✅ wired |
| Insurance tab CRUD (PROC-3) | ✅ wired |
| `npx tsc -b` (whole project) | ✅ clean |
| `npx eslint` (touched files) | ✅ clean |

> Note: the `api:sync` also split the schedule schemas (office vs provider) and dropped
> `effective_from` from the generic `ScheduleDayInput`. Two pre-existing files were
> realigned to the regenerated types: `src/services/officeScheduleApi.ts`
> (`ScheduleReplace` → `AppSchemasOfficeSetupScheduleReplace`) and
> `src/components/setup/providers/tabs/SchedulesTab.tsx`
> (`ScheduleDayInput` → `AppSchemasProviderSetupScheduleDayInput`).

---

## 7. Completion Summary

**Completed** — Backend-driven master-detail Procedure Code Setup with KPI dashboard
(now from the `/stats` aggregation), full CRUD, and four detail tabs:
- **Main** — general, financial, billing/tax codes, provider & notes defaults, scheduling/recall, NHS, flags (PROC-4).
- **Charting** — requirement toggles + chart display (category/area/draw-as/min-max surfaces/default material) + valid-teeth grid (PROC-1).
- **Insurance** — per-code coverage rules CRUD (PROC-3).
- **Fee Schedules** — read view of fee-schedule entries joined to schedule names.

No mock/hardcoded business data; categories from `stats.by_category`; provider / note-macro
/ chart-material selects from their respective endpoints.

**Outstanding** — PROC-6 (fee-schedules list latency, perf, non-blocking) and the
provider-side PROC-2 ("Procedure Codes" tab on **Provider Setup**, follow-up — endpoints
exist).

**Dependencies** — Fee Schedule Setup (`/setup/fee-schedules/fee-schedule-setup`) owns
fee-entry editing; this screen reads from it. Scheduler/Treatment-Planning consume
`default_duration_minutes` and `default_fee` respectively.

---

## 8. Explosion Codes Setup

Route: `/setup/procedure-codes/explosion-codes`
Components: `ExplosionCodeSetup.tsx` (master-detail) + `IncludedCodes.tsx` (items editor).
Status: **Shipped & live-verified** (40 code-bundles loaded; detail + 8-row included-codes
grid with joined descriptions; add-code picker verified).

**Backend = "Code Bundles"** (tag Procedures). An explosion code is a `CodeBundle`; the
"Included Codes" are `CodeBundleItem`s.

| Legacy field | Backend | Notes |
|---|---|---|
| ID# | `legacy_id` (fallback `id`) | **Read-only** — migration-assigned; NOT in `CodeBundleCreate`. |
| Description | `name` | Required. |
| Short Description | `display_code` | The alphanumeric mnemonic (e.g. "Newptadult4"). |
| Default Same Tooth No. | `same_tooth` | Yes/No. |
| Included Codes grid | `code-bundle-items` | `procedure_code` + `tooth` (Tooth/Quadrant) + `sort_order`. |

`description` is set = `name` on save (legacy exposes only Description + Short Description;
migrated rows keep `description == name`).

| Endpoint | Orval fn |
|---|---|
| `GET/POST /api/v1/code-bundles` (+ `GET/PATCH/DELETE /{id}`) | `listCodeBundles` / `createCodeBundle` / `getCodeBundle` / `updateCodeBundle` / `deleteCodeBundle` |
| `GET/POST /api/v1/code-bundle-items` (+ `PATCH/DELETE /{id}`, filter `bundle_id`) | `listCodeBundleItems` / `createCodeBundleItem` / `updateCodeBundleItem` / `deleteCodeBundleItem` |

Included-code descriptions + the add-picker reuse the cached procedure-code map
(`components/setup/insurance/procedureCodeService.ts`). Items editor is gated until the
bundle is saved (no `bundle_id` to hang items off otherwise).

**Resolves** the earlier "gap #25 — Explosion Codes (entire resource missing)": the backend
now ships the full code-bundles + items CRUD, so the screen is fully backend-driven.

**Data note (backend, non-blocking)** — the dev seed contains **duplicate bundles** (4 rows
share `legacy_id` "100" with distinct numeric `id`s; 40 rows = 10 distinct legacy ids × 4).
The UI keys rows by the unique numeric `id` and renders correctly; the duplication is a
seed-data artifact for the backend team to dedupe.
