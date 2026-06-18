# Setup screens — backend dev report

> Consolidated backend-gap report for multiple Setup screens so the backend team
> can implement them together. Sections: **1) Pick List Setup**,
> **2) Notes Macros Setup**.

---

## 1) Pick List Setup

Frontend: `src/components/setup/pick-list/` (PickListSetup master-detail screen,
`pickListData.ts` form model, `pickListService.ts` client wrapper).
Route: `/setup/pick-list/manage` (nav: Setup → Pick List → Manage Pick Lists).

## Concept mapping (legacy "PickList" ↔ backend)

The legacy **PickList Setup** screen is a parent → child structure: a pick list
(ID#, Description, Multi Select, Active) owning an ordered list of **Items**. There
is **no** `picklist` resource in the backend. It maps cleanly onto the existing
**questionnaire** pair (tag: `metadata`):

| Legacy concept | Backend resource | Notes |
| --- | --- | --- |
| Pick list (header) | `questionnaire-headers` | `QuestionnaireHeaderRead` |
| Pick list item | `questionnaire-options` | `QuestionnaireOptionRead`, FK `questionnaire_id` |

Field mapping:

| Legacy field | Backend field | Notes |
| --- | --- | --- |
| ID# | `QuestionnaireHeaderRead.id` | shown in left rail as `Description (id)` |
| Description | `description` | |
| Multi Select | `is_multi_select` | rendered Yes/No |
| Active | `is_active` | rendered Yes/No |
| Item value (01, 02, …) | `QuestionnaireOption.answer_code` | |
| Item order | `QuestionnaireOption.sort_order` | normalized 1-based on save |
| Item active | `QuestionnaireOption.is_active` | inactive items shown struck-through |

## Backend used (tag: metadata)

All CRUD is live and wired through the generated Orval client
(`src/api/generated/endpoints/metadata/metadata.ts`):

| Operation | Endpoint | Function |
| --- | --- | --- |
| List headers | `GET /api/v1/questionnaire-headers` | `listQuestionnaireHeaders` (paged, `size` max 200) |
| Create header | `POST /api/v1/questionnaire-headers` | `createQuestionnaireHeader` |
| Update header | `PATCH /api/v1/questionnaire-headers/{id}` | `updateQuestionnaireHeader` |
| Delete header | `DELETE /api/v1/questionnaire-headers/{id}` | `deleteQuestionnaireHeader` |
| List items | `GET /api/v1/questionnaire-options?questionnaire_id=` | `listQuestionnaireOptions` |
| Create item | `POST /api/v1/questionnaire-options` | `createQuestionnaireOption` |
| Update item | `PATCH /api/v1/questionnaire-options/{id}` | `updateQuestionnaireOption` |
| Delete item | `DELETE /api/v1/questionnaire-options/{id}` | `deleteQuestionnaireOption` |

## Gaps / requested backend changes

1. **PICK-1 — No cascade delete for items.** Deleting a header does not (verified
   only by the absence of any documented cascade) remove its options. The frontend
   compensates by listing + deleting each option before deleting the header
   (`handleDelete` in `PickListSetup.tsx`). A server-side cascade (or a
   `DELETE …/headers/{id}?cascade=true`) would remove this N+1 round-trip and the
   risk of orphaned options if the client dies mid-delete.

2. **PICK-2 — No atomic header+items write.** Create/edit performs one request per
   item (create header → loop create options; or update header → diff delete/update/
   create options). A bulk/transactional endpoint
   (e.g. `PUT /api/v1/questionnaire-headers/{id}` accepting an embedded `options[]`,
   or a `POST …/options:batch`) would make saves atomic and far fewer round-trips.
   Today a partial failure can leave the list half-updated.

3. **PICK-3 — No "Custom Pick List" concept.** The legacy nav has both *Manage Pick
   Lists* and *Custom Pick Lists*. The questionnaire model has no flag distinguishing
   built-in/system pick lists from user-created custom ones (no `is_custom` /
   `is_system` / owner column). The Custom route is left as a placeholder. Need a
   boolean (or `group_type`-style enum) on `questionnaire-headers` to split the two.

4. **PICK-4 — Item value is a single `answer_code` string only.** The legacy items
   are bare values (01, 02, …). If pick-list items ever need a separate
   display-label vs stored-code, or a numeric/typed value, the option model would
   need a `label`/`value_type` column. Not required for current parity — logged for
   completeness.

5. **PICK-5 — No header-level uniqueness / item-uniqueness validation surfaced.**
   The API does not appear to enforce (or expose) uniqueness of `description` across
   pick lists or `answer_code` within a pick list. The frontend only validates
   non-empty values. Confirm whether duplicates should be rejected server-side.

### Notes

- `QuestionnaireHeaderCreate` requires `description`; `is_multi_select`/`is_active`
  are nullable-optional (default applied server-side) — the UI always sends explicit
  booleans.
- `legacy_id` is read-only passthrough (not surfaced in the UI; ID# uses `id`).

---

## 2) Notes Macros Setup

Frontend: `src/components/setup/notes-macros/` (NoteMacroSetup master-detail screen,
`noteMacroData.ts` form model, `noteMacroService.ts` client wrapper).
Route: `/setup/notes-macros` (also `/manage` and `/create`; nav: Setup → Notes Macros).

### Backend used (tag: Procedures)

All CRUD is live and wired through the generated Orval client
(`src/api/generated/endpoints/procedures/procedures.ts`):

| Operation | Endpoint | Function |
| --- | --- | --- |
| List | `GET /api/v1/note-macros` | `listNoteMacros` (paged, `size` max 200, `sort`/`order`/`search`) |
| Get | `GET /api/v1/note-macros/{id}` | `getNoteMacro` |
| Create | `POST /api/v1/note-macros` | `createNoteMacro` |
| Update | `PATCH /api/v1/note-macros/{id}` | `updateNoteMacro` |
| Delete | `DELETE /api/v1/note-macros/{id}` | `deleteNoteMacro` |

`NoteMacroRead` fields used: `id`, `name`, `content`, `category`, `legacy_id`,
`created_by`. Mapping: **Macro Name** ← `name`, **Macro Category** ← `category`,
macro body ← `content`.

### Gaps / requested backend changes

1. **NM-1 — No server-side `category` filter on the list endpoint.**
   `ListNoteMacrosParams` exposes only `page`/`size`/`sort`/`order`/`search` — there
   is no `category` query param. The legacy screen's **Select Macro Category** is a
   first-class filter, so the frontend currently loads all macros and filters
   client-side (also how `AddEditProgressNote` does it). Please add a
   `category?: string` filter to `GET /api/v1/note-macros` (and ideally a
   `GET /api/v1/note-macros/categories` distinct-values endpoint) so the category
   list isn't derived from the loaded page set.

2. **NM-2 — `category` is a free-text string, not a managed enum — and seeded values
   are unresolved numeric codes.** There is no definitions/lookup resource for macro
   categories. Worse, the migrated/seeded data stores `category` as **numeric codes**
   (e.g. `"179"`, `"180"`, `"187"`) rather than the human labels the legacy screen
   shows (e.g. `DIAGNOSTIC`). So the category dropdown currently displays raw numbers.
   The legacy categories almost certainly live in a lookup table that wasn't migrated
   onto the macro row. Please either (a) expose a `NOTE_MACRO_CATEGORY` definition
   group and return a resolvable `category_id` + `category_name`, or (b) backfill
   `category` with the human label. Until then the UI shows the code verbatim and
   offers a datalist of distinct values on add/edit.

3. **NM-3 — `created_by` is an integer id only (no name expansion).** Same pattern as
   CHART-1a: the read model returns `created_by` as a user id with no joined display
   name, so an "author"/"modified by" column can't be shown without a second lookup.
   Expose `created_by_name` (or an embeddable user) if attribution should be shown.

4. **NM-4 — No `updated_at` / `updated_by`.** `NoteMacroRead` has `created_at`/
   `created_by` but no update audit fields, so edits can't show a "last modified"
   timestamp/author. Add `updated_at` (and `updated_by`) if edit history matters.

5. **NM-5 — No name/category uniqueness surfaced.** The API doesn't appear to enforce
   or expose uniqueness of macro `name` (within a category or globally). The frontend
   only validates non-empty `name`/`content`. Confirm whether duplicate names should
   be rejected server-side.

### Notes

- `NoteMacroCreate` requires `name` + `content`; `category` is nullable-optional. The
  UI sends `category: null` when left blank.
- Office-scoped assignment of macros already exists
  (`GET/PUT /api/v1/offices/{office_id}/note-macros`) and is handled separately by
  Office Assignment — this screen manages the global catalog only.

---

## 3) Medical Setup — Medical Alerts, Medical & Dental Questionnaire

Frontend: `src/components/setup/medical/` (`MedicalAlertsSetup.tsx`,
`QuestionnaireBuilder.tsx` shared by `MedicalQuestionnaireSetup` /
`DentalQuestionnaireSetup`, `definitionsService.ts`, `EditorModal.tsx`).
Routes: `/setup/medical/medical-alerts`, `/setup/medical/medical-questionnaire`,
`/setup/medical/dental-questionnaire` (nav: Setup → Medical Setup).

### Backend reality

**There is no dedicated backend resource for any of these three setup screens.**
None of the per-patient resources fit — they store *answers*, not the *template*:
`patient-alerts` (per-patient alert instances), `medical-history-records` /
`medical-history-details` (per-patient questionnaire answers: `question_code`,
`question_text`, `answer_code`, `answer_text`). The setup screens need the master
list / template that those per-patient rows reference.

As an interim, the frontend **repurposes the generic `definition-groups` +
`definitions` tables** (tag: metadata), namespaced by a frontend `group_type`
convention: `MEDALERT`, `MEDQUEST`, `DENTQUEST`. Mapping:

| Setup concept | definition-groups / definitions |
| --- | --- |
| Header / section (e.g. "ALLERGIC TO", "MEDICAL QUESTIONNAIRE") | `definition-group` (`group_type` = feature marker) |
| Medical alert item | `definition` — `description`, **`is_flash_alert`** (= Flash Alert), **`blocks_charges`**, `is_active`, `sort_order` |
| Questionnaire question | `definition` — `description` = question text, **`key1` = input-type code** (TEXT/TEXTAREA/YESNO/DATE), `sort_order`, `is_active` |

CRUD is live (`listDefinitionGroups`/`createDefinitionGroup`/… and
`listDefinitions`/`createDefinition`/…). On first use all three screens are **empty**
(no seeded groups of these types) — the user builds headers/items via Add.

### Gaps / requested backend changes

1. **MED-1 — No feature-scoped home for these catalogs.** `definition-groups` has no
   semantic `group_type` per feature (seeded values are opaque `"A"`/`"B"`), and
   `listDefinitionGroups` has **no `group_type` filter** — the UI fetches all groups
   and filters client-side by our convention markers (`MEDALERT`/`MEDQUEST`/
   `DENTQUEST`). Please either (a) add dedicated resources
   (`medical-alert-headers`+`medical-alerts`, `questionnaire-template-sections`+
   `questionnaire-template-questions`), or (b) bless these `group_type` values and add
   a `group_type` query param to `GET /api/v1/definition-groups`.

2. **MED-2 — No seed data.** The legacy screens ship a rich default catalog (alerts:
   Penicillin, Diabetes, Latex Rubber, …; questionnaire questions per the screenshots).
   None of it was migrated. Needs a seed (or a migration from the legacy tables).

3. **MED-3 — Questionnaire questions have no input-type column.** The legacy questions
   render as typed controls (text / YES-NO dropdown / date / textarea). `definitions`
   has no field for this, so the UI stores the input-type code in **`key1`** as a
   best-effort convention. Needs a real `input_type` (and ideally validation/required
   flag, option-set ref) on whatever question resource is built.

4. **MED-4 — No questionnaire ↔ patient-answer linkage by template.** Per-patient
   answers live in `medical-history-details` keyed by free-text `question_code` /
   `question_text` with no FK to a template question id. So edits to a template
   question don't propagate, and you can't tell which template a question came from.
   A stable `question_id` FK from `medical-history-details` to the template is needed.

5. **MED-5 — No "Save as Draft" / publish workflow, ordering, or section ordering.**
   The legacy screens have **Save as Draft** vs **Save** (staged template publishing)
   and drag-reorder of both headers and rows. The UI does immediate per-item CRUD and
   row `sort_order` only (no draft state, no group/section ordering field —
   `definition-group` has no `sort_order`). Add a draft/published flag and a section
   `sort_order` if the staged workflow matters.

### Notes

- `definition.key1` is **required**; for alerts the UI sets it to the alert name, for
  questions it carries the input-type code. `key2`/`color` are unused here.
- Header delete removes child definitions first (no verified cascade), mirroring the
  Pick List approach (PICK-1).
- `EMERGENCY CONTACT` / `ADDITIONAL COMMENTS` from the legacy questionnaire are just
  sections (headers) the user can add — no special handling.

---

## 4) Prescriptions Setup

Frontend: `src/components/setup/prescriptions/` (PrescriptionSetup master-detail
screen, `prescriptionData.ts` form model, `prescriptionService.ts` client wrapper).
Routes: `/setup/prescriptions` (also `/prescription-setup`, `/common`; nav: Setup →
Prescriptions).

### Backend used (tag: Procedures)

All CRUD is live and wired through the generated Orval client
(`src/api/generated/endpoints/procedures/procedures.ts`):

| Operation | Endpoint | Function |
| --- | --- | --- |
| List | `GET /api/v1/prescription-library` | `listPrescriptionLibrary` (paged, `size` max 200, `sort`/`order`/`search`) |
| Get | `GET /api/v1/prescription-library/{id}` | `getPrescriptionLibraryItem` |
| Create | `POST /api/v1/prescription-library` | `createPrescriptionLibraryItem` |
| Update | `PATCH /api/v1/prescription-library/{id}` | `updatePrescriptionLibraryItem` |
| Delete | `DELETE /api/v1/prescription-library/{id}` | `deletePrescriptionLibraryItem` |

`PrescriptionLibraryRead` → legacy fields: **RX ID#** ← `id` (shown as
`Drug Name (id)` in the rail), **Drug Name** ← `drug_name`, **Dispense** ←
`dispense`, **Sig** ← `sig`, **Refill** ← `refills`, **Dispense As Written** ←
`is_as_written` (Yes/No), plus `is_active`. Good fit — no remapping needed.

### Gaps / requested backend changes

1. **RX-1 — "Modified By" not exposed.** The legacy header shows *Modified By: DRLI*
   alongside *Modified On*. `PrescriptionLibraryRead` has `updated_at` (used for
   "Modified On") but **no `updated_by` / `created_by`** — so the author can't be
   shown. Add `updated_by` (ideally with a joined name, cf. NM-3 / CHART-1a).

2. **RX-2 — Sig length cap (240) is frontend-only.** The legacy editor enforces an
   "Allowed 240 Characters" limit on `sig`. The UI replicates it (`maxLength=240` +
   remaining counter), but the API doesn't appear to advertise/enforce a max length.
   Confirm the column limit so the two stay in sync.

3. **RX-3 — No drug/formulary lookup.** `drug_name` is free text; there's no
   drug-database/formulary endpoint (NDC, strength, form). The per-patient
   `prescriptions` model has `dosespot_rx_id`/`dosespot_status` hinting at a DoseSpot
   integration, but the library has no structured drug reference. Out of scope for
   parity — logged for completeness.

4. **RX-4 — No uniqueness on `drug_name`.** Duplicate drug names are allowed (the
   seed has several, e.g. multiple "Amoxicillin 500mg" variants). The UI only
   validates non-empty `drug_name`. Confirm whether duplicates should be constrained.

### Notes

- `PrescriptionLibraryCreate` requires only `drug_name`; `dispense`/`sig` are sent as
  `null` when blank, `refills` defaults to `0`, `is_as_written`/`is_active` default
  to explicit booleans from the form.
- Office-scoped assignment already exists
  (`GET/PUT /api/v1/offices/{office_id}/prescription-library`) and is handled by
  Office Assignment — this screen manages the global library only.

---

## 5) Custom Toolbar Setup

Frontend: `src/components/setup/custom-toolbar/` (CustomToolbarSetup master-detail
screen, `toolbarCatalog.tsx` function catalog). Routes: `/setup/custom-toolbar`
(also `/configure`; nav: Setup → Custom Toolbar).

### Backend reality

**There is no backend resource for toolbars** (no `toolbar`, `toolbar-function`,
`layout`, or `shortcut` schema/path). As with Medical Setup (§3), the frontend
**repurposes `definition-groups` + `definitions`** (tag: metadata), `group_type`
= `TOOLBAR`:

| Toolbar concept | definition-groups / definitions |
| --- | --- |
| Toolbar (Front Desk, Dentist, …) | `definition-group` (`group_type`=`TOOLBAR`), `description`=name, `id`=Toolbar ID |
| Ordered function in a toolbar | `definition` — `key1`=function code, `description`=label, `sort_order`=position |

The **function catalog** (Scheduler, Patient Overview, Transaction Entry, … Print
Reports — 26 entries) is **frontend-defined** in `toolbarCatalog.tsx` with icons.
CRUD is live via the generic definitions client. Reused `definitionsService.ts`
(GROUP_TYPE now includes `TOOLBAR`). Screen starts **empty** (no seeded toolbars).
Add / Edit (reorder/add/remove functions) / Copy / Delete all work.

### Gaps / requested backend changes

1. **TB-1 — No toolbar resource.** Needs a real `toolbars` + `toolbar-functions`
   (ordered) resource, or — minimally — bless the `group_type`=`TOOLBAR` convention
   and add a `group_type` filter to `GET /api/v1/definition-groups` (same as MED-1;
   today the UI fetches all groups and filters client-side).

2. **TB-2 — No function/feature registry.** The set of toolbar functions and their
   icons is hardcoded on the frontend (`toolbarCatalog.tsx`) because the backend has
   no catalog of assignable app features. If functions should be data-driven (e.g.
   gated by licensing/permissions), expose a `toolbar-functions` catalog endpoint
   (code, label, icon/feature key).

3. **TB-3 — No `updated_at` / `updated_by` on definition-groups.** The legacy header
   shows *Modified On* / *Modified By* (blank in the captures). `DefinitionGroupRead`
   has only `created_at` (no `updated_at`/`updated_by`), so the UI shows "Created On"
   and cannot show modified metadata. Add update audit columns.

4. **TB-4 — No group-level `sort_order`, role binding, or default flag.** Toolbars map
   to job roles (Dentist, Hygienist, Front Desk, …) and the legacy has *Reset to
   Default*. There is no field to (a) order toolbars, (b) bind a toolbar to a
   security role/user, or (c) mark a system default. Needs these if toolbars should
   drive per-role UI.

5. **TB-5 — No seed data + no transactional copy/save.** No default toolbars are
   seeded (legacy ships Dentist/Hygienist/Front Desk/etc.). **Copy Toolbar** and
   **Save** perform one request per function (create group → loop create defs; or
   diff delete/update/create), so a partial failure can leave a toolbar half-built —
   a bulk/transactional write would fix this (cf. PICK-2).

### Notes

- `definition.key1` (required) stores the function code; `description` the label.
- Toolbar delete removes child function definitions first (no verified cascade).
- "Toolbar ID" in the rail = `definition-group.id`.
