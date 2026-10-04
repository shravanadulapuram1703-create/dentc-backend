# Time Clock — backend dev report (TC-BE-1 … TC-BE-14)

**Date:** 2026-10-03 · **Frontend:** `src/features/time-clock/` · **Branch:** `feature/uat-realse-v2`

## 1. What shipped on the frontend

Denticon-parity Time Clock (Utilities → User Functions → TimeClock / TimeClock Editor):

| Surface | Route / place | Who |
|---|---|---|
| Punch button in the top bar (status dot + elapsed time, Clock in / Clock out panel) | `GlobalNav` → `TimeClockButton` | every signed-in user |
| My Time Clock — live clock, big Clock in/out, own time card (period, overtime rule, CSV, print) | `/time-clock` | every signed-in user |
| Time Clock Report — all staff, per-employee totals (regular / OT / total), drill-down per day, issue flags, Summary + Detail CSV, print (jsPDF), office scope toggle | `/time-clock/report` | owner / admin / manager |
| Time entry editor — add missed shift, correct in/out, delete | dialog on the report | owner / admin / manager |
| Logout guard — "You are still clocked in → Clock out & log out / stay clocked in" | `GlobalNav` logout | everyone |
| `clock_in_required` (Users → Time Clock) — panel auto-opens once per session + amber dot until punched in | `TimeClockButton` | users with the flag |

Legacy menu paths `/utilities/user-functions/timeclock` and `…/timeclock-editor` now redirect to the new screens.

**Endpoints used (all exist today):**

| Purpose | Call |
|---|---|
| Current shift | `GET /api/v1/time-clock-entries?user_id={me}&sort=clock_in&order=desc&size=10&all_offices=true` |
| Clock in | `POST /api/v1/time-clock-entries` `{ user_id, office_id, clock_in }` (+ `X-Office-ID`) |
| Clock out | `PATCH /api/v1/time-clock-entries/{id}` `{ clock_out, total_hours }` |
| Report range | `GET /api/v1/time-clock-entries?sort=clock_in&order=desc&size=200&page=N[&user_id][&office_id][&all_offices]` — paged until past `from` |
| Editor | `POST` / `PATCH` / `DELETE /api/v1/time-clock-entries/{id}` |
| Clock-in required / OT method | `GET /api/v1/users/{id}/time-clock-config` |

Live-verified against the local backend (tenant 1, 31,756 migrated Denticon punches): clock in → clock out round-trip,
manager add (9:00–17:00 EST stored as 14:00Z–22:00Z, `total_hours: "8.00"`) → edit → delete, report over legacy data.
All test rows were deleted afterwards.

## 2. Gaps — please implement

Severity: **Blocker** = wrong pay / data integrity · **High** = needed for a trustworthy payroll report · **Medium/Low** = polish.

| ID | Gap | Observed today (probed 2026-10-03) | Ask | Severity |
|---|---|---|---|---|
| **TC-BE-1** | **Server-stamped punch time** | `clock_in` / `clock_out` are whatever the client sends — a user can change the PC clock or call the API with any time. | Add action endpoints that stamp `now()` server-side: `POST /time-clock-entries/clock-in` `{ office_id? }` → 201 entry (`user_id` = caller) and `POST /time-clock-entries/clock-out` → 200 entry (closes the caller's open shift). Keep generic CRUD for managers only (TC-BE-5). | **Blocker** |
| **TC-BE-2** | **One open shift per user** | A second `POST` while a shift is open is accepted (`31757` and `31758` both open for user 1). FE pre-checks, but two tabs/workstations can race. | Reject with `409 already_clocked_in` (return the open entry in `error.details`). Partial unique index `(tenant_id, user_id) WHERE clock_out IS NULL` (after cleaning legacy open rows, see TC-BE-10). Clock-out with no open shift → `409 not_clocked_in`. | **Blocker** |
| **TC-BE-3** | **`total_hours` not computed** | `PATCH {clock_out}` leaves `total_hours: null`; the FE now computes and sends it. A PATCH that changes only `clock_in` leaves a stale total. | Compute `total_hours = round((clock_out − clock_in)/3600, 2)` on every create/update; make it read-only (ignore client value). | High |
| **TC-BE-4** | **No date-range filter** | `GET /time-clock-entries` ignores `clock_in_from`/`date_from`; `search` is ignored too. The FE pages newest-first up to 60 × 200 rows and shows a "range too large" warning. | Add `clock_in_from` / `clock_in_to` (ISO date or datetime, inclusive), indexed on `(tenant_id, clock_in)`. | High |
| **TC-BE-5** | **Authorization by caller** | Any authenticated user can list every employee's punches and PATCH/DELETE anyone's entry (the role gate is client-side only). Not yet verified with a non-admin token — please confirm. | Non-managers: list returns own rows only; create/patch/delete only via TC-BE-1 actions. Managers (owner/admin/manager or a `time_clock_edit` right): full CRUD. 403 otherwise. | **Blocker** |
| **TC-BE-6** | **Hard delete + no audit trail** | `DELETE` returns 204 and the row is gone (GET → 404). Edits overwrite in place; no record of who changed a punch or the original time. Payroll/labour-law audits need both. | Soft delete (`is_active=false`, `deleted_by`, `deleted_at`) and an audit row per change: `edited_by`, `edited_at`, `edit_reason`, `original_clock_in`, `original_clock_out`. Expose `updated_at`, `updated_by`, `updated_by_name`, `is_edited` on `TimeClockEntryRead`. Optional `reason` on PATCH/DELETE. | High |
| **TC-BE-7** | **Overtime method vocabulary** | `time-clock-config.overtime_method` is free text and `null` for every user probed (1, 159, 196). FE offers None / Weekly>40 / Daily>8 / Daily>8+Weekly>40 per report run, default Weekly>40 (Sun–Sat week). | Enum `none \| weekly \| daily \| daily_weekly` + thresholds (`daily_threshold_hours`, `weekly_threshold_hours`), `week_start_day`. Optionally a practice-level default. FE helper `overtimeRuleFromMethod()` will map it. | Medium |
| **TC-BE-8** | **Server hours report** | Report is aggregated client-side (bucketing by local day, OT split, totals). | `GET /reports/time-clock?from&to&user_id&office_id[s]` → per user `{ user_id, user_name, days:[{date, regular, overtime, total, entries:[…]}], totals }`, plus `…/report.pdf` and `…/report.csv`, using the same rules as TC-BE-7. Then the FE swaps `buildReport()` for it. | Medium |
| **TC-BE-9** | **Mixed time semantics (legacy rows)** | Migrated Denticon rows store the office **wall clock** with a `Z` suffix (`legacy_id 4341192`: `clock_in 2023-12-08T09:25:00Z` = 9:25 AM at the office). Rows punched in DentC are true UTC. FE renders legacy rows in `UTC` and new rows in the office `timezone`. | Back-fill legacy rows to real UTC using `offices.timezone` (09:25 America/New_York → 14:25Z), then the FE drops the legacy special-case (`LEGACY_WALL_CLOCK_ZONE` in `timeClockModel.ts`). Coordinate the switch. | High |
| **TC-BE-10** | **Legacy forgotten clock-outs** | Many legacy rows are open with `total_hours "0.00"` (e.g. `15593`, `15012`, 2026-02-02). FE treats open rows older than 20 h as "Missing clock-out" (not a running shift) and flags them. | Data clean-up job + optional auto-close policy (e.g. close at office close time, flag `auto_closed=true`) for shifts left open > N hours. Needed before the TC-BE-2 unique index. | Medium |
| **TC-BE-11** | **Denormalised names on read** | `TimeClockEntryRead` has only ids; FE crawls the whole `/users` directory (~250 users, several sharing a display name, e.g. "P Z" ×6) and the office catalog. | Add `user_name`, `username`, `office_name` to `TimeClockEntryRead`. | Low |
| **TC-BE-12** | **Breaks / lunch** | Denticon's time clock is in/out only, so FE models one row per shift; staff who take lunch clock out & back in (two rows per day, FE sums them). | Optional: `entry_type` (`work \| break \| lunch`) or `break_minutes`, if the practice wants paid/unpaid break tracking. | Low |
| **TC-BE-13** | **Pay-rate / payroll export** | `pay_rate`, `overtime_rate` exist on config but nothing uses them; FE report shows hours only. | If wanted: wages in TC-BE-8 (`regular × pay_rate + OT × pay_rate × overtime_rate`), gated to payroll-admin rights; payroll CSV layout (ADP/Gusto/Paychex) to be specified. | Low |
| **TC-BE-14** | **Approval / lock of a pay period** | No way to approve a period; edits after payroll is run silently change history. | `time_clock_periods` (`from`, `to`, `approved_by`, `approved_at`, `locked`) — PATCH/DELETE inside a locked period → `409 period_locked`. | Low |

### Also observed (no action needed, FYI)
- `X-Office-ID` on `POST` does stamp `office_id` when the body omits it (body value wins when present). FE sends both.
- `sort=clock_in&order=desc` works; `office_id` filter works (office 9 → 1,490 rows).
- `DELETE` returns 204 (hard), see TC-BE-6.
- `clock_out` earlier than `clock_in` is accepted by PATCH — please validate (`422 clock_out_before_clock_in`) as part of TC-BE-3. FE validates in the editor and flags existing reversed rows.

## 3. Proposed contract (TC-BE-1 / 2 / 4 / 6)

```http
POST /api/v1/time-clock-entries/clock-in          # caller only; server stamps now()
X-Office-ID: 9
{ "office_id": 9 }                                 # optional, defaults to X-Office-ID
→ 201 TimeClockEntryRead
→ 409 { "error": { "code": "already_clocked_in", "details": { "entry": TimeClockEntryRead } } }

POST /api/v1/time-clock-entries/clock-out         # closes the caller's open shift
→ 200 TimeClockEntryRead  (clock_out = now(), total_hours computed)
→ 409 { "error": { "code": "not_clocked_in" } }

GET  /api/v1/time-clock-entries/me/active         # → 200 TimeClockEntryRead | 204
GET  /api/v1/time-clock-entries?clock_in_from=2026-09-27&clock_in_to=2026-10-03&user_id=&office_id=

TimeClockEntryRead += user_name, office_name, updated_at, updated_by, updated_by_name,
                      is_edited, is_active, auto_closed
PATCH/DELETE body  += reason (string, optional; required when editing another user's entry?)
```

## 4. Frontend switch-over once delivered

| Gap | FE change |
|---|---|
| TC-BE-1/2 | `clockIn()` / `clockOut()` in `timeClockService.ts` call the action endpoints; drop the client pre-check and `TimeClockConflictError` maps from the 409. `fetchActiveEntry()` → `/me/active`. |
| TC-BE-3 | Stop sending `total_hours` (`hoursForPayload`). |
| TC-BE-4 | `fetchEntriesInRange()` passes `clock_in_from/to` and drops the crawl + `truncated` banner. |
| TC-BE-6 | Editor shows "Edited by … on …", asks for a reason; Delete copy changes from "permanently". |
| TC-BE-7 | Overtime select defaults to the user's/practice's configured method. |
| TC-BE-8 | `HoursReport` reads the server report; CSV/PDF from server. |
| TC-BE-9 | Remove `LEGACY_WALL_CLOCK_ZONE` branch in `entryTimeZone()` / `wallTimeToIso()`. |
| TC-BE-11 | Drop the `/users` directory crawl from the report. |
