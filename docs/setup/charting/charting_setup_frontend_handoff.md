# Charting Setup — Backend → Frontend Handoff (Perio Templates · Restorative Color · Restorative Materials)

> Companion to `charting_setup_backend_devreport.md`. Captures the legacy Denticon
> "Charting" setup screens as **screens to (re)build in our app**, in the existing
> application format — same master/list patterns as `ProcedureCodeSetup` /
> `ExplosionCodeSetup`. Data field names are **snake_case**, bound directly to the
> backend DTOs (no camelCase aliases).

Routes (Setup → Charting submenu):

- `/setup/charting/restorative-colors` — Restorative Charting Color Setup
- `/setup/charting/restorative-materials` — Restorative Charting Materials Setup
- `/setup/charting/perio-templates` — Perio Setup Templates *(blocked on backend, see below)*

| Screen | Data source | Build state |
|---|---|---|
| Restorative Colors | `chart-colors` (Orval tag **metadata**) | ✅ build now |
| Restorative Materials | `chart-materials` (Orval tag **procedures**) | ✅ build now |
| Perio Templates | `perio-chart-templates` *(not yet shipped)* | ⛔ wait for CHART-1 |

---

## SCREEN 1 — Restorative Charting Color Setup  *(build now)*

A single-table read-grid with an inline "Edit Chart Colors" panel below it (no KPIs),
matching the legacy layout.

**Grid columns:** Condition · Stroke Color · Fill Color · Sample · Modified By · Modified On

**Data source:** `GET /api/v1/chart-colors` → `ChartColorRead`. Bind:

| Column | Field |
|---|---|
| Condition | `name` |
| Stroke Color | `stroke_color` |
| Fill Color | `fill_color` |
| Sample | render a swatch from `stroke_color` (border) + `fill_color` (fill) |
| Modified On | `updated_at` |
| Modified By | `created_by` *(see open question — not yet the true last editor)* |

**Edit panel:** select a row → Condition shown read-only, Stroke Color + Fill Color as
dropdowns, live Sample swatch, Save / Cancel. `PATCH /api/v1/chart-colors/{id}` with
`{ stroke_color, fill_color }`.

- The Stroke/Fill **color options are a fixed FE palette** (Blue, Green, Firebrick,
  Red, DarkGreen, HotPink, SpringGreen, Pink, Purple, Black, …). Keep this list in the
  FE — it's presentation, not business data. (Confirm with backend, see open questions.)
- No add/delete in the legacy screen — the condition set is fixed. Edit-only.
- Extra DTO fields (`fill_type`, `fill_color2`, `fill_pattern`, `gradient_angle`,
  `gradient_method`, `category_type`) belong to the chart renderer — **don't surface**
  on this screen.

---

## SCREEN 2 — Restorative Charting Materials Setup  *(build now)*

Single-table read-grid + an "Add New Chart Material" row below.

**Grid columns:** Name · Sample · Modified By · Modified On

**Data source:** `GET /api/v1/chart-materials` → `ChartMaterialRead`. Bind:

| Column | Field |
|---|---|
| Name | `name` |
| Sample | render the SVG fill pattern keyed by `pattern` (× `color`) |
| Modified On | `updated_at` *(⚠ not present yet — CHART-3a)* |
| Modified By | *(not present yet — CHART-3b)* |

**Add / edit:** Name text input + Sample = pattern dropdown (keys: `hash`, `round`,
`r5hash`, `r6hash`, `r2hash`, `r4hash`, `round1`, `crosshatch`, `r3hash`, `sealant`,
`veneer`, …). `POST /api/v1/chart-materials` `{ name, pattern }`;
`PATCH /{id}`; `DELETE /{id}` (hard delete — registered `soft_field=None`).

- The **pattern catalog is an FE asset** (key → SVG preview); `pattern` stores the key
  string. (Confirm, see open questions.)
- ⚠ **Sample rendering (CHART-3e, fixed backend-side):** `pattern` previously held
  legacy GIF filenames (`hash.gif`) which the catalog couldn't match → `?` placeholder.
  Backend has normalized them to **bare keys**. Your FE catalog must cover:
  `hash, round, round1, r2hash, r3hash, r4hash, r5hash, r6hash, crosshash, sealant,
  veneer, arestin`. A NULL `pattern` (e.g. "Unknown") legitimately has no swatch — render
  a neutral placeholder, not `?`.
- ✅ **Duplicate rows (CHART-3f, fixed):** the list previously showed each material 4×
  (and colors 5×) from a migration re-run bug; the backend has deduped + added a unique
  key. Materials now return ~23 distinct rows, colors ~10. No client-side dedupe needed.
- ⚠ Until CHART-3a/3b ship, the **Modified On / Modified By columns have no data** —
  either hide them or show "—" and unhide once the backend lands.

---

## SCREEN 3 — Perio Setup Templates  *(blocked — do not build yet)*

A named-template manager: left rail list of templates (`+ ADD TEMPLATE`, search),
right pane "Template Info" + "Auto Advance Direction", footer `EDIT TEMPLATE` /
`DELETE TEMPLATE`, "Modified On / Modified By" stamp.

**Why blocked:** the current `perio-chart-settings` resource is a **per-user, single-row
preference** (`user_id` unique) — it has no template name, no tenant scoping, no
CAL/FGM/Start-Voice fields, and only a single forward/back flag instead of the 8-region
Auto Advance grid. See **GAP CHART-1** in the dev report for the requested
`perio-chart-templates` resource. Build once it ships.

**Planned binding (against the proposed `perio-chart-templates`):**

Template Info: `name` · `show_mgj` · `pd_warning_level` · `cal_warning_level` ·
`bp_level` · `ip_level` · `fgm_level` · `start_voice`.
Auto Advance Direction: `auto_advance` JSON, 8 keys (`ur_facial`, `ul_facial`,
`ul_lingual`, `ur_lingual`, `ll_facial`, `lr_facial`, `lr_lingual`, `ll_lingual`),
each `"01-08"`-style two-way toggle (see the region table in the dev report).
Stamp: `updated_at` / `updated_by`. Full CRUD (list / add / edit / delete).

---

## Action items for the frontend

1. Add the **Setup → Charting** submenu with the three reserved routes.
2. Build Screens 1 & 2 now against `chart-colors` / `chart-materials` (`npm run api:sync`
   first). Screens reuse the `ProcedureCodeSetup` single-table master/edit pattern.
3. Keep the **color palette** and **pattern catalog** as FE static assets.
4. Hide Modified On/By on the Materials screen until CHART-3a/3b ship.
5. Leave Perio Templates as a `PlaceholderPage` until `perio-chart-templates` lands.

## Open questions back to backend

1. Color palette (Screen 1) and pattern catalog (Screen 2) — OK to keep FE-static, or
   do you want them backend-served (e.g. a `definitions` group)?
2. "Modified By" — will you add `modified_by` to `chart_colors` / `chart_materials`
   (CHART-2a / CHART-3b)? Until then we bind `created_by` / show "—".
3. Perio Templates — confirm the `perio-chart-templates` shape and `auto_advance` as
   JSON (CHART-1).
4. Default seeding for new tenants (CHART-2c / CHART-3d) — will `seed_chart_defaults`
   ship so the grids aren't empty?
