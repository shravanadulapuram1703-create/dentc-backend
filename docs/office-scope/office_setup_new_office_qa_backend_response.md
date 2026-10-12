# Office Setup — New-office QA pass: backend response

**Date:** 2026-10-11 · **Report:** [office_setup_new_office_qa_backend_devreport.md](office_setup_new_office_qa_backend_devreport.md)
· **Alembic:** `8d1ef924bb92` (**applied to the dev DB**) · **Tests:** `tests/test_office_setup_qa.py` (25)

All 18 items are addressed (OFF-QA-14 and the delete-office items OFF-QA-15…18 were added after the first pass; Alembic `81e09d9576e9` for OFF-QA-16, also **applied**). Two parts were deliberately done differently from the ask:
**OFF-QA-3** keeps `office_code` globally unique, and **OFF-QA-13** uses
`ON CONFLICT DO NOTHING` for the 1:1 settings rows. The reasons are below.

New validation rules are listed in one place: `GET /offices/setup-rules`
(`app/services/office_rules.py`). The form can read them from there.

| # | Status | What changed |
|---|---|---|
| OFF-QA-1 | ✅ | Custom address used as a block. `logo_source` = `custom \| account \| none` (**breaking**) |
| OFF-QA-2 | ✅ | `Literal` vocabularies (case-folded, else 422) + stored rows normalised |
| OFF-QA-3 | ✅ / ⚠️ | 409 `duplicate_short_id` (per tenant) and 409 `duplicate_office_code` (global). No DB constraint yet (the `MOON` pair) |
| OFF-QA-4 | ✅ | Per-day time validation (422 with `loc`). PUT upserts only the days sent |
| OFF-QA-5 | ✅ | `EmailStr`, http(s)-only URLs, verify-email send + confirm |
| OFF-QA-6 | ✅ | Catalog served until first save, `/smart-assist/catalog`, SMS-template lookup + validation |
| OFF-QA-7 | ✅ | `GET /offices/{id}/calendar`. 409 `office_closed` on create/move, with override |
| OFF-QA-8 | ✅ | Ranges/formats, POS words → CMS codes. ADA Item 38 now defaults from the office |
| OFF-QA-9 | ✅ | NPI 10 digits + Luhn, NUCC taxonomy shape |
| OFF-QA-10 | ✅ | Office pointers checked field by field. Raw driver text removed from **every** DB error |
| OFF-QA-11 | ✅ | `OperatoryCreate.id` optional. Server generates `op-{office}-{n}` |
| OFF-QA-12 | ✅ | `observed` (default **true**) on both federal-import routes |
| OFF-QA-13 | ✅ | Schedule/SmartAssist GETs write nothing. Settings singletons are race-safe |
| OFF-QA-14 | ✅ | `POST /offices` with `X-Office-ID` → 201 (was 500) |
| OFF-QA-15 | ✅ | `GET /offices/{id}/delete-impact`. 409 `office_in_use` unless `?force`. Operatories deactivated (and restored on reactivate). 409 `office_inactive` on new writes |
| OFF-QA-16 | ✅ | `deleted_at`/`deleted_by`/`deleted_by_name` on `OfficeRead`. Stamped on DELETE, cleared on reactivate |
| OFF-QA-17 | ✅ | `DELETE /offices/{id}?hard=true` (admin/owner/super_admin), only when nothing references the office |
| OFF-QA-18 | ✅ | Already there: `me-full.offices[].is_active`. Working office now never resolves to an inactive one |

---

## OFF-QA-1: letterhead

`print_service.resolve_letterhead`: when `address_source = custom`, lines 1/2, city,
state and zip all come from the custom block. A blank line 2 stays blank. Only an
**entirely empty** custom block falls back to the office address. The phone is not
part of the postal block, so a blank custom phone still prints the office phone.

**Breaking:** `OfficeRead.letterhead.logo_source` is now
`custom` (Statement-tab upload) | `account` (Account Info practice logo) | `none`.
The old values were `office` | `tenant`.

## OFF-QA-2: vocabularies

| field | accepted (case-insensitive in) | stored |
|---|---|---|
| `logo_option` | office, custom, none | lowercase |
| `address_source` | office, custom | lowercase |
| holiday `status` | CLOSED, OPEN, HALF_DAY (also `half day`) | uppercase |
| holiday `holiday_type` | FEDERAL, CUSTOM | uppercase |

These apply on the office **and** account holiday routes, including `/holidays/range`
and `/holidays/federal`'s `status`. Any other value returns 422. The migration
normalised the stored rows. On the dev DB, 5 `Custom` holidays became `CUSTOM`; the
statement rows were already lowercase. The frontend's read-side normalisation can be
removed.

## OFF-QA-3: Short ID / office code

- **Short ID:** unique per tenant, case-insensitive and trimmed. A clash returns
  409 `duplicate_short_id`, with `details.office_id`/`office_name` of the clashing
  office. The check only runs when the Short ID changes, so the existing **`MOON`
  pair (offices 1 and 4)** can still be edited. There is **no DB constraint yet**:
  a constraint would need that pair resolved first, which is a practice decision
  (rename one?). Once it is resolved, the unique index on
  `(tenant_id, upper(short_id))` is a single migration.
- **Office code: not made tenant-scoped.** `office_code` is the AppointNow public
  booking key: `/appointnow/{office_code}` resolves the office **without a tenant**
  (`appointnow_service.resolve_public_office`). If two tenants could both have
  `MAIN`, that anonymous page could not tell which office is meant. The lookup is
  also case-insensitive while the DB constraint is not, so `MAIN` + `main` would have
  500'd the booking page. The write path now returns 409 `duplicate_office_code` for
  a case-insensitive clash across all tenants. The error never names the other
  office, because it may belong to another tenant.

## OFF-QA-4: weekly schedule

- Per day: an open day needs both start and end, with end after start. Lunch must
  have both times or neither, end after it starts, and fall inside the day. A
  repeated `day_of_week` is rejected. Errors are 422 with `loc = ["body","days",<i>,…]`.
- **`PUT /offices/{id}/schedule` upserts only the days sent.** An omitted day keeps
  its stored row. Send all 7 to set the whole week. A day with `is_closed: true` has
  its stored times cleared.

## OFF-QA-5: integrations

- `service_email` is validated with `EmailStr` (blank clears it).
  `patient_comm_url`/`patient_portal_url` must be `http(s)://` with a host, so
  `javascript:`, `data:` and `ftp:` all return 422.
- `service_email_verified` is now **server-owned** (no longer writable through PATCH).
  Changing the address resets it to false.
- `POST /offices/{id}/integrations/verify-email` mails a 6-digit code (valid 24 h)
  to the saved address. The response includes `transport` (`graph|smtp|log`); `log`
  means no mail transport is configured and the code only appears in the server log.
- `POST …/verify-email/confirm {code}` marks the address verified. It allows 5 wrong
  tries before a new code is needed. Only the code's sha256 is stored, bound to the
  office and the address. New columns are in the migration.

## OFF-QA-6: SmartAssist

- `GET /offices/{id}/smart-assist` now returns the **catalog defaults** for an office
  that has not saved its grid yet (`items_source: "catalog"`, `id: null`, every
  item `is_enabled: false`). Nothing is written until the first PATCH. Every item
  carries a `label`. The catalog is the 12 codes the tab already labels, also
  available at `GET /offices/smart-assist/catalog`.
- `GET /offices/{id}/smart-assist/sms-templates` lists the office's own plus the
  tenant-shared active `sms_templates`. A PATCH with an `sms_template_id` outside that
  list returns 422 `unknown_sms_template` (`loc` points at the row), so the
  **4 placeholder ids in the frontend will now be rejected**; switch to the lookup. A
  repeated `item_code` returns 422.
- **What runs SmartAssist? Nothing yet.** No backend job or check reads these
  settings today. They are stored configuration only. A check-in/check-out executor
  is a product decision (which screen evaluates the items, and does it block?) and
  is not in this pass.

## OFF-QA-7: office hours and holidays

- `GET /offices/{id}/calendar?from_date&to_date` (≤ 400 days) returns, per date:
  `is_open`, `start_time`/`end_time`, `lunch_*`, `closed_reason`
  (`closed_day|holiday`), the effective `holiday` (an office row beats an account
  row), `hours_source` (`stored|default`) and `hours_enforced`.
- Staff `POST /appointments`, and a PATCH that **moves** one (date/time/office
  changes), into a closed slot return **409 `office_closed`**, with
  `details.reasons[]` (`kind: holiday|closed_day|outside_hours|lunch`) and
  `override_field: "allow_outside_office_hours"`. Sending
  `allow_outside_office_hours: true` books it anyway. A PATCH that does not move the
  appointment (notes, status, …) is never blocked.
- **Hours only apply to an office that has saved its week.** A weekday with no
  stored row reports the 8–5 default but does not enforce it. Enforcing a default
  nobody chose would block existing workflows at every migrated office on deploy
  day. A `CLOSED` holiday always applies. `HALF_DAY` stores no hours, so it is
  reported but never blocks.
- Kill switch: `OFFICE_HOURS_ENFORCED` (default on).
- The scheduler feed was left unchanged. Read the calendar endpoint once per visible
  range.

## OFF-QA-8: advanced settings

- Percentages 0–100, money ≥ 0, `days_before_charge` 0–3650,
  `default_appt_duration` 5–720, `area_code` = 3 digits, `default_state` = 2 letters
  (upper-cased), `place_of_service` = 2-digit CMS code. Old words (`office`,
  `hospital`, …) are still **accepted** and converted to codes. The migration
  converted stored words (none on the dev DB).
- `preferred_provider_id` returns a field-level 422 when it is not a provider in the
  tenant.
- **Consumers:** ADA claim **Item 38** now resolves claim → office
  `place_of_service` → `11`, with `place_of_treatment_source = claim|office|default`.
  `preferred_provider_id`, `default_appt_duration`, the finance-charge fields,
  `area_code` and the default city/state/zip **still have no backend consumer**.
  They are stored for the UI. Wiring them (finance charges especially) needs a
  product spec.

## OFF-QA-9: NPI / taxonomy

`npi` must be 10 digits and pass the CMS Luhn check (prefix `80840`), otherwise
422 `invalid_npi`. `taxonomy_code` is upper-cased and must match
`^[0-9]{3}[0-9A-Z]{6}X$`, otherwise 422 `invalid_taxonomy_code`. Both checks only run
when the value changes, so office 40's stored values are not re-judged on an
unrelated save.

## OFF-QA-10: database internals

- Office writes check `billing_provider_id`, `default_fee_schedule_id`,
  `default_ucr_fee_schedule_id` and `office_group_id` against the tenant first. A bad
  value returns 422 `provider_not_found`/`fee_schedule_not_found`/`office_group_not_found`
  with `details.loc = ["body", <field>]` and `msg`.
- **API-wide:** `app_error_from_db` no longer returns `details.db_message` (the raw
  Postgres text). It is logged server-side. A single offending column is now also
  reported as `field` + `loc`. `sqlstate`/`table`/`column`/`constraint` remain.

## OFF-QA-11: operatory ids

`OperatoryCreate.id` is optional. When it is omitted, the server generates
`op-{office_id}-{n}` using the first unused `n`, so a remove-then-add without a
reload no longer collides. An explicit id is kept (imports keep `OPR-102`).

## OFF-QA-12: observed federal holidays

`FederalHolidaysImport.observed` defaults to **true**: a Saturday holiday is stored on
the Friday before, a Sunday holiday on the Monday after, named `… (observed)`. Example:
2026-07-04 → **Fri 2026-07-03**. `observed: false` keeps the calendar dates. This
applies to both the office and the account route.

## OFF-QA-13: side-effecting GETs

- `GET /schedule` and `GET /smart-assist` no longer write anything. They return the
  defaults with `id: null` until the first save. Keeping "never saved" distinct
  from "saved as 8–5" is also what makes the OFF-QA-7 rule possible.
- The 1:1 settings rows (statement / integrations / advanced) are still created on
  first read, because their read models carry an `id`. The insert is now
  `INSERT … ON CONFLICT (office_id) DO NOTHING` followed by a re-read, so two
  concurrent first reads land on the same row and neither returns a 500.

## OFF-QA-14: `POST /offices` 500 with a working office selected

Fixed both ways the report suggested:

1. `create_item` (`app/crud/router_factory.py`) skips the write-stamp for a
   `list_scope_only` resource. `offices` uses the office scope only to narrow its list,
   and an office is not a record owned by an office.
2. `apply_write_office` now takes the model and only **stamps** `field` /
   `created_office_field` when that column exists. Any other resource configured the
   same way can no longer turn the header into a `TypeError`.

A body-supplied office is still validated as before. Regression tests:
`test_create_office_with_working_office_header` (POST → 201, then PATCH with the header
→ 200) and `test_write_stamp_skips_columns_the_model_lacks`. No frontend change is
needed: keep sending the header.

## OFF-QA-15: office delete dependency check

**`GET /offices/{id}/delete-impact`** returns everything in one call:

```json
{"office_id": 40, "is_active": true, "as_of": "2026-10-11",
 "future_appointments": 3, "home_patients": 12, "assigned_users": 4,
 "users_with_no_other_office": 1, "stranded_user_ids": [17],
 "providers": 2, "operatories": 2,
 "blocking": ["future_appointments", "users_with_no_other_office"]}
```

- `future_appointments`: not archived, not cancelled, dated on or after **the
  office's local today**.
- `home_patients`: active patients whose `home_office_id` is this office.
- `users_with_no_other_office`: active users who have no other **active** office
  assigned.
- `providers`: active providers on the office roster (`provider_offices`) plus those
  whose legacy home office is this one (the PROV-1 union).
- `operatories`: active chairs.

**`DELETE /offices/{id}`** (same `delete_office` operation id; now a dedicated route):
- **409 `office_in_use`** while `blocking` is non-empty. `details.impact` carries
  the payload above and `override_param: "force"`. **`?force=true`** deletes anyway.
- **What a delete does to operatories (forced or not):** the office's active chairs
  are deactivated, so an inactive office never shows bookable columns. Their ids are
  remembered on the office (`deleted_operatory_ids`). Reactivating
  (`PATCH is_active: true`) turns **exactly those** back on; a chair that was already
  retired before the delete stays retired.
- Upcoming appointments are **not** cancelled or moved. They are real bookings, and
  staff should move them. Assignments of stranded users are **not** removed.
- Honours `If-Match` like the generic route did. Still returns 204. The path
  parameter is now named `office_id` (was `item_id`); the call shape is unchanged.

**AppointNow, confirmed:** `resolve_public_office` already returns 404
`office_not_found` for an inactive office, so the public page stops taking
bookings. A gap remained: a request **still pending** when the office was deleted
could be approved or paid into it. `book_request` (shared by approve and the
payment webhook) now returns 409 `office_inactive`.

**New writes into an inactive office, confirmed missing before; now 409 `office_inactive`:**
- any office-scoped create whose body `office_id` is inactive (`loc: ["body","office_id"]`);
- a create stamped from an inactive **`X-Office-ID`** (`loc: ["header","X-Office-ID"]`);
- a PATCH that **moves** a record onto an inactive office. A record already at that
  office stays editable, even when the form re-sends its own office;
- `POST /appointments`, and an appointment PATCH that changes `office_id`, even with
  `allow_outside_office_hours`.

Reads with an inactive `X-Office-ID` are not refused.

Not changed: setting Status → Inactive on the Info tab (`PATCH is_active:false`)
does not run the dependency check. It is the deliberate, reversible switch.

## OFF-QA-16: delete vs inactive

New `offices.deleted_at`, `deleted_by` (FK users) and `deleted_operatory_ids` columns.
They are server-owned: excluded from Create/Update, so a client cannot write them.
`OfficeRead` returns `deleted_at`, `deleted_by` and `deleted_by_name`.
- Deleted office: `is_active=false` with `deleted_at` set.
- Inactive office: `is_active=false` with `deleted_at=null`.

The audit row for the delete records `deleted`, `forced`, the deactivated operatory
ids and the impact counts.

## OFF-QA-17: hard delete

`DELETE /offices/{id}?hard=true` is limited to `admin`/`owner`/`super_admin`; any
other role gets 403 `hard_delete_forbidden`. It walks **every foreign key into
`offices`** from the model metadata (70 today). A table added later is therefore
checked automatically, with no list to keep up to date. It also checks every foreign
key into the operatories it would remove (appointments,
`providers.default_operatory_id`, booking requests).

Any hit returns **409 `office_in_use`** with `details.references: [{table, column}]`.
**User and provider assignments block it**, as asked.

When nothing references the office, it is removed together with its own
configuration: statement / integration / advanced / smart-assist (+ items) /
schedule days / office holidays / phone assignments / the office assignment grids /
AppointNow reasons / operatories. Any user's remembered `current_office_id` pointing
at it is cleared.

On the dev DB the check takes about 2 s for an unreferenced office (it has to scan
some large tables to prove there are no references). That is acceptable for a
rare admin action.

## OFF-QA-18: me-full and inactive offices

**This already existed:** every `me-full.offices[]` entry has carried `is_active`
since OFF-SCOPE-10, so "My offices" can hide or grey them out today with no API
change.

Added: `current_office_id` never resolves to an inactive office while the user has
an active one. A remembered working office that has since been deleted falls back to
the active primary, then to the first active office. Otherwise every write would be
`office_inactive`.

---

## Frontend action items

1. `letterhead.logo_source`: `office`→`custom`, `tenant`→`account`.
2. SmartAssist: render `items_source: "catalog"` rows (null `id`); use `label`; pick
   templates from `/smart-assist/sms-templates` (placeholder ids now 422).
3. Integration tab: add Send code / Confirm against the two verify-email routes;
   stop sending `service_email_verified`.
4. Scheduler: read `/offices/{id}/calendar`; on 409 `office_closed` show the reasons
   and offer a re-submit with `allow_outside_office_hours: true`.
5. Operatories: stop generating `op-…` ids; omit `id` on create.
6. Schedule tab: a partial PUT is now safe. `id` can be null on unsaved days.
7. Delete Office: replace the 5 count calls with `GET /offices/{id}/delete-impact`;
   on 409 `office_in_use` show `details.impact` and offer `?force=true`; for a
   test/typo office offer `?hard=true` (admin) and show `details.references` on 409.
   Show `deleted_at`/`deleted_by_name` to tell deleted from inactive. Handle 409
   `office_inactive` on writes (switch the working office).
8. Regenerate the Orval client. New components: `OfficeScheduleDayInput` /
   `OfficeScheduleReplace` (renamed from module-prefixed collision names so they stop
   changing between builds). Two **pre-existing** collisions elsewhere also changed
   names in this regeneration (`FeeScheduleOption`, `MedicalAlertIn`; this happens
   whenever route order shifts). Fixing those properly means renaming the colliding
   classes in their own modules.
