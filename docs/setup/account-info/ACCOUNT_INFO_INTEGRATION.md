# Setup → Account Info — Integration & Modernization Report

> **Module:** Setup · **Screen:** Account Info (Tenant / Organization Configuration)
> **Component:** [`src/components/pages/setup/AccountSetup.tsx`](../../../src/components/pages/setup/AccountSetup.tsx)
> **Route:** `/setup/account-info` · **Nav label:** "Account Info" ([`GlobalNav.tsx:1057`](../../../src/components/navigation/GlobalNav.tsx))
> **Date:** 2026-05-31 · **Backend:** DentC Backend v1.0.0 (`/api/v1`, schema in [`openapi.json`](../../../openapi.json))

---

## ⚠️ Headline

The Account Info screen and its entire service layer were built against a **speculative, AI-authored design doc** — [`docs/api-contracts/ACCOUNT_SETUP_DATA_DEFINITION.md`](../../api-contracts/ACCOUNT_SETUP_DATA_DEFINITION.md) (labeled *"Author: AI Assistant / Status: Production-Ready"*). That doc invents an `/api/accounts/*` + `/api/lookup/*` API surface and a 60-column `accounts` table.

**None of that exists in the real backend.** Verified against `openapi.json` (195 paths):

- ❌ No `/api/accounts/*` path of any kind.
- ❌ No `/api/lookup/*` namespace of any kind.
- ✅ The real org/tenant entity is `/api/v1/tenants/{item_id}` (tag: Organization) — but `TenantRead`/`TenantUpdate` carry only **6 fields** (`id, name, code, is_active, legacy_id, created_at`), versus the **~50 fields** this screen edits.

So this is **not a wire-up task** — it is a **contract-drift remediation** that is blocked on substantial backend work. This report maps what *can* be served today, what must change in the frontend, and itemizes every backend gap in [`backend_devreport.md`](../../../backend_devreport.md).

---

## 1. Screen Analysis

5 tabs (`AccountSetup.tsx:1402-1411`). Footer Edit/Cancel/Save apply to **Basic + Advanced**; Communications and Online-Registration have their own internal edit/save state.

### Tab: BASIC (`AccountSetup.tsx:94-586`)
Account identity + addresses + contact + branding. Fields (form key → type):

| Field | Type | Notes |
|---|---|---|
| `accountNumber` | text | **read-only**, "auto-generated" |
| `accountName` * | text | required |
| `accountShortId` * | text | required, forced lowercase (subdomain/login slug) |
| `contactFirstName`, `contactLastName` | text | |
| `corporateAddress`, `corporateCity`, `corporateZip` | text | |
| `corporateState` | **select** ← `states()` lookup | |
| `statementAddress`, `statementCity`, `statementZip` | text | |
| `statementState` | **select** ← `states()` lookup | |
| `email` * | email | required, regex-validated |
| `phone`, `phone2` | tel | |
| `cultureCode` | **select** ← `cultures()` lookup | locale |
| `custom1`, `custom2` | text | |
| `logoUrl` | file upload (JPG/PNG ≤2 MB) | base64 → POST logo |

Header shows audit chips: **PGID**, **OID**, **Modified On**, **Modified By** (`:1528-1548`).

### Tab: ADVANCED (`AccountSetup.tsx:592-1270`)
Account-wide configuration blob. Sections:
- **Ledger Colors** — 7 transaction-type color selects (`procedureColor … notesLinesColor`), options ← `ledgerColors()`.
- **Options** — `enableFullScreen`, `maxTreatmentPlanDiscount` (0–100), `onlyShowOfficeItems`, `statementCloseOutIndividual`, `autoPostPeriodicCharges`, `showFlashAlertsInsurance`, `pronounFieldVisible`.
- **Default Settings** — `chartingOption` (select), `defaultChartingTab` (select), `passwordExpirationDays` (0–365), `schedulerShowNonWorkingDays`, `defaultFeeIncreaseCode`, `defaultWriteOffCode`.
- **Required Fields** — 6 patient-field-requirement toggles.
- **Third Party** — `ediVendor` (select), `transworldEnabled`, `xvwebEnabled`, `cloud9Enabled`.
- **Payment Portal** — `paymentPortalPostingOffice` (select ← offices), `postPaymentToResponsibleParty`.
- **AI Assist** — `aiAssistOrgId`, `aiAssistClientId`, `aiAssistClientSecret` (write-only; never read back, `accountSetupTransform.ts:117`).

### Tab: HOLIDAYS (`HolidaysTabContent.tsx`)
Grid (Date / Name+Recurring / Status / Type / Actions) + CRUD modal, bulk delete, "Add Federal Holidays" (year select), "Select Range". Status/Type selects ← `holidayStatuses()` / `holidayTypes()`.

### Tab: COMMUNICATIONS (`CommunicationsTabContent.tsx`)
Business info (name, region, country, address, EIN-encrypted, website), business contact, **Phone Number Assignment** dual-list transfer (Office-Specific max 5 vs Multi-Office Shared), business-type/company-status/stock-exchange/industry selects, telecom verification status badge + verify action.

### Tab: ONLINE REGISTRATION (`OnlineRegistrationTabContent.tsx`)
Versioned consent template: `header` (≤150 chars) + `body_html` (contentEditable rich text). Save creates a new version; Preview + Export-PDF actions.

### State / data-flow
`accountId = currentOrganization` from `useAuth()` (`:1303-1304`). **`currentOrganization` is the stringified tenant id** — `AuthContext.tsx:103` sets it from `me.tenant?.id ?? u.tenant_id`. So the screen already *has* the correct tenant id; it just routes it to the wrong (fabricated) endpoints.

---

## 2. Existing API Mapping (frontend call → backend reality)

All calls go through the hand-written [`src/services/accountSetupApi.ts`](../../../src/services/accountSetupApi.ts) (axios), **not** the generated Orval client.

| Screen feature | Frontend call (current) | Real backend | Status |
|---|---|---|---|
| Load account (Basic) | `GET /api/accounts/{id}` | `GET /api/v1/tenants/{item_id}` → `TenantRead` | 🟡 endpoint exists; **6 of ~20 Basic fields backed** (only name≈accountName, code≈accountShortId, is_active) |
| Save account (Basic) | `PUT /api/accounts/{id}` | `PATCH /api/v1/tenants/{item_id}` (`TenantUpdate`) | 🟡 **verb mismatch (PUT→PATCH)** + field gap |
| Advanced settings | `GET/PUT /api/accounts/{id}/advanced-settings` | — | ❌ no endpoint |
| Logo upload/delete | `POST/DELETE /api/accounts/{id}/logo` | — | ❌ no endpoint; no logo field on Tenant |
| Holidays (all 7 ops) | `/api/accounts/{id}/holidays*` | — | ❌ no endpoint, no schema |
| Communications | `GET/PUT /api/accounts/{id}/communications` | — | ❌ no endpoint |
| Verify telecom | `POST …/communications/verify-telecom` | — | ❌ no endpoint |
| Phone assignments | `GET/PUT /api/accounts/{id}/phone-assignments` | — | ❌ no endpoint |
| Consents (active/create/pdf/preview) | `/api/accounts/{id}/consents*` | — | ❌ no endpoint, no schema |
| Audit chips (PGID/OID/Modified On/By) | (from account GET) | `TenantRead` has none; `/api/v1/audit-logs` is a generic request log | ❌ no per-record `updated_at/updated_by/pgid/oid` |

### Lookups (all currently `GET /api/lookup/*` — none exist)

| Lookup | Real source | How |
|---|---|---|
| states, cultures, charting-options, charting-tabs, edi-vendors, holiday-statuses, holiday-types, business-types, stock-exchanges, company-statuses, countries, business-industries | **`/api/v1/definitions`** (Metadata) | `useListDefinitions({ group_code, is_active: true })` — **server-side `group_code` filter is supported** ✅. Each Definition row: `key1`=value, `description`=label. ⚠️ **exact `group_code` strings are seed data, not in `openapi.json`** — needs backend confirmation. |
| ledger colors | **`/api/v1/chart-colors`** (Metadata) | `useListChartColors()`; **shape differs** (`name`/`stroke_color`/`fill_*`/`gradient_*`, not flat value/label) → needs adapter. No server-side category filter. |
| posting offices | **`/api/v1/offices`** (Organization) | `useListOffices()`; tenant-scoped by `X-Tenant-ID` header, **not** `?accountId=`. |

**Generated Orval assets available now:** `useGetTenant` / `useUpdateTenant` (PATCH) / `useListTenants` (organization), `useListDefinitions` / `useListDefinitionGroups` (metadata), `useListChartColors` (metadata), offices hooks (organization), `MeFull` / `UserRead.tenant_id` (auth). See [`src/api/generated/endpoints/`](../../../src/api/generated/endpoints/).

---

## 3. Required Frontend Changes

Sequenced so the *backed* parts land cleanly and the *unbacked* parts fail visibly rather than silently.

**A. Re-platform Basic onto the real tenant endpoint (do now).**
1. Replace `fetchAccount`/`updateAccount` with generated `useGetTenant(tenantId)` / `useUpdateTenant` (**PATCH**). `tenantId` = `Number(currentOrganization)`.
2. Reduce the Basic form's *backed* fields to the real `TenantUpdate` surface (`name`, `code`, `is_active`). Map `accountName↔name`, `accountShortId↔code`.
3. Mark every other Basic field (addresses, contact, email, phone, culture, custom, logo) as **disabled + "Pending backend (see gap #N)"** rather than editing into the void — or hide behind a feature flag until the backend lands.

**B. Make lookups backend-driven via `definitions` (do once group_codes are confirmed).**
4. Replace `accountSetupLookups.*` with `useListDefinitions({ group_code })` + a small `DefinitionRead → {value:key1, label:description}` adapter.
5. Replace `ledgerColors()` with `useListChartColors()` + a `ChartColorRead → option` adapter (and resolve hex from `fill_color`/`stroke_color`).
6. Replace `postingOffices(accountId)` with `useListOffices()`.
7. **Remove the silent-empty failure mode:** `parseLookup` swallows all errors → `[]` (`accountSetupApi.ts:50-57`), so against the real backend every dropdown renders empty with no error. Add loading/empty/error states.

**C. Remove hardcoded/dummy data** (audit in §4 of the discovery; key items):
8. `ledgerColors` array (`AccountSetup.tsx:611-619`), Required-Fields array (`:1010-1017`), and the duplicated default-color/charting/culture literals in `accountSetupTransform.ts:44,83-118` → derive from backend once advanced-settings exists.
9. Delete orphaned mock file [`src/data/organizationData.ts`](../../../src/data/organizationData.ts) (3 fake orgs; **not imported** by this screen — confirmed; only a commented-out ref in `organizationApi.ts:2`). *(Flagging as a separate cleanup task.)*

**D. Gate the unbacked tabs (do now, pending backend).**
10. Advanced, Holidays, Communications, Online-Registration have **zero** backend support. Until the gaps below are filled, show an explicit "Not yet available" empty state instead of wiring them to dead `/api/accounts/*` routes. Do **not** ship edit UIs that POST into nonexistent endpoints.

**E. Retire the legacy service layer.**
11. After A–D, delete `accountSetupApi.ts` + `accountSetupTransform.ts` and the speculative contract doc's authority (keep it only as a backend feature request, cross-linked to the dev report).

---

## 4. Backend Gaps

Filed incrementally in [`backend_devreport.md`](../../../backend_devreport.md). Summary:

| # | Gap | Severity |
|---|---|---|
| 1 | Tenant lacks Account-Info fields (contact, corporate/statement address, email, phone, culture, logo, custom1/2, account_number) | 🔴 blocks Basic tab |
| 2 | Tenant update verb is PATCH; frontend sends PUT (also affects users/patients per prior drift report) | 🟡 method mismatch |
| 3 | No Advanced-Settings endpoint (ledger colors as config, options, required-fields, third-party toggles, payment-portal, AI-assist credentials) | 🔴 blocks Advanced tab |
| 4 | No account logo upload/delete + storage | 🟠 blocks branding |
| 5 | No Holidays resource (CRUD, bulk-delete, federal-import, range) | 🔴 blocks Holidays tab |
| 6 | No Communications settings + verify-telecom + phone-assignments | 🔴 blocks Communications tab |
| 7 | No Online-Registration consent versioning (active/create/pdf/preview) + signatures | 🔴 blocks Online-Reg tab |
| 8 | No per-record audit fields (`updated_at`, `updated_by`, `pgid`, `oid`) on Tenant | 🟠 audit chips empty |
| 9 | Lookup `group_code` values for `definitions` are undocumented seed data | 🟡 blocks lookup mapping until confirmed |

---

## 5. Validation Checklist

Run after each change increment.

- [ ] **Basic — read:** `useGetTenant(tenantId)` populates `accountName`(name) / `accountShortId`(code); no console 404s.
- [ ] **Basic — update:** edit + Save issues `PATCH /api/v1/tenants/{id}` (not PUT), returns `TenantRead`, UI reflects saved values.
- [ ] **Tenant id source:** `accountId` resolves from `auth.tenant_id` for a fresh login (no `localStorage` priming).
- [ ] **Lookups:** each migrated dropdown loads from `definitions`/`chart-colors`/`offices`; correct loading → populated → empty/error states (no silent empty).
- [ ] **No legacy paths:** grep confirms zero remaining `/api/accounts/` and `/api/lookup/` references after retirement (`accountSetupApi.ts` deleted).
- [ ] **Unbacked tabs:** Advanced/Holidays/Communications/Online-Reg show "Not yet available" — no network calls to dead routes.
- [ ] **Hardcoded data:** `ledgerColors`/Required-Fields/default literals removed or backend-sourced; `organizationData.ts` deleted.
- [ ] **Type safety:** screen compiles with generated `TenantRead`/`TenantUpdate` types (no `Record<string, unknown>` form state for backed fields).
- [ ] **Regression:** existing login/org-switch flows unaffected.
- [ ] CRUD/pagination/sort/search checks deferred to Holidays tab until gap #5 lands.

---

## 6. Completion Summary

**Status: ⛔ Blocked on backend — analysis complete, partial frontend remediation possible.**

- The screen is wired to a **fabricated API surface**; ~90% of its fields and all four secondary tabs have **no backend**.
- **Buildable today:** Basic tab's `accountName`/`accountShortId`/`is_active` onto real `PATCH /api/v1/tenants/{id}`, plus migrating lookups to `definitions`/`chart-colors`/`offices` **once `group_code` seed values are confirmed**.
- **Requires backend (gaps #1–#9)** before the screen can be "completed" as designed. Recommend a product decision: either (a) implement the gaps, or (b) descope Account Info to the fields the Tenant model actually supports.
- **Next action:** confirm with backend (1) the planned shape of tenant/account config, and (2) the `definition` `group_code` values for the lookups, then proceed with §3-A and §3-B.

This screen does **not** advance to "done" in this pass. Per the plan, the Offices screen is the next Setup module to analyze while the backend gaps are triaged.
