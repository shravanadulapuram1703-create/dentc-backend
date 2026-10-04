# Time Clock — backend response (TC-BE-1 … TC-BE-14)

**Date:** 2026-10-03 · **Report:** [time_clock_backend_devreport.md](time_clock_backend_devreport.md) ·
**Alembic:** `1745e318c65a` (revises `8e4a6a8e5ab0`) · **Tests:** `tests/test_time_clock.py`

All 14 gaps are implemented. `time-clock-entries` left the generic CRUD registry: its authorization is
by **caller** (TC-BE-5), which the generic engine cannot express on list/get/delete. The five classic
routes keep the operation ids Orval already generated (`list_time_clock_entries`,
`create_time_clock_entry`, `get_`, `update_`, `delete_time_clock_entry`), so the generated client does not
churn. Code: [app/api/v1/time_clock.py](../../app/api/v1/time_clock.py) +
[app/services/time_clock_service.py](../../app/services/time_clock_service.py).

> **Not applied to the dev DB.** The dev DB is stamped `fc6450e398ee`, a revision that exists in no
> branch or worktree of this repo (a parallel session applied an unshipped migration), so `alembic upgrade`
> cannot run from it. The migration was verified against the dev DB inside a **rolled-back** transaction
> (upgrade 2.3 s → 856 open legacy rows flagged, the one live shift kept open, partial unique index
> created; downgrade restores the original 9 columns). Apply it once the revision chain is reconciled.

## Status by gap

| ID | Status | What shipped |
|---|---|---|
| TC-BE-1 | ✅ | `POST /time-clock-entries/clock-in` `{office_id?, entry_type?, notes?}` → 201, `POST …/clock-out` `{notes?}` → 200, `GET …/me/active` → 200 \| 204. Server stamps `now()`; `user_id` = caller. |
| TC-BE-2 | ✅ | Pre-check → **409 `already_clocked_in`** (`details.entry` = full read, `details.stale`); clock-out with nothing open → **409 `not_clocked_in`**. Partial unique index `uq_time_clock_entries_open_shift (tenant_id, user_id) WHERE clock_out IS NULL AND is_active AND NOT auto_closed`; a lost race maps to the same 409. |
| TC-BE-3 | ✅ | `total_hours` derived on every write, client value ignored (still accepted in the body so today's FE does not 422). 422 `clock_out_before_clock_in`, `punch_in_future` (> 5 min ahead), `shift_too_long` (> 24 h). |
| TC-BE-4 | ✅ | `clock_in_from` / `clock_in_to`: ISO date (a whole **office-local** day, inclusive) or datetime. Bare dates resolve in `?tz=` → the `office_id` office's zone → the `X-Office-ID` office's zone. Index `(tenant_id, clock_in)`. `search` now works (employee name / username / notes). Also `entry_type`, `source`, `is_open`, `auto_closed`, `is_edited`. |
| TC-BE-5 | ✅ | See *Authorization*. Confirmed the hole: before this change any token could list/PATCH/DELETE anyone's punches. |
| TC-BE-6 | ✅ | Soft delete (`is_active=false`, `deleted_at/by`, `delete_reason`; `DELETE …?reason=`), `POST …/{id}/restore`, `GET …/{id}/history`. Every manager change appends a `time_clock_entry_edits` row (action, edited_by(+name), edited_at, edit_reason, original/new in & out, field diff). The row carries `is_edited`, the **first** pre-edit `original_clock_in/out`, `edit_reason`, `updated_at/by(+name)`. Practice switch `require_edit_reason` → 422 `edit_reason_required` when changing *another* user's punch. PATCH/DELETE honour `If-Match` / `If-Unmodified-Since` / body `expected_updated_at` → 412 (GET returns an `ETag`). |
| TC-BE-7 | ✅ | Enum `none \| weekly \| daily \| daily_weekly`; legacy `weekly_40` / `daily_8` / `california` are folded on write, anything else **422 `invalid_overtime_method`** (it decides pay — the PROV-3 "store as written" call does not apply). Per-user `daily_threshold_hours`, `weekly_threshold_hours`, `week_start_day` on `PUT /users/{id}/time-clock-config`; practice defaults in `GET/PUT /time-clock/settings` (weekly / 8 / 40 / sunday / 1.5×). Existing configs migrated (`weekly_40 → weekly`). |
| TC-BE-8 | ✅ | `GET /reports/time-clock?from&to&user_id&office_id[&office_ids][&all_offices]&overtime_method&include_wages` → per user `{rule, days:[{date, regular, overtime, total, break_hours, issues, entries}], totals}` + grand totals. `…/report.csv?layout=summary\|detail`, `…/report.pdf?detail=`. Both audited (`PRINT` / `time_clock_report`). |
| TC-BE-9 | ✅ (tooling) | Every migrated row is `source='legacy'`, `clock_basis='wall_clock'`. `scripts/backfill_time_clock_utc.py` (dry run default, `--apply`, `--revert`) converts with `offices.timezone` (null office → user's primary office → America/New_York) and marks `utc_converted`. **Not run** (needs the migration). All server date logic already reads `wall_clock` rows as local time. |
| TC-BE-10 | ✅ | Migration flags 856 of 857 open rows `auto_closed` / `missing_clock_out` (each user's newest open row survives only if it began < 20 h ago). Runtime policy in settings: `auto_close_after_hours` (20) + `auto_close_policy` = `flag` (default — 0 paid hours, **never a guessed time**) \| `office_close` (closed at the office's scheduled end time that day, flagged) \| `off`. Applied lazily on the user's next clock-in / clock-out, and by `scripts/auto_close_time_clock.py` (cron) / `POST /time-clock/auto-close?dry_run=`. |
| TC-BE-11 | ✅ | `user_name`, `username`, `office_name`, `timezone`, `work_date`, `created_by_name`, `updated_by_name`, `deleted_by_name` on every read (batched). |
| TC-BE-12 | ✅ | `entry_type` = `work` (default) \| `break` \| `lunch`. Only `work` is paid; break/lunch roll up as `break_hours`. Today's two-work-rows-per-day pattern keeps working unchanged. |
| TC-BE-13 | ✅ (hours × rate) | `include_wages=true` → `regular_pay`, `overtime_pay` (= OT × pay_rate × overtime_rate; rate falls back to the practice 1.5×), `total_pay`. Owner / admin / super_admin only (403 otherwise; `manager` excluded on purpose). Payroll-vendor CSV layouts (ADP / Gusto / Paychex) are **not** built — awaiting the spec. |
| TC-BE-14 | ✅ | `time_clock_periods` + `GET/POST /time-clock/periods`, `PATCH/DELETE /time-clock/periods/{id}`, `POST …/{id}/approve\|lock\|unlock\|reopen`. Overlap → 409 `period_overlap`. A **locked** period (office-specific or all-office) refuses create / PATCH / DELETE / restore of any entry whose office-local work date falls inside it → **409 `period_locked`**; a locked period cannot be deleted or re-dated. |

## Authorization (TC-BE-5)

| Caller | Read | Write |
|---|---|---|
| **Manager** = role `owner \| admin \| manager \| super_admin`, or the `utilities_time_clock_editor_full_control` right | everyone (office scope applies — `office_id`, `office_ids`, `all_offices`) | full CRUD, settings, periods, sweep |
| `utilities_time_clock_editor_view_only` | everyone | own punches only |
| anyone else | own rows only (another `user_id` → 403 `time_clock_forbidden`) | `/clock-in`, `/clock-out` |

A user in **no group is not a manager** (`has_strict`) — the punch data was never theirs to edit.
Non-manager writes outside the rules → 403 `time_clock_manager_required`.

**Transitional path (no FE release needed on deploy day):** a non-manager's `POST /time-clock-entries`
for themselves with no `clock_out` *is* a clock-in, and a `PATCH {clock_out[, total_hours]}` on their own
running shift *is* a clock-out — both routed to the action, so the client's timestamps are discarded.
Today's FE keeps working and the client-time hole is closed immediately. Drop it once `timeClockService.ts`
calls the actions.

`GET /time-clock/metadata` gives the FE everything to drive the UI: vocabularies, issue labels, practice
settings, `capabilities {can_edit, can_view_all, can_view_wages}` and the caller's own
`effective_rules` (incl. `clock_in_required` — `GET /users/{id}/time-clock-config` is admin-only, so a
staff user could never read their own flag).

## Read model additions

```
TimeClockEntryRead += entry_type, source, clock_basis, notes, created_by(+_name),
  updated_at, updated_by(+_name), is_edited, original_clock_in, original_clock_out, edit_reason,
  is_active, deleted_at, deleted_by(+_name), delete_reason, auto_closed, auto_closed_at,
  auto_close_reason, user_name, username, office_name, timezone, work_date,
  is_open, is_stale, issues[]
issues ⊂ { open, missing_clock_out, auto_closed, clock_out_before_clock_in, long_shift (>12h) }
```

`is_open` = no clock_out, active, not auto-closed. `is_stale` = open past `auto_close_after_hours`
(`/me/active` returns **204** for a stale row — the punch button must not show a 30-hour timer).

## Decisions worth knowing

- **A missing clock-out is never given a time by default.** A guessed clock-out is a guessed wage; the
  row is flagged and pays 0 until a manager corrects it. `office_close` is opt-in.
- **A stale shift does not block the user.** Clock-in auto-flags yesterday's forgotten row first;
  clock-out on a stale row flags it and returns 409 `not_clocked_in` with `details.auto_closed_entry`
  instead of paying 30 hours.
- **Days are office-local.** Report bucketing, range filters and period locks all use the office's
  timezone on the clock-in instant; `wall_clock` rows are read as-is.
- **Weekly overtime looks back.** The report reads the part of the first week before `from`, so a
  Wed–Fri report still knows Mon–Tue's hours.
- **`daily_weekly`** = daily OT first, then the weekly test over the remaining regular hours — never
  double-counted. California's 7th-day / double-time rules are not modelled (`california` folds here).

## FE switch-over

| Gap | FE change |
|---|---|
| TC-BE-1/2 | `clockIn()` / `clockOut()` → the action endpoints; map 409 `already_clocked_in` / `not_clocked_in` (drop the client pre-check). `fetchActiveEntry()` → `/me/active` (204 = not clocked in). |
| TC-BE-3 | Stop sending `total_hours`. |
| TC-BE-4 | `fetchEntriesInRange()` passes `clock_in_from/to` (+ `tz` if not office-scoped); drop the crawl + `truncated` banner. |
| TC-BE-5 | Role gate from `metadata.capabilities` instead of the role string. |
| TC-BE-6 | "Edited by `updated_by_name` on `updated_at`", originals from `original_clock_*`, history from `/history`; send `reason` on PATCH / `?reason=` on DELETE; "Delete" is no longer permanent (restore exists). |
| TC-BE-7 | Default the overtime select from `metadata.effective_rules.overtime_method` (or the user's config). |
| TC-BE-8 | `HoursReport` reads `/reports/time-clock`; CSV / PDF from the server. |
| TC-BE-9 | Render per row by `clock_basis` (`wall_clock` → UTC; else office `timezone`) — safe **before and after** the backfill, so `LEGACY_WALL_CLOCK_ZONE` can go as soon as this ships. |
| TC-BE-10 | "Missing clock-out" from `issues` instead of the FE's 20-hour rule. |
| TC-BE-11 | Drop the `/users` directory crawl. |
| TC-BE-14 | Period screen on `/time-clock/periods`; surface 409 `period_locked`. |

## Ops

```bash
python -c "from alembic.config import main; main(['upgrade','head'])"   # after reconciling fc6450e398ee
python -m scripts.backfill_time_clock_utc            # dry run, then --apply (coordinate with FE)
python -m scripts.auto_close_time_clock --dry-run    # then hourly cron without --dry-run
```
