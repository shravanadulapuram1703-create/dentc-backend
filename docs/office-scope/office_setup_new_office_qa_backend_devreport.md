# Office Setup — New-office QA pass: backend dev report

**Date:** 2026-10-11 · **Screen:** Setup → Offices → Office Setup (all 8 tabs) · **Backend:** local `:8000`

## How this was tested

Created a test office **`ZZ Test Office QA` (id 40, short ID `ZZQA`)** through the UI, filled every
field on every tab, saved, reopened and checked that each value round-tripped. Then sent invalid values
directly to the API, **on office 40 only**, to check server-side validation. Office 40 was restored to
valid values afterwards.

Test data left behind (safe to delete or keep):
- Office **40** `ZZ Test Office QA` (active) with 2 operatories (`op-40-1`, `op-40-2`), 11 federal
  holidays, 1 custom holiday, and statement / integration / advanced settings filled in.
- Office **42** `ZZ dup probe (QA - inactive)`: created by the duplicate-Short-ID probe (OFF-QA-3),
  then deactivated and its Short ID renamed to `ZZQA2`.

Severity: 🔴 blocks / corrupts data · 🟠 wrong behaviour users will hit · 🟡 hardening / cleanup.

---

## OFF-QA-1 🟠 Letterhead mixes the custom statement address with the office address

`resolve_letterhead()` (`app/services/print_service.py`) falls back **per field** when
`address_source = custom`:

```python
pick = (lambda custom, base: (custom or base)) if custom_address else ...
```

So a custom statement address with a blank line 2 picks up the **office's** line 2. Observed on
office 40 (`OfficeRead.letterhead` after saving the Statement tab):

| field | custom statement address | office | letterhead printed |
|---|---|---|---|
| address_line1 | `PO Box 55` | `100 Test Street` | `PO Box 55` |
| address_line2 | *(blank)* | `Suite 2` | **`Suite 2`** ← wrong |
| city | `Wexford` | `Pittsburgh` | `Wexford` |

Every report header and statement prints "PO Box 55, Suite 2, Wexford PA", which is not a real address.

**Ask:** when `address_source = custom`, use the custom block **as a whole**: a blank line 2 stays
blank. Fall back to the office only when the entire custom block is empty. (Side note: `logo_source`
reports `"office"` for a custom upload and `"tenant"` for the account logo. Consider
`custom | account | none`.)

## OFF-QA-2 🟠 Enum-like string fields accept anything (and casing is inconsistent)

Probes on office 40, all returned **200/201**:

| endpoint | body | stored |
|---|---|---|
| `PATCH /offices/40/statement-settings` | `logo_option:"garbage", address_source:"weird"` | stored verbatim |
| `POST /offices/40/holidays` | `status:"WHATEVER", holiday_type:"weird"` | stored verbatim |

Casing: the model comments say `logo_option` is `office|custom|none` and `holiday_type` is
`FEDERAL|CUSTOM`. The federal import writes `"FEDERAL"`, but older frontend builds wrote `"OFFICE"`/`"CUSTOM"`
(statement) and `"Custom"`/`"Federal"` (holidays). The frontend now sends the canonical values and
normalises old rows on read (see below), but the database holds mixed casing.

**Ask:**
1. Use `Literal[...]` types in the schemas: `logo_option ∈ {office,custom,none}`, `address_source ∈ {office,custom}`,
   holiday `status ∈ {CLOSED,OPEN,HALF_DAY}`, `holiday_type ∈ {FEDERAL,CUSTOM}`. Unknown values → 422.
2. Data migration: lowercase `office_statement_settings.logo_option/address_source`, and uppercase
   `account_holidays.holiday_type`.

## OFF-QA-3 🟠 `short_id` is not unique; `office_code` is unique across *all tenants*

- `POST /offices {"short_id":"ZZQA","office_code":"ZZQA2"}` → **201**: a second office with Short ID
  `ZZQA`. Only `office_code` is unique. Existing data already has duplicates: **`MOON` ×2**.
- The unique constraint is `offices_office_code_key` on `office_code` **alone**, not
  `(tenant_id, office_code)`. Two tenants cannot both use an office code like `MAIN`.

**Ask:** unique `(tenant_id, upper(short_id))` returning `409 duplicate_short_id`, after resolving the
existing `MOON` pair. Make the `office_code` constraint tenant-scoped too.
*(Frontend now blocks a new or changed Short ID that matches another office; existing duplicates can
still be edited.)*

## OFF-QA-4 🟠 Weekly schedule: no time validation, and a partial PUT deletes omitted days

`PUT /offices/40/schedule` with
`{"days":[{"day_of_week":0,"start_time":"17:00","end_time":"08:00","lunch_start":"19:00","lunch_end":"18:00"}]}`
→ **200**, stored as sent. The response then held **only Monday**: Tue–Sun were deleted.

**Ask:**
1. Validate per day: `end_time > start_time`; lunch both-or-neither; `lunch_end > lunch_start`; lunch
   inside the day; an open day needs start and end. Return 422 with `loc` pointing at the day.
2. Either require all 7 `day_of_week` values, or upsert only the days sent. Silently deleting
   omitted days is data loss.
*(Frontend now validates the day/lunch times before saving.)*

## OFF-QA-5 🟠 Integrations: unvalidated email, `javascript:` URLs accepted, no email-verify flow

`PATCH /offices/40/integrations {"service_email":"not-an-email","patient_portal_url":"javascript:alert(1)"}`
→ **200**, stored verbatim. Those URLs are meant to be shown and opened as links, so a `javascript:`
URL is a stored-XSS vector for any client that renders it.

**Ask:** `service_email: EmailStr`; `patient_comm_url` / `patient_portal_url`: `HttpUrl` restricted to
`http`/`https`. Also, `service_email_verified` exists, but no endpoint sends or confirms a verification,
so every office shows "Not Verified" forever. Add `POST …/integrations/verify-email` (+ confirm), or
drop the flag.
*(Frontend now rejects invalid email and non-http(s) URLs.)*

## OFF-QA-6 🟠 SmartAssist can never be configured (no item catalog)

`GET /offices/{id}/smart-assist` returns `{"enabled":false,"items":[]}` for **every** office
checked (1, 2, 3, 5, 10, 40). `update_smart_assist` only replaces whatever items exist, and no catalog
or seed exists anywhere. The frontend renders rows **from the server's items** (by design, it does not
hard-code the catalog), so the SmartAssist tab is empty for every office.

**Ask:**
1. Seed the default item set when the settings row is first created, or expose
   `GET /smart-assist/catalog`. Codes the frontend already labels: `payment`, `email`, `cell_phone`,
   `eligibility`, `medical_history`, `hipaa`, `consent_form_1..4`, `progress_note`, `ledger_posting`.
2. Add an SMS-template lookup (`sms_template_id` is free text; the frontend shows 4 placeholder ids).
3. Confirm what executes SmartAssist. Nothing in the backend reads these settings today.

## OFF-QA-7 🟠 Office hours and holidays are not enforced for staff bookings

Only AppointNow (`appointnow_service.py`) honours `office_schedule_days` (closed days, lunch) and
`account_holidays`. Staff `POST/PATCH /appointments` ignore both, and the scheduler feed carries no
closure or holiday data. The Schedule tab tells users "Scheduler blocks bookings outside these hours"
and "Lunch time blocks availability", but nothing enforces that.

**Ask:** expose the office calendar to the scheduler, either as `closures`/`open_windows` in
`/appointments/scheduler` or as `GET /offices/{id}/calendar?from&to` (open windows, lunch, holidays
with status). On appointment create/move into a closed slot, return `409 office_closed` with an
explicit override flag, so staff can still book on purpose.

## OFF-QA-8 🟡 Advanced settings: no range/format validation, and most fields have no consumer

`PATCH /offices/40/advanced-settings {"finance_charge_pct":-5,"area_code":"abcd","place_of_service":"zzz"}`
→ **200**.

**Ask:**
1. Validation: percentages 0–100, money ≥ 0, `days_before_charge` ≥ 0, `area_code` = 3 digits,
   `default_state` = 2 letters, `place_of_service` = 2-digit CMS code.
2. **Data note:** the frontend previously stored words (`office`, `hospital`, `nursing_home`,
   `school`, `other`) and now stores CMS codes (`11`, `22`, `21`, `31`, `32`, `03`, `99`). Old words are
   mapped on read; please migrate existing rows (`office→11`, `hospital→22`, `nursing_home→32`,
   `school→03`, `other→99`).
3. Nothing in the backend reads `place_of_service`, `preferred_provider_id`, `default_appt_duration`,
   the finance-charge fields, `area_code` or the default city/state/zip. Please confirm the intended
   consumers. Example: ADA claim Item 38 should default from the office's `place_of_service`; claim
   fill-out still hard-codes `"11"`.

## OFF-QA-9 🟡 Office NPI / taxonomy not validated

`PATCH /offices/40 {"npi":"123"}` → **200**. **Ask:** `npi` must be 10 digits and pass the NPI Luhn
check (prefix `80840`). `taxonomy_code` should match `^[0-9]{3}[0-9A-Z]{6}X$`.
*(Frontend now enforces 10 digits. It also now saves `npi`/`taxonomy_code` to these office columns;
before, it kept them in browser storage and the claim form never received them.)*

## OFF-QA-10 🟡 FK violations leak database internals

A bad `billing_provider_id` / `default_fee_schedule_id` / `preferred_provider_id` returns 422 with
`details.sqlstate`, `db_message` (raw Postgres text) and constraint names. **Ask:** return a field-level
error instead (`{"loc":["body","billing_provider_id"],"msg":"Unknown provider"}`) and keep raw DB text
out of responses.

## OFF-QA-11 🟡 Operatory ids are client-supplied

`OperatoryCreate` requires `id`. The frontend makes up `op-{office_id}-{display_order}`, so
two operatories created at the same position (e.g. remove one and add another without reloading)
get the same id. Verified that posting an existing id (`op-40-1`) returns `409`, so the second save
fails. **Ask:** have the server generate the id (make `id` optional on create).

## OFF-QA-12 🟡 Federal holiday import uses actual dates, not observed dates

`POST /offices/{id}/holidays/federal {year:2026}` stores **Jul 4 2026 (a Saturday)**. Offices close on the
observed day (**Fri Jul 3**). **Ask:** add an `observed` option (default true), following the OPM rule
(Saturday → Friday, Sunday → Monday).

## OFF-QA-13 🟡 GETs create rows (side-effecting reads)

`GET /statement-settings`, `/integrations`, `/advanced-settings`, `/smart-assist` call
`get_or_create_singleton` and insert a row on first read. React StrictMode fires each GET twice in dev.
No duplicate showed up in this run (both GETs returned row id 6). Still, two concurrent first reads can
race the unique constraint and one would 500. **Ask:** return defaults without inserting on GET and
create on first PATCH, or use `INSERT … ON CONFLICT DO NOTHING`.

---

## Frontend fixes made in this pass (for context; no backend action)

| # | Fix | Files |
|---|---|---|
| FE-1 | "Add New Office" kept the previously opened office's id, so Statement/Integration/Schedule/Holidays/Advanced/SmartAssist showed **and saved to the old office**. Add/Cancel now clear it; add mode shows "Save the office first" instead of a stale "Pending backend" message. | `OfficeSetup.tsx` |
| FE-2 | Entity NPI + taxonomy were kept in browser storage only (and disabled in add mode). Now bound to `OfficeRead/Update.npi`/`taxonomy_code`; old browser values are read once as a fallback; the ADA claim form prefers the server value. | `OfficeSetup.tsx`, `InfoTab.tsx`, `officeData.ts`, `adaClaimFormData.ts` |
| FE-3 | Statement `logo_option`/`address_source` used uppercase and never matched the server's lowercase values ("Use office logo" displayed as "No logo will be printed"). | `officeStatementApi.ts`, `StatementTab.tsx` |
| FE-4 | Holiday dates displayed **one day early** in US timezones (`new Date("2026-01-19")` = UTC midnight). Fixed on Office, Account and Provider holiday screens via `formatIsoDateOnly`. | `utils/datetime.ts`, 3 holiday tabs |
| FE-5 | `holiday_type` sent `"Custom"`/`"Federal"` while the server uses `FEDERAL`/`CUSTOM`. The federal-row date lock never applied, and manual holidays defaulted to "Federal". | `accountSetupApi.ts`, 2 holiday tabs |
| FE-6 | Operatory "Default provider" picker was empty for a new office. Now lists this office's providers first, then everyone else (`ProviderOptionGroups`). | `OperatoriesTab.tsx` |
| FE-7 | Advanced "Default Preferred Provider" was a free-text box → provider picker. Place of Service now stores CMS codes. Form state renamed to snake_case. | `AdvancedTab.tsx` |
| FE-8 | Client-side validation for OFF-QA-3/4/5/9 (Short ID clash, day/lunch times, email + http(s) URLs, 10-digit NPI). | `OfficeSetup.tsx`, `ScheduleTab.tsx`, `IntegrationTab.tsx` |
