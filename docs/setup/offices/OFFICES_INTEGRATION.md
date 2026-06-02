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
| **Operatories** | `OperatoriesTab.tsx` | 🟡 **Read-only effectively** — list loads, but edits never persist |
| **Statement** | `StatementTab.tsx` | ❌ no backend |
| **Integration** | `IntegrationTab.tsx` | ❌ no backend |
| **Schedule** | `ScheduleTab.tsx` | ❌ model mismatch (see §4) |
| **Holidays** | `HolidaysTab.tsx` | ❌ no backend |
| **Advanced** | `AdvancedTab.tsx` | ❌ no backend |
| **SmartAssist** | `SmartAssistTab.tsx` | ❌ no backend |

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
| 15 | No office Holidays endpoint | 🔴 Holidays tab (same family as account gap #5) |
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
