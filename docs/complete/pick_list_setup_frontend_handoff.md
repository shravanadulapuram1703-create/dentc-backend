# Setup screens — backend → frontend handoff (changes shipped)

> Response to `pick_list_setup_backend_devreport.md`. This is what the **backend
> team implemented** for the Pick List / Notes Macros / Medical / Prescriptions /
> Custom Toolbar setup screens, plus the decisions and the items we deliberately
> deferred. **Run `npm run api:sync`** against this backend to pick up the new
> fields and endpoints before wiring the frontend changes below.
>
> Migration: `f1a2b3c4d5e6_add_setup_screen_gaps` (revises `e945c28dd602`).
> All fields are snake_case and Orval-ready. 221 backend tests green (8 new).

---

## TL;DR — what changed

| Gap | Status | What you get |
|---|---|---|
| PICK-1 | ✅ Shipped | `DELETE /questionnaire-headers/{id}/cascade` — one call removes a list + its items |
| PICK-2 | ✅ Shipped | `PUT /questionnaire-headers/{id}/options` — atomic replace of all items |
| PICK-3 | ✅ Shipped | `is_custom` on `questionnaire-headers` (+ `?is_custom=` filter) splits Manage vs Custom |
| PICK-4 | ⏸ Deferred | label/value_type — not needed for parity (logged) |
| PICK-5 | 🔵 Decision | no server uniqueness on `description`/`answer_code` — see below |
| NM-1 | ✅ Shipped | `?category=` filter on `GET /note-macros` |
| NM-4 | ✅ Shipped | `updated_at` + `updated_by` on `note-macros` |
| NM-3 | ⏸ Deferred | `created_by_name` join — bind the id; name expansion deferred |
| NM-2 | ⏸ Deferred | managed category enum / backfill — see below |
| NM-5 | 🔵 Decision | no name uniqueness — see below |
| RX-1 | ✅ Shipped | `updated_by` on `prescription-library` |
| RX-2/3/4 | 🔵/⏸ | sig cap confirmed FE-side; formulary + uniqueness deferred |
| MED-1 / TB-1 | ✅ Shipped | `?group_type=` filter on `GET /definition-groups` |
| MED-3 | ✅ Shipped | `input_type` column on `definitions` |
| TB-3 | ✅ Shipped | `updated_at` + `updated_by` on `definition-groups` (and `definitions`) |
| MED-2/4/5, TB-2/4/5 | ⏸ Deferred | dedicated resources / seeds / draft workflow — see "Deferred" |

---

## 1) Pick List Setup

### PICK-2 — atomic header items save *(new endpoint)*

`PUT /api/v1/questionnaire-headers/{header_id}/options` — replaces the **whole**
item set in one transaction. Drop the per-item create/update/delete loop.

Request:
```jsonc
{ "items": [
  { "id": 12, "answer_code": "01", "is_active": true },  // id present → update
  { "answer_code": "02" }                                 // id absent  → create
] }                                                        // omitted existing item → deleted
```
- `sort_order` is **server-normalised** to contiguous 1-based order following the
  array order — don't send it; send items in display order.
- Items present in the DB but **absent from the payload are hard-deleted** (true
  replace semantics — they won't reappear as inactive rows).
- Returns the refreshed `PickListOptionRead[]` (`id, questionnaire_id, answer_code,
  sort_order, is_active, legacy_id, created_at`), already ordered.
- 404 if the header isn't in the caller's tenant.

Operation id: `replace_pick_list_items`.

### PICK-1 — cascade delete *(new endpoint)*

`DELETE /api/v1/questionnaire-headers/{header_id}/cascade` → `{ header_id,
options_deleted }`. **Soft-deletes the header** (`is_active=false`, same as the
generic delete) **and removes all its options** in one transaction. Replaces the
client's "list options → delete each → delete header" N+1. Operation id:
`delete_pick_list_cascade`. (The FK also now has `ON DELETE CASCADE` as a safety
net for any hard delete.)

### PICK-3 — Manage vs Custom split *(new field)*

`QuestionnaireHeaderRead.is_custom: boolean` (default `false`). Write it on
create/update. Filter the two nav routes:
- **Manage Pick Lists** → `GET /questionnaire-headers?is_custom=false`
- **Custom Pick Lists** → `GET /questionnaire-headers?is_custom=true`

### PICK-4 / PICK-5 — decisions
- **PICK-4** (separate label vs code, typed values): not built — not needed for
  parity. If you need a display label distinct from `answer_code`, ask and we'll add
  a column.
- **PICK-5** (uniqueness): **not enforced server-side.** Duplicate `description`
  across lists and duplicate `answer_code` within a list are allowed. Keep your
  non-empty validation; if you want hard rejection, confirm and we'll add a
  constraint (it would surface as the standard `409 conflict` envelope).

---

## 2) Notes Macros Setup

### NM-1 — category filter *(new query param)*
`GET /api/v1/note-macros?category=DIAGNOSTIC`. Stop loading-all + filtering
client-side; bind **Select Macro Category** straight to this. (No distinct-values
endpoint yet — derive the dropdown from a one-time unfiltered fetch, or see NM-2.)

### NM-4 — Modified On / Modified By *(new fields)*
`NoteMacroRead` now has `updated_at` and `updated_by` (auto-set on every PATCH).
Bind your "Modified On" to `updated_at`. **Modified By** is a user **id** (see NM-3).

### NM-2 / NM-3 — deferred (action needed on FE)
- **NM-2** (category is a numeric code, no managed enum): **not changed yet.** The
  seeded `category` values are still raw codes (`"179"`…). We did **not** backfill or
  add a `NOTE_MACRO_CATEGORY` definition group in this pass — it needs a data
  decision (map table vs. re-migrate). Keep showing the code + your add/edit
  datalist for now. Tracked; tell us which option (a: `category_id`+`category_name`,
  b: backfill labels) you want.
- **NM-3** (`updated_by`/`created_by` are ids, no name): we expose the **id** only
  (consistent with the charting screens you already shipped). Name expansion is
  deferred — bind the id, show "—" or resolve via your users cache if needed.

### NM-5 — decision
No server-side `name` uniqueness. Same stance as PICK-5 — confirm if you want it.

---

## 3) Prescriptions Setup

### RX-1 — Modified By *(new field)*
`PrescriptionLibraryRead.updated_by` (id, auto-set on PATCH). `updated_at` was
already present → "Modified On". As with NM-3, it's an id, not a joined name.

### RX-2 / RX-3 / RX-4 — decisions / deferred
- **RX-2** (sig 240-char cap): the column is `String(500)`, so the API won't reject
  at 240. Keep your FE `maxLength=240`. If you want the API to enforce 240 exactly,
  say so and we'll tighten the column + validation.
- **RX-3** (drug/formulary lookup): out of scope — no formulary endpoint. `drug_name`
  stays free text.
- **RX-4** (uniqueness on `drug_name`): not enforced (the seed intentionally has
  variants). Confirm if you want it constrained.

---

## 4) Medical Setup  &  5) Custom Toolbar Setup

These still ride on `definition-groups` + `definitions`. We shipped the **filter +
audit + typed-question** pieces now; the **dedicated resources / seeds / workflow**
are deferred (see below).

### MED-1 / TB-1 — group_type filter *(new query param)*
`GET /api/v1/definition-groups?group_type=MEDALERT` (also `MEDQUEST`, `DENTQUEST`,
`TOOLBAR`, …). Stop fetching all groups + filtering by your convention markers —
filter server-side. `group_type` widened to `varchar(20)` so longer markers fit.

### MED-3 — typed questionnaire control *(new field)*
`DefinitionRead.input_type: string | null` (e.g. `TEXT` / `TEXTAREA` / `YESNO` /
`DATE`). **Migrate off the `key1` convention** — store the control type in
`input_type` and leave `key1` for the legacy key. Round-trips on create/update.

### TB-3 — Modified On / Modified By *(new fields)*
`DefinitionGroupRead` now has `updated_at` + `updated_by`, and `DefinitionRead`
also gained `updated_at` + `updated_by` (auto-set on PATCH). Use these for the
toolbar/medical "Modified On/By" headers instead of "Created On".

### Deferred (need product / data decisions — not in this pass)
- **MED-2 / TB-5 — seed data.** No default alert/questionnaire/toolbar catalog was
  seeded. Screens still start empty. Needs a seed or legacy migration — flag if it's
  blocking and we'll prioritise a `seed_*` script.
- **MED-4 — template ↔ patient-answer FK.** `medical-history-details` still keys by
  free-text `question_code`/`question_text`; no `question_id` FK to a template. Needs
  the dedicated questionnaire-template resource first.
- **MED-5 — draft/publish + section ordering.** No draft flag, no group-level
  `sort_order`. Row `sort_order` only.
- **TB-2 — function/feature registry.** Toolbar function catalog stays FE-owned
  (`toolbarCatalog.tsx`); no backend feature registry.
- **TB-4 — toolbar role binding / default flag / ordering.** Not added.
- **MED-1 / TB-1 dedicated resources.** We blessed the `group_type` convention +
  filter rather than building `medical-alert-headers` / `toolbars` resources. If you
  want first-class resources later, it's a clean follow-up — the filter unblocks the
  screens now.

---

## New fields summary (post-`api:sync`)

| Read model | New fields |
|---|---|
| `QuestionnaireHeaderRead` | `is_custom` |
| `NoteMacroRead` | `updated_at`, `updated_by` |
| `PrescriptionLibraryRead` | `updated_by` |
| `DefinitionRead` | `input_type`, `updated_at`, `updated_by` |
| `DefinitionGroupRead` | `updated_at`, `updated_by` |

New endpoints (tag **Metadata**): `replace_pick_list_items`
(`PUT /questionnaire-headers/{id}/options`), `delete_pick_list_cascade`
(`DELETE /questionnaire-headers/{id}/cascade`).

New filters: `note-macros?category=`, `definition-groups?group_type=`,
`questionnaire-headers?is_custom=`.

## Open questions back to frontend
1. **PICK-5 / NM-5 / RX-4** — do you want server-side uniqueness (→ `409`s to
   handle) or keep FE-only non-empty validation? Default kept: no DB constraint.
2. **NM-2** — option (a) resolvable `category_id`+`category_name`, or (b) backfill
   `category` with labels? We'll do whichever you pick.
3. **Modified By (NM-3 / RX-1 / TB-3)** — id is enough, or do you want a joined
   `*_by_name` on these read models (app-wide pattern)?
4. **MED-2 / TB-5 seeds** — is empty-on-first-use blocking? If so we'll ship a seed.
