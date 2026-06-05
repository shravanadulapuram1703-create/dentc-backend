# Office Assignment — Backend Dev Report

Backend gaps discovered while building **Setup → Offices → Office Assignment**
(`src/components/setup/offices/OfficeAssignment.tsx`). Tabs in scope this phase:
**Procedures, Exp Codes, Prod Types, Users**.

Verified read-only against `openapi.json` (v1.0.0, 897 KB) and the generated Orval
client under `src/api/generated/**`. Gap numbers continue the master
`backend_devreport.md` sequence (#24–#27).

| Tab | Status | Buildable now? |
|-----|--------|----------------|
| Users | ✅ Backed (with client-side glue) | **Yes — shipped** |
| Procedures | ⛔ No office-assignment endpoints | No — gated (#24) |
| Exp Codes | ⛔ Resource absent from API | No — gated (#25) |
| Prod Types | ⛔ Resource absent from API | No — gated (#26) |

After any of these land, run `npm run api:sync` and re-check the generated client
before wiring the tab.

---

## Missing API — #24 Office ↔ procedure-code assignment

Module: Setup → Office Assignment
Screen: Office Assignment → Procedures tab (Available ↔ Assigned picker; columns Code, Description)

Business Requirement:
Assign a subset of the tenant's procedure codes to a specific office (the office's
"Procedures List"), and add/remove that assignment.

Current Status:
The **master list works** — `GET /api/v1/procedure-codes` → `listProcedureCodes`
(`src/api/generated/endpoints/procedures/procedures.ts`) returns
`ProcedureCodeRead` with `code` + `description`. But there is **no office-scoped
assignment concept**: `ProcedureCodeRead` has no `office_id`, `ListProcedureCodesParams`
has no `office_id` filter, no `/api/v1/offices/{office_id}/procedure-codes` route
exists, and there is no link model (`OfficeProcedureCode`). The fee-schedule-assignment
endpoints assign fee schedules, not procedure codes — not a substitute.

Suggested Endpoint:
- `GET /api/v1/offices/{office_id}/procedure-codes` → list assigned codes
- `PUT /api/v1/offices/{office_id}/procedure-codes` → set the full assigned list (bulk), **or** POST/DELETE pair to assign/unassign one code

Expected Request Model:
`{ procedure_code_ids: string[] }` (bulk set), or `{ procedure_code_id: string }` (single).

Expected Response Model:
List of assigned `ProcedureCodeRead` (or link rows `{ id, office_id, procedure_code_id }`).

Reason Required:
The Procedures tab cannot list, add, or remove office assignments without a link
table + endpoints. The left "all codes" pane is already feasible from `listProcedureCodes`.

Impact on Frontend:
Tab is gated ("pending backend") until these land. UI shell + dual-list component
are ready to wire immediately on availability.

---

## Missing API — #25 Explosion (Exp) Codes resource + office assignment

Module: Setup → Office Assignment
Screen: Office Assignment → Exp Codes tab (columns Code, Description)

Business Requirement:
Maintain a catalog of explosion codes and assign them per office.

Current Status:
**The entire resource is absent.** No `/explosion-codes`, `/exp-codes`, or
`/offices/{office_id}/exp-codes` path exists in `openapi.json`; no `ExplosionCode`/
`ExpCode` model exists in `src/api/generated/model/**`; no generated endpoint module
exists. (The only `exp` substrings in the spec are unrelated:
`password_expiration_days`, `expires_in`, `preauth_expires`.)

Suggested Endpoint:
- `GET /api/v1/explosion-codes` → global list (`code`, `description`)
- `GET /api/v1/offices/{office_id}/exp-codes` → assigned list
- `PUT /api/v1/offices/{office_id}/exp-codes` (bulk set) or POST/DELETE pair

Expected Request/Response Model:
`ExplosionCodeRead { id, code, description, is_active }`; assignment body
`{ explosion_code_ids: string[] }`.

Reason Required:
Nothing can be listed or assigned — the feature does not exist on the backend.

Impact on Frontend:
Tab is gated. Requires both the catalog resource and the office-assignment
endpoints, then `npm run api:sync`.

---

## Missing API — #26 Production Types resource + office assignment

Module: Setup → Office Assignment
Screen: Office Assignment → Prod Types tab (columns Production Type, Production Color, Description, Visible in AppointNow, AppointNow Duration, Inactive)

Business Requirement:
Maintain production types (with color, AppointNow visibility/duration, inactive
flag) and assign them per office.

Current Status:
**The entire resource is absent.** No `production-type`/`prod-type` path or schema
exists in `openapi.json`; no `ProductionType` model exists; no generated endpoint
module exists. The only "production" hits are the booleans `show_booked_production`
and `show_production_colors` on `AccountSettingsRead/Update` — unrelated to a
production-type catalog. No `appointnow` field exists anywhere.

Suggested Endpoint:
- `GET /api/v1/production-types` → global list
- `GET /api/v1/offices/{office_id}/production-types` → assigned list
- `PUT /api/v1/offices/{office_id}/production-types` (bulk set) or POST/DELETE pair

Expected Response Model:
`ProductionTypeRead { id, name, color, description, appointnow_visible: bool, appointnow_duration: int, is_inactive: bool }`.

Reason Required:
Nothing can be listed or assigned — the feature does not exist on the backend.

Impact on Frontend:
Tab is gated. Requires the catalog resource + office-assignment endpoints, then
`npm run api:sync`.

---

## Degraded (not blocked) — #27 Users tab: missing bulk/copy endpoints + `created_by`

Module: Setup → Office Assignment
Screen: Office Assignment → Users tab (Available ↔ Assigned picker; "Copy Users From"; Active/Inactive/All filter)

Business Requirement:
Assign/unassign users to an office; copy the assignment from another office; show
who created each user.

Current Status:
**The tab is shipped and functional** via existing endpoints:
- `GET /api/v1/users` → `listUsers` (master list)
- `GET /api/v1/user-offices?office_id=` → `listUserOffices` (assignment links)
- `POST /api/v1/user-offices` → `createUserOffice` (assign one)
- `DELETE /api/v1/user-offices/{id}` → `deleteUserOffice` (unassign one)

But several conveniences require **client-side emulation** because the backend
lacks dedicated endpoints/fields:

1. **No bulk "set assignments for office" endpoint.** Save diffs the desired set
   against the loaded snapshot and fires N individual `POST`/`DELETE` calls
   (`Promise.allSettled`, aggregated result). A `PUT /api/v1/offices/{office_id}/users`
   (or `/user-offices:bulk`) accepting `{ user_ids: number[] }` would make Save
   atomic and faster.
2. **No "copy assignments from office" endpoint.** "Copy Users From" is emulated
   by reading the source office's links (`listUserOffices(office_id=source)`) and
   unioning their `user_ids` into the staged set. A
   `POST /api/v1/offices/{target}/users:copy-from/{source}` would do this server-side.
3. **`UserRead` has no `created_by`.** The legacy "Created By" column cannot be
   populated, so it is omitted. (Twin of office gap #22 / account gap #21.)
4. **`listUsers` has no `office_id` or `is_active` query param.** Available-vs-Assigned
   partitioning and the Active/Inactive/All filter are computed client-side from
   `UserRead.is_active`. Acceptable at current tenant scale; server-side filters
   would help large tenants.
5. **`listUserOffices` returns link rows only** (`user_id`, no denormalized user
   fields). The frontend joins `user_id` → `UserRead` to render name/active/created.
   A denormalized `GET /api/v1/offices/{office_id}/users` returning full `UserRead`
   would remove the join.

Suggested Endpoint:
`PUT /api/v1/offices/{office_id}/users` (bulk set); `GET /api/v1/offices/{office_id}/users`
(denormalized); add `created_by` to `UserRead`.

Reason Required:
Performance/atomicity and faithful reproduction of the legacy screen; current
behavior is correct but degraded (N round-trips, partial-failure surface, no
Created-By column).

Impact on Frontend:
None blocking — tab works today. The bulk endpoint would simplify
`src/services/officeUserAssignmentApi.ts` (replace the diff-and-fan-out save with a
single call).

---

# Batch 2 — Providers, Notes Macros, RX, Ortho Misc Setup, Letters

Discovered while adding the remaining five tabs. Common theme: **none of these have a
many-to-many office-assignment link table** (unlike `user_offices`), so the dual-list
assign/unassign editor does not apply.

| Tab | Status | Built as |
|-----|--------|----------|
| Providers | Office-scoped **read** only (single `office_id`, no M:N) | Read-only assigned grid (#28) |
| Notes Macros | Tenant-wide catalog, no office scope | Read-only catalog preview (#29) |
| RX | Tenant-wide catalog, no office scope | Read-only catalog preview (#30) |
| Letters | Tenant-wide catalog, no office scope | Read-only catalog preview (#31) |
| Ortho Misc Setup | Resource absent | Gated (#32) |

## Missing API — #28 Provider ↔ office is single-office (no M:N assignment) + `name`/`created_by`

Module: Setup → Office Assignment
Screen: Providers tab (legacy columns: Provider ID, Provider Short ID, First Name, Last Name, Active, Created On, Created By)

Business Requirement:
Assign/unassign providers to an office and show first/last name + who created each.

Current Status:
- **Read works.** `GET /api/v1/providers?office_id=` → `listProviders`
  (`organization.ts`) returns the office's providers. Built as a read-only grid.
- **No M:N assignment.** `ProviderRead.office_id` is a single FK — a provider belongs
  to exactly one office. There is no `provider_offices` link table and no
  assign/unassign endpoint. "Assigning" an existing provider here would mean
  PATCHing its `office_id`, which **removes it from its current office** — destructive,
  so the tab is intentionally read-only.
- **Field gaps:** `ProviderRead` has a single `name` (no `first_name`/`last_name` split)
  and **no `created_by`** — those legacy columns can't be reproduced.

Suggested Endpoint:
- A `provider_offices` link table + `GET /api/v1/offices/{office_id}/providers`,
  `POST`/`DELETE /api/v1/provider-offices` (mirror `user-offices`) **if** providers
  should be multi-office.
- Add `first_name` / `last_name` and `created_by` to `ProviderRead`.

Impact on Frontend:
Tab ships read-only. A true assign/unassign editor needs the M:N model; the
`DualListPicker` is ready to wire if/when it lands.

## Missing API — #29 Office ↔ note-macro assignment

Module: Setup → Office Assignment
Screen: Notes Macros tab (columns Category, Macro Name)

Business Requirement:
Choose which note macros an office uses.

Current Status:
`GET /api/v1/note-macros` → `listNoteMacros` (`procedures.ts`) is **tenant-wide**:
no `office_id` filter, no `/offices/{office_id}/note-macros` route, no link table.
Shown as a read-only tenant-wide catalog preview. `NoteMacroRead` fields: `category`,
`name`.

Suggested Endpoint:
`GET` + bulk `PUT /api/v1/offices/{office_id}/note-macros` (or POST/DELETE pair) + a
link model.

Impact on Frontend:
Read-only preview only until office-scoping lands.

## Missing API — #30 Office ↔ prescription (RX) assignment

Module: Setup → Office Assignment
Screen: RX tab (columns Rx ID#, Drug Name)

Business Requirement:
Choose which prescription-library entries an office uses.

Current Status:
`GET /api/v1/prescription-library` → `listPrescriptionLibrary` (`procedures.ts`) is
**tenant-wide** (`id`, `drug_name`): no `office_id` filter, no office-scoped route, no
link table. (Patient-level `/api/v1/prescriptions` has an `office_id` but that is a
per-patient clinical record, not the office's RX catalog.) Shown as a read-only
tenant-wide catalog preview.

Suggested Endpoint:
`GET` + bulk `PUT /api/v1/offices/{office_id}/prescription-library` + a link model.

Impact on Frontend:
Read-only preview only until office-scoping lands.

## Missing API — #31 Office ↔ letter-template assignment

Module: Setup → Office Assignment
Screen: Letters tab (columns Letter Type, Letter Name)

Business Requirement:
Choose which letter templates an office uses.

Current Status:
`GET /api/v1/letter-templates` → `listLetterTemplates` (`communications.ts`) is
**tenant-wide** (`letter_type`, `name`): no `office_id` filter, no office-scoped
route, no link table. Shown as a read-only tenant-wide catalog preview.

Suggested Endpoint:
`GET` + bulk `PUT /api/v1/offices/{office_id}/letter-templates` + a link model.

Impact on Frontend:
Read-only preview only until office-scoping lands.

## Missing API — #32 Ortho Misc Setup resource

Module: Setup → Office Assignment
Screen: Ortho Misc Setup tab (legacy screen renders empty)

Business Requirement:
Office-scoped "ortho misc" setup (unknown columns — the legacy screen is empty).

Current Status:
**No `ortho_misc` resource exists** in `openapi.json` or the generated client. The only
ortho resource is `GET /api/v1/ortho-plans` (`billing.ts`), which is **patient-level**
(`patient_id` filter) — unrelated to office ortho setup.

Suggested Endpoint:
Define the resource first (columns unknown), then `GET`/`PUT /api/v1/offices/{office_id}/ortho-misc`.

Impact on Frontend:
Tab gated. Needs requirements + a backend resource before anything can be built.

## Verify — #33 `?office_id=` filter must be honored server-side (listUserOffices / listProviders)

Module: Setup → Office Assignment
Screen: Users tab + Providers tab (both office-scoped)

Business Requirement:
Selecting an office must show ONLY that office's assigned users / providers, and
"Copy Users From" must copy ONLY the source office's users.

Current Status:
Symptom observed: the Assigned-Users list (and Copy-Users-From) appeared to ignore the
selected office — users from other offices leaked in. Root cause is consistent with the
backend not effectively filtering `GET /api/v1/user-offices?office_id=` (and possibly
`GET /api/v1/providers?office_id=`) server-side, so the list returns cross-office rows.

Frontend mitigation (shipped): the service layer now **also filters the returned rows by
`office_id` on the client** (`fetchOfficeLinks` in `officeUserAssignmentApi.ts`,
`fetchOfficeProviders` in `officeAssignmentCatalogApi.ts`). This makes the screen correct
regardless of backend behavior.

Action Required:
Confirm the backend applies the `office_id` query filter on `listUserOffices` and
`listProviders`. If it does, the client filter is a harmless safety net. If it does not,
this is a backend bug to fix (the client filter only protects this screen — any other
consumer of these endpoints would still get unfiltered data, and pagination `total`
counts would be wrong).

Impact on Frontend:
Resolved on this screen via client-side scoping; backend confirmation still needed.
