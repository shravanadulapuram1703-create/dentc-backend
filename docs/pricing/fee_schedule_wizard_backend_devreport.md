# New Fee Schedule Wizard — backend gaps (FSW-1..9)

_2026-10-11 · frontend: `src/components/setup/insurance/FeeScheduleWizard.tsx` +
`feeScheduleWizardModel.ts` (tests: `__tests__/feeScheduleWizardModel.test.ts`)_

## What shipped (frontend)

Setup → Fee Schedule Setup → **Add New Schedule** now runs the legacy 4-step wizard instead of the
name/type modal:

| Step | Writes |
|---|---|
| 1 Schedule Type — name, effective date, type (+ pricing model on payer types) | `POST /fee-schedules` |
| 2 Not Applicable (All Offices) / Specific Offices — OID, Office Name, Office Group | — |
| 3 Not Applicable (All Providers) / Providers / Specialties | `POST /fee-schedule-assignments` per row (or `PATCH` to re-bind) |
| 4 Add Fee Schedule — fee / Plan Pays / AMB code per code, Copy From Existing, Import CSV | `PUT /fee-schedules/{id}/entries/bulk` |

**Provider list is derived, never static:** for each selected office the wizard reads
`GET /offices/{id}/providers/effective` (roster ∪ home office, falling back to the raw join) and unions
them with each provider's home `office_id`. Every row shows *which* selected offices it serves.
"All Offices" lists every active provider. A "show providers not assigned to the selected office(s)"
toggle covers the sparse-roster case without hiding anyone by default.

**Fee Schedule → Office(s) → Provider(s)** is stored as `fee_schedule_assignments` rows
`{fee_schedule_id, provider_id, office_id}` — one row per provider × selected office the provider
serves (a provider added through the toggle is bound to every selected office). Specialties →
`{specialty_id, office_id}`; "All Offices" → `office_id = null`.

Verified live (tenant 1): offices 1 + 9 → 94 providers; PRV-100 + PRV-162 → 4 rows; `POST
/pricing/quote` for PRV-100 @ office 1 → D0120 $55 `assignment_provider` from the new schedule, while
PRV-100 @ office 4 and PRV-113 @ office 1 still resolve `office_default`. Test data was removed.

## Backend gaps

| ID | Severity | Gap | Ask |
|---|---|---|---|
| FSW-1 | High | **No atomic create.** Apply = create schedule + bulk entries + N assignment calls. If a later call fails, the schedule exists half-linked (the UI reports the failed links, but nothing rolls back). | `POST /fee-schedules/wizard` (or `assignments[]` + `entries[]` on `FeeScheduleCreate`) in one transaction, returning per-row outcomes. |
| FSW-2 | Medium | **No batch assignment endpoint.** Providers × offices fan out to one `POST` per row (6 in parallel). 50 providers × 5 offices = 250 requests. | `POST /fee-schedule-assignments/bulk` with `on_conflict: "error" \| "rebind" \| "skip"`. |
| FSW-3 | High — decision | **Office + All Providers has no home.** Legacy lets an Office schedule apply to specific offices for all providers. Here an office-only row is refused (`422 assignment_needs_target`), so the wizard offers an opt-in "make this the default fee schedule of the selected office(s)" (`PATCH /offices/{id}` `default_fee_schedule_id`). That **replaces** the office's single pointer and also changes which list new patients get. | Confirm that is the intended mapping, or allow office-scoped assignment rows ranked under the provider tier (above `office_default`). |
| FSW-4 | Medium | **Fee Schedule Type vocabulary ≠ legacy.** Legacy radios are Office / Ins-Smart Fee / Ins-Managed Care / Ins-PPO / Ins-Pat Co-pay; `/fee-schedules/metadata` exposes `ucr / standard / plan / carrier` + `pricing_model`. The wizard renders the server vocabulary; there's no defined mapping for Smart Fee or Managed Care. | Add `legacy_label` / aliases to `fee_types` in metadata (e.g. Ins-PPO → carrier+percentage, Ins-Pat Co-pay / Managed Care → plan+copay, Smart Fee → ?). |
| FSW-5 | High (data) | **Specialty is free text and almost empty.** 95 of 97 active providers have a blank `specialty` (other values: "Orthodontist", "Dental"). `specialty_id` on an assignment is a string matched exactly against `providers.specialty`, so the Specialties option lists almost nothing and a spelling or case difference silently stops pricing. | Specialty catalog with an id (or a normalized code), FK from providers, and a backfill from legacy `Providers.SPECIALTY`. |
| FSW-6 | Low | **No multi-office provider lookup.** The wizard calls `/offices/{id}/providers/effective` once per selected office. | `GET /providers?office_ids=1,9&effective=true` returning `served_office_ids` per provider. |
| FSW-7 | Medium | **Conflict detection needs the whole table.** The assignment tuple is unique across all schedules (`409 assignment_duplicate_target`). To show "Currently Bound To" and offer re-binding, the wizard pages every assignment row. `GET /fee-schedule-assignments` has no `specialty_id` filter and no "provider is set" filter. | Add a `specialty_id` filter + `has_provider`/`has_specialty`, or have FSW-2's bulk endpoint return conflicts. |
| FSW-8 | Low | **No server import.** "Import From Excel File" accepts the CSV template only (same format as Utilities → Fee Schedule template), parsed in the browser. Native `.xlsx` isn't supported. | `POST /fee-schedules/{id}/entries/import` accepting xlsx/csv, returning a row-level report. |
| FSW-9 | Low | **No "scope" read.** After creation, "Edit Schedule" can't show the office/provider scope. It lives only in Fee Schedule Assignments. | `GET /fee-schedules/{id}/scope` (offices, providers, specialties, office-default pointers), or `include=assignments` on GET. |

## Frontend follow-ups (no backend needed)

- Step 4 lists **all active procedure codes**. Legacy narrows the list to codes activated for the
  office (`GET /offices/{id}/procedure-codes/effective` exists). Not applied yet because those
  activations are as sparse as the provider rosters. Revisit once they're seeded.
- "Edit Schedule" still uses the simple modal (name/type/model). Re-entering the wizard for edits
  depends on FSW-9.
