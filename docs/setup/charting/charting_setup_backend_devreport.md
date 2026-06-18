# Charting Setup — Backend Dev Report / Gaps Report (Perio Templates · Restorative Color · Restorative Materials)

> **Gaps report for the backend team.** Captures the functionality of the legacy
> Denticon "Charting" setup screens and what the current API is missing to back
> them. Companion to `charting_setup_frontend_handoff.md`.

Routes (reserved under `/setup/charting/`):

- `/setup/charting/perio-templates` — "Perio Setup Templates"
- `/setup/charting/restorative-colors` — "Restorative Charting Color Setup"
- `/setup/charting/restorative-materials` — "Restorative Charting Materials Setup"

**Status summary:**

| Screen | Backing model | CRUD exists? | State |
|---|---|---|---|
| Restorative Color Setup | `chart_colors` | ✅ `chart-colors` (tag Metadata) | **Buildable now** — minor audit gap |
| Restorative Materials Setup | `chart_materials` | ✅ `chart-materials` (tag Procedures) | **Buildable now** — audit gap (no `updated_at`) |
| Perio Setup Templates | `perio_chart_settings` | ⚠️ `perio-chart-settings` (tag Clinical) | **Blocked** — model is a per-user preference, not a named template library |

Two screens are essentially wireable today against existing CRUD; the Perio
Templates screen needs a model change (details in **GAP CHART-1**).

---

## Verification (how we know the state)

Checked against `app/db/models/` and `app/api/v1/registry.py`:

1. `chart_colors` (`app/db/models/codes.py:151`) is registered CRUD at
   `chart-colors` (`registry.py:335`, tag **Metadata**), `TimestampMixin`
   (`created_at` + `updated_at`), `soft_field=None`.
2. `chart_materials` (`codes.py:88`) is registered CRUD at `chart-materials`
   (`registry.py:214`, tag **Procedures**), `CreatedAtMixin` (**no `updated_at`**),
   `soft_field=None`.
3. `perio_chart_settings` (`app/db/models/clinical.py:144`) is registered CRUD at
   `perio-chart-settings` (`registry.py:279`, tag Clinical) but `user_id` is
   **`unique=True`** → one row per user, no `name`, no `tenant_id`.
4. No seed scripts touch any of the three tables (`scripts/` greps clean) — content
   exists only for migrated tenants via `legacy_id`; new tenants start empty.

---

## GAP CHART-1 — Perio Setup Templates  *(blocking)*

Legacy screen: a **named template manager** — left list of templates, `ADD
TEMPLATE` / `EDIT TEMPLATE` / `DELETE TEMPLATE`, a "Template Info" panel, an
"Auto Advance Direction" panel, and a "Modified On / Modified By" stamp.

### Legacy fields → current model

| Legacy field | `perio_chart_settings` column | Status |
|---|---|---|
| Template Name | — | ❌ no `name` |
| (tenant scoping) | — | ❌ no `tenant_id` (keyed by `user_id`, `unique`) |
| Show MGJ (Yes/No) | `is_mgj` | ✅ |
| Pocket Depth Warning Level | `pd_level` | ✅ |
| CAL Warning Level | — | ❌ no `cal_level` |
| Default Buccal and Palatal Level for Pocket Depth | `bp_level` | ✅ |
| Default Inter-proximal Level for Pocket Depth | `ip_level` | ✅ |
| Default Level for FGM | — | ❌ no `fgm_level` |
| Start Voice (Yes/No) | — | ❌ no `start_voice` |
| Auto Advance Direction (8 region rows) | `is_forward` (single bool) | ⚠️ partial |
| Modified On | `created_at` only | ❌ no `updated_at` |
| Modified By | — | ❌ no `modified_by` |

`is_indicator` exists on the model but is not on the screen — leave as-is.

**Auto Advance Direction** is 8 region rows, each a two-way direction toggle:

| Region | Option A | Option B |
|---|---|---|
| UR Facial | 01 → 08 | 08 → 01 |
| UL Facial | 09 → 16 | 16 → 09 |
| UL Lingual | 16 → 09 | 09 → 16 |
| UR Lingual | 08 → 01 | 01 → 08 |
| LL Facial | 17 → 24 | 24 → 17 |
| LR Facial | 25 → 32 | 32 → 25 |
| LR Lingual | 32 → 25 | 25 → 32 |
| LL Lingual | 24 → 17 | 17 → 24 |

The single `is_forward` boolean cannot represent 8 independently-toggled regions.

### Recommended backend — new dedicated resource `perio-chart-templates`

`perio_chart_settings` stays as the **per-user runtime preference** (don't repurpose
it). Add a **named, tenant-scoped template** model:

```
perio_chart_templates
  id            (pk)
  tenant_id     (fk tenants, index)        # named templates are practice-level
  legacy_id     string?                    # migration lineage
  name          string                     # "Default Template"
  show_mgj          boolean  default false # legacy "Show MGJ"
  pd_warning_level  int      default 4     # "Pocket Depth Warning Level"
  cal_warning_level int      default 4     # NEW "CAL Warning Level"
  bp_level          int      default 2     # "Default Buccal and Palatal Level"
  ip_level          int      default 3     # "Default Inter-proximal Level"
  fgm_level         int      default 2     # NEW "Default Level for FGM"
  start_voice       boolean  default false # NEW "Start Voice"
  auto_advance      JSON                   # NEW: {"ur_facial":"01-08", ...} 8 keys
  created_by    (fk users)
  updated_by    (fk users)                 # NEW -> "Modified By"
  created_at / updated_at                  # TimestampMixin -> "Modified On"
```

Endpoints (standard CRUD via `register_crud`): `GET/POST /api/v1/perio-chart-templates`,
`GET/PATCH/DELETE /{id}`, paginated, `search=("name",)`, tenant-scoped. snake_case,
Orval-ready. Tag suggestion: **Clinical** (alongside the existing perio resources).

`auto_advance` as a JSON object (8 keys, values `"01-08"` / `"08-01"`) keeps the
8 regions extensible without 8 columns; matches the `valid_teeth: JSON` precedent on
`procedure_codes`. If you prefer columns, 8 `*_dir` varchars work too — flag your
preference.

---

## GAP CHART-2 — Restorative Charting Color Setup  *(buildable now, minor gaps)*

Legacy screen: read-grid `Condition | Stroke Color | Fill Color | Sample | Modified
By | Modified On` + an "Edit Chart Colors" panel (Condition read-only, Stroke Color
dropdown, Fill Color dropdown, live Sample swatch). Conditions seen: Pre-existing,
Completed, Treatment Plans, Defective, Infection, Decay/Caries, Abrasion, Lesions,
Referred Out, Cracked/Fractured.

### Legacy fields → `chart_colors`

| Legacy field | `chart_colors` column | Status |
|---|---|---|
| Condition | `name` | ✅ |
| Stroke Color | `stroke_color` | ✅ |
| Fill Color | `fill_color` | ✅ |
| Sample | *(derived from stroke/fill on FE)* | ✅ |
| Modified On | `updated_at` (TimestampMixin) | ✅ |
| Modified By | `created_by` (String) only | ❌ no `modified_by` |

`fill_type`, `fill_color2`, `fill_pattern`, `gradient_angle`, `gradient_method`,
`category_type` are extra columns the legacy screen doesn't surface — leave for the
charting renderer.

**Gaps / decisions:**

- **CHART-2a (minor):** "Modified By" has no user FK. `created_by` is a free-text
  string, not the *last* editor. Add `modified_by (fk users)` if the column must be
  accurate; otherwise FE will show `created_by` and we accept it's creator, not
  modifier. *Recommend:* add `modified_by`.
- **CHART-2b (decision):** Stroke/Fill dropdowns enumerate named colors (Blue, Green,
  Firebrick, Red, HotPink, SpringGreen, Purple, Black, DarkGreen, Pink, …). This is a
  fixed presentation palette — *recommend FE owns it as a static list*; no backend
  endpoint needed. Confirm you don't want it as a `definitions` group.
- **CHART-2c (seeding):** no seed for the default 10 condition rows → new tenants get
  an empty grid. *Recommend* a `seed_chart_defaults` script (idempotent, per tenant)
  populating the standard conditions + default colors.

---

## GAP CHART-3 — Restorative Charting Materials Setup  *(buildable now, audit gap)*

Legacy screen: read-grid `Name | Sample | Modified By | Modified On` + "Add New
Chart Material" (Name text input, Sample = pattern dropdown). Materials seen:
Arestin, Ceramic, Composite, Gold, Gutta-percha, High Noble Metal, Metal, Other.
Pattern dropdown keys: hash, round, r5hash, r6hash, r2hash, r4hash, round1,
crosshatch, r3hash, sealant, veneer, …

### Legacy fields → `chart_materials`

| Legacy field | `chart_materials` column | Status |
|---|---|---|
| Name | `name` | ✅ |
| Sample (pattern) | `pattern` (+ `color`) | ✅ |
| Modified On | — | ❌ no `updated_at` (`CreatedAtMixin`) |
| Modified By | — | ❌ no `created_by` / `modified_by` |

**Gaps / decisions:**

- **CHART-3a (audit):** `chart_materials` uses `CreatedAtMixin` (no `updated_at`).
  The "Modified On" column cannot be filled. *Recommend* switching to `TimestampMixin`
  (adds `updated_at`) — one-line model change + autogenerate migration.
- **CHART-3b (audit):** no `created_by`/`modified_by` → "Modified By" unfillable.
  *Recommend* adding `modified_by (fk users)`.
- **CHART-3c (decision):** the Sample dropdown is a fixed set of SVG fill-pattern keys
  stored in `pattern`. *Recommend FE owns the pattern catalog* (key + preview render);
  backend just stores the chosen key string. Confirm.
- **CHART-3d (seeding):** no seed for the default material set → empty grid for new
  tenants. Fold into the same `seed_chart_defaults` script as CHART-2c.

---

## DEFECTS found in live data (Restorative Materials)

Two defects surfaced while wiring the Materials screen against the migrated DB.

### CHART-3e — Sample column renders `?` (FIXED)

**Symptom:** every row's Sample cell shows a `?` placeholder instead of the fill
pattern.

**Root cause:** `chart_materials.pattern` was migrated as the legacy **GIF filename**
(`hash.gif`, `round.gif`, `arestin.gif`, …), but the charting renderer / FE pattern
catalog keys on the **bare** name (`hash`, `round`, `arestin`). `"hash.gif"` matches
no catalog key → fallback `?`. The importer (`s12_chart_materials.py`) inserted
`MATPATTERN` verbatim. (The `Unknown` material has a genuinely NULL pattern — that one
`?` is legitimate.)

**Fix applied:**
- One-off normalization `python -m scripts.backfill_chart_material_patterns` — strips
  the extension + lowercases; **88 rows normalized**, NULLs left alone. Idempotent.
- `s12_chart_materials.py` now normalizes `MATPATTERN` on import (`_pattern_key`) so
  re-runs store bare keys.

Resulting catalog keys in use: `hash, round, round1, r2hash, r3hash, r4hash, r5hash,
r6hash, crosshash, sealant, veneer, arestin` (FE catalog must cover these).

### CHART-3f — Duplicate rows in chart_materials AND chart_colors (FIXED)

**Symptom:** the grid lists each material 4×; the same audit found `chart_colors`
duplicated 5×.

| Table | Before | After |
|---|---|---|
| `chart_materials` | 92 rows / 23 distinct | **23** |
| `chart_colors` | 50 rows / 10 distinct | **10** |

**Root cause:** neither table had a unique constraint on `(tenant_id, legacy_id)`, so
the importer's `ON CONFLICT DO NOTHING` (`s12_chart_materials.py:39`) was a no-op and
each of the ~4 migration re-runs re-inserted the full set. **Identical bug class
already fixed for `code_bundles`** (`uq_code_bundles_tenant_legacy`).

**Fix applied (mirrors code_bundles):**
1. `UniqueConstraint("tenant_id", "legacy_id", …)` added to **both** `ChartMaterial`
   and `ChartColor` (NULL `legacy_id` exempt — API-created rows).
2. Alembic migration `a0b1c2d3e4f5_dedupe_chart_setup_unique` — dedupes (keep
   `min(id)` per group) then adds both constraints. `chart_materials`'s four inbound
   FKs (`patient_procedures`, `chart_conditions`, `appointment_procedures.material_id`,
   `procedure_codes.default_material_id`) are **repointed to the survivor** before
   delete (verified 0 orphans). `chart_colors` has no inbound FKs.
3. `scripts/dedupe_chart_setup.py` (idempotent, `--dry-run`/`--tenant`) for on-demand use.
4. Regression tests in `tests/test_chart_setup_dedupe.py`.

With the unique key in place the importer's `ON CONFLICT DO NOTHING` now actually
fires, so future migration re-runs are idempotent.

---

## Consolidated backend asks

| # | Ask | Effort | Blocks |
|---|---|---|---|
| CHART-1 | New `perio-chart-templates` resource (named, tenant-scoped, +`cal_warning_level`, `fgm_level`, `start_voice`, `auto_advance` JSON, audit cols) | Medium (new model + migration + registry row) | Perio Templates screen |
| CHART-2a | Add `modified_by` to `chart_colors` | Tiny | "Modified By" accuracy |
| CHART-3a | `chart_materials` → `TimestampMixin` (`updated_at`) | Tiny | "Modified On" column |
| CHART-3b | Add `modified_by` to `chart_materials` | Tiny | "Modified By" column |
| CHART-2c/3d | `seed_chart_defaults` script (conditions+colors, materials), idempotent per tenant | Small | Non-empty grids for new tenants |
| CHART-3e | Normalize `pattern` (`*.gif` → bare key) + importer fix | **Done** | Sample column rendering |
| CHART-3f | Dedupe `chart_materials` + `chart_colors` + unique `(tenant_id, legacy_id)` (mirror code_bundles) | **Done** | Duplicate rows in grid |

**Decisions needed back from backend:**

1. `perio_chart_templates.auto_advance` — JSON object (recommended) vs 8 `*_dir` columns?
2. Keep `perio_chart_settings` as the per-user runtime preference (recommended), or fold it into templates with a `user_id` FK?
3. Color palette (CHART-2b) and material pattern catalog (CHART-3c) — FE-static (recommended) or backend-served?
4. Should `modified_by` be added app-wide via a shared mixin, or per-table here?
