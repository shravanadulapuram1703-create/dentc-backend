# Charting Setup — Backend Dev Report / Gaps Report (Perio Templates · Restorative Color · Restorative Materials)

> **Gaps report for the backend team.** Captures the functionality of the legacy
> Denticon "Charting" setup screens and what the current API is missing to back
> them. Companion to `charting_setup_frontend_handoff.md`.

Routes (live under `/setup/charting/`):

- `/setup/charting/per-use-templates` — "Perio Setup Templates" *(PlaceholderPage — blocked on CHART-1)*
- `/setup/charting/colors` — "Restorative Charting Color Setup" *(shipped)*
- `/setup/charting/materials` — "Restorative Charting Materials Setup" *(shipped)*

**Status summary:**

| Screen | Backing model | CRUD exists? | State |
|---|---|---|---|
| Restorative Color Setup | `chart_colors` | ✅ `chart-colors` (tag Metadata) | **Done** — `updated_by` added (CHART-2a) |
| Restorative Materials Setup | `chart_materials` | ✅ `chart-materials` (tag Procedures) | **Done** — `updated_at`/`updated_by` added (CHART-3a/3b) |
| Perio Setup Templates | `perio_chart_templates` | ✅ `perio-chart-templates` (tag Clinical) | **Done** — new named, tenant-scoped resource (CHART-1) |

> ✅ **All gaps below are now implemented** (migration `e945c28dd602`, head). Run
> `alembic upgrade head` + `npm run api:sync`, then `python -m scripts.seed_chart_defaults`
> to populate default colors/materials for new tenants. The per-screen sections are
> retained for reference; the **Resolution** note under each says what shipped.

**Naming note:** the house convention is `updated_by` (int FK → users), not
`modified_by` as originally drafted. It is **auto-populated on every PATCH** by
`CRUDBase.update` and exposed in the `*Read` DTO, so "Modified By" wires up with no
service code. "Modified On" = `updated_at`.

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

> **✅ Resolution (CHART-1 — shipped):** `perio_chart_templates` created exactly as
> specced above — model `app/db/models/clinical.py` (`PerioChartTemplate`), CRUD at
> `GET/POST /api/v1/perio-chart-templates` + `/{id}` (tag Clinical, `search=name`,
> tenant-scoped), migration `e945c28dd602`. `perio_chart_settings` is **kept** as the
> per-user runtime preference. `auto_advance` implemented as JSON (decision #1 → JSON).
> Region keys: `ur_facial, ul_facial, ul_lingual, ur_lingual, ll_facial, lr_facial,
> lr_lingual, ll_lingual`; values `"01-08"`/`"08-01"`-style.

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

> **✅ Resolution (CHART-2a / CHART-2c — shipped):** `chart_colors.updated_by`
> (FK → users) added (migration `e945c28dd602`), auto-set on PATCH. Default 10
> conditions + colors seeded by `python -m scripts.seed_chart_defaults` (idempotent
> by `(tenant_id, name)`). Color palette stays FE-static (decision #3 → FE-static).

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

> **✅ Resolution (CHART-3a/3b/3d — shipped):** `chart_materials` switched to
> `TimestampMixin` (adds `updated_at` → "Modified On") and gained `updated_by`
> (FK → users → "Modified By"), auto-set on PATCH (migration `e945c28dd602`). Default
> 22 materials (name + bare pattern key) seeded by `scripts.seed_chart_defaults`.
> Pattern catalog stays FE-static (decision #3 → FE-static). CHART-3c unchanged.
> (CHART-3e pattern-normalization and CHART-3f dedupe were shipped earlier.)

---

## Consolidated backend asks

| # | Ask | Status |
|---|---|---|
| CHART-1 | New `perio-chart-templates` resource (named, tenant-scoped, +`cal_warning_level`, `fgm_level`, `start_voice`, `auto_advance` JSON, audit cols) | ✅ **Done** |
| CHART-2a | Add `updated_by` to `chart_colors` | ✅ **Done** |
| CHART-3a | `chart_materials` → `TimestampMixin` (`updated_at`) | ✅ **Done** |
| CHART-3b | Add `updated_by` to `chart_materials` | ✅ **Done** |
| CHART-2c/3d | `seed_chart_defaults` script (conditions+colors, materials), idempotent per tenant | ✅ **Done** |
| CHART-3e | Normalize `pattern` (`*.gif` → bare key) + importer fix | ✅ Done (earlier) |
| CHART-3f | Dedupe `chart_materials` + `chart_colors` + unique key | ✅ Done (earlier) |

All work landed in migrations `a0b1c2d3e4f5` (dedupe) and `e945c28dd602` (audit cols +
templates) plus `scripts/seed_chart_defaults.py`. After deploy: `alembic upgrade head`,
`npm run api:sync`, `python -m scripts.seed_chart_defaults`.

**Decisions taken (defaults applied; flag if you disagree):**

1. `perio_chart_templates.auto_advance` → **JSON object** (8 region keys).
2. `perio_chart_settings` **kept** as the per-user runtime preference (templates are a
   separate, tenant-scoped resource).
3. Color palette (CHART-2b) and material pattern catalog (CHART-3c) → **FE-static** — no
   backend endpoint.
4. Actor column named **`updated_by`** (house convention; auto-set by `CRUDBase`), added
   per-table here rather than via a new shared mixin (matches existing tables).
