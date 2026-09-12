# Lab Tracking (M12) — backend response

Answers every gap in
[`lab_tracking_backend_devreport.md`](lab_tracking_backend_devreport.md) (re-verified
2026-09-11).

Migration **`587baa6a0ba7`** (`lab_tracking_gaps`) — **applied to `recondental_migrated`**.
`openapi.json` regenerated (480 paths); re-run Orval. Tests:
`tests/test_lab_tracking.py` (33).

| ID | Status | What shipped |
|----|--------|--------------|
| **LAB-1** | ✅ done | `labs` catalog (`/labs` CRUD + `/labs/name-availability`), `appointments.lab_vendor_id` (FK) + `lab_vendor_name` on reads, `lab_short_notice`; `lab_dds` **confirmed = the dentist** |
| **LAB-2** | ✅ done | `GET /appointments` accepts `has_lab`, `lab_vendor_id`, `lab_short_notice`, `lab_status`, `lab_sent_on_from/_to`, `lab_due_on_from/_to`, `lab_received_on_from/_to`; `lab_status` is also **on the read** |
| **LAB-3** | ✅ done | `AppointmentSchedulerRead` carries the whole lab block + `lab_vendor_name` + `lab_status` |
| **LAB-4** | ✅ done | `GET /appointments/lab-cases/cost-report` (+ `.pdf`), `…/report.pdf`, `…/export.csv` |
| **LAB-5** | ✅ done | `GET /appointments/lab-cases` — office-wide / per-patient, denormalised, paged, with per-status counts |
| **LAB-6** | ✅ done (API-wide) | `lab_dds` > 100 → 422 naming the field; the schema factory now propagates **every** `String(n)` length |
| **LAB-7** | ✅ done | `lab_cost`: `ge=0`, `max_digits=10`, `decimal_places=2` → 422 |
| **LAB-8** | ✅ done — **contract (a) + derive** | `has_lab=false` **clears** the lab block; lab data on a non-lab row **derives** `has_lab=true` |
| **LAB-9** | ✅ done | 422 `lab_date_order` on the merge of payload + stored row |
| **LAB-10** | ✅ done | `extra="forbid"` on `AppointmentCreate` / `AppointmentUpdate` |
| **LAB-11** | ✅ done — **option (a)** | archived rows leave `GET /appointments` by default (`?is_archived=true` opts back in); `/lab-cases` has `include_archived` |

---

## 1. Data model (LAB-1)

### Semantics — settled

| Field | Meaning | Bind it to |
|-------|---------|------------|
| `lab_dds` | **The dentist** the case is for (free text, ≤ 100). Legacy lab slips carry initials or an outside dentist, so it is not a providers FK. | Add/Edit Appointment → "DDS" |
| `lab_vendor_id` | **Which lab** the case went to — FK into the new `labs` catalog. `lab_vendor_name` is denormalised onto `AppointmentRead`, the scheduler feed and `/lab-cases`, so no name lookup is needed. | Lab Tracking → "Lab"; (optionally the appointment form) |
| `lab_short_notice` | The legacy rush flag. `bool`, default `false`, never null. | Lab Tracking → "Short Notice" |

Both new columns are on `AppointmentCreate` / `AppointmentUpdate` / `AppointmentRead`
(generated), so the two screens bind to the same names. Please stop reading
`GET /definitions?group_code=LAB` — there is no such group and there will not be one;
the vendor list is `GET /labs?is_active=true`.

### `labs`

`GET/POST/PATCH/DELETE /labs` (soft delete → `is_active=false`), tag *Appointments*.
Columns: `name` (required, ≤ 200), `code`, `contact_name`, `phone`, `fax`, `email`,
`address_line1/2`, `city`, `state`, `zip`, `default_turnaround_days` (so the FE can
pre-fill Due On = Sent On + n), `notes`, `office_id` (nullable = every office),
`is_active`, `created_by`/`updated_by` (+ `_name` on the read). Filters `office_id`,
`is_active`; `?ids=1,2,3` batch lookup; `search` over name/code/contact/phone/email/city.

Duplicate prevention is the INS-PT-13 shape, **not a DB constraint**: `POST /labs` with
an *active* lab of the same name (trimmed, whitespace-collapsed, case-insensitive) is
**409 `duplicate_lab_name`** with `details.matches[]`; `allow_duplicate_name: true`
overrides (the same lab name in two states is legitimate). Only *create* is guarded — a
rename onto a taken name is usually a deliberate merge. `GET /labs/name-availability?name=`
(`&exclude_id=` when editing) is the same check as a probe.

`lab_vendor_id` on an appointment must be one of **this tenant's** labs
(422 `lab_vendor_not_found`); an **inactive** lab is refused only when the id *moves*
onto it (422 `lab_vendor_inactive`), so a case already on a since-retired lab stays
editable.

**The catalog is empty on the migrated tenant** (`labs` = 0 rows): the Denticon
`Appointments` export has no lab-vendor or short-notice column (only ISLAB / LABCOST /
LABSENTON / LABDUEON / LABRECVDON, all already migrated by `s26`), so there is nothing
to backfill. Vendors are entered through `POST /labs` (Setup) — a seed script would be
inventing practice data.

## 2. Write rules (LAB-6 / 7 / 8 / 9 / 10)

All of it lives in
[`app/services/lab_tracking_service.py`](../../app/services/lab_tracking_service.py)
(`apply_lab_rules`) and runs on **every** appointment write — generic `POST` / `PATCH`
route through `AppointmentCRUD`, so no client can route around it. Published at
`GET /metadata/lab-tracking-rules`.

### LAB-8 — the contract

Two rules, both **implications** (auto-applied, the patient-checkbox shape), never a 422:

1. **`has_lab: false` clears the lab block** — `lab_vendor_id`, `lab_dds`, `lab_cost`,
   the three dates → `null`, `lab_short_notice` → `false`. Values that ride along in
   the *same* payload are cleared too. That is deliberate: the Add/Edit Appointment
   form sends the stale DDS / cost / dates together with the un-tick (it builds the
   payload from `formData` whether or not the box is ticked), so "reject lab fields
   when `has_lab` is false" would 422 every un-tick. The un-tick is the user's stated
   intent; the residue is the form's.
2. **Lab data on a non-lab row derives `has_lab: true`** — when the payload carries any
   non-empty lab detail and no `has_lab`, and the stored row has `has_lab=false`. An
   appointment with lab data *is* a lab case. "Empty" = `null`, blank string,
   `lab_cost` of `0` (the migration wrote a literal `0.00` on every non-lab
   appointment) or `lab_short_notice: false`.

Consequence for the Lab Tracking tab's `toUpdateBody`: keep sending `has_lab: true`
(harmless), and to *remove* a case send `{"has_lab": false}` alone — the server clears
the rest. Consequence for the Add/Edit form's known limitation (cannot clear a saved DDS
because `undefined` keys are stripped): unchanged, but un-ticking Lab now clears
everything server-side, which is what the user usually wants.

Live data: 0 rows carry lab data with `has_lab=false`, so nothing was rewritten.

### LAB-9 — date order

`lab_due_on < lab_sent_on` or `lab_received_on < lab_sent_on` → **422**
`{"code": "lab_date_order", "field": "lab_due_on" | "lab_received_on", "lab_sent_on": …, "<field>": …}`.
Judged against the **merge of payload + stored row** (a PATCH carrying only
`lab_received_on` is checked against the stored `lab_sent_on`) and **only when the
payload touches a lab date** — one migrated row already holds received-before-sent and
re-pricing it must not fail. Received without a sent date is allowed (legacy data has it).

### LAB-6 — `lab_dds` length, fixed API-wide

The cause was not one missing `max_length` but the schema factory: it never carried a
column's `String(n)` onto the generated Create/Update, so *every* over-long string in
the API was a 500 (`RX-2` hit the same thing on `sig`). `build_schemas` now emits
`max_length` from the column for every generated write schema — `lab_dds` (100),
`campaign_id` (100), `procedure_label` (200), `status` (30) … all 422 with the field in
`details[].loc`. Reads are untouched (a read never rejects stored data). `Text` columns
stay unbounded.

One visible side effect: where a service already enforced the *same* cap with its own
code, the factory now answers first with the standard shape — `POST /note-macros` with
a 101-char `name` is `validation_error` (+ `loc: ["body","name"]`) rather than
`name_too_long`. `GET /note-macros/limits` is unchanged. `sig_too_long` on the
prescription library is unaffected (its 240 cap is tighter than the 500 column).

### LAB-7 — `lab_cost`

`Field(ge=0, max_digits=10, decimal_places=2)` on Create/Update: `-5`, `123456789.00`
and `12.345` are all 422 naming `lab_cost`; `123.45`, `"100.00"` and `null` are fine.
Note the last one — the previous "rounds to 2 dp" behaviour is gone; send money with at
most two decimals (the form's `parseFloat` output is fine, a computed float with
binary noise is not — round it).

### LAB-10 — unknown keys

`AppointmentCreate` / `AppointmentUpdate` are `extra="forbid"`: `short_notice`,
`lab_recvd_on` or any other unknown key is a **422** with the key in `details[].loc`.
I checked `schedulerApi.ts` / the Add/Edit form before turning this on — every key they
send is a real column, so nothing in the current FE breaks. A stale generated client
that still sends a renamed field will now be told so instead of silently dropping it.

## 3. Listing (LAB-2 / LAB-11) and the read

`GET /appointments` gains typed, OpenAPI-visible params:

| Param | Semantics |
|-------|-----------|
| `has_lab` | plain equality (was silently ignored) |
| `lab_vendor_id`, `lab_short_notice` | plain equality |
| `lab_status` | `not_sent` \| `sent` \| `overdue` \| `received` \| `not_received` (= sent OR overdue, the legacy Lab Report filter). Implies `has_lab=true`. Unknown value → 422 `invalid_lab_status`. |
| `lab_sent_on_from/_to`, `lab_due_on_from/_to`, `lab_received_on_from/_to` | inclusive ranges (the engine's `{field}_from/_to` convention — not the `lab_sent_from` spelling in the ask; `/lab-cases` below uses the short spelling) |

`AppointmentRead` gains `lab_vendor_name` and **`lab_status`** — the same derivation the
filter evaluates (`received` → `overdue` → `sent` → `not_sent`, exactly the FE's
`deriveStatus`), `null` when `has_lab` is false. The FE can delete its copy. Sortable
now also on `lab_sent_on`, `lab_due_on`, `lab_received_on`, `lab_cost`, `updated_at`.

"Today" for `overdue` on the generic list is **UTC**; the `/lab-cases` view uses the
office's local date when `office_id` is given (or an explicit `as_of`).

**LAB-11 — option (a)**: `GET /appointments` now hides `is_archived=true` rows by default
(`hide_soft_deleted`, the same shape `appointment-procedures`, the contract resources
and the scheduler feed already had). `?is_archived=true` still returns the tombstones.
The lab data survives an archive so `POST /appointments/{id}/restore` brings the case
back whole. **Breaking for a caller that relied on archived rows in the default
listing** — I found none in the FE or the tests. Live: 18 lab cases in 176,558
migrated appointments, 14 of them archived — so without this the Lab Tracking tab would
have shown 14 tombstones for every 4 live cases.

## 4. Scheduler feed (LAB-3)

`AppointmentSchedulerRead` carries `has_lab`, `lab_vendor_id`, `lab_vendor_name`,
`lab_dds`, `lab_cost`, `lab_short_notice`, `lab_sent_on`, `lab_due_on`,
`lab_received_on`, `lab_status`. Vendor names are one batched query per feed, no N+1.

## 5. Office-wide view and reports (LAB-4 / LAB-5)

### `GET /appointments/lab-cases`

Every `has_lab` appointment the tenant can see, denormalised
(`patient_name`, `chart_no`, `patient_phone`, `provider_name`, `office_name`,
`lab_vendor_name`, `lab_status`, `days_overdue`), server-paged. Filters:
`office_id`, `patient_id`, `provider_id`, `lab_vendor_id`, `lab_short_notice`,
`lab_status`, `date_from/_to` (appointment date), `lab_sent_from/_to`, `lab_due_from/_to`,
`lab_received_from/_to`, `include_archived` (default false), `as_of`, `search`
(patient name / chart / id, description, DDS, lab name), `sort` (`date` default,
`lab_sent_on`, `lab_due_on`, `lab_received_on`, `lab_cost`, `patient_name`,
`provider_name`, `lab_vendor_name`, `created_at`, `updated_at`), `order`, `page`, `size`.

Response: `{items, meta, counts, total_cost, as_of}` — `counts` (`all`/`not_sent`/`sent`/
`overdue`/`received`/`not_received`) is computed over every filter **except**
`lab_status`, so the review tabs keep their badges while one is selected;
`total_cost` is over the selected set, all pages. The per-patient Lab Tracking tab is
`?patient_id=` on the same endpoint — one request instead of paging the patient's
whole appointment book and filtering client-side. The new
`appointments(office_id, has_lab)` index is what the planner uses (verified `EXPLAIN`).

### Reports

- `GET /appointments/lab-cases/report.pdf` — the legacy **Lab Report** (same filters +
  `sort`/`order`), landscape, totals row, status column. `lab_status=not_received` is
  the "Not Received" report, `not_sent` / `received` the others.
- `GET /appointments/lab-cases/cost-report` — the **Lab Cost Report** as JSON:
  `date_from/_to` on `date_basis=appointment|sent|due|received`, `group_by=vendor|
  provider|office|month|dds`, plus `office_id`/`provider_id`/`lab_vendor_id`. Rows carry
  `key` (id / code / `YYYY-MM`), `label`, `case_count`, `total_cost`; `key: null` is the
  "(no lab)" / "(no DDS)" bucket. `…/cost-report.pdf` renders it.
- `GET /appointments/lab-cases/export.csv` — the case grid as CSV (Excel), same filters.

Every print / export writes an `audit_logs` row (`action=PRINT`,
`resource_type=lab_report`), like the patient PDFs.

## 6. What I did not do

- **No vendor seed** (see §1) — the practice's lab list is not in the export.
- **No rewrite of the one migrated row** with received-before-sent; the rule fires
  only when a date is next edited.
- **`lab_status` on `GET /appointments` uses UTC "today"** (the generic list has no
  office context). Use `/lab-cases` or pass `lab_due_on_to` for exact office-day
  semantics.
