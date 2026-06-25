# Restorative Charting — Backend Capability Assessment Report

**Module:** Restorative Charting (`/patient/:id/restorative`)
**Frontend:** `src/features/restorative/**`
**Backend contract:** `openapi.json` (267 paths, 486 schemas) + Orval client `src/api/generated/**`
**Status date:** 2026-06-23
**Companion doc:** `restorative_charting_backend_devreport.md` (gaps `REST-1`…`REST-10`) — this report supersedes/links it as the consolidated spec.

> **Bottom line up front.** The backend is **substantially more capable than the frontend currently uses**. All core charting entities already exist as first-class resources with full CRUD, soft-delete, and audit coverage. The dominant remaining work is **(a) a frontend re-architecture to make ADA `procedure_code` the source of truth on every charting action** (the column already exists on `chart_conditions` and is currently left null for pre-existing/condition entries), and **(b) promoting a handful of interim `region`-packed qualifiers to first-class columns** (`REST-1/7/9`). No greenfield charting backend is required.

---

## 1. Current State Analysis

### 1.1 What works today
- The chart **reads and reconstructs** full patient state on open from four list endpoints (`chart-conditions`, `patient-procedures`, `treatment-plans` + `-items`, `progress-notes`) plus catalogs (`procedure-codes`, `chart-materials`, `providers`). Reopening a patient restores conditions, completed procedures, planned items, watch arrows, tooth notes, and freehand drawings.
- **Three charting modules** (Pre-existing / Completed / TxPlans) each persist to a different resource:
  | Module | Resource written | Color |
  |---|---|---|
  | Pre-existing | `chart-conditions` (`chart_as='pre-existing'`) | blue |
  | Completed | `patient-procedures` | green |
  | TxPlans | `treatment-plan-items` (auto-creates a `treatment-plan`) | red |
- **Soft-delete** is honored everywhere (`is_inactive`, `is_void`, `is_deleted`).
- **ADA codes already flow** for Completed + TxPlans (the `AddAdaCodeModal` writes `procedure_code` directly from the backend `procedure-codes` catalog — no mock data).

### 1.2 The core defect (this report's primary driver)
**Pre-existing conditions and findings do NOT store an ADA code.** They persist a UI string in `chart_conditions.condition_code` (e.g. `"CROWN"`, `"DECAY"`, `"CLASS_V"`, `"WATCH"`) and leave `chart_conditions.procedure_code` **null**. Consequently:
- Conditions cannot be reconciled against the ADA master (`procedure-codes`).
- Descriptions/categories/fees are not derivable from backend data for condition rows.
- Reporting, claims, and downstream analytics can't treat the chart uniformly.

The fix is **not** a new table — `chart_conditions.procedure_code` already exists. It is a **frontend mapping + a small backend seed/lookup** effort (see §4).

### 1.3 Interim encodings still in place
Sub-attributes are packed into `chart_conditions.region` as a `;`-delimited string because first-class columns don't exist yet (tracked as `REST-1/7/9`). Currently packed: `g` (group_id), `grade`, `sub`, `roots`, `rctfill`, `dir`, `wx`, `wy`, `root`. This works but is opaque to the DB (not queryable, not validated).

---

## 2. Frontend Functionality Inventory

| # | User action | Selection model | Persisted to | Body fields sent | ADA code today? |
|---|---|---|---|---|---|
| 1 | Apply **Pre-existing** condition | whole/crown/junction/root/surface | `POST chart-conditions` (`useCreateChartCondition`) | `patient_id, office_id, tooth, surface, area, region, material_id, condition_code, chart_as, description, activity_date, is_inactive` | ❌ `procedure_code` null |
| 2 | Apply **Completed** procedure | tooth/surface | `POST patient-procedures` (`useCreatePatientProcedure`) | `id, patient_id, office_id, procedure_code, date_of_service, provider_id, tooth, surface, fee, insurance_estimate` | ✅ |
| 3 | Apply **TxPlan** item | tooth/surface | `POST treatment-plan-items` (`useCreateTreatmentPlanItem`, auto-creates plan) | `id, plan_id, procedure_code, description, tooth, surface, fee, insurance_estimate, status:'planned', priority` | ✅ |
| 4 | **Watch** arrow | whole | `chart-conditions` (`condition_code='WATCH'`) | + `region: dir,wx,wy`; notes via update | ❌ |
| 5 | **Material-aware** apply (Crown/Bridge/Filling/Implant/RCT) | crown/root/whole | `chart-conditions` + `material_id` | `material_id` from `MaterialPicker` | ❌ |
| 6 | **Mobility** grade | whole | `chart-conditions` | `region: grade=m1\|m2\|m3` | ❌ |
| 7 | Whole-tooth sub-type (Missing/Impacted/Erupted) | whole | `chart-conditions` | `region: sub=…` | ❌ |
| 8 | **Bridge/Denture template** | multi-tooth | N× `chart-conditions` sharing `region: g=<uuid>` | `expandTemplate()` | ❌ |
| 9 | **Tooth note** | whole | `chart-conditions` (`condition_code='NOTE'`) | `notes`; delete+recreate on save | n/a |
| 10 | **Draw mode** (freehand) | overlay | `POST progress-notes` (`notes_html` JSON) + `POST patient-documents` (PNG) | `{type:'rx-draw',strokes,doc_id}` | n/a |
| 11 | **Delete** row | grid | `DELETE chart-conditions/{id}` (soft) | — | n/a |
| 12 | **Edit** row | grid | `PATCH chart-conditions/{id}` | `notes, activity_date, is_inactive` | n/a |
| 13 | **Timeline** date filter | toolbar | client-side filter only | — | n/a |

**Frontend-only logic NOT persisted** (intentional render layer): glyph patterns (`glyphFills.ts` — hatch/houndstooth/dots/stripes/checker), source colors (`SOURCE_COLOR`), symbol marks (`chartGlyphs.tsx`), legend catalog (`legendCatalog.tsx`), dentition/numbering (localStorage via `restorativeService.ts`), undefined→solid fallback. These are derived from `condition_code`/`procedure_code` + `chart_as` and should remain client-side.

---

## 3. Backend Capability Inventory

All resources below have full `GET list / POST / GET{id} / PATCH / DELETE` unless noted. List endpoints share `page` (default 1), `size` (default 20, **max 200**), `sort`, `order`, `search`, `X-Tenant-ID`.

| Resource | Key fields (charting-relevant) | Soft-delete | Notes |
|---|---|---|---|
| **chart-conditions** | `tooth, surface, area, region, condition_code, **procedure_code**, chart_as, material_id, provider_id, office_id, activity_date, description, notes, is_inactive` | `is_inactive` | filters: `patient_id, tooth, provider_id, search` |
| **patient-procedures** | `procedure_code(req), tooth, surface, quadrant, material_id, provider_id(req), date_of_service(req), fee(req), patient_estimate, insurance_estimate, ucr_fee, billing_status, is_void, is_archived, appointment_id, claim_id` | `is_void`/`is_archived` | filters: `patient_id, procedure_code, provider_id, billing_status, is_void, date_of_service_from/to` |
| **appointment-procedures** | `procedure_code, tooth, surface, material_id, **treatment_plan_id**, provider_id, status, fee, insurance_estimate` | `is_archived` | has the `treatment_plan_id` link that `patient-procedures` lacks |
| **treatment-plans** | `id, patient_id, name, status, office_id` + `/{id}/summary` (counts, totals) | status | |
| **treatment-plan-items** | `plan_id, procedure_code(req), tooth, surface, fee, status, insurance_estimate, priority, description, diagnosed_by, billing_order` | status | |
| **procedure-codes** (ADA master) | `code, description, category, chart_category, **draw_as**, default_fee, default_material_id, default_provider_id, valid_teeth[], tooth_area, requires_tooth/surface/quadrant, min/max_surfaces, is_ortho, is_active, ar_code` | `is_active` | filters: `category, is_active, is_ortho, chart_category, search`; `/stats` |
| **chart-materials** | `name, color, pattern` | — | |
| **chart-colors** | `name, fill_color, fill_color2, stroke_color, fill_pattern, fill_type, gradient_*, category_type` | — | rendering palettes |
| **code-bundles** / **-items** | bundle: `name, same_tooth, display_code`; item: `bundle_id, procedure_code, sort_order, tooth` | — | explosion codes |
| **progress-notes** | `notes, notes_html, tooth, surface, region, note_date, signed_by/at, is_deleted, is_struck_off` + `/{id}/sign` | `is_deleted` | drawing JSON lives in `notes_html` |
| **patient-documents** | multipart upload; `GET` requires `patient_id` | hard delete | drawing PNGs |
| **definitions** / **definition-groups** | `group_code, group_type, key1/key2, description, color, input_type, sort_order, is_active` | `is_active` | catalog for chart conditions/surfaces if seeded |
| **icd-codes** | `code, icd10, icd9, snomed, is_active` + `/bulk-status` | `is_active` | diagnosis linkage (unused by chart) |
| **audit-logs** | `action, method, path, resource_type, resource_id, user_id, details, created_at` (read-only) | — | covers all resources incl. chart-conditions/patient-procedures |

**Critical positive findings:**
1. `chart_conditions.procedure_code` **already exists** — the ADA-driven redesign needs no new column here.
2. `procedure-codes` is ADA-complete with charting hints (`draw_as`, `chart_category`, `valid_teeth`, surface/tooth requirements) — enough to **drive** condition rendering & validation from the backend.
3. **Audit/versioning already exists** (`audit-logs` filterable by `resource_type`/`resource_id`) — satisfies the audit-tracking requirement with no new work.
4. **State restoration already works** — load is solved; the gap is data *quality* (ADA codes), not data *retrieval*.

---

## 4. ADA Code Integration Strategy (the central redesign)

**Principle:** every charting action references an ADA `procedure_code` from `procedure-codes`; descriptions/categories/fees/draw hints are read from that record, not invented in the UI.

### 4.1 Target data flow
```
User picks a condition/finding/procedure
        │
        ▼
Resolve to an ADA procedure_code  (via a CONDITION→ADA map + procedure-codes lookup)
        │
        ▼
Persist row with BOTH:
  • procedure_code  (ADA, source of truth)
  • condition_code  (retained as the chart GLYPH key for rendering)
  • chart_as        (module → color)
        │
        ▼
On reload: glyph/pattern derived from procedure_code.draw_as ?? condition_code;
           description/category/fee read from procedure-codes
```

### 4.2 Mapping layer (frontend, new)
- Build `adaMap.ts`: `condition_code → { ada_code, fallback_draw_as }`. Seed from the legacy chart (e.g. `CROWN→D2740`, `DECAY→(diagnostic finding code)`, `RCT→D3310/20/30`, `EXTRACTION→D7140`, `CLASS_V→D2335`, …). Where no clinical ADA code exists for a pure *finding* (e.g. "Watch", "Abfraction"), use a **tenant-defined "charting/finding" code range** seeded in `procedure-codes` with `chart_category='finding'` so even findings carry a real code.
- `ConditionsPopup` / `ConditionPalette` apply path resolves the ADA code and sets `procedure_code` on the `chart-conditions` body (currently null).
- `procedureGlyphCode()` already prefers `procedure_code.draw_as` → extend so rendering is **backend-hint-first**, `condition_code` second.

### 4.3 Backend support needed
- **Seed `procedure-codes`** with the finding/condition codes (or confirm an existing range) and set their `draw_as` + `chart_category` so the FE can render and validate from data. (`REST-2`/`REST-5` adjacent.)
- Optionally add `chart_conditions.condition_code` ↔ `procedure_code` referential expectation in validation (warn if `procedure_code` not in catalog).

### 4.4 Result
After this, **every** chart row (condition, finding, restoration, planned, completed) is reconstructable from backend data alone: ADA code → description/category/fee/draw hint; `chart_as` → module/color; `tooth/surface/area` → placement; first-class qualifier columns (§7) → grade/root/group/watch.

---

## 5. Data Model Recommendations

1. **Use `chart_conditions.procedure_code` for the ADA code on every condition row** (no schema change — population change).
2. **Promote `region`-packed qualifiers to first-class columns** on `chart_conditions` (`REST-1/7/9`):
   - `group_id` (string/uuid) — bridge/denture grouping (replaces `g=`).
   - `root_segment` (string) — anatomical root label (replaces `root=`); `segment` (`crown|junction|root|surface`) mirroring `area`.
   - `grade` (string) — mobility m1/m2/m3 (replaces `grade=`).
   - `tooth_status` (string) — `unerupted|deciduous|supernumerary|permanent` (replaces `sub=`).
   - `rct_fill` (string) — `gutta|other|unknown` (replaces `rctfill=`).
   - `watch_dir` (string) + `watch_x` / `watch_y` (numeric %) — watch arrow placement (replaces `dir/wx/wy`).
   - `status` (string) — explicit `existing|completed|planned|condition` to complement `chart_as`.
3. **Drawing fidelity** (`REST-10`): add `progress_notes.drawing_strokes` (json) + `drawing_doc_id` (fk → patient_documents) to retire the `notes_html` JSON packing.
4. **Tooth notes** (`REST-4`): optional dedicated `chart_tooth_notes` (per-patient per-tooth) to replace the `condition_code='NOTE'` delete-recreate pattern.
5. **Chart settings** (`REST-3`): per-patient `chart_settings` (dentition mode, numbering) — currently localStorage-only, so it doesn't roam across devices/users.

---

## 6. API Recommendations

Mostly **reuse**; targeted additions:
- **Reuse as-is:** all CRUD on chart-conditions, patient-procedures, treatment-plans/-items, procedure-codes, chart-materials/colors, code-bundles, progress-notes, patient-documents, audit-logs.
- **Add filter:** `chart-conditions?procedure_code=` and `?chart_as=` and `?is_inactive=` to query the chart by ADA code / module / active-state server-side (today the FE pulls `size=200` and filters client-side).
- **Add:** `GET /procedure-codes?chart_category=finding` returns the seeded condition/finding codes for the palette (depends on §4.3 seed).
- **Consider:** a `treatment_plan_id` column on `patient-procedures` (it exists on `appointment-procedures`) so a completed procedure can trace back to the plan it fulfilled — needed for "planned → completed" lineage.
- **Bulk write (optional):** `POST /chart-conditions/bulk` to persist template expansions (bridge = N rows) atomically with a server-assigned `group_id`.
- **Nice-to-have:** `GET /patients/{id}/chart` aggregate (conditions + procedures + plan items + notes in one payload) to cut the 4–6 round-trips on open.

---

## 7. Database Schema Recommendations

Apply the `REST-1/7/9` column additions from §5(2) to `chart_conditions`. Migration is **additive and backward-compatible**: keep `region` writable during transition; backfill new columns by parsing existing `region` strings; switch the FE `encodeRegion`/`decodeRegion` to read/write columns; deprecate `region` packing once backfilled. Add indexes on `(patient_id, is_inactive)`, `(patient_id, procedure_code)`, and `group_id`.

---

## 8. Gap Analysis

### 8.1 Existing backend support (reuse — no work)
- Full CRUD + soft-delete for every charting entity.
- ADA master (`procedure-codes`) with charting hints + search + `/stats`.
- Treatment-plan summary aggregation (`/{id}/summary`).
- Audit/versioning (`audit-logs`).
- Materials/colors catalogs; code bundles (explosions); progress-note signing; patient-document binary store.
- State restoration on reopen (already functional).

### 8.2 Missing backend support
| Gap | Severity | Tracked as |
|---|---|---|
| Finding/condition ADA codes not seeded in `procedure-codes` (blocks §4 if absent) | **High** | new (REST-2/5 adjacent) |
| `chart_conditions` first-class qualifier columns (group_id, root_segment, grade, tooth_status, rct_fill, watch_*, status) | **High** | REST-1, REST-7, REST-9 |
| Server-side filters `?procedure_code/?chart_as/?is_inactive` on chart-conditions | Medium | new |
| `patient_procedures.treatment_plan_id` (planned→completed lineage) | Medium | new |
| `progress_notes.drawing_strokes` + `drawing_doc_id` | Low | REST-10 |
| `chart_tooth_notes` table | Low | REST-4 |
| `chart_settings` (per-patient dentition/numbering) | Low | REST-3 |
| Bulk `chart-conditions` write / server group_id | Low | new |
| Aggregate `GET /patients/{id}/chart` | Low (perf) | new |
| FHIR R4 export | Deferred | REST-6 |

### 8.3 Frontend changes required
- **ADA mapping layer** (`adaMap.ts`) + populate `procedure_code` on all `chart-conditions` writes (Pre-existing, Watch, Material-aware, Mobility, templates, findings).
- **Render backend-hint-first** (`procedure_code.draw_as` → glyph) with `condition_code` fallback (the undefined→solid fallback already added stays as the final safety net).
- **Switch `encodeRegion`/`decodeRegion` to first-class columns** once `REST-1/7/9` land (single-file change in `chartModel.ts`).
- **Move chart settings to backend** (`REST-3`) — optional.
- **Pull condition palette from `procedure-codes?chart_category=finding`** instead of the hardcoded `conditionTaxonomy.ts` (taxonomy becomes a render/label fallback, not the source of truth).

---

## 9. Required Frontend Changes (task list)
1. `adaMap.ts`: condition_code → ADA code; load + cache `procedure-codes` (already loaded via `loadProcedureCodes`).
2. `chartModel.ts`: write `procedure_code` on condition create; add column read/write to replace `region` packing (behind a feature flag until backend lands).
3. `ConditionPalette`/`ConditionsPopup`: source items from backend finding codes; carry `procedure_code` through apply.
4. `txPlanModel.procedureGlyphCode`: backend `draw_as` first.
5. `RestorativeChart`: add server-side filters to the list queries (`chart_as`, `is_inactive`) to reduce client filtering.
6. Migrate `restorativeService` chart settings to `chart_settings` API (optional).

## 10. Required Backend Development Tasks (task list)
1. **Seed `procedure-codes`** with condition/finding codes (`chart_category='finding'`, `draw_as` set) — unblocks ADA-driven conditions.
2. **`chart_conditions` columns** (`REST-1/7/9`): `group_id, segment, root_segment, grade, tooth_status, rct_fill, watch_dir, watch_x, watch_y, status` + indexes; backfill from `region`.
3. **Filters** on `chart-conditions`: `procedure_code`, `chart_as`, `is_inactive`.
4. **`patient_procedures.treatment_plan_id`** column + filter.
5. **`progress_notes.drawing_strokes` + `drawing_doc_id`** (`REST-10`).
6. **`chart_tooth_notes`** (`REST-4`) and **`chart_settings`** (`REST-3`) — lower priority.
7. **Optional:** bulk chart-condition write; aggregate `GET /patients/{id}/chart`.

## 11. Recommended Implementation Roadmap

| Phase | Scope | Outcome | Deps |
|---|---|---|---|
| **P0 — ADA seed + mapping** | Backend task 1; FE tasks 1, 2(write `procedure_code`), 4 | Every new chart row carries an ADA code; rendering is backend-hint-first | none |
| **P1 — First-class columns** | Backend task 2; FE task 2 (column read/write), 3 | `region` packing retired; grade/root/group/watch/status queryable + validated | P0 |
| **P2 — Query & lineage** | Backend tasks 3, 4; FE task 5 | Server-side filtering; planned→completed traceability | P1 |
| **P3 — Fidelity & settings** | Backend tasks 5, 6 (`REST-10/4/3`); FE task 6 | Drawing/notes/settings first-class; settings roam across devices | P2 |
| **P4 — Optional perf/export** | Bulk write, aggregate chart endpoint, FHIR (`REST-6`) | Fewer round-trips; interop | P2 |

**Sequencing rationale:** P0 delivers the ADA-code-driven requirement with the least backend change (the column already exists), so it should ship first and independently. P1 removes the opaque `region` field. P2+ are incremental hardening.

---

### Appendix A — Region qualifiers to migrate (P1 backfill source)
`g`→`group_id` · `grade`→`grade` · `sub`→`tooth_status` · `roots`→(reserved) · `rctfill`→`rct_fill` · `dir`→`watch_dir` · `wx`→`watch_x` · `wy`→`watch_y` · `root`→`root_segment`. Parser already exists in `chartModel.decodeRegion()`; reuse for the migration job.

### Appendix B — Key file references
`RestorativeChart.tsx` (container/wiring) · `chartModel.ts` (region encode/decode, `toToothStates`, `expandTemplate`) · `txPlanModel.ts` (ADA classification, `procedureGlyphCode`, `buildOverlayGlyphs`) · `conditionTaxonomy.ts` (condition catalog — becomes label fallback) · `AddAdaCodeModal.tsx` (ADA picker — the pattern to extend to conditions) · `glyphFills.ts` / `chartGlyphs.tsx` / `legendCatalog.tsx` (render layer — stays client-side).
