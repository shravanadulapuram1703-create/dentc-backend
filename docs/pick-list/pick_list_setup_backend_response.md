# Prescriptions Setup — backend → frontend handoff (round 2: RX-1 / RX-2 / RX-4)

> Response to §4 *Prescriptions Setup* of `pick_list_setup_backend_devreport.md`
> (the 2026-09-10 revision that added the "every drug 5×" root cause). Round 1
> (`docs/complete/pick_list_setup_frontend_handoff.md`, migration `f1a2b3c4d5e6`)
> shipped `updated_by`; this round closes the three open questions it left for
> the Rx screen. **Run `npm run api:sync`** to pick up the new fields/endpoints.
>
> Migration: `239077e738d5_dedupe_prescription_library_unique` (revises
> `b6c7d8e9f0a1`) — **applied to the shared dev DB on 2026-09-10**. All fields
> snake_case, Orval-ready. 13 new tests (`tests/test_prescription_library.py`).

---

## TL;DR

| Gap | Status | What you get |
|---|---|---|
| RX-4 (data) | ✅ **Applied** | `prescription_library` 427 → **87** rows (85 legacy + 2 API-created), 0 duplicate groups, 0 dangling refs; `uq_prescription_library_tenant_legacy` stops the importer recurring it |
| RX-4 (API) | ✅ Shipped | 409 `duplicate_prescription` on an identical **active** `drug_name + dispense + sig`, overridable with `allow_duplicate`; same-name/different-config is reported, never blocked |
| RX-4 (probe) | ✅ Shipped | `GET /prescription-library/availability?drug_name=&dispense=&sig=&exclude_id=` |
| RX-2 | ✅ Shipped | `sig` > 240 chars is a 422 `sig_too_long`; caps published at `GET /prescription-library/limits` |
| RX-1 | ✅ Shipped | `created_by` + `created_by_name` / `updated_by_name` on `PrescriptionLibraryRead` |
| RX-3 | ⏸ Deferred | no formulary endpoint (unchanged) |

---

## RX-4 — the duplicates are gone, and they cannot come back

### What was applied

Verified against the dev DB before running (matches your report exactly):
427 rows = 85 legacy drugs × 5 byte-identical copies + 2 API-created rows;
14 `prescriptions.library_rx_id` and 1 `office_prescription_library` link
pointed at a duplicate; those two tables are the only inbound FKs.

The migration was dry-run inside a rolled-back transaction first, then applied:

| Check | After |
|---|---|
| `prescription_library` rows | 87 (85 with `legacy_id`, all distinct) |
| duplicate `(tenant_id, legacy_id)` groups | 0 |
| `prescriptions` rows pointing at a missing library row | 0 |
| office links pointing at a missing library row | 0 |
| drug names listed more than once | 1 — *Chlorhexidine Gluconate 0.12% Oral Rinse* (ids 1 and 66, different dispense/sig — the legitimate pair) |

Survivor = lowest id per group, which is what `dedupeRxLibrary` was already
keeping — **the client-side de-dupe can be deleted**; it now filters nothing.
`rxDrugOptionLabels` (the `dispense · sig` suffix on repeated names) is still
worth keeping for the Chlorhexidine pair.

The importer (`s16_prescription_library.py`) needed no change: its
`ON CONFLICT DO NOTHING` was inert only because there was nothing to conflict
on; the new unique constraint makes it do what it always said.

### The API-side guard

`prescription_library` had no uniqueness, and after the constraint above it
still has none on *content* — deliberately. An admin may want a second
"Amoxicillin" on purpose, and the seed legitimately holds one drug twice. So the
rule is the INS-PT-19 shape: **refuse the accidental duplicate, never the
duplicate.**

- `POST /prescription-library` / `PATCH /prescription-library/{id}` → **409**
  `duplicate_prescription` when an **active** row already has the same
  `drug_name` + `dispense` + `sig` (trimmed, internal whitespace collapsed,
  case-insensitive; blank and `null` are the same value).
- Send `"allow_duplicate": true` in the body to override (not persisted, not
  echoed). This is the dialog's third button.
- `error.details` carries everything the dialog needs:

```json
{
  "error": {
    "code": "duplicate_prescription",
    "message": "An active prescription with this drug name, dispense and sig already exists",
    "details": {
      "drug_name": "Amoxicillin 500mg", "dispense": "30 caps", "sig": "1 cap tid x 10 days",
      "matches":           [{ "id": 12, "drug_name": "...", "dispense": "...", "sig": "...", "refills": 0, "is_as_written": false, "is_active": true, "legacy_id": "101" }],
      "inactive_matches":  [],
      "same_name_matches": [],
      "override_field": "allow_duplicate"
    }
  }
}
```

- `inactive_matches` — identical configuration but deactivated. Reported so the
  dialog can offer *Reactivate* instead of creating a twin. Never blocks a create.
  **Re-activating** such a row (`PATCH {is_active: true}`) *is* guarded, because
  that is the write that recreates the duplicate.
- `same_name_matches` — same drug, different dispense/sig (the Chlorhexidine
  case). Reported, never blocks.
- On PATCH the guard fires only on a **move** — the (name, dispense, sig) identity
  actually changing (judged against the merge of payload + stored row, so a PATCH
  carrying only `sig` is still checked against the row's own name/dispense). A
  pre-existing duplicate stays editable (refills, flags, …).
- A row created with `is_active: false` never collides — the picker does not
  offer it.

### The probe

`GET /prescription-library/availability?drug_name=…&dispense=…&sig=…&exclude_id=…`
→ `PrescriptionAvailabilityResult`:

```json
{ "drug_name": "…", "dispense": "…", "sig": "…",
  "taken": true,
  "matches": [ …PrescriptionMatch ], "inactive_matches": [], "same_name_matches": [],
  "override_field": "allow_duplicate" }
```

`taken` is **exactly** the condition the save path 409s on (same function).
Pass `exclude_id` when editing so the row never collides with itself. Use it on
blur of the Drug Name field, not on every keystroke.

## RX-2 — sig cap is now server-side and published

`GET /prescription-library/limits`:

```json
{ "sig_max_length": 240, "drug_name_max_length": 255, "dispense_max_length": 255,
  "duplicate_key_fields": ["drug_name", "dispense", "sig"], "override_field": "allow_duplicate" }
```

`sig` over 240 → **422** `sig_too_long`, `details: {field, max_length, length}`
(same shape for `drug_name_too_long` / `dispense_too_long` at 255). Only fields
present in the payload are judged, so a PATCH of `is_active` on a migrated row
can never fail on a sig it did not touch. Drive `maxLength` and the remaining
counter from `sig_max_length` rather than a literal. The column stays
`String(500)` on purpose (no live value exceeds 177 chars; narrowing it would
turn an over-long legacy value into a migration failure instead of a 422).

Also: `drug_name`, `dispense`, `sig` are stored **trimmed**; a blank
`drug_name` is a 422 `drug_name_required` rather than a NOT NULL error.

## RX-1 — Created By / Modified By as names

`PrescriptionLibraryRead` gains `created_by` (stamped on POST) and the resolved
`created_by_name` / `updated_by_name` (batched, no N+1; user's first+last name,
falling back to username). Migrated rows have `created_by = null` — the
Denticon export carries no author for the library, so the header shows
*Created By* only for rows added through the app. `updated_by` /
`updated_by_name` populate on the first PATCH.

`GET /prescription-library?sort=drug_name&order=asc` is now honoured
(`drug_name` joined the sortable set), so the rail can stop sorting client-side.

## Not in this round

- **NM-6 / NM-7** were the *same two defects* on `note_macros` and are closed in
  the *Notes Macros Setup* section below (same migration shape, same guard).
- **RX-3** formulary lookup — still out of scope.

---

# Notes Macros Setup — round 2 (NM-3 / NM-5 / NM-6 / NM-7)

> Same shape as the Rx pass above, applied to `note_macros`. Migration
> `3a8f2c41b7d9_dedupe_note_macros_unique` (revises `b08a4634a3e3`) —
> **applied to the shared dev DB on 2026-09-10**. 9 new tests
> (`tests/test_note_macros.py`). Run `npm run api:sync`.

| Gap | Status | What you get |
|---|---|---|
| NM-7 (data) | ✅ **Applied** | `note_macros` 481 → **121** rows (120 legacy + 1 API-created), 0 duplicate groups, 0 dangling refs; `uq_note_macros_tenant_legacy` stops the importer recurring it |
| NM-6 | ✅ Shipped | `GET /note-macros?sort=name` / `sort=category` (+ `order=`) is honoured |
| NM-5 | ✅ Shipped | 409 `duplicate_note_macro` on the same `name` in the same `category`, overridable with `allow_duplicate`; `GET /note-macros/availability` + `/limits` |
| NM-3 | ✅ Shipped | `created_by_name` / `updated_by_name` on `NoteMacroRead` |
| NM-2 | ⏸ Unchanged | categories are still the numeric legacy codes (`179`, `180`, …) — see below |

## NM-7 — what was applied

Verified before running: 481 rows = 120 legacy macros × 4 byte-identical copies
+ 1 API-created row; the only inbound FKs are `office_note_macros.note_macro_id`
(1 link pointing at a duplicate) and `procedure_codes.default_notes_macro_id`
(all 3 pointing at duplicates). Dry-run in a rolled-back transaction, then applied.

| Check | After |
|---|---|
| `note_macros` rows | 121 (120 distinct `legacy_id` + 1 API row) |
| duplicate `(tenant_id, legacy_id)` groups | 0 |
| `procedure_codes` / office links pointing at a missing macro | 0 / 0 (3 codes repointed to the survivor) |
| same name + category listed more than once | 1 — *Fixed/Detach Try-in* (category `186`), two distinct legacy rows |

Survivor = lowest id per group. Every macro list (Setup, Progress Notes left
panel, Patient Notes → Add Notes Macro) now shows each entry once; any
client-side de-dupe can go.

## NM-6 — sort

`name` and `category` joined the sortable set (`created_at` / `updated_at` / `id`
were the only ones, so the documented `?sort=name` silently fell back to id
order). `?sort=name&order=asc` now returns A→Z across pages with `id` as the
tiebreaker; both the Setup rail and the Patient Notes picker can drop their
client-side sort.

## NM-5 — duplicate guard (same contract as Rx)

- `POST /note-macros` / `PATCH /note-macros/{id}` → **409** `duplicate_note_macro`
  when a macro with the same `name` already exists in the same `category`
  (trimmed, whitespace-collapsed, case-insensitive; blank category == no category).
  `"allow_duplicate": true` overrides (not persisted, not echoed).
- `error.details`: `{name, category, matches: [NoteMacroMatch], other_category_matches: [...], override_field: "allow_duplicate"}`.
  `other_category_matches` (same name under another category — e.g. *Consult*
  under `179` and `189`) is informational and never blocks.
- PATCH fires on a **move** only (name or category actually changing, judged
  against the merge of payload + stored row). The migrated *Fixed/Detach
  Try-in* pair stays editable.
- `GET /note-macros/availability?name=&category=&exclude_id=` → `{name, category,
  taken, matches, other_category_matches, override_field}` — `taken` is exactly
  what the save path 409s on. `GET /note-macros/limits` →
  `{name_max_length: 100, category_max_length: 100, duplicate_key_fields, override_field}`;
  over-long values are 422 `name_too_long` / `category_too_long` (previously a
  raw database error), blank `name` is 422 `name_required`.
- `name` / `category` are stored trimmed; a blank `category` is stored as
  `null` so `/note-macros/categories` never grows an empty bucket.

## NM-3

`NoteMacroRead.created_by_name` / `updated_by_name` (batched, no N+1; first+last
name, falling back to username). Migrated rows have `created_by = null`.

## NM-2 — still open, and now the only blocker left on this screen

`category` values are still Denticon's numeric group codes. Nothing in the
export links them to labels (the lookup was never migrated), so the choice
between (a) a `NOTE_MACRO_CATEGORY` definitions group + `category_name` on the
read and (b) a backfill of the column needs the legacy label list from the
practice. Send us the code→label mapping and either shape is a small change;
the guard above already treats a category as an opaque key, so it will not
need to change.
