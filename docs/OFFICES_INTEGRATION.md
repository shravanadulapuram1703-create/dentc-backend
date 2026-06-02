# Setup → Offices — Integration & Modernization Report

> **Module:** Setup · **Screen:** Offices (Office Setup)
> **Component:** [`src/components/setup/offices/OfficeSetup.tsx`](../../../src/components/setup/offices/OfficeSetup.tsx)
> **Route:** `/setup/offices/office-setup` ([`App.tsx:289`](../../../src/App.tsx)) · imported [`App.tsx:31`](../../../src/App.tsx)
> **Date:** 2026-05-31 · **Backend:** DentC Backend v1.0.0 (`/api/v1`)

---

## Headline

Unlike Account Info, the **core of this screen is already correctly migrated** to the generated Orval
client: `listOffices`, `getOffice`, `createOffice`, `updateOffice`, `listOperatories` all hit real
`/api/v1/offices` and `/api/v1/operatories` routes (tag: Organization). The Office **list, open,
create, and core-field save work against the real backend today.**

The problems are narrower and concrete:
1. **Real bugs** — the Info tab loads metadata and creates fee schedules from **fabricated endpoints**
   (`/api/v1/offices/metadata`, `/api/v1/offices/billing-providers`, `/api/v1/offices/fee-schedules`)
   that return 404; a **real `/api/v1/fee-schedules`** endpoint exists and is used by a commented-out
   code path right next to the broken one.
2. **Silent data loss** — several Info-tab fields and **all operatory edits** are accepted in the UI
   but never sent on save (the save body omits them; operatory CRUD is never called even though the
   generated client exposes it).
3. **Unbacked tabs** — Statement, Integration, Schedule, Holidays, Advanced, SmartAssist have no
   backend and silently drop edits.

---

## 1. Screen Analysis

Master-detail screen. List view (search + audit columns) → detail view with 8 tabs and a global
**Save Office** button (`OfficeSetup.tsx:683-697`) that applies to the whole record.

**Data flow:**
- List: `listOffices({ size: 200 })` → mapped to the local `Office` shape (`:243-256`, `:441-453`).
- Open: `handleSelectOffice` → `getOffice(id)` + `listOperatories({ office_id })` composed into `formData` (`:303-373`).
- Add: `handleAddOffice` resets form; id assigned server-side (`:379-385`).
- Save: `buildOfficeBody` → `createOffice` (add) or `updateOffice` (edit, **PATCH**) (`:407-461`).

**Tabs:**

| Tab | Editor | Backed? |
|---|---|---|
| **Info** | `InfoTab.tsx` | 🟡 **Partial** — core fields backed; billing/fee/opening-date fields not |
| **Operatories** | `OperatoriesTab.tsx` | ✅ **Backed & persisted** — list loads; add/edit/delete/reorder diffed and saved via operatory CRUD in `persistOperatories`. Verified §8. |
| **Statement** | `StatementTab.tsx` | 🟡 **UI built & ready, gated** — messages + settings + logo; no office backend yet (gap #12). See §9. |
| **Integration** | `IntegrationTab.tsx` | 🟡 **UI built & ready, gated** — production-layout replica; no office backend yet (gap #13). See §8. |
| **Schedule** | `ScheduleTab.tsx` | 🟡 **UI built & ready, gated** — weekly grid; backend model mismatch (gap #14). See §8. |
| **Holidays** | `HolidaysTab.tsx` | 🟡 **UI built & ready, gated** — account-screen replica; no office-scoped backend yet (gap #15). See §7. |
| **Advanced** | `AdvancedTab.tsx` | 🟡 **UI built & ready, gated** — General/Defaults/Check-In/Campaigns; no office backend yet (gap #16). See §8. |
| **SmartAssist** | `SmartAssistTab.tsx` | 🟡 **UI built & ready, gated** — enable + item grid; no office backend yet (gap #17). See §8. |

---

## 2. Existing API Mapping

### ✅ Working (real endpoints, generated client)

| Action | Call | Backend |
|---|---|---|
| List offices | `listOffices({size})` | `GET /api/v1/offices` → `PaginatedResponse_OfficeRead_` |
| Open office | `getOffice(id)` | `GET /api/v1/offices/{item_id}` → `OfficeRead` |
| List operatories | `listOperatories({office_id})` | `GET /api/v1/operatories` |
| Create office | `createOffice(body)` | `POST /api/v1/offices` |
| Update office | `updateOffice(id, body)` | `PATCH /api/v1/offices/{item_id}` |

**Core Info fields that map cleanly to `OfficeRead`/`OfficeUpdate`:**
`name`, `office_code`/`short_id`, `address_line1`, `address_line2`, `city`, `state`, `zip`, `phone`,
`email`, `timezone`, `slot_interval_minutes`, `is_active`.

### ❌ Broken — fabricated endpoints (404)

| Call | Location | Reality |
|---|---|---|
| `GET /api/v1/offices/metadata` | `InfoTab.tsx:55` | **No such path.** Powers Time Zones, Billing Providers, Fee Schedules → all render empty. |
| `POST /api/v1/offices/billing-providers` | `InfoTab.tsx:111` | **No such path.** "Add Provider" 404s. |
| `POST /api/v1/offices/fee-schedules` | `InfoTab.tsx:234,272` | **Wrong path.** The real one is `POST /api/v1/fee-schedules` (used by the commented-out `createFeeSchedule` at `:149`). |

### ⚠️ Silent data loss on save

- **Info fields edited but never sent** (`buildOfficeBody` `:407-421` omits them, and `OfficeUpdate` has
  no columns for them): `openingDate`, `billingProviderId/Name`, `useBillingLicense`, `taxId`,
  `officeGroup`, `defaultFeeSchedule`, `defaultUCRFeeSchedule`, `phone2`, `phone1Ext`.
- **Operatory edits never persist** — `handleSave` only calls `createOffice`/`updateOffice`. The
  generated client exposes `createOperatory`, `updateOperatory`, `deleteOperatory` but **none are
  called**, so add/rename/reorder/deactivate in the Operatories tab is lost.

### Backend fields exposed but UNUSED by the UI
`fax`, `schedule_start_hour`, `schedule_end_hour` exist on `OfficeRead`/`OfficeUpdate` but the screen
neither displays nor saves them.

### Hardcoded data
- `US_STATES` array (`InfoTab.tsx:175-181`) — acceptable as static, but ideally from `definitions`.
- Scheduler interval options `5/10/15/20/30` hardcoded (`InfoTab.tsx:937-941`).
- Debug `console.log` noise: `InfoTab.tsx:49,51,101,102,211,291,292`.

---

## 3. Required Frontend Changes

**A. Fix the real bugs (do now — pure frontend, real endpoints exist).**
1. Replace the `/api/v1/offices/fee-schedules` POSTs (`InfoTab.tsx:234,272`) with the generated
   `createFeeSchedule` → `POST /api/v1/fee-schedules`.
2. Load Fee Schedules from `listFeeSchedules()` (`/api/v1/fee-schedules`) instead of the dead
   `/api/v1/offices/metadata` aggregate.
3. Source Time Zones from a static list (or `definitions` once group_codes land — gap #9) rather than
   the dead metadata call. Source Billing Providers from `/api/v1/providers` (real) instead of the
   dead `/api/v1/offices/billing-providers`.

**B. Wire operatory persistence (do now — generated CRUD exists).**
4. On save, diff `formData.operatories` against the loaded set and call
   `createOperatory`/`updateOperatory`/`deleteOperatory` accordingly. Operatory `id` is a
   client-supplied string per `OperatoryCreate`.

**C. Stop silent data loss.**
5. Disable (with a "pending backend" hint, as in Account Info) the Info fields with no `OfficeUpdate`
   column: billing config (tax_id, billing provider, use-license, office group, opening date), the two
   fee-schedule selects (unless modeled via `/api/v1/fee-schedule-assignments` — see gap #11), and
   `phone2`/`phone1Ext`. Or wire fee schedules via the assignment resource.
6. Gate Statement / Integration / Schedule / Holidays / Advanced / SmartAssist with a "Not yet
   available" empty state instead of editors that drop data.

**D. Use the backend fields that already exist.**
7. Add UI for `fax`, `schedule_start_hour`, `schedule_end_hour` (all on `OfficeUpdate`) — cheap wins.

**E. Cleanup.**
8. Remove `console.log` debug lines in `InfoTab.tsx`; delete the large commented-out blocks; retire the
   mock `Office` type usage in `data/officeData.ts` in favor of generated `OfficeRead` where practical.

---

## 4. Backend Gaps

Appended to [`backend_devreport.md`](../../../backend_devreport.md) (#10–#17).

| # | Gap | Severity |
|---|---|---|
| 10 | No `/api/v1/offices/metadata` (time zones, billing providers, fee schedules aggregate) | 🟡 breaks Info dropdowns |
| 11 | `OfficeUpdate` lacks billing config (tax_id, billing_provider, use_license, office_group, opening_date) and per-office default fee schedules | 🟠 Info billing section unbacked |
| 12 | No office Statement settings/messages endpoint | 🔴 Statement tab |
| 13 | No office Integrations endpoint (eClaims, Transworld, imaging, text messaging, accepted cards, patient URLs) | 🔴 Integration tab |
| 14 | Office schedule model mismatch — backend has only `slot_interval_minutes` + `schedule_start_hour`/`schedule_end_hour`; UI needs a weekly grid with per-day hours + lunch | 🔴 Schedule tab |
| 15 | No office Holidays endpoint — holidays are tenant-scoped only (no `office_id` on model) | 🔴 Holidays tab UI built & gated; same family as account gap #5. See §7. |
| 16 | No office Advanced-settings endpoint (financial, insurance, scheduler defaults, patient check-in, automation) | 🔴 Advanced tab |
| 17 | No office SmartAssist endpoint | 🔴 SmartAssist tab |

> Note: `phone2`/extension is a frontend-only concept; backend `OfficeRead` has single `phone` + `fax`.

---

## 5. Validation Checklist

- [ ] **List/open/create/update** core office round-trips against `/api/v1/offices` (verify in network tab; PATCH on update).
- [ ] **Fee schedules** load from `/api/v1/fee-schedules`; "Add Fee Schedule" POSTs there and the new row appears (no 404).
- [ ] **No 404s** from `/api/v1/offices/metadata` or `/api/v1/offices/billing-providers` after the fix.
- [ ] **Operatories**: add/rename/reorder/deactivate persists — reload shows the change (operatory CRUD fired).
- [ ] **No silent drops**: disabled/unbacked fields can't be edited into the void; gated tabs show "Not yet available".
- [ ] **Backend-supported extras**: `fax`, `schedule_start_hour`, `schedule_end_hour` save and reload.
- [ ] **Search/pagination**: list search works; confirm whether `size:200` is sufficient or server paging/`search` param is needed.
- [ ] **No legacy refs**: zero `/offices/metadata`, `/offices/billing-providers`, `/offices/fee-schedules` references remain.
- [ ] `tsc -b`, `eslint`, `vite build` green; `console.log` noise removed.

---

## 6. Completion Summary

**Status: 🟢 Core works · 🟠 Buildable fixes outstanding · 🔴 6 tabs blocked on backend.**

- **Already integrated:** office list/open/create/update + operatory read, all on real endpoints. This
  screen is in far better shape than Account Info.
- **Buildable now (no backend needed):** fix the fabricated fee-schedule/metadata/billing-provider
  calls (a real `/api/v1/fee-schedules` exists), wire operatory CRUD persistence, surface
  `fax`/schedule-hours, stop silent data loss, gate the 6 unbacked tabs, and remove debug noise.
- **Blocked on backend (gaps #10–#17):** Statement, Integration, Schedule (model mismatch), Holidays,
  Advanced, SmartAssist.
- **Recommended next action:** implement the §3-A/B/C "buildable slice" (mirrors the Account Info
  approach) so the working core is bug-free and honest about what persists, then triage gaps #10–#17
  with the backend team.

---

## 7. Office Holidays (2026-06-01)

**Goal:** a per-office Holidays tab that replicates the Account Info Holidays screen
([`HolidaysTabContent.tsx`](../../../src/components/pages/setup/HolidaysTabContent.tsx)) — same table,
add/edit/delete, bulk-delete, federal import, and closure-range modals — but scoped to one office.

### Screen analysis
- **UI components:** date-range header (From/To + Select Range), "Add Federal Holidays", a holidays
  grid (checkbox select, Date, Holiday Name + Recurring badge, Status badge, Type badge, edit/delete),
  bulk "Delete Selected", and four modals (Add, Edit, Federal-by-year, Range-confirm).
- **Workflow:** identical to account-level holidays, with `officeId` as the scope key instead of
  `accountId`/`tenant_id`.

### What was built
| Artifact | Path | Role |
|---|---|---|
| Component | [`tabs/HolidaysTab.tsx`](../../../src/components/setup/offices/tabs/HolidaysTab.tsx) | Faithful replica of the account Holidays UI; props `officeId`, `holidayStatusOptions`, `holidayTypeOptions`. (Replaces the old legacy form-based `HolidaysTab` that called the defunct `/offices/{id}/setup` aggregate.) |
| Data layer | [`services/officeSetupApi.ts`](../../../src/services/officeSetupApi.ts) | Office-scoped holiday CRUD/bulk/federal/range against the **intended** gap #15 contract via raw axios. |
| Wiring | [`OfficeSetup.tsx`](../../../src/components/setup/offices/OfficeSetup.tsx) | Renders the tab behind the `OFFICE_HOLIDAYS_BACKEND_READY` flag (currently `false`); loads Status/Type lookups from the shared `accountSetupLookups`. |

### Why it is gated
Holidays exist **only at the tenant level** in the backend (`/api/v1/tenants/{id}/holidays` family).
`AccountHolidayRead/Create/Update` carry `tenant_id` and have **no `office_id`**;
`ListAccountHolidaysParams` filters by date only. There is no path or query param to scope holidays to
an office, so wiring the tab to the live tenant endpoints would make every office share one
account-wide list and edits would leak across offices. Per the chosen approach, the component is fully
built but kept behind `TabNotAvailable` until the backend lands office-scoped endpoints.

### Lookups (backend-driven where available)
Status (`OPEN`/`HALF_DAY`/`CLOSED`) and Type (`Federal`/`Custom`) come from the shared
`accountSetupLookups` (the same stable client-side source the account screen uses; should migrate to
`definitions` once group_codes land — gap #9). No mock holiday rows remain.

### Go-live (one flag)
1. Backend implements the gap #15 endpoints (see [`backend_devreport.md`](../../../backend_devreport.md) #15).
2. `npm run api:sync` to regenerate Orval; optionally swap the raw-axios calls in `officeSetupApi.ts`
   for the generated client.
3. Set `OFFICE_HOLIDAYS_BACKEND_READY = true` in `OfficeSetup.tsx`.

### Validation checklist
- [x] Component builds, type-checks (`tsc -b`), and lints clean.
- [x] No mock/hardcoded holiday data; lookups sourced from the shared lookup service.
- [x] Tab stays gated — zero calls to non-existent routes in production.
- [ ] CRUD/bulk/federal/range round-trips — **blocked on gap #15** (verify once endpoints exist).

---

## 8. Schedule / Integration / Advanced / SmartAssist + Operatories (2026-06-01)

A screenshot-driven sweep of the remaining tabs, mirroring the Holidays approach (refactor the existing
component to match the production screen, back it with a per-tab service against the *intended*
office-scoped contract, and gate it). Built via a 10-agent map→build workflow; shared-file wiring + docs
done by the orchestrator. `tsc -b` + `eslint` clean across the whole project after integration.

| Tab | Component | Service | Flag | Backend | Status |
|---|---|---|---|---|---|
| **Schedule** | `tabs/ScheduleTab.tsx` | `services/officeScheduleApi.ts` | `OFFICE_SCHEDULE_BACKEND_READY` | gap #14 (model mismatch) | 🟡 built, gated |
| **Integration** | `tabs/IntegrationTab.tsx` | `services/officeIntegrationApi.ts` | `OFFICE_INTEGRATION_BACKEND_READY` | gap #13 | 🟡 built, gated |
| **Advanced** | `tabs/AdvancedTab.tsx` | `services/officeAdvancedApi.ts` | `OFFICE_ADVANCED_BACKEND_READY` | gap #16 | 🟡 built, gated |
| **SmartAssist** | `tabs/SmartAssistTab.tsx` | `services/officeSmartAssistApi.ts` | `OFFICE_SMARTASSIST_BACKEND_READY` | gap #17 | 🟡 built, gated |
| **Operatories** | `tabs/OperatoriesTab.tsx` | (generated client) | — (live) | ✅ backed | ✅ verified |

### What changed
- **Schedule** — replaced the legacy formData grid with a weekly Day/Day-Start/Day-Stop/Lunch-Start/
  Lunch-Stop table (Mon–Sun), self-fetching by `officeId`. Backend has only `slot_interval_minutes` +
  single start/end hour (no per-day grid, no lunch) → gated. Intended: `GET/PUT …/schedule` (gap #14).
- **Integration** — rebuilt to the **current production layout** (Service Email + verified badges, AI
  Assist toggle, Patient Communication URLs, Dentiray storage format, Transfirst device, DoseSpot id +
  masked key, accepted credit cards). The stale eClaims/Transworld/imaging/text-messaging sections were
  removed. Intended: `GET/PATCH …/integrations` (gap #13).
- **Advanced** — General / Default / Patient Check-In / Automated Campaigns settings, dirty-tracked Save;
  removed a hardcoded `sendECard:true` bug, dead `updateSection` helper, `console.log`s, and `any` casts.
  Intended: `GET/PATCH …/advanced-settings` (gap #16).
- **SmartAssist** — master Enable toggle + 12-item grid (Item / Description / Frequency / SMS Template)
  with the Payment "include unpaid balance" flag in the Description column. Intended:
  `GET/PATCH …/smart-assist` (gap #17).
- **Operatories** — **already backed and persisted** (`persistOperatories` in `OfficeSetup.tsx` diffs the
  form list against the loaded snapshot and fires `createOperatory`/`updateOperatory`/`deleteOperatory`
  on save). Verified the screenshot's ID + Name map to `OperatoryRead.id`/`name`; light comment cleanup
  only; remains **live** (not gated).

### Backend-driven data / no mocks
No mock business rows remain in any of these tabs. Stable presentation enums kept as typed, commented
constants (and flagged for lookup migration once sources exist — gap #9): Schedule weekday rows;
Integration Dentiray storage formats; Advanced place-of-service & coverage-type; SmartAssist frequency
(`EVERY_VISIT`/`EVERY_YEAR`) and placeholder SMS-template ids. Advanced's Preferred-Provider / HIPAA-notice
/ consent-form selects and SmartAssist's SMS-template select need real lookup endpoints before go-live.

### Go-live (per tab, one flag each)
1. Backend implements the gap's endpoints (models in [`backend_devreport.md`](../../../backend_devreport.md) #13/#14/#16/#17).
2. `npm run api:sync` → regenerate Orval; optionally swap the raw-axios calls in the per-tab service for the generated client.
3. Flip the corresponding `OFFICE_*_BACKEND_READY` flag in `OfficeSetup.tsx`.

### Validation checklist
- [x] All four components build, type-check (`tsc -b`), and lint clean; wired behind flags in `OfficeSetup.tsx`.
- [x] No mock/hardcoded business data; presentation enums commented and earmarked for gap #9 lookups.
- [x] Tabs stay gated — zero calls to non-existent routes in production.
- [x] Operatories CRUD persistence path re-verified end-to-end (save diff → operatory CRUD).
- [ ] Per-tab CRUD round-trips — **blocked on gaps #13/#14/#16/#17** (verify once endpoints exist).

---

## 9. Statement (2026-06-01)

The last unbacked Office tab, given the same treatment (refactor → back with intended service → gate).

| Tab | Component | Service | Flag | Backend | Status |
|---|---|---|---|---|---|
| **Statement** | `tabs/StatementTab.tsx` | `services/officeStatementApi.ts` | `OFFICE_STATEMENT_BACKEND_READY` | gap #12 | 🟡 built, gated |

### Screen analysis
- **Monthly Statement Messages:** six textareas — General, Current, 30 / 60 / 90 / 120 Day — each ≤ 100 chars with a live counter.
- **Statement Settings:** Correspondence Name; Current Logo Option (`Use office logo` / `Use custom logo` / `No logo`); Logo (upload/remove, shown only for the custom option); "Statement Name, Address and Phone" source (`Use office statement address and phone` / custom); and, when custom, Statement Address (line 1/2), City/State/Zip, and Phone. When the source is "office", the address/phone/logo are resolved from the office record (read-only hints).

### What changed
Replaced the old formData-bound component (which had `console.log`s and a ~300-line dead commented block) with a self-fetching `{ officeId }` component matching the screenshot: 6-message grid + a settings table, logo upload/remove, address-source toggle that reveals custom address/phone fields, dirty-tracked Save, and loading/error(+retry)/saving states. Service `officeStatementApi.ts` targets the intended `GET/PATCH …/statement-settings` + `POST/DELETE …/statement-logo` (gap #12).

### Backend-driven data / no mocks
No mock data. Logo-option and address-source choices are stable typed UI enums (commented). Effective office address/phone/logo (when source = office) must be resolved server-side.

### Go-live
1. Backend implements gap #12 (models in [`backend_devreport.md`](../../../backend_devreport.md) #12).
2. `npm run api:sync`; optionally swap the raw-axios calls for the generated client.
3. Flip `OFFICE_STATEMENT_BACKEND_READY = true` in `OfficeSetup.tsx`.

### Validation checklist
- [x] Builds (`tsc -b`), lints clean; wired behind the flag in `OfficeSetup.tsx`.
- [x] No mock/hardcoded data; enums commented.
- [x] Stays gated — zero calls to non-existent routes.
- [ ] CRUD + logo upload round-trips — **blocked on gap #12** (verify once endpoints exist).

> **All eight Office Setup tabs are now handled:** Info ✅ + Operatories ✅ live & backed; Statement / Integration / Schedule / Holidays / Advanced / SmartAssist built & gated pending backend gaps #12/#13/#14/#15/#16/#17.
