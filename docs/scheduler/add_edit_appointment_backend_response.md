# Add / Edit Appointment — backend response

Answers every gap raised in
[`add_edit_appointment_backend_devreport.md`](add_edit_appointment_backend_devreport.md).

Migration **`f0a1b2c3d4e5`** (`add_add_edit_appointment_gaps`) — applied to
`recondental_migrated`. `openapi.json` regenerated (400 paths); re-run Orval.

| ID | Status | What shipped |
|----|--------|--------------|
| **APPT-PROC-1** | ✅ done | `duration_minutes` on appointment procedures |
| **APPT-PROC-2** | ✅ done | `provider_units` (default 1) |
| **APPT-PROC-3** | ✅ done | `bill_to` (`P`/`I`) |
| **APPT-PROC-4** | ✅ done | archived lines excluded from the default listing + `is_archived` filter |
| **SCHED-DEL-1** | ✅ done — **option (a)**, and (b) too | `/appointments/scheduler` excludes archived rows; `is_archived` exposed |
| **SCHED-DEL-2** | ✅ answered + endpoint | soft delete is intentional; `POST /appointments/{id}/restore` added |
| **APPT-5** | ✅ done | `lab_dds` on Appointment create/update/read |
| **APPT-6** | ✅ **already existed** | explosion codes have been a first-class resource since CHG-4 |
| **APPT-7** | ✅ done | new `campaigns` catalog; `campaign_id` stays a string |
| **APPT-8** | ✅ done (seeded) | 418 codes got requirement flags from the CDT families |
| **APPT-9** | ⚠️ answered + tooling | durations seeded (693 codes); fee schedules stay the fee source of truth |
| **APPT-10** | ✅ done | `GET /procedure-code-categories` |
| **APPT-11** | ✅ confirmed | the Home → `phone` mapping is intended |
| **APPT-12** | ✅ confirmed | `chart_no` is **not** unique and cannot be made unique — use the numeric id |

---

## 1. `appointment-procedures`

### APPT-PROC-1 / 2 / 3 — the three missing line columns

Three additive columns on `appointment_procedures`, auto-exposed on
`AppointmentProcedureCreate` / `Update` / `Read` by the schema factory:

| Column | Type | Notes |
|--------|------|-------|
| `duration_minutes` | `int \| null` | **Nullable on purpose** — "not set" has to stay distinguishable from "zero minutes", so **Calc Time** can keep falling back to `procedure_codes.default_duration_minutes` (now seeded, see APPT-9) rather than treating an unset line as 0. |
| `provider_units` | `int`, default `1` | The legacy "P. Units". Existing rows were backfilled to `1` by the migration's `server_default`, which is the value they were implicitly carrying. |
| `bill_to` | `str(1) \| null` | `"P"` patient / `"I"` insurance. Left as a 1-char string rather than an enum so it matches the legacy column and does not 422 on a migrated value nobody predicted. |

```json
POST /api/v1/appointment-procedures
{ "appointment_id": "APPT-…", "procedure_code": "D2391", "tooth": "19",
  "surface": "MO", "fee": "92.00",
  "duration_minutes": 45, "provider_units": 2, "bill_to": "I" }
```

### APPT-PROC-4 — deleted procedures no longer come back

`GET /api/v1/appointment-procedures` now **excludes archived rows by default**.
This is the engine's `hide_soft_deleted` opt-in (the same switch the payment-plan
contracts use), so it is one behaviour, not a per-endpoint special case:

* default listing → live lines only;
* `?is_archived=true` → the archived lines, on purpose;
* `?is_archived=false` → explicit, same as the default.

`is_archived` is now a declared filter, alongside two more the reconciliation loop
wanted: `treatment_plan_id` and `status`.

> **Client cleanup available:** the client-side archived filter added in fix #16
> (both in the form and in the appointment details pop-out) is now redundant. It
> is harmless to leave, but it can go.

**Breaking-ish:** any caller that was *relying* on archived lines coming back in
the default listing must now pass `?is_archived=true`. Nothing in the FE does.

---

## 2. Appointment

### SCHED-DEL-1 — the calendar feed hands back deleted appointments

Fixed with **option (a), plus (b) for free**, exactly as you preferred:

* `GET /appointments/scheduler` now filters `is_archived = false` **by default** —
  no extra round trip, and every other consumer of the feed (dashboard KPIs,
  report metrics, lab tracking, patient overview, details pop-out) is fixed with
  it, without each of them having to remember to subtract tombstones.
* `AppointmentSchedulerRead.is_archived` is exposed anyway, because a caller that
  opts back in needs to tell a tombstone apart from a live row.
* `?include_archived=true` is the opt-in.

> **Client cleanup available:** the workaround in `fetchAppointments` — the
> parallel `GET /appointments?is_archived=true` call whose ids get subtracted from
> the feed — can be deleted. Same for the Appointment Report. The
> `is_archived: false` params added to the other list calls are still correct and
> should stay (they hit `/appointments`, not the feed, and `/appointments` has no
> `hide_soft_deleted`: it is the resource you *page archived rows from*).

One behavioural note: `PATCH /appointments/{id}/status` composes its response from
this same feed, so it now asks for `include_archived=true` internally — otherwise
transitioning an archived appointment would hide the row from its own response.

### SCHED-DEL-2 — is soft delete intentional?

**Yes, and it stays.** An appointment that existed is a fact about the patient's
record — it is referenced by `sms_messages.appointment_id`, by
`patient_procedures.appointment_id`, and by the audit trail; hard-deleting it
would orphan those and erase history the practice may need to answer for. What
was missing was the *other half* of soft delete, and that is what shipped:

* **list** the archived ones — `GET /appointments?is_archived=true` (already
  existed; now the documented, supported way to build an "archived appointments"
  view);
* **restore** one — `POST /api/v1/appointments/{id}/restore` → the denormalized
  `AppointmentSchedulerRead`. Tenant-checked, **idempotent** (restoring a live
  appointment is a 200 no-op, not a 409, so a double-click on Undo is safe),
  stamps `updated_by`.

That makes an "Undo delete" toast or an archived-appointments screen a one-call
feature whenever you want to build it.

### APPT-5 — `lab_dds`

Added to `appointments`. Deliberately **free text** (`varchar(100)`), not a
`providers` FK: legacy lab slips carry initials or an outside dentist's name,
neither of which resolves to a provider row, and a FK would have made the field
unfillable for exactly the cases it exists for.

### APPT-6 — explosion codes

**No backend work needed — this already exists** and has since the Transactions
pass (CHG-4). The "By Explosion Code" filter can be restored:

| Endpoint | What it gives you |
|----------|-------------------|
| `GET /api/v1/explosion-codes` | the header list, `?office_id=`, `?is_active=`, searchable on `code`/`description` |
| `GET /api/v1/explosion-code-items?explosion_code_id=` | the member procedures with `display_order`, `default_fee`, `tooth`, `surface` |
| `GET /api/v1/explosion-codes/{code}/expand` | **the one you want** — resolves a code straight to its priced procedure set in one call |

`explosion_codes` is tenant + office scoped, so a practice's own bundles are what
the filter offers. The catalog will be empty until the practice defines bundles
(or the migration loads `CODESEXPLOSION*`) — an empty list is not a missing API.

### APPT-7 — campaigns

New `campaigns` catalog (`GET/POST /api/v1/campaigns`, `GET/PATCH/DELETE
/api/v1/campaigns/{id}`), tenant-scoped, unique on `(tenant_id, code)`:

```
code · name · description · channel · office_id · start_date · end_date · is_active
```

Filters: `office_id`, `channel`, `is_active`, plus `start_date_from/_to` and
`end_date_from/_to`. Searchable on `code`/`name`/`description`.

**`appointments.campaign_id` is unchanged — still a string holding the campaign
`code`.** No wire change, no migration of existing values, nothing breaks if a
campaign is later renamed or deleted. The field becomes a picker rather than a
free-text box, and campaign roll-ups become possible; a free-typed value still
saves, which matters for the migrated appointments whose campaign codes predate
any catalog row.

---

## 3. Procedure codes

### APPT-8 — requirement flags: seeded

You were right about D2391, and it was catalog-wide: **every** `requires_*` flag
was false across all 1,122 codes, so enforcement could never fire.

`scripts/seed_procedure_code_rules.py` derives the flags from the **CDT code
families** — the published `D<category><series>` taxonomy (D2xxx restorative,
D3xxx endodontics, D4xxx periodontics, …), not from a licensed CDT data file.
Every rule is an explicit, reviewable inclusive range with a note, so a practice
can audit and override it.

**Run against the live catalog:**

```
scanned 1122 code(s); 429 not CDT-derivable
updated: 418 requirement flag set(s), 693 duration(s), 15 surface rule(s)
```

Spot-check:

| Code | tooth | surface | quadrant | lab | duration |
|------|-------|---------|----------|-----|----------|
| D2391 resin composite, 1 surface | ✔ | ✔ | | | 60 |
| D2740 porcelain crown | ✔ | | | ✔ | 90 |
| D3310 anterior root canal | ✔ | | | | 90 |
| D4341 scaling and root planing | | | ✔ | | 60 |
| D0150 comprehensive evaluation | | | | | 60 |

The 429 unmatched codes are the non-CDT ones (migrated practice codes, CPT/HCPCS)
— they carry no ADA taxonomy to derive from and are seeded by CSV instead:

```bash
python -m scripts.seed_procedure_code_rules --csv rules.csv --apply
```

The script also fills **CHG-2 `surface_rules`** for the 15 families whose CDT
descriptor *is* the surface count (D2140 one surface → `{"min":1,"max":1}`, D2150
two, D2160 three, D2161 four-or-more, and the same ladder for the composites) —
so the enforcement modal gets a real min/max instead of fabricating one.

Safety: dry-run by default; without `--overwrite` it only fills blanks and lifts
`false → true`, so a hand-set flag is never silently cleared.

### APPT-9 — fees and durations

Two different answers:

* **`default_duration_minutes` — seeded.** 693 codes now carry a per-family chair
  time (see the table above), so **Calc Time** adds up something real instead of
  falling back to 30 minutes for everything.
* **`default_fee` — fee schedules are the intended source, and should stay that
  way.** A fee is a contract between the practice and a payer; the same code
  prices differently per schedule, per office, and per provider, so a single
  catalog-level number is wrong for everyone the moment there is more than one
  schedule. `resolve_procedure_fee` / `POST /patients/{id}/estimate` are the
  correct path, and the picker already uses them.

  For the "code has no schedule entry → prices at $0" case, the fix is to fill the
  gap **from a real schedule the practice already maintains**, not to invent a
  number:

  ```bash
  python -m scripts.seed_procedure_code_rules --fee-schedule-id <id> --apply
  ```

  That copies `fee_schedule_entries.patient_fee` into `default_fee` for codes
  whose default is still 0. Not run here — pick the schedule you want as the
  house default and tell us, or run it yourselves.

### APPT-10 — category taxonomy

```
GET /api/v1/procedure-code-categories            → [{category, code_count, active_code_count}]
GET /api/v1/procedure-code-categories?active_only=true
```

Grouped from `procedure_codes.category` — the same column `/procedure-codes/stats`
groups by — so the taxonomy cannot drift from the catalog it describes. Blank /
NULL categories collapse into `"Uncategorized"` (those codes still exist and the
picker has to be able to reach them). Sorted case-insensitively, so the buttons
render in a stable order. No more paging 1,100 codes to draw a row of buttons.

---

## 4. Patients

### APPT-11 — Home → `phone`

**Confirmed, the mapping is intended.** `patients` has three phone columns —
`phone`, `cell_phone`, `work_phone` — and `phone` *is* the home number; the
migration loaded it from the legacy home field. Cell → `cell_phone`, Work →
`work_phone`, Home → `phone` is exactly right and needs no backend change.

(`home_phone` does exist on **`responsible_parties`**, which is a different
entity — the guarantor, who may not live at the patient's address. Don't map the
patient's Home field to it.)

### APPT-12 — `chart_no` uniqueness

**Confirmed: `chart_no` is not unique, and it cannot be made unique.** Measured on
the live database:

```
10,045 duplicated (tenant_id, chart_no) groups across 83,898 patients
```

That is migrated legacy data — Denticon allowed chart numbers to repeat across
offices within one account, and roughly a quarter of the patient base is affected.
A unique constraint would fail to build, and rewriting 10k+ patients' chart
numbers would break every paper chart, label and referral letter that references
them.

**So: the numeric `patients.id` is the only safe key** — which is precisely the
conclusion defect #6 reached, and it is the right one. `?chart_no=` on
`/patients` stays a *search* filter that may legitimately return more than one
row; treat a chart-number lookup as ambiguous and disambiguate on office/name.

Auto-generated chart numbers (LEG, `PatientCRUD`) are already collision-safe —
they probe `{id}`, `{id}-1`, `{id}-2`, … — so new patients do not add to the pile.

---

## 5. Files

| Area | Path |
|------|------|
| Migration | [`alembic/versions/f0a1b2c3d4e5_add_add_edit_appointment_gaps.py`](../../alembic/versions/f0a1b2c3d4e5_add_add_edit_appointment_gaps.py) |
| Models | [`app/db/models/scheduling.py`](../../app/db/models/scheduling.py), [`app/db/models/comms.py`](../../app/db/models/comms.py) (`Campaign`) |
| Registry | [`app/api/v1/registry.py`](../../app/api/v1/registry.py) (appointment-procedures, campaigns) |
| Scheduler feed + restore | [`app/api/v1/scheduler.py`](../../app/api/v1/scheduler.py), [`app/services/scheduler_service.py`](../../app/services/scheduler_service.py), [`app/schemas/scheduler.py`](../../app/schemas/scheduler.py) |
| Categories | [`app/api/v1/procedure_codes.py`](../../app/api/v1/procedure_codes.py), [`app/services/procedure_setup_service.py`](../../app/services/procedure_setup_service.py), [`app/schemas/procedure_setup.py`](../../app/schemas/procedure_setup.py) |
| CDT rule seeding | [`scripts/seed_procedure_code_rules.py`](../../scripts/seed_procedure_code_rules.py) |
| Tests | [`tests/test_add_edit_appointment_gaps.py`](../../tests/test_add_edit_appointment_gaps.py) — 12 tests |
