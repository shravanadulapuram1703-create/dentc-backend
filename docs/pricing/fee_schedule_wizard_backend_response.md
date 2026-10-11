# New Fee Schedule Wizard — backend response (FSW-1..9)

_2026-10-11 · answers [fee_schedule_wizard_backend_devreport.md](fee_schedule_wizard_backend_devreport.md) ·
no migration · tests: `tests/test_fee_schedule_wizard.py` (26)_

All nine gaps are closed. New code lives in
[`app/services/fee_schedule_wizard_service.py`](../../app/services/fee_schedule_wizard_service.py);
routes are in [`app/api/v1/fee_schedules.py`](../../app/api/v1/fee_schedules.py). `openapi.json` is
regenerated, so run Orval.

| ID | Status | What to call |
|---|---|---|
| FSW-1 | Done | `POST /fee-schedules/wizard` |
| FSW-2 | Done | `POST /fee-schedule-assignments/bulk` |
| FSW-3 | Decided: office pointer, applied atomically by the wizard | `office_defaults` on the wizard |
| FSW-4 | Done | `legacy_schedule_types` on `/fee-schedules/metadata`; legacy labels accepted as `fee_type` |
| FSW-5 | Done, plus data backfill | `specialty_id` = taxonomy code; `GET /provider-specialties` |
| FSW-6 | Done | `GET /providers?office_ids=1,9` → `served_office_ids` |
| FSW-7 | Done | new filters on `GET /fee-schedule-assignments`, or the bulk `dry_run` |
| FSW-8 | Done | `POST /fee-schedules/{id}/entries/import` (csv + xlsx) |
| FSW-9 | Done | `GET /fee-schedules/{id}/scope` |

## FSW-1 — `POST /fee-schedules/wizard`

Steps 1–4 run in **one transaction**:

```json
{
  "schedule": {"name": "Delta PPO 2026", "fee_type": "Ins-PPO", "effective_date": "2026-01-01"},
  "copy_from_schedule_id": 137,
  "entries": [{"procedure_code": "D0120", "patient_fee": 55}],
  "assignments": [{"provider_id": "PRV-100", "office_id": 1}, {"specialty_id": "1223X0400X"}],
  "on_conflict": "error",
  "office_defaults": {"office_ids": [1, 9], "set_default_fee_schedule": true},
  "dry_run": false
}
```

- **All or nothing.** These roll back everything and write nothing:
  - an unknown procedure code, a negative fee, or Plan Pays on a percentage list → **422**
  - an invalid assignment or office → **422**
  - an assignment conflict while `on_conflict` is `"error"` → **409**

  In each case `error.details` (with `code: "fee_schedule_wizard_failed"`) holds the same report a
  success returns. The UI can render every failed row from it and doesn't need to guess what landed.
- **201 response:** `fee_schedule`, `entries` {`created`, `copied`, `dropped_plan_pays`,
  `effective_date`, `errors`}, `assignments` {`summary`, `outcomes[]`}, `office_defaults`
  {`results[]`, `errors[]`}.
- **`dry_run: true`** returns that report with **200** and writes nothing (`fee_schedule.id` is
  `null`). This is the "Review before Apply" call.
- **Entry dates:** entries take `entries_effective_date`, else the schedule's `effective_date`, else
  today. A `effective_date` on a single entry overrides that for its row.
- **Copy From Existing:** `copy_from_schedule_id` copies each code's price *in force* on that date.
  Explicit `entries` override the copied ones. If the new list isn't a copay list, Plan Pays amounts
  are dropped and counted in `dropped_plan_pays`. A retired source is allowed.
- **Assignments:** each row's `fee_schedule_id` is ignored, because the rows bind to the new schedule.
- Validation is the same code the per-row endpoints use, so the wizard cannot accept a row that
  `POST /fee-schedule-assignments` would refuse.

## FSW-2 — `POST /fee-schedule-assignments/bulk`

`{on_conflict: "error"|"rebind"|"skip", dry_run, assignments: [{fee_schedule_id, provider_id, office_id, …}]}`
(max 2,000 rows).

- **Per-row `status`:** `created` · `rebound` · `unchanged` · `skipped` · `conflict` · `error`
  (with `error_code`). Conflict and rebound rows also carry `previous_fee_schedule_id` and
  `previous_fee_schedule_name`.
- **`unchanged`** means the target is already bound to that same schedule. It is never a conflict,
  so re-applying is idempotent.
- **Error codes** you'll see:
  - `assignment_needs_target`
  - `assignment_schedule_invalid`
  - `assignment_provider_invalid`, `assignment_office_invalid`, `assignment_target_invalid`
    (the id doesn't exist in the tenant)
  - `assignment_specialty_unknown`
  - `assignment_duplicate_in_request` (same target twice in one payload, with `duplicate_of_index`)
- **Failure:** any `error` row returns 422; any `conflict` row while `on_conflict` is `"error"`
  returns 409. Either way the whole batch rolls back and `details.outcomes` lists every row.
- **`dry_run`** returns 200 with the report and writes nothing. This is the conflict probe for the
  "Currently Bound To" column (FSW-7).

## FSW-3 — Office + All Providers → the office pointer (confirmed)

The data backs the mapping the wizard uses. In the Denticon export:

- `FeeScheH.OID` is `0` on all 36 headers.
- `FeeScheA` contains no office-only row.

So a Denticon "Office" schedule applied to specific offices for all providers is
`Office.PATIENTFEEID`. That is our `offices.default_fee_schedule_id`, tier 5 of the precedence card.

Office-scoped assignment rows stay refused (`assignment_needs_target`). They would be a second
"default for this office", competing with the pointer that Office Setup maintains. The migrated
tenant's eight all-NULL rows show what that turns into.

What changed is that the wizard now sets the pointer **inside the same transaction**:

- Pass `office_defaults.set_default_fee_schedule`, and optionally `set_ucr_fee_schedule`.
- Each result reports `previous_default_fee_schedule_id` / `_name` and `replaced_default`, so the
  confirmation step can say "replaces *UCR -Excel Dental* on Office 1".

The pointer is also the office's tier in pricing. **Whether a new patient registered at that office
is pre-filled with it is a frontend choice**, and the server doesn't do it. If replacing it shouldn't
change the new-patient default, keep that prefill on its own setting.

## FSW-4 — legacy schedule types

`GET /fee-schedules/metadata` now includes `legacy_schedule_types[]`. Each `fee_types[]` entry also
gains `legacy_labels`.

| Legacy radio | fee_type | pricing_model | evidence |
|---|---|---|---|
| Office | standard | percentage | export (FEETYPE 0: UCR-Excel, CP-40/50) |
| Ins-Smart Fee | carrier | percentage | **none — `provisional: true`** (FEETYPE 1 never occurs) |
| Ins-Managed Care | plan | copay | export (FEETYPE 2: Medicaid/HMO "Assign To Plan", INSAMT lists) |
| Ins-PPO | carrier | percentage | export (FEETYPE 3: 19 PPO "Assign To Carrier" lists) |
| Ins-Pat Co-pay | plan | copay | inferred from the name (FEETYPE 4 never occurs) |

You can send a legacy label as `fee_type` on `POST/PATCH /fee-schedules` or the wizard. Matching
ignores case and punctuation, and the `Ins-` prefix is optional. The label sets **both** columns;
an explicit `pricing_model` in the same payload still wins.

`ucr` has no radio. Being an office's UCR list is a pointer, not a schedule type.

**Smart Fee needs a product answer** before its mapping is trusted.

## FSW-5 — specialty is the taxonomy code

Denticon's `Providers.SPECIALTYID` and `FeeScheA.SPECIALTYID` both hold the **NUCC taxonomy code**
(`1223G0001X` on 85 of 93 exported providers). That is the catalog already published by
`provider_taxonomy_service`, so no new table was needed.

**On write:**
- An assignment's `specialty_id` is folded onto that code: `"orthodontist"` and `"Orthodontics"` are
  both stored as `1223X0400X`.
- An unrecognised value returns 422 `assignment_specialty_unknown`. This check only runs when the
  value changes, so legacy rows stay editable.

**In pricing (v1 and v2):**
- The provider's specialty key is the stored `taxonomy_code`, else the code derived from the
  free-text `specialty`.
- It is **never** the General-Dentist default, so a provider with no specialty can't match every
  "Dentist" assignment.
- Both sides of the match are compared in canonical form.

**`ProviderRead`** gains `specialty_code` and `specialty_label`.

**`GET /provider-specialties`** returns the catalog with `provider_count` and `provider_ids` per code
(active providers; use `?include_inactive=true` for all). It also lists codes that aren't in the
catalog, plus a "No specialty" bucket. The Specialties option should render this instead of the
`specialty` free text.

**Data:** `scripts/backfill_provider_specialties.py` (dry-run by default, NULL-only, writes a JSON
backup, `--restore` to undo).

## FSW-6 — `GET /providers?office_ids=1,9`

- Returns providers serving **any** listed office (home office ∪ `provider_offices`, the same union
  as `?office_id=`).
- Every `ProviderRead` now carries `served_office_ids`, read in one batched query per page.
- The wizard can drop its per-office `/offices/{id}/providers/effective` fan-out and the client-side
  union.

## FSW-7 — assignment filters

`GET /fee-schedule-assignments` gains:

- `specialty_id` (matched in canonical form, so a name works)
- `has_provider`, `has_specialty`, `has_payer` (booleans)
- `provider_ids` and `office_ids` (comma lists)

The "Currently Bound To" column needs either
`?provider_ids=<the listed providers>&has_payer=false` or a bulk `dry_run` (FSW-2). The bulk
`dry_run` also returns the bound schedule's name.

## FSW-8 — `POST /fee-schedules/{id}/entries/import`

**Request:** multipart `file` (`.csv` or native `.xlsx`; `.xls` is refused with a hint), plus
optional form fields `effective_date`, `dry_run`, `all_or_nothing`.

**Columns:**
- Matched by **header name**, not position.
- The Utilities template (`procedure_code, description, fee, effective_date`) works unchanged.
- Common spellings also work: `Code`, `Plan Pays`, `AMB Code`, `No Charge`, `Effective Date`.
- Amounts may carry `$` and thousands separators.
- Dates may be `YYYY-MM-DD`, `MM/DD/YYYY`, or real Excel dates.

**Validation:** each row gets the same checks as a single entry: known code, no negative fee, Plan
Pays only on a copay list, and no duplicate code+date in the file.

**Rows without a date:** a blank `effective_date` uses the form's date, else the schedule's
`effective_date`, else today.

**Report:** `{total_rows, valid_rows, error_rows, created, updated, written, errors: [{row, procedure_code, code, message}]}`.
`row` is the 1-based data row, the same numbering as the browser validator.

**What gets written:**
- Valid rows are upserted on `(schedule, code, effective_date)`.
- With `all_or_nothing`, any error means nothing is written.
- A bad header returns 422 `import_header_invalid`.

## FSW-9 — `GET /fee-schedules/{id}/scope`

Returns:

- `assignments[]`, denormalised with provider, office, carrier, plan and specialty names and the
  `fee_source` each row prices as
- `offices`, `providers`, `specialties`, `carriers`, `plans`
- `office_pointers[]` (`is_default_fee_schedule` / `is_ucr_fee_schedule`)
- `patients` count
- a `wizard` block in the wizard's own vocabulary, which "Edit Schedule" can use to re-enter the
  wizard:

```json
{"offices": {"mode": "specific", "office_ids": [1, 9]},
 "providers": {"mode": "providers", "provider_ids": ["PRV-100"], "specialty_ids": []},
 "is_office_default": true}
```

Payer rows and legacy rows with no target never count toward the provider scope.

**Example (live dev DB):** UCR -Excel Dental reads as specific offices `[1,5,6,7,8,12,13]`, all
providers, office default.

## Frontend follow-ups

- Replace the Apply fan-out with `POST /fee-schedules/wizard`. Call it with `dry_run: true` for the
  review step.
- Replace the per-office provider calls with `GET /providers?office_ids=` and `served_office_ids`.
- Replace the full assignment-table paging with the bulk `dry_run` (or `?provider_ids=`).
- Build the Specialties option from `GET /provider-specialties`. Send taxonomy codes as `specialty_id`.
- Point "Import From Excel File" at the server import and accept `.xlsx`.
- Rebuild "Edit Schedule" on `/scope`.
